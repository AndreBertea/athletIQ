#!/usr/bin/env python3
"""backtest_louis.py — Backtest V3 vs reel sur les courses de Louis.

Pipeline:
  Phase A  Export Supabase (activites Run + streams depuis storage), avec cache disque.
  Phase B  Construit une db SQLite JETABLE au schema Activity et y insere l'historique.
  Phase C  Leave-one-out: pour chaque course >=20km, predict_v3 as_of=veille,
           excluded={course}, sur le GPX reconstruit de la course; compare au reel.
  Rapport  Erreur signee (%) stratifiee par D+/km (route / zone_morte / trail).

Lancement:
  cd backend && PYTHONPATH=. venv/bin/python ../tools/v3-backtest/backtest_louis.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import requests

LOUIS = "c77fef20-6fad-4741-b268-cf39b22c1e3f"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
DB_PATH = HERE / "backtest_louis.db"
RELAY_ENV = HERE.parent / "garmin-relay" / ".env"


def log(msg: str) -> None:
    print(msg, flush=True)


def load_env() -> tuple[str, str]:
    url = key = ""
    for line in RELAY_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("SUPABASE_URL="):
            url = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            key = line.split("=", 1)[1].strip()
    if not (url and key):
        sys.exit("SUPABASE_URL / SERVICE_ROLE_KEY introuvables dans garmin-relay/.env")
    return url.rstrip("/"), key


# ----------------------------- Phase A : export -----------------------------
def export_activities(url: str, key: str) -> list[dict]:
    manifest = CACHE / "manifest.json"
    if manifest.exists():
        rows = json.loads(manifest.read_text())
        log(f"[A] manifest cache: {len(rows)} activites")
    else:
        h = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "select": "id,start_date_utc,distance_m,moving_time_s,elapsed_time_s,"
            "elev_gain_m,avg_speed_m_s,max_speed_m_s,activity_type,activity_type_override,"
            "sport_type,raw_streams_path",
            "user_id": f"eq.{LOUIS}",
            "sport_type": "eq.Run",
            "order": "start_date_utc.asc",
        }
        r = requests.get(f"{url}/rest/v1/activities", headers=h, params=params, timeout=60)
        r.raise_for_status()
        rows = r.json()
        manifest.write_text(json.dumps(rows))
        log(f"[A] export REST: {len(rows)} activites Run")

    # streams: telecharge ce qui manque
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    miss = 0
    for i, row in enumerate(rows, 1):
        path = row.get("raw_streams_path")
        if not path:
            continue
        dest = CACHE / f"{row['id']}.json"
        if dest.exists():
            continue
        rr = requests.get(f"{url}/storage/v1/object/activity-raw/{path}", headers=h, timeout=120)
        if rr.status_code == 200:
            dest.write_bytes(rr.content)
            miss += 1
            if miss % 20 == 0:
                log(f"[A] streams telecharges: {miss}")
    log(f"[A] streams: {miss} nouveaux, total cache {len(list(CACHE.glob('*.json'))) - 1}")
    return rows


def load_streams(activity_id: str) -> dict | None:
    p = CACHE / f"{activity_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _arr(streams: dict, k: str) -> list:
    v = streams.get(k)
    if isinstance(v, dict) and "data" in v:
        v = v["data"]
    return v if isinstance(v, list) else []


def hr_stats(streams: dict) -> tuple[float | None, float | None]:
    hr = [h for h in _arr(streams, "heartrate") if isinstance(h, (int, float)) and h > 0]
    if not hr:
        return None, None
    return round(sum(hr) / len(hr), 1), float(max(hr))


# ------------------------- Phase B : db + insertion -------------------------
def build_db(rows: list[dict]):
    # DATABASE_URL doit etre pose AVANT d'importer app (engine cree a l'import).
    if DB_PATH.exists():
        DB_PATH.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    os.environ.setdefault("JWT_SECRET_KEY", "backtest-local-only")
    os.environ.setdefault("ENCRYPTION_KEY", "backtest-local")

    import logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    from sqlmodel import Session, SQLModel  # noqa
    from app.core.database import engine  # noqa
    engine.echo = False
    import app.domain.entities  # noqa: F401 (enregistre les modeles)
    from app.domain.entities.activity import Activity, ActivityType, ActivitySource

    SQLModel.metadata.create_all(engine)

    type_map = {
        "Run": ActivityType.RUN,
        "VirtualRun": ActivityType.VIRTUAL_RUN,
        "TrailRun": ActivityType.TRAIL_RUN,
        "Walk": ActivityType.WALK,
    }
    inserted = skipped = 0
    with Session(engine) as session:
        for row in rows:
            streams = load_streams(row["id"])
            if streams is None:
                skipped += 1
                continue
            avg_hr, max_hr = hr_stats(streams)
            base_type = row.get("activity_type") or row.get("sport_type") or "Run"
            override = row.get("activity_type_override")
            sd = row["start_date_utc"].replace("Z", "+00:00")
            start = datetime.fromisoformat(sd).replace(tzinfo=None)  # naive: le moteur compare a utcnow() naive
            act = Activity(
                id=UUID(row["id"]),
                user_id=UUID(LOUIS),
                name=f"Run {start.date()}",
                activity_type=type_map.get(base_type, ActivityType.RUN),
                activity_type_override=type_map.get(override) if override else None,
                start_date=start,
                start_date_local=start,
                distance=float(row.get("distance_m") or 0),
                moving_time=int(row.get("moving_time_s") or 0),
                elapsed_time=int(row.get("elapsed_time_s") or row.get("moving_time_s") or 0),
                total_elevation_gain=float(row.get("elev_gain_m") or 0),
                average_speed=row.get("avg_speed_m_s"),
                max_speed=row.get("max_speed_m_s"),
                average_heartrate=avg_hr,
                max_heartrate=max_hr,
                source=ActivitySource.GARMIN.value,
                streams_data=streams,
            )
            session.add(act)
            inserted += 1
        session.commit()
    log(f"[B] db construite: {inserted} inserees, {skipped} sans streams")
    return engine


# --------------------------- Phase C : backtest -----------------------------
def reconstruct_gpx(streams: dict) -> str | None:
    latlng = _arr(streams, "latlng")
    altitude = _arr(streams, "altitude")
    if not latlng or not altitude:
        return None
    n = min(len(latlng), len(altitude))
    if n < 20:
        return None
    stride = max(1, n // 1500)
    pts = []
    for i in range(0, n, stride):
        c = latlng[i]
        if not isinstance(c, (list, tuple)) or len(c) < 2 or c[0] is None or c[1] is None:
            continue
        try:
            lat, lon, ele = float(c[0]), float(c[1]), float(altitude[i])
        except (TypeError, ValueError, IndexError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        pts.append(f'<trkpt lat="{lat:.8f}" lon="{lon:.8f}"><ele>{ele:.2f}</ele></trkpt>')
    if len(pts) < 20:
        return None
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<gpx version="1.1" creator="backtest"><trk><name>bt</name><trkseg>'
            + "".join(pts) + "</trkseg></trk></gpx>")


def cat_of(dpkm: float) -> str:
    return "trail" if dpkm >= 15 else ("zone_morte" if dpkm >= 6 else "route")


def run_backtest(engine, rows: list[dict]):
    from sqlmodel import Session
    from app.domain.services.race_predictor.v3_prediction_service import predict_v3

    targets = []
    for row in rows:
        dist = float(row.get("distance_m") or 0)
        if dist < 20000:
            continue
        streams = load_streams(row["id"])
        if streams is None:
            continue
        gpx = reconstruct_gpx(streams)
        if gpx is None:
            continue
        targets.append((row, streams, gpx))
    log(f"[C] {len(targets)} courses >=20km a tester (leave-one-out)\n")

    results = []
    hdr = f"{'date':10} {'km':>5} {'D+':>5} {'m/km':>5} {'cat':>10} {'reel':>7} {'pred':>7} {'err%':>7}"
    log(hdr)
    log("-" * len(hdr))
    with Session(engine) as session:
        for row, streams, gpx in sorted(targets, key=lambda t: -float(t[0]["distance_m"])):
            dist_km = float(row["distance_m"]) / 1000.0
            dplus = float(row.get("elev_gain_m") or 0)
            dpkm = dplus / dist_km if dist_km else 0
            real_min = float(row["moving_time_s"]) / 60.0
            sd = row["start_date_utc"].replace("Z", "+00:00")
            as_of = datetime.fromisoformat(sd).replace(tzinfo=None)  # naive (cf. utcnow() interne)
            try:
                res = predict_v3(
                    session, UUID(LOUIS), gpx,
                    race_datetime=None, effort_mode="steady", analysis_mode="auto",
                    target_heartrate=None, weather_mode="manual", manual_temperature_c=11.0,
                    ravito_mode="auto", custom_ravitos=None,
                    as_of_date=as_of, excluded_activity_ids={UUID(row["id"])},
                    history_start_date=as_of - timedelta(days=366), filename="backtest.gpx",
                )
                pred_min = float(res.get("moving_time_min")
                                 or res.get("summary", {}).get("moving_time_min"))
                err = (pred_min - real_min) / real_min * 100.0
                results.append({"cat": cat_of(dpkm), "dpkm": dpkm, "err": err,
                                "real": real_min, "pred": pred_min, "km": dist_km})
                log(f"{as_of.date()!s:10} {dist_km:5.1f} {dplus:5.0f} {dpkm:5.1f} "
                    f"{cat_of(dpkm):>10} {real_min:6.0f}m {pred_min:6.0f}m {err:+6.1f}%")
            except Exception as exc:
                log(f"{as_of.date()!s:10} {dist_km:5.1f} ECHEC: {str(exc)[:80]}")
    return results


def report(results: list[dict]):
    if not results:
        log("\nAucun resultat.")
        return
    log("\n" + "=" * 60 + "\nSYNTHESE PAR CATEGORIE (err% > 0 = trop LENT, < 0 = trop RAPIDE)")
    for cat in ("route", "zone_morte", "trail"):
        sub = [r for r in results if r["cat"] == cat]
        if not sub:
            continue
        errs = sorted(r["err"] for r in sub)
        n = len(errs)
        mean = sum(errs) / n
        med = errs[n // 2] if n % 2 else (errs[n // 2 - 1] + errs[n // 2]) / 2
        mae = sum(abs(e) for e in errs) / n
        log(f"  {cat:10} n={n:2}  biais_moy={mean:+6.1f}%  median={med:+6.1f}%  MAE={mae:5.1f}%")
    allerr = [r["err"] for r in results]
    log(f"  {'GLOBAL':10} n={len(allerr):2}  biais_moy={sum(allerr)/len(allerr):+6.1f}%  "
        f"MAE={sum(abs(e) for e in allerr)/len(allerr):5.1f}%")
    log("\nLecture: si biais devient negatif et s'aggrave avec le D+/km (route->trail),")
    log("le moteur est trop optimiste en cote pour Louis (hypothese biais plat confirmee).")
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    log(f"\nDetail -> {HERE / 'results.json'}")


def main():
    url, key = load_env()
    rows = export_activities(url, key)
    engine = build_db(rows)
    results = run_backtest(engine, rows)
    report(results)


if __name__ == "__main__":
    main()
