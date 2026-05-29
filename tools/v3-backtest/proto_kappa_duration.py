#!/usr/bin/env python3
"""proto_kappa_duration.py — Prototype kappa(duree) : le headroom decroit avec la duree.

kappa_eff(T) = 1 + (kappa_flat - 1) * f(T_base)
  f = 1                              si T_base <= T_FULL  (effort court/intense -> plein headroom)
  f = (T_ZERO - T)/(T_ZERO - T_FULL) si T_FULL < T < T_ZERO (decroissance lineaire)
  f = 0                              si T_base >= T_ZERO  (ultra -> on court a p_ref)
T_base = duree predite a kappa=1 (pas de circularite).

Reutilise la db deja construite (bt_<id>.db). Sweep (T_FULL,T_ZERO) + option lambda.
Lancement: cd backend && BACKTEST_USER_ID=<uuid> BACKTEST_MIN_KM=N \\
  PYTHONPATH=. venv/bin/python ../tools/v3-backtest/proto_kappa_duration.py
"""
from __future__ import annotations
import json, os, statistics
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

USER = os.environ.get("BACKTEST_USER_ID", "c77fef20-6fad-4741-b268-cf39b22c1e3f")
MIN_KM = float(os.environ.get("BACKTEST_MIN_KM", "20"))
LAMBDA = float(os.environ.get("BACKTEST_LAMBDA", "1.3"))
EXCLUDE = {x.strip() for x in os.environ.get("BACKTEST_EXCLUDE_IDS", "").split(",") if x.strip()}
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / USER
DB_PATH = HERE / f"bt_{USER[:8]}.db"
RELAY_ENV = HERE.parent / "garmin-relay" / ".env"
REF_BAND, RACE_BAND, KAPPA_CAP, MINETTI_FLAT = (0.72, 0.78), (0.85, 0.90), 1.20, 3.6


def log(m): print(m, flush=True)
def arr(s, k):
    v = s.get(k)
    return v["data"] if isinstance(v, dict) and "data" in v else (v if isinstance(v, list) else [])
def streams_of(aid):
    p = CACHE / f"{aid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def estimate_fcmax(rows):
    pool = []
    for row in rows:
        s = streams_of(row["id"])
        if s: pool += [h for h in arr(s, "heartrate") if isinstance(h, (int, float)) and 60 <= h <= 230]
    if len(pool) < 500: return 190.0
    pool.sort(); return float(pool[min(len(pool) - 1, int(len(pool) * 0.995))])


def compute_kappa(rows, fcmax):
    lo_r, hi_r = REF_BAND[0] * fcmax, REF_BAND[1] * fcmax
    lo_c, hi_c = RACE_BAND[0] * fcmax, RACE_BAND[1] * fcmax
    vr, vc = [], []
    for row in rows:
        dist = float(row.get("distance_m") or 0)
        if dist < 3000 or float(row.get("elev_gain_m") or 0) / (dist / 1000.0) >= 6: continue
        s = streams_of(row["id"])
        if not s: continue
        hr, vs = arr(s, "heartrate"), arr(s, "velocity_smooth")
        for i in range(min(len(hr), len(vs))):
            h, v = hr[i], vs[i]
            if not isinstance(h, (int, float)) or not isinstance(v, (int, float)) or v <= 0: continue
            if lo_r <= h <= hi_r: vr.append(v)
            elif lo_c <= h <= hi_c: vc.append(v)
    if len(vr) < 200 or len(vc) < 200: return 1.0
    return min(KAPPA_CAP, statistics.median(vc) / statistics.median(vr))


def gpx_of(s):
    ll, al = arr(s, "latlng"), arr(s, "altitude")
    n = min(len(ll), len(al))
    if n < 20: return None
    st = max(1, n // 1500); pts = []
    for i in range(0, n, st):
        c = ll[i]
        if not isinstance(c, (list, tuple)) or len(c) < 2 or c[0] is None or c[1] is None: continue
        try: lat, lon, e = float(c[0]), float(c[1]), float(al[i])
        except (TypeError, ValueError, IndexError): continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            pts.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"><ele>{e:.1f}</ele></trkpt>')
    if len(pts) < 20: return None
    return ('<?xml version="1.0"?><gpx version="1.1" creator="kd"><trk><trkseg>'
            + "".join(pts) + "</trkseg></trk></gpx>")


def cat_of(d): return "trail" if d >= 15 else ("zone_morte" if d >= 6 else "route")


def f_decay(t, t_full, t_zero):
    if t <= t_full: return 1.0
    if t >= t_zero: return 0.0
    return (t_zero - t) / (t_zero - t_full)


def main():
    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    os.environ.setdefault("JWT_SECRET_KEY", "x"); os.environ.setdefault("ENCRYPTION_KEY", "x")
    import logging; logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    from sqlmodel import Session
    from app.core.database import engine; engine.echo = False
    import app.domain.entities  # noqa
    import app.domain.services.race_predictor.physics_engine as pe
    from app.domain.services.race_predictor.v3_prediction_service import predict_v3

    rows = json.loads((CACHE / "manifest.json").read_text())
    fcmax = estimate_fcmax(rows); kappa = compute_kappa(rows, fcmax)
    targets = []
    for row in rows:
        if float(row.get("distance_m") or 0) < MIN_KM * 1000 or row["id"] in EXCLUDE: continue
        s = streams_of(row["id"])
        if not s: continue
        g = gpx_of(s)
        if g: targets.append((row, g))
    log(f"user={USER[:8]} kappa_flat={kappa:.3f}  {len(targets)} courses >= {MIN_KM:.0f}km")

    orig_mult, orig_min = pe.effort_multiplier, pe.minetti_run_cost

    def predict_one(s, row, gpx, kap, lam):
        pe.effort_multiplier = lambda m: kap
        if lam != 1.0:
            pe.minetti_run_cost = lambda g: (lambda c: c if c <= MINETTI_FLAT else MINETTI_FLAT + (c - MINETTI_FLAT) * lam)(orig_min(g))
        else:
            pe.minetti_run_cost = orig_min
        as_of = datetime.fromisoformat(row["start_date_utc"].replace("Z", "+00:00")).replace(tzinfo=None)
        r = predict_v3(s, UUID(USER), gpx, race_datetime=None, effort_mode="steady", analysis_mode="auto",
                       target_heartrate=None, weather_mode="manual", manual_temperature_c=11.0,
                       ravito_mode="auto", custom_ravitos=None, as_of_date=as_of,
                       excluded_activity_ids={UUID(row["id"])}, history_start_date=as_of - timedelta(days=366))
        mt = (r.get("uncertainty") or {}).get("moving_time") or {}
        return float(r.get("moving_time_min")), mt.get("p10"), mt.get("p90")

    # base durations (kappa=1) pour piloter le decay
    with Session(engine) as s:
        base_T = {}
        for row, gpx in targets:
            base_T[row["id"]], _, _ = predict_one(s, row, gpx, 1.0, 1.0)

    def evaluate(t_full, t_zero, lam, label):
        res = []
        with Session(engine) as s:
            for row, gpx in targets:
                km = float(row["distance_m"]) / 1000.0
                dpkm = float(row.get("elev_gain_m") or 0) / km
                real = float(row["moving_time_s"]) / 60.0
                f = f_decay(base_T[row["id"]], t_full, t_zero)
                kap = 1.0 + (kappa - 1.0) * f
                pred, p10, p90 = predict_one(s, row, gpx, kap, lam)
                cov = (p10 is not None and p90 is not None and p10 <= real <= p90)
                res.append({"km": km, "dpkm": dpkm, "cat": cat_of(dpkm), "real": real,
                            "pred": pred, "cov": cov, "err": (pred - real) / real * 100, "kap": kap})
        n = len(res); c = sum(1 for r in res if r["cov"])
        log(f"\n--- {label} ---  couv={100*c/n:.0f}%  biais_med={statistics.median([r['err'] for r in res]):+.1f}%  "
            f"MAE={sum(abs(r['err']) for r in res)/n:.1f}%")
        for cc in ("route", "zone_morte", "trail"):
            sub = [r for r in res if r["cat"] == cc]
            if sub:
                cv = sum(1 for r in sub if r["cov"])
                log(f"     {cc:11} n={len(sub):2} couv={100*cv/len(sub):3.0f}% biais_med={statistics.median([r['err'] for r in sub]):+5.1f}%")
        # detail des longs (>=40km) pour verifier les ultras
        longs = [r for r in res if r["km"] >= 40]
        for r in sorted(longs, key=lambda x: -x["km"]):
            log(f"        {r['km']:5.1f}km {r['dpkm']:4.0f}m/km  reel {r['real']:.0f}  pred {r['pred']:.0f}  "
                f"kappa_eff={r['kap']:.3f}  err {r['err']:+.0f}%  {'OK' if r['cov'] else 'HORS'}")
        return res

    out = {}
    for (tf, tz) in ((120, 300), (90, 360), (150, 420)):
        out[f"kd_{tf}_{tz}"] = evaluate(tf, tz, 1.0, f"kappa(duree) T_full={tf} T_zero={tz}, lambda=1.0")
    out["kd_120_300_lam"] = evaluate(120, 300, LAMBDA, f"kappa(duree) 120/300 + lambda={LAMBDA}")
    pe.effort_multiplier, pe.minetti_run_cost = orig_mult, orig_min
    (HERE / f"kd_{USER[:8]}.json").write_text(json.dumps({"kappa": kappa, "variants": out}, indent=2))


if __name__ == "__main__":
    main()
