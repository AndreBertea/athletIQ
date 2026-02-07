"""
Service de features derivees avancees (Tache 4.2.1).
Axe A — Per-segment : minetti_cost, grade_variability, efficiency_factor, cardiac_drift, cadence_decay.
Axe B — Per-day : TRIMP, CTL (EWMA 42j), ATL (EWMA 7j), TSB = CTL - ATL, rhr_delta_7d.
"""
import logging
import statistics
from datetime import date as date_type, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.activity import Activity
from app.domain.entities.garmin_daily import GarminDaily
from app.domain.entities.segment import Segment
from app.domain.entities.segment_features import SegmentFeatures
from app.domain.entities.training_load import TrainingLoad

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CTL_DAYS = 42
ATL_DAYS = 7
RHR_DELTA_WINDOW = 7


# ===================================================================
# Axe A — Features per-segment
# ===================================================================

def minetti_cost(grade_fraction: float) -> float:
    """Cout metabolique de Minetti (J/(kg*m)) en fonction de la pente (fraction).

    Formule : C(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6
    """
    i = grade_fraction
    return (
        155.4 * i**5
        - 30.4 * i**4
        - 43.3 * i**3
        + 46.3 * i**2
        + 19.5 * i
        + 3.6
    )


def _compute_grade_variability(segments: List[Segment]) -> Dict[UUID, Optional[float]]:
    """Ecart-type glissant du grade sur une fenetre de 5 segments centres.

    Pour les bords, la fenetre est reduite.
    Retourne {segment_id: grade_variability}.
    """
    result: Dict[UUID, Optional[float]] = {}
    n = len(segments)
    for idx, seg in enumerate(segments):
        if seg.avg_grade_percent is None:
            result[seg.id] = None
            continue
        # Fenetre centree de 5 segments (2 avant, 2 apres)
        lo = max(0, idx - 2)
        hi = min(n, idx + 3)
        grades = [
            segments[j].avg_grade_percent
            for j in range(lo, hi)
            if segments[j].avg_grade_percent is not None
        ]
        if len(grades) < 2:
            result[seg.id] = 0.0
        else:
            result[seg.id] = statistics.stdev(grades)
    return result


def _compute_cardiac_drift(segments: List[Segment]) -> Dict[UUID, Optional[float]]:
    """Cardiac drift : variation relative HR / pace entre 1ere et 2eme moitie de l'activite.

    cardiac_drift = (HR_2nd / pace_2nd) / (HR_1st / pace_1st) - 1
    Positif = derive cardiaque (fatigue).
    Attribue la meme valeur a tous les segments de l'activite (metrique globale).
    """
    result: Dict[UUID, Optional[float]] = {}

    # Filtrer les segments avec HR et pace valides
    valid = [s for s in segments if s.avg_hr and s.pace_min_per_km and s.pace_min_per_km > 0]
    if len(valid) < 4:
        for seg in segments:
            result[seg.id] = None
        return result

    mid = len(valid) // 2
    first_half = valid[:mid]
    second_half = valid[mid:]

    def _avg_ratio(segs: List[Segment]) -> Optional[float]:
        hrs = [s.avg_hr for s in segs if s.avg_hr]
        paces = [s.pace_min_per_km for s in segs if s.pace_min_per_km and s.pace_min_per_km > 0]
        if not hrs or not paces:
            return None
        return (sum(hrs) / len(hrs)) / (sum(paces) / len(paces))

    r1 = _avg_ratio(first_half)
    r2 = _avg_ratio(second_half)

    drift = None
    if r1 and r2 and r1 > 0:
        drift = (r2 / r1) - 1.0

    for seg in segments:
        result[seg.id] = drift
    return result


def _compute_cadence_decay(segments: List[Segment]) -> Dict[UUID, Optional[float]]:
    """Cadence decay : variation relative de cadence entre 1ere et 2eme moitie.

    cadence_decay = (cadence_2nd / cadence_1st) - 1
    Negatif = la cadence diminue (fatigue). Attribue a tous les segments.
    """
    result: Dict[UUID, Optional[float]] = {}

    valid = [s for s in segments if s.avg_cadence is not None and s.avg_cadence > 0]
    if len(valid) < 4:
        for seg in segments:
            result[seg.id] = None
        return result

    mid = len(valid) // 2
    avg_1 = sum(s.avg_cadence for s in valid[:mid]) / mid
    avg_2 = sum(s.avg_cadence for s in valid[mid:]) / len(valid[mid:])

    decay = None
    if avg_1 > 0:
        decay = (avg_2 / avg_1) - 1.0

    for seg in segments:
        result[seg.id] = decay
    return result


def _compute_efficiency_factor(segments: List[Segment]) -> Dict[UUID, Optional[float]]:
    """Efficiency factor par segment : pace_min_per_km / avg_hr.

    Plus la valeur est basse, meilleure est l'efficacite (court vite avec HR bas).
    """
    result: Dict[UUID, Optional[float]] = {}
    for seg in segments:
        if seg.avg_hr and seg.avg_hr > 0 and seg.pace_min_per_km and seg.pace_min_per_km > 0:
            result[seg.id] = seg.pace_min_per_km / seg.avg_hr
        else:
            result[seg.id] = None
    return result


def compute_segment_features(session: Session, activity_id: UUID) -> int:
    """Calcule les features derivees per-segment pour une activite.

    Met a jour les SegmentFeatures existants.
    Retourne le nombre de segments mis a jour.
    """
    segments = session.exec(
        select(Segment)
        .where(Segment.activity_id == activity_id)
        .order_by(Segment.segment_index)
    ).all()

    if not segments:
        return 0

    # Calculs vectoriels sur tous les segments
    grade_var = _compute_grade_variability(segments)
    drift = _compute_cardiac_drift(segments)
    decay = _compute_cadence_decay(segments)
    eff = _compute_efficiency_factor(segments)

    updated = 0
    for seg in segments:
        features = session.exec(
            select(SegmentFeatures).where(SegmentFeatures.segment_id == seg.id)
        ).first()
        if not features:
            continue

        # Minetti cost
        if seg.avg_grade_percent is not None:
            features.minetti_cost = minetti_cost(seg.avg_grade_percent / 100.0)

        features.grade_variability = grade_var.get(seg.id)
        features.cardiac_drift = drift.get(seg.id)
        features.cadence_decay = decay.get(seg.id)
        features.efficiency_factor = eff.get(seg.id)

        session.add(features)
        updated += 1

    session.commit()
    logger.info(f"Activite {activity_id}: {updated} segment features derivees mises a jour")
    return updated


def compute_all_segment_features(
    session: Session, user_id: Optional[UUID] = None
) -> Dict[str, int]:
    """Calcule les features derivees pour toutes les activites segmentees.

    Retourne {processed, skipped, errors}.
    """
    query = select(Segment.activity_id).distinct()
    if user_id:
        query = query.where(Segment.user_id == user_id)
    activity_ids = session.exec(query).all()

    processed = 0
    skipped = 0
    errors = 0

    for aid in activity_ids:
        try:
            # Verifier si deja calcule (minetti_cost non null sur au moins 1 segment)
            check = session.exec(
                select(SegmentFeatures)
                .where(
                    SegmentFeatures.activity_id == aid,
                    SegmentFeatures.minetti_cost.is_not(None),
                )
                .limit(1)
            ).first()
            if check:
                skipped += 1
                continue

            count = compute_segment_features(session, aid)
            if count > 0:
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"Erreur features derivees activite {aid}: {e}")
            session.rollback()
            errors += 1

    return {"processed": processed, "skipped": skipped, "errors": errors}


# ===================================================================
# Axe B — Features per-day (TRIMP, CTL, ATL, TSB)
# ===================================================================

def compute_trimp(avg_hr: Optional[float], duration_min: float, max_hr: Optional[float] = None) -> Optional[float]:
    """Calcule le TRIMP (Training Impulse) simplifie.

    TRIMP = duration_min * avg_hr (simplifie, sans seuil lactique).
    Si max_hr fourni, normalise : TRIMP = duration_min * (avg_hr / max_hr) * 100.
    """
    if avg_hr is None or avg_hr <= 0:
        return None
    if max_hr and max_hr > 0:
        return duration_min * (avg_hr / max_hr) * 100.0
    return duration_min * avg_hr


def _get_daily_trimp(session: Session, user_id: UUID, target_date: date_type) -> float:
    """Somme les TRIMP de toutes les activites d'un jour donne."""
    start_dt = _date_to_datetime_range(target_date)
    end_dt = _date_to_datetime_range(target_date + timedelta(days=1))

    activities = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.start_date >= start_dt,
            Activity.start_date < end_dt,
        )
    ).all()

    total_trimp = 0.0
    for act in activities:
        duration_min = act.moving_time / 60.0 if act.moving_time else 0
        trimp = compute_trimp(act.average_heartrate, duration_min, act.max_heartrate)
        if trimp is not None:
            total_trimp += trimp
    return total_trimp


def _date_to_datetime_range(d: date_type):
    """Convertit une date en datetime pour comparaison."""
    from datetime import datetime
    return datetime(d.year, d.month, d.day)


def _get_rhr_delta_7d(
    session: Session, user_id: UUID, target_date: date_type
) -> Optional[float]:
    """Delta RHR sur 7 jours : rhr_today - rhr_7_days_ago. None si pas de donnees Garmin."""
    today_data = session.exec(
        select(GarminDaily).where(
            GarminDaily.user_id == user_id,
            GarminDaily.date == target_date,
        )
    ).first()

    past_date = target_date - timedelta(days=RHR_DELTA_WINDOW)
    past_data = session.exec(
        select(GarminDaily).where(
            GarminDaily.user_id == user_id,
            GarminDaily.date == past_date,
        )
    ).first()

    if (
        today_data
        and today_data.resting_hr is not None
        and past_data
        and past_data.resting_hr is not None
    ):
        return float(today_data.resting_hr - past_data.resting_hr)
    return None


def compute_training_load(
    session: Session, user_id: UUID, date_from: date_type, date_to: date_type
) -> int:
    """Calcule CTL/ATL/TSB pour un utilisateur sur une plage de dates.

    Utilise la methode EWMA incrementale :
      CTL_today = CTL_yesterday * (1 - 1/42) + TRIMP_today * (1/42)
      ATL_today = ATL_yesterday * (1 - 1/7)  + TRIMP_today * (1/7)
      TSB = CTL - ATL

    Retourne le nombre de jours calcules.
    """
    # Recuperer le dernier CTL/ATL connu avant date_from
    prev_load = session.exec(
        select(TrainingLoad)
        .where(
            TrainingLoad.user_id == user_id,
            TrainingLoad.date < date_from,
        )
        .order_by(TrainingLoad.date.desc())
        .limit(1)
    ).first()

    ctl = prev_load.ctl_42d if prev_load and prev_load.ctl_42d is not None else 0.0
    atl = prev_load.atl_7d if prev_load and prev_load.atl_7d is not None else 0.0

    days_computed = 0
    current = date_from
    while current <= date_to:
        trimp = _get_daily_trimp(session, user_id, current)

        # EWMA
        ctl = ctl * (1 - 1 / CTL_DAYS) + trimp * (1 / CTL_DAYS)
        atl = atl * (1 - 1 / ATL_DAYS) + trimp * (1 / ATL_DAYS)
        tsb = ctl - atl

        rhr_delta = _get_rhr_delta_7d(session, user_id, current)

        # Upsert
        existing = session.exec(
            select(TrainingLoad).where(
                TrainingLoad.user_id == user_id,
                TrainingLoad.date == current,
            )
        ).first()

        if existing:
            existing.ctl_42d = round(ctl, 2)
            existing.atl_7d = round(atl, 2)
            existing.tsb = round(tsb, 2)
            existing.rhr_delta_7d = rhr_delta
            session.add(existing)
        else:
            tl = TrainingLoad(
                user_id=user_id,
                date=current,
                ctl_42d=round(ctl, 2),
                atl_7d=round(atl, 2),
                tsb=round(tsb, 2),
                rhr_delta_7d=rhr_delta,
            )
            session.add(tl)

        days_computed += 1
        current += timedelta(days=1)

    session.commit()
    logger.info(f"User {user_id}: training load calcule pour {days_computed} jours ({date_from} -> {date_to})")
    return days_computed
