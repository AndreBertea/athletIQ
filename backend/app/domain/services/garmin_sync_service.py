"""
Service de sync Garmin — Tache 3.3.1 + 5.1.2
Synchronise les donnees physiologiques quotidiennes depuis Garmin Connect via garth.
Inclut le download et parsing de fichiers FIT (Running Dynamics, power, Training Effect).
"""
import asyncio
import logging
from io import BytesIO
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import garth
from sqlmodel import Session, select

from app.auth.garmin_auth import garmin_auth
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
