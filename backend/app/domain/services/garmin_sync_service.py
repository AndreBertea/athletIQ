"""
Service de sync Garmin — Tache 3.3.1 + 5.1.2 + activites Garmin
Synchronise les donnees physiologiques quotidiennes depuis Garmin Connect via garth.
Inclut le download et parsing de fichiers FIT (Running Dynamics, power, Training Effect).
Inclut la sync des activites Garmin dans la table Activity unifiee.
"""
from __future__ import annotations

import asyncio
import logging
import zipfile
from io import BytesIO
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from urllib.parse import quote
from uuid import UUID

import garth
from sqlalchemy import and_, func
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

if TYPE_CHECKING:
    pass  # garth.Activity used only in annotations

from app.auth.garmin_auth import garmin_auth
from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.entities.activity_weather import ActivityWeather
from app.domain.entities.fit_metrics import FitMetrics
from app.domain.entities.garmin_daily import GarminDaily
from app.domain.entities.user import GarminAuth
from app.domain.services.activity_matching_service import (
    DEDUP_DISTANCE_TOLERANCE_M,
    DEDUP_TIME_TOLERANCE_S,
)
from app.domain.services.derived_features_service import recompute_training_load_from

logger = logging.getLogger(__name__)

REQUEST_DELAY_S = 1.0  # 1s entre chaque date (safe pour Garmin)


def _number(value: Any) -> Optional[float]:
    """Retourne un nombre Garmin utilisable, sinon None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _get_number(payload: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = _number(payload.get(key))
        if value is not None:
            return value
    return None


def _extract_vo2max(payload: Any) -> Optional[float]:
    """Extrait la VO2 max de la reponse maxmet, dont la forme varie selon Garmin."""
    if isinstance(payload, list):
        for entry in reversed(payload):
            value = _extract_vo2max(entry)
            if value is not None:
                return value
        return None
    if not isinstance(payload, dict):
        return None

    value = _get_number(
        payload,
        "vo2MaxPreciseValue",
        "vo2MaxValue",
        "vo2Max",
        "vo_2_max_precise_value",
        "vo_2_max",
    )
    if value is not None:
        return value

    for key in ("running", "generic", "metrics", "maxMet"):
        value = _extract_vo2max(payload.get(key))
        if value is not None:
            return value
    return None


def _extract_race_prediction_times(payload: Any) -> Dict[str, float]:
    """Normalise les formats Garmin Race Predictor en durees exprimees en secondes."""
    result: Dict[str, float] = {}

    if isinstance(payload, dict):
        direct_fields = {
            "race_prediction_5k_seconds": (
                "racePrediction5KTime",
                "racePrediction5kTime",
                "prediction5KTime",
            ),
            "race_prediction_10k_seconds": (
                "racePrediction10KTime",
                "racePrediction10kTime",
                "prediction10KTime",
            ),
            "race_prediction_half_seconds": (
                "racePredictionHalfTime",
                "racePredictionHalfMarathonTime",
                "predictionHalfTime",
            ),
            "race_prediction_marathon_seconds": (
                "racePredictionMarathonTime",
                "predictionMarathonTime",
            ),
        }
        for target, keys in direct_fields.items():
            value = _get_number(payload, *keys)
            if value is not None:
                result[target] = value

        nested = payload.get("racePredictions")
        if nested is not None:
            result.update(_extract_race_prediction_times(nested))

        distance = _get_number(payload, "raceDistance", "distance", "distanceMeters")
        duration = _get_number(
            payload,
            "time",
            "racePredictionTime",
            "predictedTime",
            "timeSeconds",
        )
        if distance is not None and duration is not None:
            if abs(distance - 5000) < 100:
                result["race_prediction_5k_seconds"] = duration
            elif abs(distance - 10000) < 100:
                result["race_prediction_10k_seconds"] = duration
            elif abs(distance - 21097.5) < 200:
                result["race_prediction_half_seconds"] = duration
            elif abs(distance - 42195) < 300:
                result["race_prediction_marathon_seconds"] = duration

    elif isinstance(payload, list):
        for entry in payload:
            result.update(_extract_race_prediction_times(entry))

    return result


def _fetch_current_performance(client: garth.Client) -> Dict[str, Any]:
    """Recupere les indicateurs Garmin courants qui ne sont pas des mesures par jour."""
    data: Dict[str, Any] = {}
    try:
        settings = client.connectapi("/userprofile-service/userprofile/user-settings")
        user_data = settings.get("userData", {}) if isinstance(settings, dict) else {}
        vo2max = _get_number(user_data, "vo2MaxRunning")
        threshold_speed = _get_number(user_data, "lactateThresholdSpeed")
        threshold_hr = _get_number(user_data, "lactateThresholdHeartRate")
        if vo2max is not None:
            data["vo2max_estimated"] = vo2max
        if threshold_speed is not None:
            data["lactate_threshold_speed_mps"] = threshold_speed
        if threshold_hr is not None:
            data["lactate_threshold_hr"] = round(threshold_hr)
    except Exception as e:
        logger.debug(f"Garmin user performance settings: {e}")

    try:
        profile = client.user_profile
        display_name = profile.get("displayName") if isinstance(profile, dict) else None
        if display_name:
            predictions = client.connectapi(
                f"/metrics-service/metrics/racepredictions/latest/{quote(str(display_name), safe='')}"
            )
            data.update(_extract_race_prediction_times(predictions))
    except Exception as e:
        logger.debug(f"Garmin race predictions: {e}")

    return data


async def sync_daily_data(
    session: Session,
    user_id: UUID,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Synchronise les donnees quotidiennes Garmin pour un utilisateur.

    Boucle sur chaque date (aujourd'hui - days_back), appelle les endpoints
    Garmin via garth, upsert dans garmin_daily. Delai 500ms entre dates.

    Returns:
        dict avec days_synced, errors, total_requested
    """
    garmin_auth_record = session.exec(
        select(GarminAuth).where(GarminAuth.user_id == user_id)
    ).first()

    if not garmin_auth_record:
        raise ValueError(f"Aucune authentification Garmin pour user_id={user_id}")

    client = garmin_auth.get_client(garmin_auth_record.oauth_token_encrypted)

    today = date.today()
    current_performance = _fetch_current_performance(client)
    synced = 0
    errors = 0

    for i in range(days_back):
        target_date = today - timedelta(days=i)
        try:
            data = _fetch_day(client, target_date)
            if target_date == today and current_performance:
                data = {**(data or {}), **current_performance}
            if data:
                _upsert(session, user_id, target_date, data)
                synced += 1
        except Exception as e:
            logger.warning(f"Erreur sync Garmin {target_date}: {e}")
            errors += 1

        if i < days_back - 1:
            await asyncio.sleep(REQUEST_DELAY_S)

    garmin_auth_record.last_sync_at = datetime.utcnow()
    session.add(garmin_auth_record)
    session.commit()

    return {
        "days_synced": synced,
        "errors": errors,
        "total_requested": days_back,
        "performance_metrics_synced": bool(current_performance),
    }


def _fetch_day(client: garth.Client, day: date) -> Optional[Dict[str, Any]]:
    """Recupere toutes les donnees Garmin pour une journee."""
    data: Dict[str, Any] = {}
    summary = None  # DailySummary reutilise pour stress, body battery, spo2

    # Training Readiness
    try:
        tr = garth.TrainingReadinessData.get(day, client=client)
        if tr:
            entries = tr if isinstance(tr, list) else [tr]
            morning = next(
                (e for e in entries if getattr(e, "input_context", None) == "AFTER_WAKEUP_RESET"),
                None,
            )
            entry = morning or entries[0]
            data["training_readiness"] = entry.score
    except Exception as e:
        logger.debug(f"TrainingReadiness {day}: {e}")

    # HRV
    try:
        hrv = garth.HRVData.get(day, client=client)
        if hrv and hrv.hrv_summary and hrv.hrv_summary.last_night_avg:
            data["hrv_rmssd"] = hrv.hrv_summary.last_night_avg
    except Exception as e:
        logger.debug(f"HRV {day}: {e}")

    # Sleep
    try:
        sleep = garth.SleepData.get(day, client=client)
        if sleep and sleep.daily_sleep_dto:
            dto = sleep.daily_sleep_dto
            # Score global (existant)
            if dto.sleep_scores:
                data["sleep_score"] = getattr(dto.sleep_scores, "overall", None)
                if data["sleep_score"] and hasattr(data["sleep_score"], "value"):
                    data["sleep_score"] = data["sleep_score"].value
            # Duree totale (existant)
            if dto.sleep_time_seconds:
                data["sleep_duration_min"] = dto.sleep_time_seconds / 60
            # SpO2 (existant)
            if getattr(dto, "average_sp_o2_value", None):
                data["spo2"] = dto.average_sp_o2_value
            # Phases de sommeil
            if dto.deep_sleep_seconds is not None:
                data["deep_sleep_seconds"] = dto.deep_sleep_seconds
            if dto.light_sleep_seconds is not None:
                data["light_sleep_seconds"] = dto.light_sleep_seconds
            if dto.rem_sleep_seconds is not None:
                data["rem_sleep_seconds"] = dto.rem_sleep_seconds
            if dto.awake_sleep_seconds is not None:
                data["awake_sleep_seconds"] = dto.awake_sleep_seconds
            # Heures coucher/reveil
            try:
                data["sleep_start_time"] = dto.sleep_start.strftime("%H:%M")
                data["sleep_end_time"] = dto.sleep_end.strftime("%H:%M")
            except Exception:
                pass
            # Respiration et stress pendant le sommeil
            if getattr(dto, "average_respiration_value", None) is not None:
                data["average_respiration"] = dto.average_respiration_value
            if getattr(dto, "avg_sleep_stress", None) is not None:
                data["avg_sleep_stress"] = dto.avg_sleep_stress
    except Exception as e:
        logger.debug(f"Sleep {day}: {e}")

    # Resting Heart Rate
    try:
        hr = garth.DailyHeartRate.get(day, client=client)
        if hr and hr.resting_heart_rate:
            data["resting_hr"] = hr.resting_heart_rate
    except Exception as e:
        logger.debug(f"RHR {day}: {e}")

    # Stress + Body Battery (via DailySummary pour max/min directs)
    try:
        summary = garth.DailySummary.get(day, client=client)
        if summary:
            if summary.average_stress_level is not None:
                data["stress_score"] = summary.average_stress_level
            if summary.total_steps is not None:
                data["total_steps"] = summary.total_steps
            if summary.total_kilocalories is not None:
                data["total_kilocalories"] = summary.total_kilocalories
            if summary.active_kilocalories is not None:
                data["active_kilocalories"] = summary.active_kilocalories
            if summary.body_battery_highest_value is not None:
                data["body_battery_max"] = summary.body_battery_highest_value
            if summary.body_battery_lowest_value is not None:
                data["body_battery_min"] = summary.body_battery_lowest_value
    except Exception as e:
        logger.debug(f"Stress/BodyBattery {day}: {e}")

    # SpO2 fallback via DailySummary (si pas deja recupere via Sleep)
    if "spo2" not in data and summary and summary.average_spo_2 is not None:
        data["spo2"] = summary.average_spo_2

    # Weight / Body Composition
    try:
        weight = garth.WeightData.get(day, client=client)
        if weight and weight.weight:
            data["weight_kg"] = weight.weight / 1000  # grammes -> kg
    except Exception as e:
        logger.debug(f"Weight {day}: {e}")

    # VO2max
    try:
        max_metrics = client.connectapi(
            f"/metrics-service/metrics/maxmet/daily/{day}/{day}"
        )
        vo2max = _extract_vo2max(max_metrics)
        if vo2max is None:
            scores = garth.GarminScoresData.get(day, client=client)
            vo2max = getattr(scores, "vo_2_max_precise_value", None) if scores else None
        if vo2max is not None:
            data["vo2max_estimated"] = vo2max
    except Exception as e:
        logger.debug(f"VO2max {day}: {e}")

    # Training Status
    try:
        from garth.stats import DailyTrainingStatus

        ts_list = DailyTrainingStatus.list(end=day, period=1, client=client)
        if ts_list:
            ts = ts_list[0]
            if hasattr(ts, "training_status_feedback_phrase") and ts.training_status_feedback_phrase:
                data["training_status"] = str(ts.training_status_feedback_phrase)
            elif hasattr(ts, "training_status") and ts.training_status is not None:
                data["training_status"] = str(ts.training_status)
    except Exception as e:
        logger.debug(f"TrainingStatus {day}: {e}")

    return data if data else None


def _upsert(
    session: Session,
    user_id: UUID,
    day: date,
    data: Dict[str, Any],
) -> None:
    """Upsert dans garmin_daily (user_id + date unique)."""
    existing = session.exec(
        select(GarminDaily).where(
            GarminDaily.user_id == user_id,
            GarminDaily.date == day,
        )
    ).first()

    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        existing.updated_at = datetime.utcnow()
        session.add(existing)
    else:
        record = GarminDaily(user_id=user_id, date=day, **data)
        session.add(record)

    session.commit()


def download_fit_file(client: garth.Client, garmin_activity_id: int) -> Optional[bytes]:
    """
    Telecharge le fichier FIT original d'une activite Garmin.
    Garmin Connect retourne un ZIP contenant le .fit — on extrait le FIT du ZIP.

    Args:
        client: Client garth authentifie
        garmin_activity_id: ID de l'activite sur Garmin Connect

    Returns:
        Contenu du fichier FIT en bytes, ou None si echec
    """
    try:
        raw_bytes = client.download(
            f"/download-service/files/activity/{garmin_activity_id}"
        )
        if not raw_bytes:
            logger.warning(f"FIT file vide pour activite {garmin_activity_id}")
            return None

        logger.info(f"Download activite {garmin_activity_id}: {len(raw_bytes)} bytes")

        # Garmin Connect retourne un ZIP contenant le fichier .fit
        if raw_bytes[:2] == b"PK":
            try:
                with zipfile.ZipFile(BytesIO(raw_bytes)) as zf:
                    fit_names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
                    if not fit_names:
                        logger.warning(f"ZIP pour activite {garmin_activity_id} ne contient aucun .fit: {zf.namelist()}")
                        return None
                    fit_bytes = zf.read(fit_names[0])
                    logger.info(f"FIT extrait du ZIP pour activite {garmin_activity_id}: {fit_names[0]} ({len(fit_bytes)} bytes)")
                    return fit_bytes
            except zipfile.BadZipFile:
                logger.warning(f"Fichier corrompu (ni ZIP ni FIT valide) pour activite {garmin_activity_id}")
                return None

        # Si ce n'est pas un ZIP, c'est peut-etre du FIT brut
        logger.info(f"FIT brut (non-ZIP) pour activite {garmin_activity_id} ({len(raw_bytes)} bytes)")
        return raw_bytes
    except Exception as e:
        logger.warning(f"Echec telechargement FIT pour activite {garmin_activity_id}: {e}")
        return None


def parse_fit_file(fit_bytes: bytes) -> Dict[str, Any]:
    """
    Parse un fichier FIT et extrait TOUTES les metriques session exploitables.

    Extrait depuis les messages 'record' (moyennes calculees) :
    - Running Dynamics : GCT, oscillation verticale, balance, ratio, longueur de foulee
    - Puissance par seconde

    Extrait depuis le message 'session' (valeurs Garmin) :
    - FC, vitesse, cadence, temperature, puissance (avg/max)
    - Training Effect, calories, strides, denivele, distances, temps
    """
    import fitparse

    fitfile = fitparse.FitFile(BytesIO(fit_bytes))

    # Accumulateurs pour moyennes sur les records
    stance_times: List[float] = []
    vertical_oscillations: List[float] = []
    stance_balances: List[float] = []
    stance_time_percents: List[float] = []
    step_lengths: List[float] = []
    vertical_ratios: List[float] = []
    powers: List[float] = []

    for record in fitfile.get_messages("record"):
        val = record.get_value("stance_time")
        if val is not None:
            stance_times.append(float(val))

        val = record.get_value("vertical_oscillation")
        if val is not None:
            vertical_oscillations.append(float(val))

        val = record.get_value("stance_time_balance")
        if val is not None:
            stance_balances.append(float(val))

        val = record.get_value("stance_time_percent")
        if val is not None:
            stance_time_percents.append(float(val))

        val = record.get_value("step_length")
        if val is not None:
            step_lengths.append(float(val))

        val = record.get_value("vertical_ratio")
        if val is not None:
            vertical_ratios.append(float(val))

        val = record.get_value("power")
        if val is not None:
            powers.append(float(val))

    result: Dict[str, Any] = {
        "record_count": len(stance_times) + len(powers),
    }

    # Moyennes calculees depuis les records
    if stance_times:
        result["ground_contact_time_avg"] = round(sum(stance_times) / len(stance_times), 1)
    if vertical_oscillations:
        result["vertical_oscillation_avg"] = round(sum(vertical_oscillations) / len(vertical_oscillations), 2)
    if stance_balances:
        result["stance_time_balance_avg"] = round(sum(stance_balances) / len(stance_balances), 2)
    if stance_time_percents:
        result["stance_time_percent_avg"] = round(sum(stance_time_percents) / len(stance_time_percents), 2)
    if step_lengths:
        result["step_length_avg"] = round(sum(step_lengths) / len(step_lengths), 1)
    if vertical_ratios:
        result["vertical_ratio_avg"] = round(sum(vertical_ratios) / len(vertical_ratios), 2)
    if powers:
        result["power_avg"] = round(sum(powers) / len(powers), 1)

    # Metriques session (valeurs Garmin directes)
    for session_msg in fitfile.get_messages("session"):
        # Training Effect
        v = session_msg.get_value("total_training_effect")
        if v is not None:
            result["aerobic_training_effect"] = round(float(v), 1)
        v = session_msg.get_value("total_anaerobic_training_effect")
        if v is not None:
            result["anaerobic_training_effect"] = round(float(v), 1)

        # FC
        v = session_msg.get_value("avg_heart_rate")
        if v is not None:
            result["heart_rate_avg"] = int(v)
        v = session_msg.get_value("max_heart_rate")
        if v is not None:
            result["heart_rate_max"] = int(v)

        # Vitesse
        v = session_msg.get_value("enhanced_avg_speed")
        if v is not None:
            result["speed_avg"] = round(float(v), 3)
        v = session_msg.get_value("enhanced_max_speed")
        if v is not None:
            result["speed_max"] = round(float(v), 3)

        # Puissance session
        v = session_msg.get_value("avg_power")
        if v is not None and "power_avg" not in result:
            result["power_avg"] = round(float(v), 1)
        v = session_msg.get_value("max_power")
        if v is not None:
            result["power_max"] = round(float(v), 1)
        v = session_msg.get_value("normalized_power")
        if v is not None:
            result["normalized_power"] = round(float(v), 1)

        # Cadence
        v = session_msg.get_value("avg_running_cadence")
        if v is not None:
            result["cadence_avg"] = round(float(v), 1)
        v = session_msg.get_value("max_running_cadence")
        if v is not None:
            result["cadence_max"] = round(float(v), 1)

        # Temperature
        v = session_msg.get_value("avg_temperature")
        if v is not None:
            result["temperature_avg"] = round(float(v), 1)
        v = session_msg.get_value("max_temperature")
        if v is not None:
            result["temperature_max"] = round(float(v), 1)

        # Totaux
        v = session_msg.get_value("total_calories")
        if v is not None:
            result["total_calories"] = int(v)
        v = session_msg.get_value("total_strides")
        if v is not None:
            result["total_strides"] = int(v)
        v = session_msg.get_value("total_ascent")
        if v is not None:
            result["total_ascent"] = int(v)
        v = session_msg.get_value("total_descent")
        if v is not None:
            result["total_descent"] = int(v)
        v = session_msg.get_value("total_distance")
        if v is not None:
            result["total_distance"] = round(float(v), 2)
        v = session_msg.get_value("total_timer_time")
        if v is not None:
            result["total_timer_time"] = round(float(v), 3)
        v = session_msg.get_value("total_elapsed_time")
        if v is not None:
            result["total_elapsed_time"] = round(float(v), 3)

        break  # Une seule session par activite

    return result


# ============================================================
# Mapping des types d'activite Garmin -> ActivityType
# ============================================================

GARMIN_TYPE_MAP: Dict[str, ActivityType] = {
    "running": ActivityType.RUN,
    "trail_running": ActivityType.TRAIL_RUN,
    "treadmill_running": ActivityType.RUN,
    "cycling": ActivityType.RIDE,
    "indoor_cycling": ActivityType.RIDE,
    "mountain_biking": ActivityType.RIDE,
    "gravel_cycling": ActivityType.RIDE,
    "swimming": ActivityType.SWIM,
    "open_water_swimming": ActivityType.SWIM,
    "pool_swimming": ActivityType.SWIM,
    "walking": ActivityType.WALK,
    "hiking": ActivityType.WALK,
}

def _map_garmin_activity(
    garmin_act: garth.Activity,
    user_id: UUID,
) -> Dict[str, Any]:
    """Convertit une activite garth en dict compatible Activity."""
    # Determiner le type
    type_key = None
    if garmin_act.activity_type and hasattr(garmin_act.activity_type, "type_key"):
        type_key = garmin_act.activity_type.type_key
    activity_type = GARMIN_TYPE_MAP.get(type_key, ActivityType.RUN)

    # Distance en metres (garth retourne des metres directement)
    distance = garmin_act.distance or 0.0

    # Durees en secondes (garth retourne des secondes)
    moving_time = int(garmin_act.moving_duration or garmin_act.duration or 0)
    elapsed_time = int(garmin_act.elapsed_duration or garmin_act.duration or 0)

    # Pace en min/km
    average_pace = None
    if distance > 0 and moving_time > 0:
        average_pace = round((moving_time / 60) / (distance / 1000), 2)

    return {
        "user_id": user_id,
        "source": ActivitySource.GARMIN.value,
        "garmin_activity_id": garmin_act.activity_id,
        "name": garmin_act.activity_name or "Garmin Activity",
        "activity_type": activity_type,
        "start_date": garmin_act.start_time_gmt or garmin_act.start_time_local or datetime.utcnow(),
        "start_date_local": garmin_act.start_time_local,
        "distance": distance,
        "moving_time": moving_time,
        "elapsed_time": elapsed_time,
        "total_elevation_gain": garmin_act.elevation_gain or 0.0,
        "average_speed": garmin_act.average_speed,
        "max_speed": garmin_act.max_speed,
        "average_heartrate": garmin_act.average_hr,
        "max_heartrate": garmin_act.max_hr,
        "average_cadence": garmin_act.average_running_cadence_in_steps_per_minute,
        "average_pace": average_pace,
    }


def _deduplicate_activity(
    session: Session,
    user_id: UUID,
    garmin_activity_id: int,
    start_date: datetime,
    distance: float,
    start_date_local: Optional[datetime] = None,
) -> Optional[Activity]:
    """
    Verifie si une activite Garmin existe deja par son identifiant fournisseur.

    Strava est suspendu : aucune ligne Strava existante ne doit etre rattachee
    ni reutilisee pour construire l'historique Garmin.
    """
    return session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.garmin_activity_id == garmin_activity_id,
        )
    ).first()


def _get_garmin_client_for_user(session: Session, user_id: UUID) -> Any:
    garmin_auth_record = session.exec(
        select(GarminAuth).where(GarminAuth.user_id == user_id)
    ).first()

    if not garmin_auth_record:
        raise ValueError(f"Aucune authentification Garmin pour user_id={user_id}")

    return garmin_auth.get_client(garmin_auth_record.oauth_token_encrypted)


def _garmin_activity_start_time(activity: Any) -> Optional[datetime]:
    return activity.start_time_gmt or activity.start_time_local


async def _list_garmin_activities_for_period(client: Any, days_back: int) -> List[Any]:
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    all_activities: List[Any] = []
    start = 0
    page_size = 20

    while True:
        page = garth.Activity.list(limit=page_size, start=start, client=client)
        if not page:
            break

        all_activities.extend(page)
        last_time = _garmin_activity_start_time(page[-1])
        if last_time and last_time < cutoff:
            break

        start += page_size
        await asyncio.sleep(1.0)

    return [
        activity
        for activity in all_activities
        if not _garmin_activity_start_time(activity)
        or _garmin_activity_start_time(activity) >= cutoff
    ]


async def preview_garmin_activity_import(
    session: Session,
    user_id: UUID,
    days_back: int = 30,
) -> Dict[str, Any]:
    """Compte les activites Garmin disponibles sur une periode sans les importer."""
    client = _get_garmin_client_for_user(session, user_id)
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    activities = await _list_garmin_activities_for_period(client, days_back)

    garmin_ids: list[int] = []
    for activity in activities:
        try:
            garmin_ids.append(int(activity.activity_id))
        except (TypeError, ValueError):
            continue

    existing_ids: set[int] = set()
    if garmin_ids:
        existing_ids = {
            int(activity_id)
            for activity_id in session.exec(
                select(Activity.garmin_activity_id).where(
                    Activity.user_id == user_id,
                    Activity.garmin_activity_id.in_(garmin_ids),
                )
            ).all()
            if activity_id is not None
        }

    total = len(garmin_ids)
    existing = len(existing_ids)

    return {
        "days_back": days_back,
        "period_started_at": cutoff.isoformat(),
        "total_activities": total,
        "existing_activities": existing,
        "missing_activities": max(0, total - existing),
    }


async def sync_garmin_activities(
    session: Session,
    user_id: UUID,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Synchronise les activites Garmin dans la table Activity.

    Liste les activites via garth.Activity.list(), dedup par identifiant Garmin,
    et cree des Activity source=GARMIN.

    Returns:
        dict avec created, linked, merged, skipped, errors, total
    """
    client = _get_garmin_client_for_user(session, user_id)

    # Recuperer les activites (garth pagine par start/limit)
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    created = 0
    linked = 0
    merged = 0
    skipped = 0
    errors = 0

    try:
        all_activities = await _list_garmin_activities_for_period(client, days_back)
    except Exception as e:
        logger.error(f"Erreur listing activites Garmin: {e}")
        return {"created": 0, "linked": 0, "merged": 0, "skipped": 0, "errors": 1, "total": 0}

    for garmin_act in all_activities:
        act_time = garmin_act.start_time_gmt or garmin_act.start_time_local
        if act_time and act_time < cutoff:
            continue

        try:
            mapped = _map_garmin_activity(garmin_act, user_id)
            existing = _deduplicate_activity(
                session, user_id, garmin_act.activity_id,
                mapped["start_date"], mapped["distance"], mapped["start_date_local"],
            )

            if existing:
                if existing.start_date_local is None and mapped["start_date_local"]:
                    existing.start_date_local = mapped["start_date_local"]
                    session.add(existing)
                session.commit()
                skipped += 1
            else:
                # Nouvelle activite Garmin
                activity = Activity(**mapped)
                session.add(activity)
                session.commit()
                created += 1

        except Exception as e:
            logger.warning(f"Erreur sync activite Garmin {garmin_act.activity_id}: {e}")
            errors += 1

    # Une sync Garmin est aussi la bascule de provenance des charges derivees :
    # on reconstruit l'historique depuis les seules activites Garmin.
    earliest_garmin_dt = session.exec(
        select(func.min(Activity.start_date)).where(
            Activity.user_id == user_id,
            Activity.source == ActivitySource.GARMIN.value,
        )
    ).one()
    if earliest_garmin_dt:
        try:
            recompute_training_load_from(session, user_id, earliest_garmin_dt.date())
        except Exception as e:
            logger.warning(f"Sync Garmin: recalcul training load echoue: {e}")

    return {
        "created": created,
        "linked": linked,
        "merged": merged,
        "skipped": skipped,
        "errors": errors,
        "total": len(all_activities),
    }


# ============================================================
# FIT file streams extraction + enrichissement
# ============================================================

# Conversion semicircles -> degrees (FIT GPS encoding)
SEMICIRCLE_TO_DEG = 180.0 / (2 ** 31)


def parse_fit_file_streams(fit_bytes: bytes) -> Dict[str, Any]:
    """
    Parse un fichier FIT et extrait TOUS les streams par seconde.

    Format de sortie compatible avec streams_data Strava :
    {
        "time": {"data": [0, 1, 2, ...]},
        "distance": {"data": [0.0, 5.2, ...]},
        "altitude": {"data": [100.0, 101.2, ...]},
        "heartrate": {"data": [120, 125, ...]},
        "cadence": {"data": [85, 86, ...]},
        "latlng": {"data": [[lat, lng], ...]},
        "velocity_smooth": {"data": [1.2, 1.3, ...]},
        "grade_smooth": {"data": [0.0, 1.2, ...]},
        "power": {"data": [300, 310, ...]},
        "temperature": {"data": [19, 20, ...]},
        "stance_time": {"data": [279.0, 280.0, ...]},
        "vertical_oscillation": {"data": [90.5, 91.0, ...]},
        "step_length": {"data": [1010, 1020, ...]},
        "vertical_ratio": {"data": [8.5, 8.6, ...]},
    }
    """
    import fitparse

    fitfile = fitparse.FitFile(BytesIO(fit_bytes))

    times: List[Any] = []
    distances: List[Any] = []
    altitudes: List[Any] = []
    heartrates: List[Any] = []
    cadences: List[Any] = []
    latlngs: List[Any] = []
    speeds: List[Any] = []
    grades: List[Any] = []
    powers: List[Any] = []
    temperatures: List[Any] = []
    stance_times: List[Any] = []
    vertical_oscillations: List[Any] = []
    step_lengths: List[Any] = []
    vertical_ratios: List[Any] = []

    start_timestamp = None

    for record in fitfile.get_messages("record"):
        # Timestamp -> time relative
        ts = record.get_value("timestamp")
        if ts is not None:
            if start_timestamp is None:
                start_timestamp = ts
            elapsed = (ts - start_timestamp).total_seconds()
            times.append(elapsed)
        else:
            times.append(None)

        # Distance cumulative (metres)
        dist = record.get_value("distance")
        distances.append(float(dist) if dist is not None else None)

        # Altitude
        alt = record.get_value("enhanced_altitude") or record.get_value("altitude")
        altitudes.append(float(alt) if alt is not None else None)

        # Heart rate
        hr = record.get_value("heart_rate")
        heartrates.append(int(hr) if hr is not None else None)

        # Cadence (running = steps/min, FIT donne demi-cycles)
        cad = record.get_value("cadence")
        cadences.append(int(cad) if cad is not None else None)

        # GPS : position_lat/position_long en semicircles
        lat_raw = record.get_value("position_lat")
        lng_raw = record.get_value("position_long")
        if lat_raw is not None and lng_raw is not None:
            lat = lat_raw * SEMICIRCLE_TO_DEG
            lng = lng_raw * SEMICIRCLE_TO_DEG
            latlngs.append([lat, lng])
        else:
            latlngs.append(None)

        # Vitesse (m/s)
        spd = record.get_value("enhanced_speed")
        speeds.append(float(spd) if spd is not None else None)

        # Grade (%)
        grade = record.get_value("grade")
        grades.append(float(grade) if grade is not None else None)

        # Puissance (W)
        pwr = record.get_value("power")
        powers.append(int(pwr) if pwr is not None else None)

        # Temperature capteur (°C)
        temp = record.get_value("temperature")
        temperatures.append(int(temp) if temp is not None else None)

        # Running Dynamics par seconde
        st = record.get_value("stance_time")
        stance_times.append(float(st) if st is not None else None)

        vo = record.get_value("vertical_oscillation")
        vertical_oscillations.append(float(vo) if vo is not None else None)

        sl = record.get_value("step_length")
        step_lengths.append(float(sl) if sl is not None else None)

        vr = record.get_value("vertical_ratio")
        vertical_ratios.append(float(vr) if vr is not None else None)

    # Construire le dict streams (n'inclure que les champs avec des donnees)
    streams: Dict[str, Any] = {}
    _candidates = [
        ("time", times),
        ("distance", distances),
        ("altitude", altitudes),
        ("heartrate", heartrates),
        ("cadence", cadences),
        ("latlng", latlngs),
        ("velocity_smooth", speeds),
        ("grade_smooth", grades),
        ("power", powers),
        ("temperature", temperatures),
        ("stance_time", stance_times),
        ("vertical_oscillation", vertical_oscillations),
        ("step_length", step_lengths),
        ("vertical_ratio", vertical_ratios),
    ]
    for key, data in _candidates:
        if any(v is not None for v in data):
            streams[key] = {"data": data}

    return streams


async def enrich_garmin_activity_fit(
    session: Session,
    user_id: UUID,
    activity_id: UUID,
) -> Dict[str, Any]:
    """
    Enrichit une activite Garmin avec son fichier FIT.

    1. Telecharge le FIT
    2. Parse les streams + metriques Running Dynamics
    3. Stocke streams_data dans l'activite
    4. Cree/update FitMetrics
    5. Lance segmentation + meteo

    Returns:
        dict avec status, streams_keys, fit_metrics_stored, segments_created
    """
    activity = session.exec(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == user_id,
        )
    ).first()

    if not activity:
        raise ValueError(f"Activite {activity_id} non trouvee")

    if not activity.garmin_activity_id:
        raise ValueError(f"Activite {activity_id} n'a pas de garmin_activity_id")

    # Recuperer le client Garmin
    garmin_auth_record = session.exec(
        select(GarminAuth).where(GarminAuth.user_id == user_id)
    ).first()
    if not garmin_auth_record:
        raise ValueError(f"Aucune authentification Garmin pour user_id={user_id}")

    client = garmin_auth.get_client(garmin_auth_record.oauth_token_encrypted)

    # 1. Download FIT
    fit_bytes = download_fit_file(client, activity.garmin_activity_id)
    if not fit_bytes:
        return {"status": "fit_download_failed", "activity_id": str(activity_id)}

    # 2. Parse streams
    streams = parse_fit_file_streams(fit_bytes)

    # 3. Parse metriques FIT (Running Dynamics, power, TE)
    fit_data = parse_fit_file(fit_bytes)

    # 4. Fusionner les streams Garmin dans streams_data
    #    - Si streams_data est vide : ecrire tout
    #    - Si streams_data existe deja (Strava) : fusionner les cles
    #      exclusives FIT (stance_time, vertical_oscillation, etc.)
    #    - Harmoniser les doublons : power->watts, temperature->temp
    stored_streams = False

    # Cles exclusives Garmin (Running Dynamics)
    garmin_exclusive_keys = {
        "stance_time", "vertical_oscillation", "step_length",
        "vertical_ratio",
    }
    # Mapping des cles Garmin vers les cles Strava equivalentes
    garmin_to_strava_key = {
        "power": "watts",
        "temperature": "temp",
    }

    if streams:
        # Harmoniser les cles avant fusion : renommer power->watts, temperature->temp
        for garmin_key, strava_key in garmin_to_strava_key.items():
            if garmin_key in streams:
                streams[strava_key] = streams.pop(garmin_key)

        if not activity.streams_data:
            # Pas de streams existants : tout ecrire
            activity.streams_data = streams
            stored_streams = True
        else:
            # Fusionner les cles Garmin exclusives dans les streams existants
            existing = dict(activity.streams_data)
            merged_keys = []
            for key in garmin_exclusive_keys:
                if key in streams and key not in existing:
                    existing[key] = streams[key]
                    merged_keys.append(key)
            # Aussi fusionner watts/temp si absents (activites sans Strava)
            for strava_key in garmin_to_strava_key.values():
                if strava_key in streams and strava_key not in existing:
                    existing[strava_key] = streams[strava_key]
                    merged_keys.append(strava_key)
            if merged_keys:
                activity.streams_data = existing
                stored_streams = True
                logger.info(
                    f"Streams Garmin fusionnes pour activite {activity_id}: {merged_keys}"
                )
        if stored_streams:
            flag_modified(activity, "streams_data")
            activity.updated_at = datetime.utcnow()
            session.add(activity)

    # 5. Cree/update FitMetrics
    existing_fm = session.exec(
        select(FitMetrics).where(FitMetrics.activity_id == activity_id)
    ).first()

    if existing_fm:
        for key, value in fit_data.items():
            if hasattr(existing_fm, key):
                setattr(existing_fm, key, value)
        existing_fm.fit_downloaded_at = datetime.utcnow()
        existing_fm.updated_at = datetime.utcnow()
        session.add(existing_fm)
    else:
        fm_fields = {
            k: v for k, v in fit_data.items()
            if hasattr(FitMetrics, k)
        }
        fm = FitMetrics(
            activity_id=activity_id,
            fit_downloaded_at=datetime.utcnow(),
            **fm_fields,
        )
        session.add(fm)

    session.commit()

    result = {
        "status": "success",
        "activity_id": str(activity_id),
        "streams_keys": list(streams.keys()),
        "fit_metrics_stored": bool(fit_data),
    }

    # 6. Segmentation + meteo (non-bloquant)
    segments_created = 0
    if streams:
        try:
            from app.domain.services.segmentation_service import segment_activity, is_activity_segmented
            if stored_streams or not is_activity_segmented(session, activity.id):
                segments_created = segment_activity(session, activity)
                result["segments_created"] = segments_created
        except Exception as e:
            logger.warning(f"Segmentation echouee pour activite Garmin {activity_id}: {e}")

        try:
            from app.domain.services.weather_service import fetch_weather_for_activity
            weather_ok = await fetch_weather_for_activity(session, activity)
            result["weather_enriched"] = weather_ok
        except Exception as e:
            logger.warning(f"Meteo echouee pour activite Garmin {activity_id}: {e}")

    return result


def get_garmin_enrichment_status(session: Session, user_id: UUID) -> Dict[str, Any]:
    """
    Retourne le statut d'enrichissement FIT pour les activites Garmin d'un utilisateur.

    Returns:
        dict avec total_garmin_activities, enriched_activities, pending_activities, enrichment_percentage
    """
    total = session.exec(
        select(func.count()).select_from(Activity).where(
            Activity.user_id == user_id,
            Activity.garmin_activity_id.is_not(None),
        )
    ).one()

    enriched = session.exec(
        select(func.count()).select_from(FitMetrics).where(
            FitMetrics.activity_id.in_(
                select(Activity.id).where(
                    Activity.user_id == user_id,
                    Activity.garmin_activity_id.is_not(None),
                )
            )
        )
    ).one()

    pending = max(0, total - enriched)
    percentage = round((enriched / total) * 100) if total > 0 else 0

    return {
        "total_garmin_activities": total,
        "enriched_activities": enriched,
        "pending_activities": pending,
        "enrichment_percentage": percentage,
    }


def get_garmin_period_import_status(
    session: Session,
    user_id: UUID,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Retourne les compteurs d'import pour une periode precise.

    `weather_done` compte les activites avec timeline 10 min, pas seulement une
    ligne meteo ancienne, car c'est le format exploite dans le detail activite.
    """
    from app.domain.services.weather_service import _extract_activity_gps

    cutoff = datetime.utcnow() - timedelta(days=days_back)
    activities = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.source == ActivitySource.GARMIN.value,
            Activity.garmin_activity_id.is_not(None),
            Activity.start_date >= cutoff,
        ).order_by(Activity.start_date.desc())
    ).all()
    activity_ids = [activity.id for activity in activities if activity.id is not None]
    total = len(activity_ids)

    fit_done_ids: set[UUID] = set()
    weather_row_ids: set[UUID] = set()
    weather_timeline_ids: set[UUID] = set()

    if activity_ids:
        fit_done_ids = {
            activity_id
            for activity_id in session.exec(
                select(FitMetrics.activity_id).where(FitMetrics.activity_id.in_(activity_ids))
            ).all()
            if activity_id is not None
        }

        weather_rows = session.exec(
            select(ActivityWeather.activity_id, ActivityWeather.hourly_snapshot).where(
                ActivityWeather.activity_id.in_(activity_ids)
            )
        ).all()
        weather_row_ids = {row[0] for row in weather_rows}
        weather_timeline_ids = {
            row[0]
            for row in weather_rows
            if isinstance(row[1], dict) and isinstance(row[1].get("timeline_10min"), list)
        }

    weather_eligible = sum(
        1 for activity in activities if _extract_activity_gps(activity) is not None
    )
    fit_done = len(fit_done_ids)
    weather_done = len(weather_timeline_ids)

    return {
        "days_back": days_back,
        "period_started_at": cutoff.isoformat(),
        "total_activities": total,
        "fit_total": total,
        "fit_done": fit_done,
        "fit_pending": max(0, total - fit_done),
        "weather_total": weather_eligible,
        "weather_recorded": len(weather_row_ids),
        "weather_done": weather_done,
        "weather_pending": max(0, weather_eligible - weather_done),
        "weather_without_coordinates": max(0, total - weather_eligible),
    }


async def batch_enrich_garmin_fit(
    session: Session,
    user_id: UUID,
    max_activities: int = 50,
) -> Dict[str, Any]:
    """
    Enrichit en batch les activites Garmin sans metriques FIT.

    Returns:
        dict avec enriched, errors, total
    """
    # Trouver les activites Garmin sans metriques FIT
    fit_subq = select(FitMetrics.activity_id)
    activities = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.garmin_activity_id.is_not(None),
            ~Activity.id.in_(fit_subq),
        ).order_by(Activity.start_date.desc()).limit(max_activities)
    ).all()

    enriched = 0
    errors_count = 0

    for activity in activities:
        try:
            result = await enrich_garmin_activity_fit(
                session, user_id, activity.id,
            )
            if result.get("status") == "success":
                enriched += 1
            else:
                errors_count += 1
        except Exception as e:
            logger.warning(f"Erreur enrichissement FIT activite {activity.id}: {e}")
            errors_count += 1

        await asyncio.sleep(1.5)  # rate limit genereux entre enrichissements FIT

    return {
        "enriched": enriched,
        "errors": errors_count,
        "total": len(activities),
    }
