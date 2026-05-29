#!/usr/bin/env python3
"""proto_kappa.py — Prototype du facteur de headroom personnel kappa_flat + simulation.

kappa_flat = P(bande FC course) / P(bande FC reference Z3), mesure le headroom
submax->course de l'athlete sur le PLAT. On le simule SANS modifier le moteur en
monkeypatchant physics_engine.effort_multiplier -> kappa, puis on rejoue les 22
courses en leave-one-out et on stratifie l'erreur par D+/km.

Lancement: cd backend && PYTHONPATH=. venv/bin/python ../tools/v3-backtest/proto_kappa.py
"""
from __future__ import annotations
import json, os, statistics
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
# user_id parametrable (env BACKTEST_USER_ID) -> reproductible pour tout athlete
LOUIS_S = os.environ.get("BACKTEST_USER_ID", "c77fef20-6fad-4741-b268-cf39b22c1e3f")
REF_BAND = (0.72, 0.78)  # bande p_ref (tempo Z3), identique au moteur
RACE_BAND = (0.85, 0.90) # bande "allure course" soutenue
KAPPA_CAP = 1.20         # plafond de securite anti sur-estimation
MINETTI_FLAT = 3.6


def arr(s, k):
    v = s.get(k)
    return v["data"] if isinstance(v, dict) and "data" in v else (v if isinstance(v, list) else [])


def load_manifest():
    return json.loads((CACHE / "manifest.json").read_text())


def estimate_fcmax(rows):
    """FCmax = percentile 99.5 du pool HR, comme _estimate_fcmax_from_history du moteur.
    Derive des donnees -> reproductible pour n'importe quel athlete (pas de valeur en dur)."""
    pool = []
    for row in rows:
        p = CACHE / f"{row['id']}.json"
        if not p.exists():
            continue
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        pool += [h for h in arr(s, "heartrate") if isinstance(h, (int, float)) and 60 <= h <= 230]
    if len(pool) < 500:
        return 190.0  # HARD_FALLBACK du moteur si pool insuffisant
    pool.sort()
    return float(pool[min(len(pool) - 1, int(len(pool) * 0.995))])


def compute_kappa(rows, fcmax):
    """v_ref / v_race medianes sur les sorties PLATES (<6 m/km), filtrees par bande FC."""
    lo_ref, hi_ref = REF_BAND[0] * fcmax, REF_BAND[1] * fcmax
    lo_rc, hi_rc = RACE_BAND[0] * fcmax, RACE_BAND[1] * fcmax
    v_ref, v_race = [], []
    flats = 0
    for row in rows:
        dist = float(row.get("distance_m") or 0)
        if dist < 3000:
            continue
        dpkm = float(row.get("elev_gain_m") or 0) / (dist / 1000.0)
        if dpkm >= 6:           # garder le plat: pas de grade_smooth -> on isole par activite
            continue
        p = CACHE / f"{row['id']}.json"
        if not p.exists():
            continue
        s = json.loads(p.read_text())
        hr = arr(s, "heartrate"); vs = arr(s, "velocity_smooth")
        n = min(len(hr), len(vs))
        if n < 60:
            continue
        flats += 1
        for i in range(n):
            h, v = hr[i], vs[i]
            if not isinstance(h, (int, float)) or not isinstance(v, (int, float)) or v <= 0:
                continue
            if lo_ref <= h <= hi_ref:
                v_ref.append(v)
            elif lo_rc <= h <= hi_rc:
                v_race.append(v)
    mref = statistics.median(v_ref) if v_ref else None
    mrace = statistics.median(v_race) if v_race else None
    return mref, mrace, len(v_ref), len(v_race), flats


def cat_of(dpkm):
    return "trail" if dpkm >= 15 else ("zone_morte" if dpkm >= 6 else "route")


def reconstruct_gpx(s):
    ll = arr(s, "latlng"); al = arr(s, "altitude")
    n = min(len(ll), len(al))
    if n < 20:
        return None
    st = max(1, n // 1500); pts = []
    for i in range(0, n, st):
        c = ll[i]
        if not isinstance(c, (list, tuple)) or len(c) < 2 or c[0] is None or c[1] is None:
            continue
        try:
            lat, lon, ele = float(c[0]), float(c[1]), float(al[i])
        except (TypeError, ValueError, IndexError):
            continue
        pts.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"><ele>{ele:.1f}</ele></trkpt>')
    if len(pts) < 20:
        return None
    return ('<?xml version="1.0"?><gpx version="1.1" creator="proto"><trk><trkseg>'
            + "".join(pts) + "</trkseg></trk></gpx>")


def run_variant(predict_v3, Session, engine, targets, label):
    rows_out = []
    with Session(engine) as s:
        for row, gpx in targets:
            dist_km = float(row["distance_m"]) / 1000.0
            dpkm = float(row.get("elev_gain_m") or 0) / dist_km
            real = float(row["moving_time_s"]) / 60.0
            as_of = datetime.fromisoformat(row["start_date_utc"].replace("Z", "+00:00")).replace(tzinfo=None)
            try:
                r = predict_v3(s, UUID(LOUIS_S), gpx, race_datetime=None, effort_mode="steady",
                               analysis_mode="auto", target_heartrate=None, weather_mode="manual",
                               manual_temperature_c=11.0, ravito_mode="auto", custom_ravitos=None,
                               as_of_date=as_of, excluded_activity_ids={UUID(row["id"])},
                               history_start_date=as_of - timedelta(days=366))
                pred = float(r.get("moving_time_min"))
                rows_out.append({"cat": cat_of(dpkm), "dpkm": dpkm, "err": (pred - real) / real * 100,
                                 "real": real, "pred": pred})
            except Exception as exc:
                print(f"   ECHEC {row['id'][:8]}: {str(exc)[:70]}")
    return rows_out


def summarize(results, label):
    print(f"\n--- {label} (err%>0 = trop LENT) ---")
    for cat in ("route", "zone_morte", "trail"):
        sub = [r for r in results if r["cat"] == cat]
        if not sub:
            continue
        errs = [r["err"] for r in sub]
        print(f"  {cat:10} n={len(errs):2}  biais={sum(errs)/len(errs):+6.1f}%  "
              f"MAE={sum(abs(e) for e in errs)/len(errs):5.1f}%")
    allerr = [r["err"] for r in results]
    print(f"  {'GLOBAL':10} n={len(allerr):2}  biais={sum(allerr)/len(allerr):+6.1f}%  "
          f"MAE={sum(abs(e) for e in allerr)/len(allerr):5.1f}%")


def main():
    rows = load_manifest()
    fcmax = estimate_fcmax(rows)
    mref, mrace, nref, nrace, flats = compute_kappa(rows, fcmax)
    print(f"=== kappa_flat (FCmax derivee={fcmax:.0f} bpm, {flats} sorties plates) ===")
    print(f"  bande REF  [{REF_BAND[0]*fcmax:.0f}-{REF_BAND[1]*fcmax:.0f}] bpm : v_med={mref:.3f} m/s  (n={nref})")
    print(f"  bande RACE [{RACE_BAND[0]*fcmax:.0f}-{RACE_BAND[1]*fcmax:.0f}] bpm : v_med={mrace:.3f} m/s  (n={nrace})")
    kappa_raw = mrace / mref
    kappa = min(KAPPA_CAP, kappa_raw)
    print(f"  p_ref ~ {MINETTI_FLAT*mref:.2f} W/kg   p_race ~ {MINETTI_FLAT*mrace:.2f} W/kg")
    print(f"  kappa_raw = {kappa_raw:.3f}   kappa_applique (cap {KAPPA_CAP}) = {kappa:.3f}")

    os.environ["DATABASE_URL"] = f"sqlite:///{HERE / 'backtest_louis.db'}"
    os.environ.setdefault("JWT_SECRET_KEY", "x"); os.environ.setdefault("ENCRYPTION_KEY", "x")
    import logging; logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    from sqlmodel import Session
    from app.core.database import engine; engine.echo = False
    import app.domain.entities  # noqa
    import app.domain.services.race_predictor.physics_engine as pe
    from app.domain.services.race_predictor.v3_prediction_service import predict_v3

    # cibles
    targets = []
    for row in rows:
        if float(row.get("distance_m") or 0) < 20000:
            continue
        p = CACHE / f"{row['id']}.json"
        if not p.exists():
            continue
        gpx = reconstruct_gpx(json.loads(p.read_text()))
        if gpx:
            targets.append((row, gpx))
    print(f"\n{len(targets)} courses >=20km\n")

    # Baseline (steady, multiplicateur d'origine = 1.0)
    base = run_variant(predict_v3, Session, engine, targets, "baseline")
    summarize(base, "BASELINE V3 (steady, x1.0)")

    # Variante kappa : monkeypatch effort_multiplier -> kappa (zero modif moteur)
    pe.effort_multiplier = lambda mode: kappa
    kap = run_variant(predict_v3, Session, engine, targets, "kappa")
    summarize(kap, f"AVEC kappa_flat={kappa:.3f} (intensite seule, SANS hausse cout vertical)")

    # Couplage : kappa + amplification du cout vertical (uniquement en montee, cost>3.6)
    # -> n'affecte PAS le plat (route), ralentit les trails. Sweep de lambda.
    orig_minetti = pe.minetti_run_cost

    def make_vertical(lam):
        def f(g):
            c = orig_minetti(g)
            return c if c <= MINETTI_FLAT else MINETTI_FLAT + (c - MINETTI_FLAT) * lam
        return f

    sweep = {}
    for lam in (1.2, 1.4, 1.6):
        pe.minetti_run_cost = make_vertical(lam)
        res = run_variant(predict_v3, Session, engine, targets, f"lam{lam}")
        summarize(res, f"kappa={kappa:.2f} + cout vertical x{lam}")
        sweep[f"lambda_{lam}"] = res
    pe.minetti_run_cost = orig_minetti

    print("\nObjectif: le couple (kappa, lambda) qui met route ET trail proches de 0.")
    (HERE / "kappa_results.json").write_text(json.dumps(
        {"kappa": kappa, "baseline": base, "kappa_only": kap, "kappa_vertical_sweep": sweep}, indent=2))


if __name__ == "__main__":
    main()
