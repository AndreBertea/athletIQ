"""
Service readiness : persistance des check-ins + calcul du score.

Algorithme Saw 2017 :
  - 4 wellness 1-5 (wellbeing, sleep, legs, motivation), sRPE exclu du score.
  - Score brut = moyenne des 4 / 5 * 100.
  - Phase calibration tant que < 14 jours en base : on affiche les valeurs
    brutes du jour, pas de score agrege.
  - A partir de 14 jours : on calcule des z-scores par dimension sur la
    baseline 28j glissante, et on retourne un score 0-100 colore selon
    l'ecart a la baseline.
"""
from __future__ import annotations

import statistics
from datetime import date as date_type, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.daily_checkin import (
    DailyCheckin,
    DailyCheckinCreate,
    DailyCheckinRead,
    ReadinessScore,
)

BASELINE_DAYS = 28
CALIBRATION_THRESHOLD = 14


def upsert_today(
    session: Session,
    user_id: UUID,
    payload: DailyCheckinCreate,
) -> DailyCheckin:
    """Cree ou met a jour la saisie du jour (1 par user/date)."""
    today = payload.entry_date or date_type.today()
    existing = session.exec(
        select(DailyCheckin).where(
            DailyCheckin.user_id == user_id,
            DailyCheckin.entry_date == today,
        )
    ).first()

    if existing:
        existing.wellbeing = payload.wellbeing
        existing.sleep_quality = payload.sleep_quality
        existing.legs = payload.legs
        existing.motivation = payload.motivation
        existing.srpe_yesterday = payload.srpe_yesterday
        existing.session_duration_min = payload.session_duration_min
        existing.context_tags = list(payload.context_tags)
        existing.notes = payload.notes
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    entry = DailyCheckin(
        user_id=user_id,
        entry_date=today,
        wellbeing=payload.wellbeing,
        sleep_quality=payload.sleep_quality,
        legs=payload.legs,
        motivation=payload.motivation,
        srpe_yesterday=payload.srpe_yesterday,
        session_duration_min=payload.session_duration_min,
        context_tags=list(payload.context_tags),
        notes=payload.notes,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_today(session: Session, user_id: UUID) -> Optional[DailyCheckin]:
    today = date_type.today()
    return session.exec(
        select(DailyCheckin).where(
            DailyCheckin.user_id == user_id,
            DailyCheckin.entry_date == today,
        )
    ).first()


def get_history(
    session: Session, user_id: UUID, days: int = 30
) -> list[DailyCheckin]:
    since = date_type.today() - timedelta(days=days)
    return session.exec(
        select(DailyCheckin)
        .where(
            DailyCheckin.user_id == user_id,
            DailyCheckin.entry_date >= since,
        )
        .order_by(DailyCheckin.entry_date.desc())
    ).all()


def compute_score(session: Session, user_id: UUID) -> ReadinessScore:
    """Calcule le score readiness pour l'utilisateur courant."""
    today_entry = get_today(session, user_id)
    baseline_entries = _baseline_entries(session, user_id)
    days_recorded = len(baseline_entries)

    # Phase 1 : aucune saisie
    if days_recorded == 0:
        return ReadinessScore(
            phase="no_entries",
            days_recorded=0,
            insight="Premiere saisie : commence ton check-in du jour pour bootstraper ta baseline.",
        )

    today_read = (
        DailyCheckinRead.model_validate(today_entry, from_attributes=True)
        if today_entry
        else None
    )

    # Phase 2 : calibration (< 14 jours)
    if days_recorded < CALIBRATION_THRESHOLD:
        return ReadinessScore(
            phase="calibration",
            days_recorded=days_recorded,
            today=today_read,
            insight=(
                f"Tu en es a {days_recorded}/{CALIBRATION_THRESHOLD} saisies. "
                "Le score 0-100 personnalise s'active des que ta baseline statistique est solide."
            ),
        )

    # Phase 3 : stable, calcul du score + z-scores
    if today_entry is None:
        # Pas de saisie du jour, mais baseline OK : on ne peut pas afficher le score
        return ReadinessScore(
            phase="calibration",
            days_recorded=days_recorded,
            insight="Saisis ton check-in du jour pour voir ton score readiness actualise.",
        )

    score_0_100, z_dict, insight = _score_from_baseline(today_entry, baseline_entries)

    return ReadinessScore(
        phase="stable",
        days_recorded=days_recorded,
        score_0_100=score_0_100,
        z_wellbeing=z_dict.get("wellbeing"),
        z_sleep=z_dict.get("sleep"),
        z_legs=z_dict.get("legs"),
        z_motivation=z_dict.get("motivation"),
        today=today_read,
        insight=insight,
    )


# ---------- Helpers internes ----------

def _baseline_entries(session: Session, user_id: UUID) -> list[DailyCheckin]:
    since = date_type.today() - timedelta(days=BASELINE_DAYS)
    return session.exec(
        select(DailyCheckin).where(
            DailyCheckin.user_id == user_id,
            DailyCheckin.entry_date >= since,
        )
    ).all()


def _score_from_baseline(
    today: DailyCheckin, baseline: list[DailyCheckin]
) -> tuple[float, dict[str, float], str]:
    """Retourne (score 0-100, z-scores par dimension, insight)."""
    dims = {
        "wellbeing": (today.wellbeing, [e.wellbeing for e in baseline]),
        "sleep": (today.sleep_quality, [e.sleep_quality for e in baseline]),
        "legs": (today.legs, [e.legs for e in baseline]),
        "motivation": (today.motivation, [e.motivation for e in baseline]),
    }
    z_dict: dict[str, float] = {}
    for k, (val, hist) in dims.items():
        mean = statistics.mean(hist)
        sd = statistics.pstdev(hist) if len(hist) >= 2 else 0.0
        z = ((val - mean) / sd) if sd > 0 else 0.0
        z_dict[k] = round(z, 2)

    # Score 0-100 = ((wellbeing + sleep + legs + motivation) / 4) * 20
    raw = (
        today.wellbeing + today.sleep_quality + today.legs + today.motivation
    ) / 4.0
    score_0_100 = round(raw * 20, 0)

    # Insight bref : positif si toutes z >= 0, negatif si plusieurs < -0.5
    neg = sum(1 for z in z_dict.values() if z < -0.5)
    pos = sum(1 for z in z_dict.values() if z > 0.5)
    if neg >= 2:
        insight = (
            "Plusieurs dimensions sous ta moyenne : envisage une seance plus legere aujourd'hui."
        )
    elif pos >= 3:
        insight = "Tres bonne forme par rapport a ta baseline : tu peux pousser un peu."
    else:
        insight = "Forme dans la moyenne de tes 4 dernieres semaines."

    return score_0_100, z_dict, insight
