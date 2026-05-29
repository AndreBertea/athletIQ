"""
Routes du Race Predictor.

Ces endpoints reprennent le predicteur GPX archive dans
`archive/race-predictor-v1`, en l'adaptant a l'architecture actuelle :
authentification utilisateur, base SQLModel courante et router dedie.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import joblib
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.api.routers._shared import security
from app.auth.jwt import get_current_user_id
from app.core.database import engine, get_session
from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.entities.race_prediction import (
    RacePrediction,
    RacePredictionComparison,
    RacePredictorV3ResidualModel,
    RaceReferenceCandidate,
    RaceValidationReference,
)
from app.domain.services.gpx_route_service import gpx_route_service
from app.domain.services.race_predictor.calibration_service import build_calibration
from app.domain.services.race_predictor.environment_service import build_environment, summarize_weather_exposure
from app.domain.services.race_predictor.fatigue_model import build_fatigue_profile
from app.domain.services.race_predictor.gpx_analyzer import ELEVATION_NOISE_THRESHOLD_M, analyze_gpx
from app.domain.services.race_predictor.physics_engine import predict_segments
from app.domain.services.race_predictor.ravito_service import (
    apply_pauses_to_segments as apply_v2_pauses_to_segments,
)
from app.domain.services.race_predictor.ravito_service import (
    auto_ravitos as auto_v2_ravitos,
)
from app.domain.services.race_predictor.ravito_service import (
    manual_ravitos as manual_v2_ravitos,
)
from app.domain.services.race_predictor.ravito_service import (
    ravito_config_from_points as v2_ravito_config_from_points,
)
from app.domain.services.race_predictor.reference_detection_service import (
    candidate_to_dict,
    detect_reference_candidates,
)
from app.domain.services.race_predictor.uncertainty_service import monte_carlo_uncertainty
from gpx_parser import calculate_global_stats, parse_gpx_file

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_gpx_input(
    file: Optional[UploadFile],
    route_id: Optional[str],
    session: Session,
    user_id: UUID,
) -> tuple[str, str]:
    """Retourne (gpx_text, filename) depuis le file uploade OU une route en BDD.

    Permet aux endpoints prediction d'accepter soit un upload direct
    (workflow original), soit un identifiant pointant sur une trace deja
    enregistree (catalogue public ou import perso).
    """
    if route_id:
        try:
            route_uuid = UUID(route_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="route_id invalide") from exc
        route = gpx_route_service.get_by_id_for_user(session, route_uuid, user_id)
        if route is None:
            raise HTTPException(status_code=404, detail="Trace GPX introuvable")
        try:
            text = bytes(route.gpx_data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"GPX corrompu: {exc}") from exc
        return text, route.filename

    if file is not None and file.filename:
        try:
            text = (await file.read()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"GPX invalide: {exc}") from exc
        return text, file.filename

    raise HTTPException(status_code=400, detail="file ou route_id requis")


class SaveRacePredictionRequest(BaseModel):
    name: str
    prediction: dict[str, Any]
    history_start_date: Optional[str] = None


class SaveRacePredictionComparisonRequest(BaseModel):
    prediction_id: UUID
    activity_id: str
    name: Optional[str] = None


class SaveRaceValidationReferenceRequest(BaseModel):
    category: str
    notes: Optional[str] = None
    potential_gain_min_low: Optional[float] = None
    potential_gain_min_high: Optional[float] = None


class DetectReferenceCandidatesRequest(BaseModel):
    history_start_date: Optional[str] = None
    limit: int = 200
    force: bool = False


class ResolveReferenceCandidateRequest(BaseModel):
    action: str
    category: Optional[str] = None
    notes: Optional[str] = None
    potential_gain_min_low: Optional[float] = None
    potential_gain_min_high: Optional[float] = None


REFERENCE_CATEGORIES = {
    "unclassified",
    "official_clean",
    "official_normalized",
    "training_control",
    "execution_degraded_non_scoring",
    "incident_non_scoring",
}


def _model_path() -> Path:
    """Retourne le chemin du modele principal restaure depuis Race Predictor v1."""
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "models" / "pace_predictor_model.joblib"


def _format_minutes(minutes: float) -> str:
    return f"{int(minutes // 60)}h{int(minutes % 60):02d}"


def _ensure_race_prediction_table() -> None:
    """Creation initiale des tables raceprediction, racepredictioncomparison et racevalidationreference.

    NOTE V2.3.1 R6 final: la colonne ``engine_version`` est desormais geree
    par la migration Alembic
    ``v231_engine_version_add_engine_version_to_raceprediction.py``. Le DDL
    runtime ad-hoc qui ajoutait cette colonne (ALTER TABLE) et son index
    (CREATE INDEX IF NOT EXISTS) au demarrage de l'app a ete supprime.
    Assurez-vous d'appliquer ``alembic upgrade head`` apres deploiement.
    """
    RacePrediction.__table__.create(engine, checkfirst=True)
    RacePredictionComparison.__table__.create(engine, checkfirst=True)
    RaceValidationReference.__table__.create(engine, checkfirst=True)
    RaceReferenceCandidate.__table__.create(engine, checkfirst=True)
    RacePredictorV3ResidualModel.__table__.create(engine, checkfirst=True)


def _utc_naive(value: datetime) -> datetime:
    """Normalize optional timezone-aware input for UTC-naive database dates."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_history_start_date(
    history_start_date: Optional[str],
    *,
    reference_date: Optional[datetime] = None,
) -> datetime:
    """Retourne une date de debut bornee entre 3 mois et 3 ans."""
    now = _utc_naive(reference_date or datetime.utcnow())
    earliest_start = now - timedelta(days=366 * 3)
    latest_start = now - timedelta(days=92)

    if not history_start_date:
        return earliest_start

    try:
        parsed = _utc_naive(datetime.fromisoformat(history_start_date.replace("Z", "+00:00")))
    except ValueError:
        return earliest_start

    if parsed < earliest_start:
        return earliest_start
    if parsed > latest_start:
        return latest_start
    return parsed


def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return _utc_naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _prediction_to_dict(prediction: RacePrediction) -> dict:
    engine_version = getattr(prediction, "engine_version", None) or (prediction.prediction_data or {}).get("engine_version") or "v1_random_forest"
    return {
        "id": str(prediction.id),
        "name": prediction.name,
        "filename": prediction.filename,
        "engine_version": engine_version,
        "analysis_mode": prediction.analysis_mode,
        "ravito_mode": prediction.ravito_mode,
        "history_start_date": prediction.history_start_date.isoformat() if prediction.history_start_date else None,
        "total_distance_km": prediction.total_distance_km,
        "total_elevation_gain_m": prediction.total_elevation_gain_m,
        "moving_time_min": prediction.moving_time_min,
        "total_pause_min": prediction.total_pause_min,
        "total_time_min": prediction.total_time_min,
        "avg_pace": prediction.avg_pace,
        "prediction_data": prediction.prediction_data,
        "created_at": prediction.created_at.isoformat(),
        "updated_at": prediction.updated_at.isoformat(),
    }


def _comparison_to_dict(comparison: RacePredictionComparison) -> dict:
    comparison_data = comparison.comparison_data or {}
    prediction_data = comparison_data.get("prediction") or {}
    activity_data = comparison_data.get("activity") or {}

    return {
        "id": str(comparison.id),
        "name": comparison.name,
        "prediction_id": str(comparison.prediction_id),
        "activity_id": str(comparison.activity_id) if comparison.activity_id else None,
        "prediction_name": prediction_data.get("name"),
        "activity_name": activity_data.get("name"),
        "comparison_data": comparison_data,
        "total_delta_min": comparison.total_delta_min,
        "moving_delta_min": comparison.moving_delta_min,
        "pause_delta_min": comparison.pause_delta_min,
        "avg_abs_segment_delta_min": comparison.avg_abs_segment_delta_min,
        "comparable_distance_km": comparison.comparable_distance_km,
        "created_at": comparison.created_at.isoformat(),
        "updated_at": comparison.updated_at.isoformat(),
    }


def _reference_to_dict(reference: RaceValidationReference) -> dict:
    return {
        "id": str(reference.id),
        "activity_id": str(reference.activity_id),
        "category": reference.category,
        "notes": reference.notes,
        "potential_gain_min_low": reference.potential_gain_min_low,
        "potential_gain_min_high": reference.potential_gain_min_high,
        "created_at": reference.created_at.isoformat(),
        "updated_at": reference.updated_at.isoformat(),
    }


def _candidate_with_activity_to_dict(session: Session, candidate: RaceReferenceCandidate) -> dict:
    activity = session.exec(
        select(Activity).where(Activity.id == candidate.activity_id)
    ).first()
    return candidate_to_dict(candidate, activity)


def _ravito_config_from_points(ravito_points: list[dict]) -> list[dict]:
    return [
        {
            "km": round(float(ravito.get("distance_km") or 0), 2),
            "name": ravito.get("name") or "Ravito",
            "pause_min": round(float(ravito.get("pause_min") or 0), 1),
        }
        for ravito in ravito_points
        if float(ravito.get("distance_km") or 0) > 0
    ]


def _normalize_analysis_mode(analysis_mode: Optional[str]) -> str:
    if not analysis_mode:
        return "trail"

    normalized = analysis_mode.strip().lower()
    if normalized in {"route", "road", "run"}:
        return "route"
    if normalized in {"trail", "trailrun", "trail_run"}:
        return "trail"
    raise ValueError("Mode d'analyse invalide")


def _normalize_v2_analysis_mode(analysis_mode: Optional[str]) -> str:
    if not analysis_mode:
        return "auto"

    normalized = analysis_mode.strip().lower()
    if normalized in {"auto", "automatic"}:
        return "auto"
    if normalized in {"route", "road", "run"}:
        return "route"
    if normalized in {"trail", "trailrun", "trail_run"}:
        return "trail"
    raise ValueError("Mode d'analyse invalide")


def _normalize_effort_mode(effort_mode: Optional[str]) -> str:
    if not effort_mode:
        return "steady"

    normalized = effort_mode.strip().lower()
    aliases = {
        "endurance": "endurance",
        "easy": "endurance",
        "course_maitrisee": "steady",
        "course maîtrisée": "steady",
        "steady": "steady",
        "objectif_agressif": "aggressive",
        "objectif agressif": "aggressive",
        "aggressive": "aggressive",
        "fc_cible": "hr_target",
        "fc cible": "hr_target",
        "hr_target": "hr_target",
    }
    return aliases.get(normalized, "steady")


def _normalize_ravito_mode(ravito_mode: Optional[str]) -> str:
    if not ravito_mode:
        return "auto"

    normalized = ravito_mode.strip().lower()
    if normalized in {"auto", "automatic"}:
        return "auto"
    if normalized in {"manual", "manuel"}:
        return "manual"
    raise ValueError("Mode ravito invalide")


def _normalize_weather_mode(weather_mode: Optional[str]) -> str:
    if not weather_mode:
        return "auto"
    normalized = weather_mode.strip().lower()
    if normalized in {"auto", "automatic"}:
        return "auto"
    if normalized in {"manual", "manuel"}:
        return "manual"
    raise ValueError("Mode meteo invalide")


def _parse_custom_ravitos_json(custom_ravitos: Optional[str]) -> list[dict[str, Any]]:
    if not custom_ravitos:
        return []
    try:
        parsed = json.loads(custom_ravitos)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _historical_heart_rate_stats(
    session: Session,
    user_id: UUID,
    *,
    is_trail: bool,
    history_start_date: datetime,
    target_heartrate: Optional[float] = None,
) -> tuple[int, int]:
    """Recupere la FC historique moyenne de l'utilisateur pour Run/TrailRun.

    Le predicteur v1 injectait une FC moyenne historique issue de l'ancienne
    base `activity_detail.db`. Ici on utilise la table `activity` courante.
    """
    if target_heartrate and 60 <= target_heartrate <= 220:
        return int(target_heartrate), 0

    activity_type = ActivityType.TRAIL_RUN if is_trail else ActivityType.RUN
    effective_type_clause = or_(
        Activity.activity_type_override == activity_type,
        and_(Activity.activity_type_override.is_(None), Activity.activity_type == activity_type),
    )

    heart_rates = session.exec(
        select(Activity.average_heartrate).where(
            Activity.user_id == user_id,
            Activity.source == ActivitySource.GARMIN.value,
            effective_type_clause,
            Activity.average_heartrate.is_not(None),
            Activity.average_heartrate > 0,
            Activity.start_date >= history_start_date,
        )
    ).all()
    if heart_rates:
        return int(sum(heart_rates) / len(heart_rates)), len(heart_rates)

    return 150 if is_trail else 140, 0


def _moving_time_at_distance(predictions: list[dict], target_km: float) -> float:
    cumulative_distance = 0.0
    previous_moving_time = 0.0

    for prediction in predictions:
        segment_distance = float(prediction["distance_km"])
        segment_time = float(prediction["predicted_time_min"])
        next_distance = cumulative_distance + segment_distance

        if target_km <= next_distance:
            if segment_distance <= 0:
                return previous_moving_time
            ratio = max(0.0, min(1.0, (target_km - cumulative_distance) / segment_distance))
            return previous_moving_time + segment_time * ratio

        cumulative_distance = next_distance
        previous_moving_time += segment_time

    return previous_moving_time


def _format_pause(minutes: float) -> str:
    if minutes <= 0:
        return "0min"
    if float(minutes).is_integer():
        return f"{int(minutes)}min"
    return f"{minutes:.1f}min"


def _ravito_point(
    predictions: list[dict],
    *,
    distance_km: float,
    name: str,
    pause_min: float,
    cumulative_pause_before: float,
    source: str,
) -> dict:
    moving_time = _moving_time_at_distance(predictions, distance_km)
    arrival_time = moving_time + cumulative_pause_before
    departure_time = arrival_time + pause_min

    return {
        "distance_km": round(distance_km, 2),
        "name": name,
        "pause_min": round(pause_min, 1),
        "pause_formatted": _format_pause(round(pause_min, 1)),
        "moving_time_min": round(moving_time, 1),
        "arrival_time_min": round(arrival_time, 1),
        "departure_time_min": round(departure_time, 1),
        "time_min": round(arrival_time, 1),
        "time_formatted": _format_minutes(arrival_time),
        "arrival_time_formatted": _format_minutes(arrival_time),
        "departure_time_formatted": _format_minutes(departure_time),
        "source": source,
    }


def _manual_ravitos(
    predictions: list[dict],
    custom_ravitos: Optional[str],
    total_distance_km: float,
    *,
    source: str = "manual",
) -> list[dict]:
    if not custom_ravitos:
        return []

    custom_ravitos_data = json.loads(custom_ravitos)
    normalized = []

    for index, ravito in enumerate(custom_ravitos_data):
        distance_km = float(ravito["km"])
        if distance_km <= 0 or distance_km >= total_distance_km:
            continue

        pause_min = max(0.0, float(ravito.get("pause_min", ravito.get("pause", 0)) or 0))
        normalized.append({
            "distance_km": distance_km,
            "name": str(ravito.get("name") or f"Ravito {index + 1}"),
            "pause_min": pause_min,
        })

    unique_by_distance = {}
    for ravito in normalized:
        unique_by_distance[round(ravito["distance_km"], 2)] = ravito

    ravito_points = []
    cumulative_pause = 0.0
    for ravito in sorted(unique_by_distance.values(), key=lambda item: item["distance_km"]):
        point = _ravito_point(
            predictions,
            distance_km=ravito["distance_km"],
            name=ravito["name"],
            pause_min=ravito["pause_min"],
            cumulative_pause_before=cumulative_pause,
            source=source,
        )
        ravito_points.append(point)
        cumulative_pause += ravito["pause_min"]

    return ravito_points


def _auto_ravitos(
    predictions: list[dict],
    global_stats: dict,
    moving_time_min: float,
    *,
    analysis_mode: str,
) -> list[dict]:
    total_distance = float(global_stats["total_distance_km"])
    if total_distance < 8:
        return []

    elevation_gain = float(global_stats["total_elevation_gain_m"])
    elevation_per_km = elevation_gain / total_distance if total_distance > 0 else 0
    moving_hours = moving_time_min / 60
    is_trail = analysis_mode == "trail"

    if is_trail:
        interval = 6.0 if elevation_per_km >= 55 or moving_hours >= 4 else 8.0
        min_pause = 3.0
        max_pause = 10.0
        base_pause = 3.0
    else:
        interval = 8.0 if moving_hours >= 3 else 10.0
        min_pause = 1.0
        max_pause = 5.0
        base_pause = 1.5

    distances = []
    next_distance = interval
    finish_buffer = max(2.0, interval * 0.35)
    while next_distance < total_distance - finish_buffer:
        distances.append(round(next_distance, 1))
        next_distance += interval

    ravito_points = []
    cumulative_pause = 0.0
    for index, distance_km in enumerate(distances):
        progress = distance_km / total_distance
        pause = base_pause
        pause += progress * (2.5 if is_trail else 1.0)
        pause += min(elevation_per_km / (45 if is_trail else 90), 2.0)
        pause += max(0.0, moving_hours - (3.0 if is_trail else 2.5)) * (0.45 if is_trail else 0.25)
        pause = max(min_pause, min(max_pause, pause))
        pause = round(pause * 2) / 2

        point = _ravito_point(
            predictions,
            distance_km=distance_km,
            name=f"Ravito auto {index + 1}",
            pause_min=pause,
            cumulative_pause_before=cumulative_pause,
            source="auto",
        )
        ravito_points.append(point)
        cumulative_pause += pause

    return ravito_points


def _apply_ravito_pauses_to_segments(predictions: list[dict], ravito_points: list[dict]) -> None:
    cumulative_distance = 0.0
    for prediction in predictions:
        cumulative_distance += float(prediction["distance_km"])
        pause_before_end = sum(
            float(ravito["pause_min"])
            for ravito in ravito_points
            if float(ravito["distance_km"]) <= cumulative_distance
        )
        prediction["cumulative_time_min"] = round(
            float(prediction["cumulative_moving_time_min"]) + pause_before_end,
            1,
        )


def _normalize_stream(raw: Any) -> Optional[dict]:
    if raw is None:
        return None
    if isinstance(raw, str):
        if raw.strip().lower() == "null":
            return None
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw if isinstance(raw, dict) and raw else None


def _stream_array(streams: dict, key: str) -> list:
    value = streams.get(key)
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    return value if isinstance(value, list) else []


def _time_at_distance(distance_m: list[float], time_s: list[float], target_m: float) -> Optional[float]:
    if not distance_m or not time_s:
        return None

    limit = min(len(distance_m), len(time_s))
    if limit < 2:
        return None

    if target_m <= float(distance_m[0] or 0):
        return float(time_s[0] or 0)

    for index in range(1, limit):
        previous_distance = float(distance_m[index - 1] or 0)
        current_distance = float(distance_m[index] or 0)
        previous_time = float(time_s[index - 1] or 0)
        current_time = float(time_s[index] or 0)

        if current_distance >= target_m and current_distance > previous_distance:
            ratio = (target_m - previous_distance) / (current_distance - previous_distance)
            return previous_time + ratio * (current_time - previous_time)

    return float(time_s[limit - 1] or 0)


def _compare_prediction_to_activity(prediction: RacePrediction, activity: Activity) -> dict:
    streams = _normalize_stream(activity.streams_data)
    if not streams:
        raise ValueError("Activite sans streams detailles")

    distance_stream = [float(value or 0) for value in _stream_array(streams, "distance")]
    time_stream = [float(value or 0) for value in _stream_array(streams, "time")]
    altitude_stream = [float(value or 0) for value in _stream_array(streams, "altitude")]
    heartrate_stream = [float(value or 0) for value in _stream_array(streams, "heartrate")]

    if len(distance_stream) < 2 or len(time_stream) < 2:
        raise ValueError("Activite sans streams distance/time exploitables")

    prediction_data = prediction.prediction_data or {}
    predicted_segments = prediction_data.get("segments") or []
    ravitos = prediction_data.get("ravito_points") or []
    if not predicted_segments:
        raise ValueError("Prediction sans segments")

    actual_distance_km = max(distance_stream) / 1000 if distance_stream else 0
    predicted_distance_km = float(prediction.total_distance_km or prediction_data.get("total_distance_km") or 0)
    comparable_distance_km = min(actual_distance_km, predicted_distance_km)

    comparisons = []
    previous_distance_km = 0.0
    previous_actual_time_min = 0.0
    previous_pred_total_min = 0.0
    previous_pred_moving_min = 0.0

    for segment in predicted_segments:
        segment_distance_km = float(segment.get("distance_km") or 0)
        if segment_distance_km <= 0:
            continue

        target_distance_km = previous_distance_km + segment_distance_km
        if target_distance_km > comparable_distance_km + 0.05:
            break

        actual_time_s = _time_at_distance(distance_stream, time_stream, target_distance_km * 1000)
        if actual_time_s is None:
            break

        actual_cumulative_min = actual_time_s / 60
        actual_segment_min = max(0.0, actual_cumulative_min - previous_actual_time_min)
        predicted_total_cumulative = float(segment.get("cumulative_time_min") or 0)
        predicted_moving_cumulative = float(segment.get("cumulative_moving_time_min") or predicted_total_cumulative)
        predicted_total_segment = max(0.0, predicted_total_cumulative - previous_pred_total_min)
        predicted_moving_segment = max(0.0, predicted_moving_cumulative - previous_pred_moving_min)

        segment_diff = predicted_total_segment - actual_segment_min
        cumulative_diff = predicted_total_cumulative - actual_cumulative_min

        comparisons.append({
            "segment_id": segment.get("segment_id") or len(comparisons) + 1,
            "from_km": round(previous_distance_km, 2),
            "to_km": round(target_distance_km, 2),
            "distance_km": round(segment_distance_km, 2),
            "predicted_segment_min": round(predicted_total_segment, 2),
            "predicted_moving_segment_min": round(predicted_moving_segment, 2),
            "actual_segment_min": round(actual_segment_min, 2),
            "segment_delta_min": round(segment_diff, 2),
            "predicted_cumulative_min": round(predicted_total_cumulative, 2),
            "actual_cumulative_min": round(actual_cumulative_min, 2),
            "cumulative_delta_min": round(cumulative_diff, 2),
            "predicted_pace_min_km": round(predicted_total_segment / segment_distance_km, 2) if segment_distance_km > 0 else None,
            "actual_pace_min_km": round(actual_segment_min / segment_distance_km, 2) if segment_distance_km > 0 else None,
            "elevation_gain_m": segment.get("elevation_gain_m"),
            "elevation_loss_m": segment.get("elevation_loss_m"),
            "avg_grade_percent": segment.get("avg_grade_percent"),
        })

        previous_distance_km = target_distance_km
        previous_actual_time_min = actual_cumulative_min
        previous_pred_total_min = predicted_total_cumulative
        previous_pred_moving_min = predicted_moving_cumulative

    if not comparisons:
        raise ValueError("Aucun segment comparable entre la prediction et l'activite")

    actual_elapsed_time_min = (max(time_stream) / 60) if time_stream else (activity.elapsed_time or 0) / 60
    actual_moving_time_min = (activity.moving_time or 0) / 60
    predicted_total_min = float(prediction.total_time_min or prediction_data.get("total_time_min") or 0)
    predicted_moving_min = float(prediction.moving_time_min or prediction_data.get("moving_time_min") or 0)
    predicted_pause_min = max(0.0, predicted_total_min - predicted_moving_min)
    actual_pause_min = max(0.0, actual_elapsed_time_min - actual_moving_time_min)

    segment_deltas = [item["segment_delta_min"] for item in comparisons]
    abs_segment_deltas = [abs(delta) for delta in segment_deltas]
    worst_segment = max(comparisons, key=lambda item: abs(item["segment_delta_min"]))

    ravito_comparisons = []
    for ravito in ravitos:
        ravito_distance_km = float(ravito.get("distance_km") or 0)
        if ravito_distance_km <= 0 or ravito_distance_km > actual_distance_km:
            continue
        actual_time_s = _time_at_distance(distance_stream, time_stream, ravito_distance_km * 1000)
        if actual_time_s is None:
            continue
        actual_arrival_min = actual_time_s / 60
        predicted_arrival_min = float(ravito.get("arrival_time_min") or ravito.get("time_min") or 0)
        ravito_comparisons.append({
            "name": ravito.get("name"),
            "distance_km": round(ravito_distance_km, 2),
            "predicted_arrival_min": round(predicted_arrival_min, 2),
            "actual_arrival_min": round(actual_arrival_min, 2),
            "arrival_delta_min": round(predicted_arrival_min - actual_arrival_min, 2),
            "planned_pause_min": ravito.get("pause_min"),
            "predicted_departure_min": ravito.get("departure_time_min"),
        })

    return {
        "prediction": _prediction_to_dict(prediction),
        "activity": {
            "id": str(activity.id),
            "name": activity.name,
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
            "type": (activity.activity_type_override or activity.activity_type).value if (activity.activity_type_override or activity.activity_type) else None,
            "distance_km": round((activity.distance or 0) / 1000, 2),
            "moving_time_min": round(actual_moving_time_min, 2),
            "elapsed_time_min": round(actual_elapsed_time_min, 2),
            "elevation_gain_m": activity.total_elevation_gain,
        },
        "summary": {
            "predicted_distance_km": round(predicted_distance_km, 2),
            "actual_distance_km": round(actual_distance_km, 2),
            "comparable_distance_km": round(comparable_distance_km, 2),
            "predicted_moving_time_min": round(predicted_moving_min, 2),
            "predicted_total_time_min": round(predicted_total_min, 2),
            "predicted_pause_time_min": round(predicted_pause_min, 2),
            "actual_moving_time_min": round(actual_moving_time_min, 2),
            "actual_elapsed_time_min": round(actual_elapsed_time_min, 2),
            "actual_pause_time_min": round(actual_pause_min, 2),
            "total_delta_min": round(predicted_total_min - actual_elapsed_time_min, 2),
            "moving_delta_min": round(predicted_moving_min - actual_moving_time_min, 2),
            "pause_delta_min": round(predicted_pause_min - actual_pause_min, 2),
            "avg_abs_segment_delta_min": round(sum(abs_segment_deltas) / len(abs_segment_deltas), 2),
            "avg_segment_delta_min": round(sum(segment_deltas) / len(segment_deltas), 2),
            "segments_compared": len(comparisons),
            "worst_segment": worst_segment,
            "has_heartrate": bool(heartrate_stream),
            "has_altitude": bool(altitude_stream),
        },
        "segments": comparisons,
        "ravitos": ravito_comparisons,
    }


def _get_prediction_for_user(
    session: Session,
    user_id: UUID,
    prediction_id: UUID,
) -> Optional[RacePrediction]:
    return session.exec(
        select(RacePrediction).where(
            RacePrediction.id == prediction_id,
            RacePrediction.user_id == user_id,
        )
    ).first()


def _get_activity_for_user(
    session: Session,
    user_id: UUID,
    activity_id: str,
) -> Optional[Activity]:
    try:
        activity_uuid = UUID(str(activity_id))
        activity = session.exec(
            select(Activity).where(
                Activity.id == activity_uuid,
                Activity.user_id == user_id,
                Activity.source == ActivitySource.GARMIN.value,
            )
        ).first()
        if activity:
            return activity
    except ValueError:
        pass

    try:
        provider_id = int(activity_id)
    except (TypeError, ValueError):
        return None

    return session.exec(
        select(Activity).where(
            Activity.garmin_activity_id == provider_id,
            Activity.user_id == user_id,
            Activity.source == ActivitySource.GARMIN.value,
        )
    ).first()


@router.post("/prediction/gpx-pace-prediction")
async def predict_pace_from_gpx(
    file: Optional[UploadFile] = File(None),
    route_id: Optional[str] = Form(None, description="Identifiant d'une trace deja enregistree"),
    custom_ravitos: Optional[str] = Form(None, description="Ravitos personnalises en JSON"),
    target_heartrate: Optional[float] = Form(None, description="FC cible optionnelle"),
    history_start_date: Optional[str] = Form(None, description="Date de debut de l'historique Race Predictor"),
    analysis_mode: Optional[str] = Form("trail", description="Mode d'analyse: route ou trail"),
    ravito_mode: Optional[str] = Form("auto", description="Mode ravito: auto ou manual"),
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Predit l'allure optimale a partir d'un fichier GPX OU d'une route enregistree."""
    user_id = UUID(get_current_user_id(token.credentials))
    model_path = _model_path()
    if not model_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Modele de prediction non disponible",
        )

    gpx_text, gpx_filename = await _resolve_gpx_input(file, route_id, session, user_id)

    resolved_history_start_date = _resolve_history_start_date(history_start_date)
    try:
        resolved_analysis_mode = _normalize_analysis_mode(analysis_mode)
        resolved_ravito_mode = _normalize_ravito_mode(ravito_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    is_trail_mode = resolved_analysis_mode == "trail"

    try:
        segments, elevation_points = parse_gpx_file(gpx_text)
        global_stats = calculate_global_stats(segments)

        logger.info("Statistiques GPX pour %s", gpx_filename)
        logger.info("Distance totale: %s km", global_stats["total_distance_km"])
        logger.info("D+ total: +%s m", global_stats["total_elevation_gain_m"])
        logger.info("D- total: -%s m", global_stats["total_elevation_loss_m"])
        logger.info("Segments: %s", len(segments))

        historical_heartrate, historical_activity_count = _historical_heart_rate_stats(
            session,
            user_id,
            is_trail=is_trail_mode,
            history_start_date=resolved_history_start_date,
            target_heartrate=target_heartrate,
        )

        for segment in segments:
            segment["is_trail"] = 1 if is_trail_mode else 0
            segment["avg_heartrate"] = historical_heartrate
    except Exception as exc:
        logger.error("Erreur parsing GPX: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur parsing GPX: {exc}",
        ) from exc

    try:
        model_data = joblib.load(model_path)
        model = model_data["model"]
        scaler = model_data["scaler"]

        predictions = []
        moving_time = 0.0

        for index, segment in enumerate(segments):
            features = [
                segment["distance_km"],
                segment["elevation_gain_m"],
                segment["elevation_loss_m"],
                segment["elevation_gain_m"] - segment["elevation_loss_m"],
                (segment["elevation_gain_m"] - segment["elevation_loss_m"]) / segment["distance_km"],
                segment["avg_grade_percent"],
                segment["is_trail"],
                segment["avg_heartrate"],
            ]

            x = np.array(features).reshape(1, -1)
            predicted_pace = float(model.predict(scaler.transform(x))[0])
            segment_time = predicted_pace * segment["distance_km"]
            moving_time += segment_time

            predictions.append({
                "segment_id": index + 1,
                "distance_km": segment["distance_km"],
                "elevation_gain_m": segment["elevation_gain_m"],
                "elevation_loss_m": segment["elevation_loss_m"],
                "avg_grade_percent": segment["avg_grade_percent"],
                "predicted_pace": round(predicted_pace, 2),
                "predicted_time_min": round(segment_time, 1),
                "cumulative_moving_time_min": round(moving_time, 1),
                "cumulative_time_min": round(moving_time, 1),
            })

        total_distance = global_stats["total_distance_km"]
        try:
            if resolved_ravito_mode == "manual":
                ravito_points = _manual_ravitos(predictions, custom_ravitos, total_distance)
            else:
                ravito_points = []
                if custom_ravitos:
                    try:
                        ravito_points = _manual_ravitos(
                            predictions,
                            custom_ravitos,
                            total_distance,
                            source="auto_known",
                        )
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        ravito_points = []
                if not ravito_points:
                    ravito_points = _auto_ravitos(
                        predictions,
                        global_stats,
                        moving_time,
                        analysis_mode=resolved_analysis_mode,
                    )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            ravito_points = []

        total_pause = sum(float(ravito["pause_min"]) for ravito in ravito_points)
        total_time = moving_time + total_pause
        _apply_ravito_pauses_to_segments(predictions, ravito_points)
        saved_ravito_config = _ravito_config_from_points(ravito_points)

        return {
            "engine_version": "v1_random_forest",
            "filename": gpx_filename,
            "analysis_mode": resolved_analysis_mode,
            "ravito_mode": resolved_ravito_mode,
            "history_start_date": resolved_history_start_date.isoformat(),
            "historical_avg_heartrate": historical_heartrate,
            "historical_activity_count": historical_activity_count,
            "total_distance_km": total_distance,
            "total_elevation_gain_m": global_stats["total_elevation_gain_m"],
            "total_elevation_loss_m": global_stats["total_elevation_loss_m"],
            "net_elevation_m": global_stats["net_elevation_m"],
            "avg_grade_percent": global_stats["avg_grade_percent"],
            "moving_time_min": round(moving_time, 1),
            "moving_time_formatted": _format_minutes(moving_time),
            "total_pause_min": round(total_pause, 1),
            "total_pause_formatted": _format_pause(round(total_pause, 1)),
            "total_time_min": round(total_time, 1),
            "total_time_formatted": _format_minutes(total_time),
            "avg_moving_pace": round(moving_time / total_distance, 2) if total_distance > 0 else 0,
            "avg_pace": round(total_time / total_distance, 2) if total_distance > 0 else 0,
            "segments": predictions,
            "elevation_points": elevation_points,
            "ravito_points": ravito_points,
            "custom_ravitos": saved_ravito_config if resolved_ravito_mode == "manual" else [],
            "ravito_config": saved_ravito_config,
            "prediction_date": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erreur prediction GPX: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur prediction: {exc}",
        ) from exc


@router.post("/prediction/v2/gpx")
async def predict_v2_from_gpx(
    file: Optional[UploadFile] = File(None),
    route_id: Optional[str] = Form(None, description="Identifiant d'une trace deja enregistree"),
    custom_ravitos: Optional[str] = Form(None, description="Ravitos personnalises en JSON"),
    target_heartrate: Optional[float] = Form(None, description="FC cible optionnelle"),
    history_start_date: Optional[str] = Form(None, description="Date de debut de l'historique Race Predictor"),
    analysis_mode: Optional[str] = Form("auto", description="Mode d'analyse: auto, route ou trail"),
    effort_mode: Optional[str] = Form("steady", description="Effort cible"),
    ravito_mode: Optional[str] = Form("auto", description="Mode ravito: auto ou manual"),
    race_datetime: Optional[str] = Form(None, description="Date/heure de course"),
    weather_mode: Optional[str] = Form("auto", description="Mode meteo: auto ou manual"),
    temperature_c: Optional[float] = Form(None, description="Temperature manuelle"),
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Prediction GPX V2 basee sur un moteur physique explicable."""
    user_id = UUID(get_current_user_id(token.credentials))
    gpx_text, gpx_filename = await _resolve_gpx_input(file, route_id, session, user_id)

    race_date = _parse_optional_datetime(race_datetime)
    calibration_end_date = race_date if race_date and race_date < datetime.utcnow() else None
    resolved_history_start_date = _resolve_history_start_date(
        history_start_date,
        reference_date=calibration_end_date,
    )
    custom_ravitos_data = _parse_custom_ravitos_json(custom_ravitos)

    try:
        requested_analysis_mode = _normalize_v2_analysis_mode(analysis_mode)
        resolved_effort_mode = _normalize_effort_mode(effort_mode)
        resolved_ravito_mode = _normalize_ravito_mode(ravito_mode)
        resolved_weather_mode = _normalize_weather_mode(weather_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    warnings: list[str] = []
    try:
        gpx_analysis = analyze_gpx(gpx_text, custom_ravitos=custom_ravitos_data)
        global_stats = gpx_analysis["global_stats"]
        elevation_per_km = float(global_stats.get("elevation_per_km") or 0)
        resolved_analysis_mode = (
            "trail"
            if requested_analysis_mode == "auto" and elevation_per_km >= 15
            else "route"
            if requested_analysis_mode == "auto"
            else requested_analysis_mode
        )
        if requested_analysis_mode == "auto":
            warnings.append(f"Mode auto resolu en {resolved_analysis_mode} via D+/km={elevation_per_km:.1f}.")
        if resolved_analysis_mode == "trail":
            warnings.append("Facteur terrain trail empirique x1.20 applique; calibration surface personnelle non validee.")

        calibration = build_calibration(
            session,
            user_id,
            history_start_date=resolved_history_start_date,
            history_end_date=calibration_end_date,
            target_heartrate=target_heartrate,
        )
        if calibration.get("calibration_quality") == "low":
            warnings.append("Calibration personnelle faible: fallback utilise faute de segments route plats suffisants.")

        fatigue_profile = build_fatigue_profile(
            session,
            user_id,
            history_start_date=resolved_history_start_date,
            history_end_date=calibration_end_date,
            p_run_wkg=float(calibration.get("p_run_wkg") or 9.5),
        )

        environment = build_environment(
            global_stats,
            race_datetime=race_date,
            weather_mode=resolved_weather_mode,
            manual_temperature_c=temperature_c,
            p_run_wkg=float(calibration.get("p_run_wkg") or 9.5),
        )
        if environment.get("weather_source") in {"default", "auto_failed"}:
            warnings.append("Meteo automatique indisponible: temperature neutre ou manuelle utilisee.")

        physics_result = predict_segments(
            gpx_analysis["segments"],
            calibration=calibration,
            environment=environment,
            fatigue_profile=fatigue_profile,
            analysis_mode=resolved_analysis_mode,
            effort_mode=resolved_effort_mode,
        )
        predicted_segments = physics_result["segments"]
        moving_time = float(physics_result["moving_time_min"])
        environment = summarize_weather_exposure(environment, moving_time)

        total_distance = float(global_stats["total_distance_km"])
        if resolved_ravito_mode == "manual":
            ravito_points = manual_v2_ravitos(
                predicted_segments,
                custom_ravitos_data,
                total_distance,
            )
        else:
            ravito_points = (
                manual_v2_ravitos(
                    predicted_segments,
                    custom_ravitos_data,
                    total_distance,
                    source="auto_known",
                )
                if custom_ravitos_data
                else []
            )
            if not ravito_points:
                ravito_points = auto_v2_ravitos(
                    predicted_segments,
                    global_stats,
                    moving_time,
                    analysis_mode=resolved_analysis_mode,
                    temperature_c=float(environment.get("temperature_max_c") or environment.get("temperature_c") or 11.0),
                )
        total_pause = sum(float(ravito.get("pause_min") or 0) for ravito in ravito_points)
        total_time = moving_time + total_pause
        apply_v2_pauses_to_segments(predicted_segments, ravito_points)

        uncertainty = monte_carlo_uncertainty(
            segments=predicted_segments,
            moving_time_min=moving_time,
            total_pause_min=total_pause,
            calibration=calibration,
            environment=environment,
            simulations=300,
        )

        avg_moving_pace = moving_time / total_distance if total_distance > 0 else 0
        avg_pace = total_time / total_distance if total_distance > 0 else 0
        saved_ravito_config = v2_ravito_config_from_points(ravito_points)
        summary = {
            "total_distance_km": total_distance,
            "total_elevation_gain_m": global_stats["total_elevation_gain_m"],
            "total_elevation_loss_m": global_stats["total_elevation_loss_m"],
            "moving_time_min": round(moving_time, 1),
            "moving_time_formatted": _format_minutes(moving_time),
            "total_pause_min": round(total_pause, 1),
            "total_pause_formatted": _format_pause(round(total_pause, 1)),
            "total_time_min": round(total_time, 1),
            "total_time_formatted": _format_minutes(total_time),
            "p10_total_time_min": uncertainty["total_time"]["p10"],
            "p50_total_time_min": uncertainty["total_time"]["p50"],
            "p90_total_time_min": uncertainty["total_time"]["p90"],
            "avg_moving_pace": round(avg_moving_pace, 2),
            "avg_pace": round(avg_pace, 2),
        }

        debug_trace = {
            "engine_version": "v2_physics",
            "requested_analysis_mode": requested_analysis_mode,
            "resolved_analysis_mode": resolved_analysis_mode,
            "effort_mode": resolved_effort_mode,
            "physics": physics_result["physics"],
            "gpx_cleaning": {
                "elevation_noise_threshold_m": ELEVATION_NOISE_THRESHOLD_M,
                "segment_count": len(predicted_segments),
                "adaptive_segment_min_m": 200,
                "adaptive_segment_max_m": 1000,
            },
            "calibration": calibration,
            "environment": environment,
            "fatigue": fatigue_profile,
            "weather_integration": "segment_sequential_interpolation" if environment.get("weather_timeline_enabled") else "static",
        }

        return {
            "engine_version": "v2_physics",
            "filename": gpx_filename,
            "analysis_mode": resolved_analysis_mode,
            "requested_analysis_mode": requested_analysis_mode,
            "effort_mode": resolved_effort_mode,
            "ravito_mode": resolved_ravito_mode,
            "history_start_date": resolved_history_start_date.isoformat(),
            "race_datetime": race_date.isoformat() if race_date else None,
            "total_distance_km": total_distance,
            "total_elevation_gain_m": global_stats["total_elevation_gain_m"],
            "total_elevation_loss_m": global_stats["total_elevation_loss_m"],
            "net_elevation_m": global_stats["net_elevation_m"],
            "avg_grade_percent": global_stats["avg_grade_percent"],
            "moving_time_min": summary["moving_time_min"],
            "moving_time_formatted": summary["moving_time_formatted"],
            "total_pause_min": summary["total_pause_min"],
            "total_pause_formatted": summary["total_pause_formatted"],
            "total_time_min": summary["total_time_min"],
            "total_time_formatted": summary["total_time_formatted"],
            "avg_moving_pace": summary["avg_moving_pace"],
            "avg_pace": summary["avg_pace"],
            "summary": summary,
            "calibration": calibration,
            "environment": environment,
            "fatigue": fatigue_profile,
            "ravitos": {
                "mode": resolved_ravito_mode,
                "points": ravito_points,
                "total_pause_min": round(total_pause, 1),
            },
            "ravito_points": ravito_points,
            "custom_ravitos": custom_ravitos_data if resolved_ravito_mode == "manual" else [],
            "ravito_config": saved_ravito_config,
            "segments": predicted_segments,
            "elevation_points": gpx_analysis["elevation_points"],
            "uncertainty": uncertainty,
            "warnings": warnings,
            "debug_trace": debug_trace,
            "prediction_date": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erreur prediction GPX V2: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur prediction V2: {exc}",
        ) from exc


@router.get("/prediction/saved")
async def list_saved_predictions(
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Liste les predictions GPX sauvegardees de l'utilisateur."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    predictions = session.exec(
        select(RacePrediction)
        .where(RacePrediction.user_id == user_id)
        .order_by(RacePrediction.created_at.desc())
    ).all()
    return {"items": [_prediction_to_dict(prediction) for prediction in predictions]}


@router.post("/prediction/saved")
async def save_prediction(
    payload: SaveRacePredictionRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Sauvegarde une prediction GPX pour comparaison future."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    prediction_data = payload.prediction or {}
    segments = prediction_data.get("segments") or []
    if not segments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prediction sans segments")
    engine_version = prediction_data.get("engine_version") or "v1_random_forest"
    prediction_data["engine_version"] = engine_version
    if "ravito_config" not in prediction_data:
        prediction_data["ravito_config"] = _ravito_config_from_points(prediction_data.get("ravito_points") or [])
    if prediction_data.get("ravito_mode") == "manual" and "custom_ravitos" not in prediction_data:
        prediction_data["custom_ravitos"] = prediction_data["ravito_config"]

    now = datetime.utcnow()
    name = payload.name.strip() or prediction_data.get("filename") or "Prediction GPX"
    prediction = RacePrediction(
        user_id=user_id,
        name=name[:180],
        filename=prediction_data.get("filename"),
        engine_version=engine_version,
        analysis_mode=prediction_data.get("analysis_mode") or "trail",
        ravito_mode=prediction_data.get("ravito_mode") or "auto",
        history_start_date=_parse_optional_datetime(payload.history_start_date or prediction_data.get("history_start_date")),
        total_distance_km=prediction_data.get("total_distance_km"),
        total_elevation_gain_m=prediction_data.get("total_elevation_gain_m"),
        moving_time_min=prediction_data.get("moving_time_min"),
        total_pause_min=prediction_data.get("total_pause_min"),
        total_time_min=prediction_data.get("total_time_min"),
        avg_pace=prediction_data.get("avg_pace"),
        prediction_data=prediction_data,
        created_at=now,
        updated_at=now,
    )
    session.add(prediction)
    session.commit()
    session.refresh(prediction)
    return _prediction_to_dict(prediction)


@router.delete("/prediction/saved/{prediction_id}")
async def delete_saved_prediction(
    prediction_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Supprime une prediction GPX sauvegardee."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    prediction = session.exec(
        select(RacePrediction).where(
            RacePrediction.id == prediction_id,
            RacePrediction.user_id == user_id,
        )
    ).first()
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction introuvable")

    linked_comparisons = session.exec(
        select(RacePredictionComparison).where(
            RacePredictionComparison.user_id == user_id,
            RacePredictionComparison.prediction_id == prediction_id,
        )
    ).all()
    for comparison in linked_comparisons:
        session.delete(comparison)

    session.delete(prediction)
    session.commit()
    return {"deleted": True, "id": str(prediction_id)}


@router.get("/prediction/comparisons")
async def list_saved_comparisons(
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Liste les comparaisons Race Predictor sauvegardees de l'utilisateur."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    comparisons = session.exec(
        select(RacePredictionComparison)
        .where(RacePredictionComparison.user_id == user_id)
        .order_by(RacePredictionComparison.updated_at.desc())
    ).all()
    return {"items": [_comparison_to_dict(comparison) for comparison in comparisons]}


@router.get("/prediction/references")
async def list_validation_references(
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Liste les activités qualifiées pour évaluer le Race Predictor."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    references = session.exec(
        select(RaceValidationReference)
        .where(RaceValidationReference.user_id == user_id)
        .order_by(RaceValidationReference.updated_at.desc())
    ).all()
    return {"items": [_reference_to_dict(reference) for reference in references]}


@router.get("/prediction/reference-candidates")
async def list_reference_candidates(
    status_filter: Optional[str] = None,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Liste les candidats automatiques de references de course."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    statement = select(RaceReferenceCandidate).where(
        RaceReferenceCandidate.user_id == user_id
    )
    if status_filter:
        statement = statement.where(RaceReferenceCandidate.status == status_filter)
    candidates = session.exec(
        statement.order_by(
            RaceReferenceCandidate.status.asc(),
            RaceReferenceCandidate.score.desc(),
            RaceReferenceCandidate.updated_at.desc(),
        )
    ).all()
    return {
        "items": [
            _candidate_with_activity_to_dict(session, candidate)
            for candidate in candidates
        ]
    }


@router.post("/prediction/reference-candidates/detect")
async def detect_validation_reference_candidates(
    payload: DetectReferenceCandidatesRequest = DetectReferenceCandidatesRequest(),
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Detecte automatiquement les activites candidates aux references."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    history_start = (
        _resolve_history_start_date(payload.history_start_date)
        if payload.history_start_date
        else None
    )
    candidates = detect_reference_candidates(
        session,
        user_id,
        history_start_date=history_start,
        limit=max(20, min(500, int(payload.limit or 200))),
        force=bool(payload.force),
    )
    return {
        "items": [
            _candidate_with_activity_to_dict(session, candidate)
            for candidate in candidates
        ],
        "detected_count": len(candidates),
    }


@router.put("/prediction/reference-candidates/{candidate_id}/resolve")
async def resolve_reference_candidate(
    candidate_id: UUID,
    payload: ResolveReferenceCandidateRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Valide ou rejette un candidat automatique."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    candidate = session.exec(
        select(RaceReferenceCandidate).where(
            RaceReferenceCandidate.id == candidate_id,
            RaceReferenceCandidate.user_id == user_id,
        )
    ).first()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidat introuvable")

    action = (payload.action or "").strip().lower()
    if action not in {"accept", "reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action candidate invalide")

    now = datetime.utcnow()
    if action == "reject":
        candidate.status = "rejected"
        candidate.notes = payload.notes.strip() if payload.notes else candidate.notes
        candidate.updated_at = now
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        return _candidate_with_activity_to_dict(session, candidate)

    category = payload.category or candidate.suggested_category
    if category not in REFERENCE_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Categorie de reference invalide")
    if (
        payload.potential_gain_min_low is not None
        and payload.potential_gain_min_high is not None
        and payload.potential_gain_min_low > payload.potential_gain_min_high
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Intervalle de gain potentiel invalide")

    activity = _get_activity_for_user(session, user_id, str(candidate.activity_id))
    if activity is None or activity.id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activite introuvable")

    reference = session.exec(
        select(RaceValidationReference).where(
            RaceValidationReference.user_id == user_id,
            RaceValidationReference.activity_id == activity.id,
        )
    ).first()
    notes = payload.notes.strip() if payload.notes else candidate.notes
    potential_low = (
        payload.potential_gain_min_low
        if payload.potential_gain_min_low is not None
        else candidate.potential_gain_min_low
    )
    potential_high = (
        payload.potential_gain_min_high
        if payload.potential_gain_min_high is not None
        else candidate.potential_gain_min_high
    )
    if reference:
        reference.category = category
        reference.notes = notes
        reference.potential_gain_min_low = potential_low
        reference.potential_gain_min_high = potential_high
        reference.updated_at = now
    else:
        reference = RaceValidationReference(
            user_id=user_id,
            activity_id=activity.id,
            category=category,
            notes=notes,
            potential_gain_min_low=potential_low,
            potential_gain_min_high=potential_high,
            created_at=now,
            updated_at=now,
        )
        session.add(reference)

    candidate.status = "accepted"
    candidate.suggested_category = category
    candidate.notes = notes
    candidate.potential_gain_min_low = potential_low
    candidate.potential_gain_min_high = potential_high
    candidate.updated_at = now
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return {
        **_candidate_with_activity_to_dict(session, candidate),
        "reference": _reference_to_dict(reference),
    }


@router.put("/prediction/references/{activity_id}")
async def save_validation_reference(
    activity_id: str,
    payload: SaveRaceValidationReferenceRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Crée ou actualise la qualification d'une activité de validation."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    activity = _get_activity_for_user(session, user_id, activity_id)
    if not activity or activity.id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activite introuvable")
    if payload.category not in REFERENCE_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Categorie de reference invalide")
    if (
        payload.potential_gain_min_low is not None
        and payload.potential_gain_min_high is not None
        and payload.potential_gain_min_low > payload.potential_gain_min_high
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Intervalle de gain potentiel invalide")

    now = datetime.utcnow()
    reference = session.exec(
        select(RaceValidationReference).where(
            RaceValidationReference.user_id == user_id,
            RaceValidationReference.activity_id == activity.id,
        )
    ).first()
    if reference:
        reference.category = payload.category
        reference.notes = payload.notes.strip() if payload.notes else None
        reference.potential_gain_min_low = payload.potential_gain_min_low
        reference.potential_gain_min_high = payload.potential_gain_min_high
        reference.updated_at = now
    else:
        reference = RaceValidationReference(
            user_id=user_id,
            activity_id=activity.id,
            category=payload.category,
            notes=payload.notes.strip() if payload.notes else None,
            potential_gain_min_low=payload.potential_gain_min_low,
            potential_gain_min_high=payload.potential_gain_min_high,
            created_at=now,
            updated_at=now,
        )
        session.add(reference)

    session.commit()
    session.refresh(reference)
    return _reference_to_dict(reference)


@router.post("/prediction/comparisons")
async def save_prediction_comparison(
    payload: SaveRacePredictionComparisonRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Sauvegarde ou met a jour une comparaison prediction GPX vs activite."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    prediction = _get_prediction_for_user(session, user_id, payload.prediction_id)
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction introuvable")

    activity = _get_activity_for_user(session, user_id, payload.activity_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activite introuvable")

    try:
        comparison_data = _compare_prediction_to_activity(prediction, activity)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    summary = comparison_data.get("summary") or {}
    now = datetime.utcnow()
    default_name = f"{prediction.name} vs {activity.name}"
    name = (payload.name or default_name).strip() or default_name

    comparison = session.exec(
        select(RacePredictionComparison).where(
            RacePredictionComparison.user_id == user_id,
            RacePredictionComparison.prediction_id == prediction.id,
            RacePredictionComparison.activity_id == activity.id,
        )
    ).first()

    if comparison:
        comparison.name = name[:180]
        comparison.comparison_data = comparison_data
        comparison.total_delta_min = summary.get("total_delta_min")
        comparison.moving_delta_min = summary.get("moving_delta_min")
        comparison.pause_delta_min = summary.get("pause_delta_min")
        comparison.avg_abs_segment_delta_min = summary.get("avg_abs_segment_delta_min")
        comparison.comparable_distance_km = summary.get("comparable_distance_km")
        comparison.updated_at = now
    else:
        comparison = RacePredictionComparison(
            user_id=user_id,
            prediction_id=prediction.id,
            activity_id=activity.id,
            name=name[:180],
            comparison_data=comparison_data,
            total_delta_min=summary.get("total_delta_min"),
            moving_delta_min=summary.get("moving_delta_min"),
            pause_delta_min=summary.get("pause_delta_min"),
            avg_abs_segment_delta_min=summary.get("avg_abs_segment_delta_min"),
            comparable_distance_km=summary.get("comparable_distance_km"),
            created_at=now,
            updated_at=now,
        )
        session.add(comparison)

    session.commit()
    session.refresh(comparison)
    return _comparison_to_dict(comparison)


@router.delete("/prediction/comparisons/{comparison_id}")
async def delete_saved_comparison(
    comparison_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Supprime une comparaison Race Predictor sauvegardee."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    comparison = session.exec(
        select(RacePredictionComparison).where(
            RacePredictionComparison.id == comparison_id,
            RacePredictionComparison.user_id == user_id,
        )
    ).first()
    if not comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparaison introuvable")

    session.delete(comparison)
    session.commit()
    return {"deleted": True, "id": str(comparison_id)}


@router.get("/prediction/saved/{prediction_id}/compare/{activity_id}")
async def compare_saved_prediction(
    prediction_id: UUID,
    activity_id: str,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Compare une prediction sauvegardee avec une activite reelle."""
    _ensure_race_prediction_table()
    user_id = UUID(get_current_user_id(token.credentials))
    prediction = _get_prediction_for_user(session, user_id, prediction_id)
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction introuvable")

    activity = _get_activity_for_user(session, user_id, activity_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activite introuvable")

    try:
        return _compare_prediction_to_activity(prediction, activity)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
