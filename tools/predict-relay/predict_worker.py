#!/usr/bin/env python3
"""predict_worker.py — Worker de prédiction de course sur le 2e Mac.

Fait tourner le VRAI moteur Python (V2.2 / V2.3 / V3) — celui de
backend/app/domain/services/race_predictor/ — contre la base historique
stridedelta.db (280 activités, références validées). Le moteur Edge Supabase
n'était qu'un MVP qui sortait un temps quasi-élite ; ici on retrouve la
prédiction personnalisée (trail factor, fatigue, incertitude P10/P50/P90).

Flux : poll prediction_jobs (Supabase) -> récupère le GPX depuis Storage ->
predict_v3/predict_v2_3/predict_v2_2(session_stridedelta, OLD_USER_ID, gpx, params)
-> écrit le résultat complet dans prediction_jobs.result + une ligne
race_predictions. La PWA lit le résultat.

Lancement : voir SECOND_MAC_PREDICT_PROMPT.md (PYTHONPATH=backend, env DATABASE_URL
pointant sur stridedelta.db).
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from uuid import UUID

# --- Boot du moteur : ces variables DOIVENT être posées avant d'importer `app`,
#     car app.core.database crée l'engine SQLModel à l'import depuis settings. ---
DB_PATH = os.environ.get("PREDICT_DB_PATH")  # ex: /Users/andre/predict-relay/stridedelta.db
if DB_PATH:
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH}")
os.environ.setdefault("DATABASE_URL", "sqlite:///stridedelta.db")
os.environ.setdefault("JWT_SECRET_KEY", "predict-worker-local-only")
os.environ.setdefault("STRAVA_CLIENT_ID", "0")  # non utilisé ici

try:
    import requests
    from sqlmodel import Session, SQLModel
    from app.core.database import engine as sqlmodel_engine
    import app.domain.entities  # noqa: F401 — enregistre tous les modèles dans SQLModel.metadata
    from app.domain.services.race_predictor.v3_prediction_service import predict_v3
    from app.domain.services.race_predictor.v2_3_prediction_service import predict_v2_3
    from app.domain.services.race_predictor.v2_2_prediction_service import predict_v2_2
except ImportError as exc:
    sys.exit(
        f"Import impossible ({exc}).\n"
        "Lance avec PYTHONPATH=<repo>/backend et installe les deps "
        "(pip install sqlmodel numpy gpxpy requests)."
    )

# Crée les tables manquantes (modèle résiduel V3, candidates...) sans toucher aux
# données historiques de stridedelta.db. Indispensable : ces tables sont plus
# récentes que le snapshot de la base.
SQLModel.metadata.create_all(sqlmodel_engine)


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
POLL_INTERVAL = float(os.environ.get("PREDICT_POLL_INTERVAL", "3"))
# Mapping user Supabase -> user historique stridedelta.db.
# Mono-athlète : OLD_USER_ID s'applique à tous les jobs. Sinon JSON dans PREDICT_USER_MAP.
OLD_USER_ID = os.environ.get("OLD_USER_ID", "")
USER_MAP = json.loads(os.environ.get("PREDICT_USER_MAP", "{}"))

if not (SUPABASE_URL and SERVICE_ROLE_KEY):
    sys.exit("Config manquante (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY). cf .env")
if not (OLD_USER_ID or USER_MAP):
    sys.exit("Config manquante : OLD_USER_ID (uuid user historique stridedelta.db).")

REST = f"{SUPABASE_URL}/rest/v1"
STORAGE = f"{SUPABASE_URL}/storage/v1/object"
HEADERS = {
    "apikey": SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


# --- Supabase REST + Storage --------------------------------------------------
def sb_get(table: str, params: dict) -> list[dict]:
    r = requests.get(f"{REST}/{table}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def sb_patch(table: str, params: dict, payload: dict) -> None:
    h = dict(HEADERS); h["Prefer"] = "return=minimal"
    r = requests.patch(f"{REST}/{table}", headers=h, params=params, json=payload, timeout=30)
    r.raise_for_status()


def sb_insert(table: str, payload: dict) -> str | None:
    h = dict(HEADERS); h["Prefer"] = "return=representation"
    r = requests.post(f"{REST}/{table}", headers=h, json=payload, timeout=30)
    r.raise_for_status()
    rows = r.json()
    return rows[0]["id"] if rows else None


def storage_download_text(path: str) -> str:
    r = requests.get(
        f"{STORAGE}/gpx-files/{path}",
        headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        timeout=60,
    )
    r.raise_for_status()
    return r.text


# --- Sérialisation : le moteur peut renvoyer datetime/UUID/numpy -> JSON propre -
def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    # numpy scalaires
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# --- Helpers params -----------------------------------------------------------
def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def to_float(value):
    try:
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def resolve_old_user(supabase_user_id: str) -> UUID:
    raw = USER_MAP.get(supabase_user_id, OLD_USER_ID)
    return UUID(raw)


# --- Dispatch vers le vrai moteur --------------------------------------------
def run_engine(session: Session, engine_name: str, old_user_id: UUID, gpx_text: str, p: dict) -> dict:
    common = dict(
        race_datetime=parse_dt(p.get("race_datetime")),
        effort_mode=str(p.get("effort_mode", "steady")),
        analysis_mode=str(p.get("analysis_mode", "auto")),
        target_heartrate=to_float(p.get("target_heartrate")),
        weather_mode=str(p.get("weather_mode", "manual")),
        manual_temperature_c=to_float(p.get("manual_temperature_c", p.get("temperature_c"))),
        ravito_mode=str(p.get("ravito_mode", "auto")),
        custom_ravitos=p.get("custom_ravitos") or None,
        filename=p.get("filename"),
    )
    history_start = parse_dt(p.get("history_start_date"))
    if engine_name == "v3":
        return predict_v3(session, old_user_id, gpx_text, history_start_date=history_start, **common)
    if engine_name in ("v2_3", "v2"):
        return predict_v2_3(session, old_user_id, gpx_text, history_start_date=history_start, **common)
    if engine_name == "v2_2":
        return predict_v2_2(session, old_user_id, gpx_text, **common)
    raise ValueError(f"Moteur inconnu: {engine_name}")


# --- Persistance du résultat -------------------------------------------------
def save_prediction_row(job: dict, result: dict) -> str | None:
    """Insère une ligne race_predictions (Supabase) pour la liste des prédictions."""
    try:
        return sb_insert("race_predictions", {
            "user_id": job["user_id"],
            "route_id": job.get("route_id"),
            "name": str(job.get("params", {}).get("prediction_name")
                        or result.get("filename") or "Prediction"),
            "filename": result.get("filename"),
            "engine_version": result.get("engine_version"),
            "analysis_mode": result.get("analysis_mode"),
            "ravito_mode": result.get("ravito_mode"),
            "history_start_date": result.get("history_start_date"),
            "total_distance_km": result.get("total_distance_km"),
            "total_elevation_gain_m": result.get("total_elevation_gain_m"),
            "moving_time_min": result.get("moving_time_min"),
            "total_pause_min": result.get("total_pause_min"),
            "total_time_min": result.get("total_time_min"),
            "avg_pace": result.get("avg_pace"),
            "prediction_data": result,
        })
    except Exception as exc:
        log(f"  ! insert race_predictions échoué (non bloquant): {exc}")
        return None


def process_job(job: dict) -> None:
    job_id = job["id"]
    engine_name = job.get("engine", "v3")
    params = job.get("params") or {}
    log(f"job {job_id} : moteur {engine_name} (user {job['user_id']})")
    sb_patch("prediction_jobs", {"id": f"eq.{job_id}"}, {"status": "processing"})

    # 1) GPX : depuis Storage (route) ou inline dans params.
    gpx_text = params.get("gpx_text")
    if not gpx_text:
        path = job.get("gpx_storage_path")
        if not path:
            raise ValueError("Ni gpx_storage_path ni params.gpx_text fournis.")
        gpx_text = storage_download_text(path)

    old_user_id = resolve_old_user(job["user_id"])

    # 2) Moteur réel (peut écrire dans stridedelta.db : candidates/résiduel).
    with Session(sqlmodel_engine) as session:
        raw_result = run_engine(session, engine_name, old_user_id, gpx_text, params)

    result = jsonable(raw_result)

    # 3) Persiste : ligne race_predictions + résultat complet dans le job.
    pred_id = save_prediction_row(job, result)
    sb_patch("prediction_jobs", {"id": f"eq.{job_id}"}, {
        "status": "done",
        "result": result,
        "result_prediction_id": pred_id,
        "error": None,
    })
    total = result.get("total_time_formatted") or result.get("total_time_min")
    log(f"  job {job_id} OK : {result.get('engine_version')} -> {total}")


def fail_job(job_id: str, message: str) -> None:
    try:
        sb_patch("prediction_jobs", {"id": f"eq.{job_id}"},
                 {"status": "failed", "error": message[:500]})
    except Exception as exc:
        log(f"  ! maj échec job {job_id} impossible: {exc}")
    log(f"  job {job_id} ECHEC : {message[:200]}")


def claim_next() -> dict | None:
    rows = sb_get("prediction_jobs", {
        "select": "id,user_id,engine,route_id,gpx_storage_path,params",
        "status": "eq.pending",
        "order": "created_at.asc",
        "limit": "1",
    })
    return rows[0] if rows else None


def main() -> None:
    log(f"Worker prédiction démarré (DB={os.environ['DATABASE_URL']}). Polling...")
    while True:
        try:
            job = claim_next()
            if job:
                try:
                    process_job(job)
                except Exception as exc:
                    fail_job(job["id"], f"{exc}\n{traceback.format_exc()}")
                continue
        except Exception as exc:
            log(f"!! erreur boucle : {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Arrêt demandé. Bye.")
