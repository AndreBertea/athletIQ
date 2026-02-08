"""
Service de sync Garmin — Tache 3.3.1 + 5.1.2 + activites Garmin
Synchronise les donnees physiologiques quotidiennes depuis Garmin Connect via garth.
Inclut le download et parsing de fichiers FIT (Running Dynamics, power, Training Effect).
Inclut la sync des activites Garmin dans la table Activity unifiee.
"""
from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from uuid import UUID

import garth
from sqlalchemy import and_, func
from sqlmodel import Session, select

if TYPE_CHECKING:
    pass  # garth.Activity used only in annotations

from app.auth.garmin_auth import garmin_auth
from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.entities.fit_metrics import FitMetrics
from app.domain.entities.garmin_daily import GarminDaily
from app.domain.entities.user import GarminAuth

logger = logging.getLogger(__name__)

REQUEST_DELAY_S = 0.5  # 500ms entre chaque date


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
    synced = 0
    errors = 0

    for i in range(days_back):
        target_date = today - timedelta(days=i)
        try:
            data = _fetch_day(client, target_date)
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

    return {"days_synced": synced, "errors": errors, "total_requested": days_back}


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
            if dto.sleep_scores:
                data["sleep_score"] = getattr(dto.sleep_scores, "overall", None)
                if data["sleep_score"] and hasattr(data["sleep_score"], "value"):
                    data["sleep_score"] = data["sleep_score"].value
            if dto.sleep_time_seconds:
                data["sleep_duration_min"] = dto.sleep_time_seconds / 60
            if getattr(dto, "average_sp_o2_value", None):
                data["spo2"] = dto.average_sp_o2_value
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
        scores = garth.GarminScoresData.get(day, client=client)
        if scores and scores.vo_2_max_precise_value:
            data["vo2max_estimated"] = scores.vo_2_max_precise_value
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

    Args:
        client: Client garth authentifie
        garmin_activity_id: ID de l'activite sur Garmin Connect

    Returns:
        Contenu du fichier FIT en bytes, ou None si echec
    """
    try:
        fit_bytes = client.download(
            f"/download-service/files/activity/{garmin_activity_id}"
        )
        if fit_bytes:
            logger.info(f"FIT file telecharge pour activite {garmin_activity_id} ({len(fit_bytes)} bytes)")
            return fit_bytes
        logger.warning(f"FIT file vide pour activite {garmin_activity_id}")
        return None
    except Exception as e:
        logger.warning(f"Echec telechargement FIT pour activite {garmin_activity_id}: {e}")
        return None


def parse_fit_file(fit_bytes: bytes) -> Dict[str, Any]:
    """
    Parse un fichier FIT et extrait Running Dynamics, puissance, Training Effect.

    Args:
        fit_bytes: Contenu brut du fichier FIT

    Returns:
        Dict avec:
        - ground_contact_time_avg: temps de contact au sol moyen (ms)
        - vertical_oscillation_avg: oscillation verticale moyenne (cm)
        - stance_time_balance_avg: balance G/D moyenne (%)
        - power_avg: puissance moyenne estimee (W)
        - aerobic_training_effect: Training Effect aerobique (0.0-5.0)
        - anaerobic_training_effect: Training Effect anaerobique (0.0-5.0)
        - record_count: nombre d'enregistrements parses
    """
    import fitparse

    fitfile = fitparse.FitFile(BytesIO(fit_bytes))

    # Accumulateurs pour moyennes sur les records
    stance_times: List[float] = []
    vertical_oscillations: List[float] = []
    stance_balances: List[float] = []
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

        val = record.get_value("power")
        if val is not None:
            powers.append(float(val))

    result: Dict[str, Any] = {
        "record_count": len(stance_times) + len(powers),
    }

    if stance_times:
        result["ground_contact_time_avg"] = round(
            sum(stance_times) / len(stance_times), 1
        )
    if vertical_oscillations:
        result["vertical_oscillation_avg"] = round(
            sum(vertical_oscillations) / len(vertical_oscillations), 2
        )
    if stance_balances:
        result["stance_time_balance_avg"] = round(
            sum(stance_balances) / len(stance_balances), 2
        )
    if powers:
        result["power_avg"] = round(sum(powers) / len(powers), 1)

    # Training Effect depuis le message session
    for session_msg in fitfile.get_messages("session"):
        aerobic_raw = session_msg.get_value("total_training_effect")
        if aerobic_raw is not None:
            result["aerobic_training_effect"] = round(float(aerobic_raw), 1)

        anaerobic_raw = session_msg.get_value("total_anaerobic_training_effect")
        if anaerobic_raw is not None:
            result["anaerobic_training_effect"] = round(float(anaerobic_raw), 1)
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

# Tolerance pour la deduplication fuzzy
DEDUP_TIME_TOLERANCE_S = 300  # 5 minutes
DEDUP_DISTANCE_TOLERANCE_M = 200  # 200m


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
) -> Optional[Activity]:
    """
    Verifie si une activite existe deja.
    1) Match exact par garmin_activity_id
    2) Fuzzy match par start_date + distance (pour eviter les doublons Strava/Garmin)
    Retourne l'Activity existante ou None.
    """
    # 1) Match exact garmin_activity_id
    existing = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.garmin_activity_id == garmin_activity_id,
        )
    ).first()
    if existing:
        return existing

    # 2) Fuzzy match : meme heure (+/- 5min) et distance similaire (+/- 200m)
    time_lower = start_date - timedelta(seconds=DEDUP_TIME_TOLERANCE_S)
    time_upper = start_date + timedelta(seconds=DEDUP_TIME_TOLERANCE_S)

    existing = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.start_date >= time_lower,
            Activity.start_date <= time_upper,
            Activity.distance >= distance - DEDUP_DISTANCE_TOLERANCE_M,
            Activity.distance <= distance + DEDUP_DISTANCE_TOLERANCE_M,
        )
    ).first()

    return existing


async def sync_garmin_activities(
    session: Session,
    user_id: UUID,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Synchronise les activites Garmin dans la table Activity.

    Liste les activites via garth.Activity.list(), dedup, cree Activity source=GARMIN.
    Si une activite existe deja via Strava (fuzzy match), lie le garmin_activity_id.

    Returns:
        dict avec created, linked, skipped, errors, total
    """
    garmin_auth_record = session.exec(
        select(GarminAuth).where(GarminAuth.user_id == user_id)
    ).first()

    if not garmin_auth_record:
        raise ValueError(f"Aucune authentification Garmin pour user_id={user_id}")

    client = garmin_auth.get_client(garmin_auth_record.oauth_token_encrypted)

    # Recuperer les activites (garth pagine par start/limit)
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    created = 0
    linked = 0
    skipped = 0
    errors = 0

    try:
        # garth.Activity.list() retourne les plus recentes d'abord
        # On charge par pages de 20 jusqu'a depasser le cutoff
        all_activities: List[garth.Activity] = []
        start = 0
        page_size = 20
        while True:
            page = garth.Activity.list(limit=page_size, start=start, client=client)
            if not page:
                break
            all_activities.extend(page)
            # Si la derniere activite de la page est avant le cutoff, on arrete
            last = page[-1]
            last_time = last.start_time_gmt or last.start_time_local
            if last_time and last_time < cutoff:
                break
            start += page_size
            await asyncio.sleep(0.2)  # rate limit
    except Exception as e:
        logger.error(f"Erreur listing activites Garmin: {e}")
        return {"created": 0, "linked": 0, "skipped": 0, "errors": 1, "total": 0}

    for garmin_act in all_activities:
        act_time = garmin_act.start_time_gmt or garmin_act.start_time_local
        if act_time and act_time < cutoff:
            continue

        try:
            mapped = _map_garmin_activity(garmin_act, user_id)
            existing = _deduplicate_activity(
                session, user_id, garmin_act.activity_id,
                mapped["start_date"], mapped["distance"],
            )

            if existing:
                if existing.garmin_activity_id == garmin_act.activity_id:
                    # Deja synce depuis Garmin, skip
                    skipped += 1
                else:
                    # Existe via Strava, on lie le garmin_activity_id
                    existing.garmin_activity_id = garmin_act.activity_id
                    if existing.source == ActivitySource.STRAVA.value:
                        pass  # On garde source=strava, on ajoute juste l'ID Garmin
                    session.add(existing)
                    session.commit()
                    linked += 1
            else:
                # Nouvelle activite Garmin
                activity = Activity(**mapped)
                session.add(activity)
                session.commit()
                created += 1

        except Exception as e:
            logger.warning(f"Erreur sync activite Garmin {garmin_act.activity_id}: {e}")
            errors += 1

    return {
        "created": created,
        "linked": linked,
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
    Parse un fichier FIT et extrait les streams compatibles avec le pipeline
    de segmentation existant.

    Format de sortie compatible avec streams_data Strava :
    {
        "time": {"data": [0, 1, 2, ...]},
        "distance": {"data": [0.0, 5.2, ...]},
        "altitude": {"data": [100.0, 101.2, ...]},
        "heartrate": {"data": [120, 125, ...]},
        "cadence": {"data": [85, 86, ...]},
        "latlng": {"data": [[lat, lng], ...]},
        "grade_smooth": {"data": [0.0, 1.2, ...]},
    }
    """
    import fitparse

    fitfile = fitparse.FitFile(BytesIO(fit_bytes))

    times: List[float] = []
    distances: List[float] = []
    altitudes: List[float] = []
    heartrates: List[int] = []
    cadences: List[int] = []
    latlngs: List[List[float]] = []
    grades: List[float] = []

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

        # Cadence (running = steps/min, FIT peut donner demi-cycles)
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

        # Grade
        grade = record.get_value("grade")
        grades.append(float(grade) if grade is not None else None)

    streams: Dict[str, Any] = {}

    if any(t is not None for t in times):
        streams["time"] = {"data": times}
    if any(d is not None for d in distances):
        streams["distance"] = {"data": distances}
    if any(a is not None for a in altitudes):
        streams["altitude"] = {"data": altitudes}
    if any(h is not None for h in heartrates):
        streams["heartrate"] = {"data": heartrates}
    if any(c is not None for c in cadences):
        streams["cadence"] = {"data": cadences}
    if any(ll is not None for ll in latlngs):
        streams["latlng"] = {"data": latlngs}
    if any(g is not None for g in grades):
        streams["grade_smooth"] = {"data": grades}

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

    # 4. Stocke streams_data
    if streams:
        activity.streams_data = streams
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
            from app.domain.services.segmentation_service import segment_activity
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


async def batch_enrich_garmin_fit(
    session: Session,
    user_id: UUID,
    max_activities: int = 10,
) -> Dict[str, Any]:
    """
    Enrichit en batch les activites Garmin sans streams_data.

    Returns:
        dict avec enriched, errors, total
    """
    # Trouver les activites Garmin sans streams_data
    activities = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.garmin_activity_id.is_not(None),
            Activity.streams_data.is_(None),
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

        await asyncio.sleep(0.5)  # rate limit entre activites

    return {
        "enriched": enriched,
        "errors": errors_count,
        "total": len(activities),
    }
