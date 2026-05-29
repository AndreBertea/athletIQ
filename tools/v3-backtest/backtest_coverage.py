#!/usr/bin/env python3
"""backtest_coverage.py — Backtest V3 generique + couverture P10/P90.

Pour TOUT athlete (env BACKTEST_USER_ID). Mesure, en leave-one-out:
  - biais median & MAE par categorie de D+/km (route/zone_morte/trail)
  - COUVERTURE : % des temps reels tombant dans [P10, P90] du moteur
en 3 variantes: baseline / kappa_flat / kappa+cout_vertical(lambda).
Exclut les courses-accident (env BACKTEST_EXCLUDE_IDS, liste d'UUID).

Reproductible: FCmax derivee des donnees, kappa mesure (bandes FC), user parametrable.
Lancement:
  cd backend && BACKTEST_USER_ID=<uuid> BACKTEST_MIN_KM=10 \\
    PYTHONPATH=. venv/bin/python ../tools/v3-backtest/backtest_coverage.py
"""
from __future__ import annotations
import json, os, statistics
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
import requests

USER = os.environ.get("BACKTEST_USER_ID", "c77fef20-6fad-4741-b268-cf39b22c1e3f")
MIN_KM = float(os.environ.get("BACKTEST_MIN_KM", "20"))
LAMBDA = float(os.environ.get("BACKTEST_LAMBDA", "1.3"))
EXCLUDE = {x.strip() for x in os.environ.get("BACKTEST_EXCLUDE_IDS", "").split(",") if x.strip()}
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / USER
CACHE.mkdir(parents=True, exist_ok=True)
DB_PATH = HERE / f"bt_{USER[:8]}.db"
RELAY_ENV = HERE.parent / "garmin-relay" / ".env"
REF_BAND, RACE_BAND, KAPPA_CAP, MINETTI_FLAT = (0.72, 0.78), (0.85, 0.90), 1.20, 3.6


def log(m): print(m, flush=True)
def arr(s, k):
    v = s.get(k)
    return v["data"] if isinstance(v, dict) and "data" in v else (v if isinstance(v, list) else [])


def load_env():
    u = k = ""
    for line in RELAY_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("SUPABASE_URL="): u = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="): k = line.split("=", 1)[1].strip()
    return u.rstrip("/"), k


def export(url, key):
    mani = CACHE / "manifest.json"
    if mani.exists():
        rows = json.loads(mani.read_text())
    else:
        h = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {"select": "id,start_date_utc,distance_m,moving_time_s,elapsed_time_s,elev_gain_m,"
                  "avg_speed_m_s,max_speed_m_s,activity_type,activity_type_override,sport_type,raw_streams_path",
                  "user_id": f"eq.{USER}", "sport_type": "in.(Run,TrailRun,VirtualRun)",
                  "order": "start_date_utc.asc"}
        r = requests.get(f"{url}/rest/v1/activities", headers=h, params=params, timeout=60)
        r.raise_for_status(); rows = r.json(); mani.write_text(json.dumps(rows))
    log(f"[A] {len(rows)} activites course")
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    miss = 0
    for row in rows:
        p = row.get("raw_streams_path")
        if not p: continue
        dest = CACHE / f"{row['id']}.json"
        if dest.exists(): continue
        rr = requests.get(f"{url}/storage/v1/object/activity-raw/{p}", headers=h, timeout=120)
        if rr.status_code == 200: dest.write_bytes(rr.content); miss += 1
    log(f"[A] {miss} streams telecharges")
    return rows


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
        if dist < 3000: continue
        if float(row.get("elev_gain_m") or 0) / (dist / 1000.0) >= 6: continue  # plat only
        s = streams_of(row["id"])
        if not s: continue
        hr, vs = arr(s, "heartrate"), arr(s, "velocity_smooth")
        for i in range(min(len(hr), len(vs))):
            h, v = hr[i], vs[i]
            if not isinstance(h, (int, float)) or not isinstance(v, (int, float)) or v <= 0: continue
            if lo_r <= h <= hi_r: vr.append(v)
            elif lo_c <= h <= hi_c: vc.append(v)
    if len(vr) < 200 or len(vc) < 200:
        return 1.0, None, None, len(vr), len(vc)  # garde-fou faible signal -> kappa=1.0
    mr, mc = statistics.median(vr), statistics.median(vc)
    return min(KAPPA_CAP, mc / mr), mr, mc, len(vr), len(vc)


def build_db(rows):
    if DB_PATH.exists(): DB_PATH.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    os.environ.setdefault("JWT_SECRET_KEY", "x"); os.environ.setdefault("ENCRYPTION_KEY", "x")
    import logging; logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    from sqlmodel import Session, SQLModel
    from app.core.database import engine; engine.echo = False
    import app.domain.entities  # noqa
    from app.domain.entities.activity import Activity, ActivityType, ActivitySource
    SQLModel.metadata.create_all(engine)
    tmap = {"Run": ActivityType.RUN, "VirtualRun": ActivityType.VIRTUAL_RUN,
            "TrailRun": ActivityType.TRAIL_RUN, "Walk": ActivityType.WALK}
    ins = 0
    with Session(engine) as s:
        for row in rows:
            st = streams_of(row["id"])
            if st is None: continue
            hr = [h for h in arr(st, "heartrate") if isinstance(h, (int, float)) and h > 0]
            avg_hr = round(sum(hr) / len(hr), 1) if hr else None
            max_hr = float(max(hr)) if hr else None
            d = datetime.fromisoformat(row["start_date_utc"].replace("Z", "+00:00")).replace(tzinfo=None)
            ov = row.get("activity_type_override")
            s.add(Activity(
                id=UUID(row["id"]), user_id=UUID(USER), name=f"run {d.date()}",
                activity_type=tmap.get(row.get("activity_type") or "Run", ActivityType.RUN),
                activity_type_override=tmap.get(ov) if ov else None,
                start_date=d, start_date_local=d,
                distance=float(row.get("distance_m") or 0), moving_time=int(row.get("moving_time_s") or 0),
                elapsed_time=int(row.get("elapsed_time_s") or row.get("moving_time_s") or 0),
                total_elevation_gain=float(row.get("elev_gain_m") or 0),
                average_speed=row.get("avg_speed_m_s"), max_speed=row.get("max_speed_m_s"),
                average_heartrate=avg_hr, max_heartrate=max_hr,
                source=ActivitySource.GARMIN.value, streams_data=st))
            ins += 1
        s.commit()
    log(f"[B] {ins} activites inserees")
    return engine


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
    return ('<?xml version="1.0"?><gpx version="1.1" creator="cov"><trk><trkseg>'
            + "".join(pts) + "</trkseg></trk></gpx>")


def cat_of(d): return "trail" if d >= 15 else ("zone_morte" if d >= 6 else "route")


def run_variant(predict_v3, Session, engine, targets):
    out = []
    with Session(engine) as s:
        for row, gpx in targets:
            km = float(row["distance_m"]) / 1000.0
            dpkm = float(row.get("elev_gain_m") or 0) / km
            real = float(row["moving_time_s"]) / 60.0
            as_of = datetime.fromisoformat(row["start_date_utc"].replace("Z", "+00:00")).replace(tzinfo=None)
            try:
                r = predict_v3(s, UUID(USER), gpx, race_datetime=None, effort_mode="steady",
                               analysis_mode="auto", target_heartrate=None, weather_mode="manual",
                               manual_temperature_c=11.0, ravito_mode="auto", custom_ravitos=None,
                               as_of_date=as_of, excluded_activity_ids={UUID(row["id"])},
                               history_start_date=as_of - timedelta(days=366))
                pred = float(r.get("moving_time_min"))
                mt = (r.get("uncertainty") or {}).get("moving_time") or {}
                p10, p90 = mt.get("p10"), mt.get("p90")
                covered = (p10 is not None and p90 is not None and p10 <= real <= p90)
                out.append({"date": str(as_of.date()), "km": round(km, 1), "dpkm": round(dpkm, 1),
                            "cat": cat_of(dpkm), "real": real, "pred": pred, "p10": p10, "p90": p90,
                            "covered": covered, "err": (pred - real) / real * 100})
            except Exception as exc:
                log(f"   ECHEC {row['id'][:8]}: {str(exc)[:70]}")
    return out


def report(res, label):
    log(f"\n=== {label} ===")
    log(f"{'date':11}{'km':>5}{'m/km':>6}{'cat':>11}{'reel':>6}{'pred':>6}{'P10':>6}{'P90':>6}  cov")
    for r in sorted(res, key=lambda x: -x["km"]):
        flag = "OK " if r["covered"] else ("LENT" if r["real"] > (r["p90"] or 9e9) else "RAPID")
        log(f"{r['date']:11}{r['km']:5.1f}{r['dpkm']:6.1f}{r['cat']:>11}{r['real']:6.0f}{r['pred']:6.0f}"
            f"{(r['p10'] or 0):6.0f}{(r['p90'] or 0):6.0f}  {flag}")
    n = len(res); cov = sum(1 for r in res if r["covered"])
    log(f"  -- couverture globale P10-P90 : {cov}/{n} = {100*cov/max(n,1):.0f}%  "
        f"(cible ~80%) | biais median {statistics.median([r['err'] for r in res]):+.1f}% "
        f"| MAE {sum(abs(r['err']) for r in res)/max(n,1):.1f}%")
    for c in ("route", "zone_morte", "trail"):
        sub = [r for r in res if r["cat"] == c]
        if not sub: continue
        cc = sum(1 for r in sub if r["covered"])
        log(f"     {c:11} n={len(sub):2} couv={100*cc/len(sub):3.0f}%  "
            f"biais_med={statistics.median([r['err'] for r in sub]):+5.1f}%")


def main():
    url, key = load_env()
    rows = export(url, key)
    fcmax = estimate_fcmax(rows)
    kappa, mr, mc, nr, nc = compute_kappa(rows, fcmax)
    log(f"\n[kappa] FCmax={fcmax:.0f}  REF n={nr} RACE n={nc}  kappa_flat={kappa:.3f}"
        + (f"  (p_ref {MINETTI_FLAT*mr:.1f} -> p_race {MINETTI_FLAT*mc:.1f} W/kg)" if mr else "  (FAIBLE SIGNAL -> 1.0)"))
    engine = build_db(rows)
    from sqlmodel import Session
    from app.core.database import engine as eng; eng.echo = False
    import app.domain.services.race_predictor.physics_engine as pe
    from app.domain.services.race_predictor.v3_prediction_service import predict_v3

    targets = []
    for row in rows:
        if float(row.get("distance_m") or 0) < MIN_KM * 1000: continue
        if row["id"] in EXCLUDE: continue
        st = streams_of(row["id"])
        if not st: continue
        g = gpx_of(st)
        if g: targets.append((row, g))
    log(f"\n{len(targets)} courses >= {MIN_KM:.0f}km (exclu accidents: {len(EXCLUDE)})")

    orig_mult, orig_min = pe.effort_multiplier, pe.minetti_run_cost
    base = run_variant(predict_v3, Session, engine, targets); report(base, "BASELINE V3")
    pe.effort_multiplier = lambda m: kappa
    kap = run_variant(predict_v3, Session, engine, targets); report(kap, f"kappa={kappa:.2f}")
    def vmin(g):
        c = orig_min(g); return c if c <= MINETTI_FLAT else MINETTI_FLAT + (c - MINETTI_FLAT) * LAMBDA
    pe.minetti_run_cost = vmin
    kl = run_variant(predict_v3, Session, engine, targets); report(kl, f"kappa={kappa:.2f} + vertical x{LAMBDA}")
    pe.effort_multiplier, pe.minetti_run_cost = orig_mult, orig_min
    (HERE / f"coverage_{USER[:8]}.json").write_text(json.dumps(
        {"user": USER, "kappa": kappa, "lambda": LAMBDA, "baseline": base, "kappa": kap, "kappa_lambda": kl}, indent=2))


if __name__ == "__main__":
    main()
