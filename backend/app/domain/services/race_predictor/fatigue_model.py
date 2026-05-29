"""Fatigue model for Race Predictor V2."""
from __future__ import annotations

import json
from datetime import datetime
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.domain.entities.activity import Activity, ActivitySource, ActivityType


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def stream_grade_fraction(grade_percent: float) -> float:
    """Convert Strava/Garmin grade_smooth values from percent to fraction."""
    return clamp(grade_percent / 100.0, -0.45, 0.45)


def default_fatigue_level(
    cumulative_time_min: float,
    cumulative_gain_m: float,
    cumulative_loss_m: float,
) -> float:
    """Return a 0..1 fatigue level from elapsed effort and vertical load."""
    hours = cumulative_time_min / 60
    time_load = max(0.0, hours - 2.0) / 6.0
    gain_load = max(0.0, cumulative_gain_m) / 4500
    loss_load = max(0.0, cumulative_loss_m) / 5500
    return clamp(time_load * 0.55 + gain_load * 0.30 + loss_load * 0.15, 0.0, 1.0)


def fatigue_factor(
    cumulative_time_min: float,
    cumulative_gain_m: float,
    cumulative_loss_m: float,
    *,
    alpha: float = 0.12,
) -> float:
    return 1.0 + alpha * default_fatigue_level(cumulative_time_min, cumulative_gain_m, cumulative_loss_m)


def _normalize_stream(raw: Any) -> dict[str, Any] | None:
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


def _stream_array(streams: dict[str, Any], key: str) -> list:
    value = streams.get(key)
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    return value if isinstance(value, list) else []


def _minetti_run_cost(grade_fraction: float) -> float:
    grade = clamp(grade_fraction, -0.45, 0.45)
    return max(
        1.8,
        155.4 * grade**5
        - 30.4 * grade**4
        - 43.3 * grade**3
        + 46.3 * grade**2
        + 19.5 * grade
        + 3.6,
    )


def build_fatigue_profile(
    session: Session,
    user_id: UUID,
    *,
    history_start_date: datetime,
    history_end_date: datetime | None = None,
    excluded_activity_ids: set[UUID] | None = None,
    p_run_wkg: float,
) -> dict:
    """Estimate fatigue alpha from long activities normalized by Minetti iso-effort."""
    excluded_activity_ids = excluded_activity_ids or set()
    statement = select(Activity).where(
        Activity.user_id == user_id,
        Activity.source == ActivitySource.GARMIN.value,
        Activity.start_date >= history_start_date,
        Activity.moving_time >= 7200,
        or_(
            Activity.activity_type_override.in_([ActivityType.RUN, ActivityType.TRAIL_RUN]),
            and_(
                Activity.activity_type_override.is_(None),
                Activity.activity_type.in_([ActivityType.RUN, ActivityType.TRAIL_RUN]),
            ),
        ),
    )
    if history_end_date is not None:
        statement = statement.where(Activity.start_date < history_end_date)
    if excluded_activity_ids:
        statement = statement.where(Activity.id.notin_(excluded_activity_ids))
    activities = session.exec(statement).all()
    alpha_samples: list[float] = []
    used_activities = 0
    for activity in activities:
        streams = _normalize_stream(activity.streams_data)
        if not streams:
            continue
        time = [float(value) for value in _stream_array(streams, "time") if value is not None]
        velocity = [float(value) for value in _stream_array(streams, "velocity_smooth") if value is not None]
        grade_percent = [float(value) for value in _stream_array(streams, "grade_smooth") if value is not None]
        if len(time) < 600 or len(velocity) < 600 or not grade_percent:
            continue

        limit = min(len(time), len(velocity), len(grade_percent))
        normalized_ratios: list[tuple[float, float]] = []
        cumulative_gain = 0.0
        cumulative_loss = 0.0
        previous_time = time[0]
        previous_grade = stream_grade_fraction(grade_percent[0])
        for index in range(limit):
            speed = velocity[index]
            current_time = time[index]
            if speed < 1.0 or current_time <= 0:
                continue
            grade_fraction = stream_grade_fraction(grade_percent[index])
            if index > 0:
                elapsed_delta = max(0.0, current_time - previous_time)
                distance_delta = speed * elapsed_delta
                elevation_delta = previous_grade * distance_delta
                if elevation_delta > 0:
                    cumulative_gain += elevation_delta
                else:
                    cumulative_loss += abs(elevation_delta)
            previous_time = current_time
            previous_grade = grade_fraction

            expected_speed = p_run_wkg / _minetti_run_cost(grade_fraction)
            if expected_speed <= 0:
                continue
            normalized_ratios.append((current_time / 3600, expected_speed / speed))

        early = [ratio for hour, ratio in normalized_ratios if 0.25 <= hour <= 1.0]
        late = [ratio for hour, ratio in normalized_ratios if hour >= 2.0]
        if len(early) < 120 or len(late) < 120:
            continue
        early_median = median(early)
        late_median = median(late[-max(120, len(late) // 3):])
        if early_median <= 0:
            continue
        final_time_min = max(time[:limit]) / 60
        fatigue_level = default_fatigue_level(final_time_min, cumulative_gain, cumulative_loss)
        if fatigue_level <= 0.05:
            continue
        alpha = clamp((late_median / early_median - 1.0) / fatigue_level, 0.04, 0.22)
        alpha_samples.append(alpha)
        used_activities += 1

    if not alpha_samples:
        return fatigue_summary(
            history_start_date=history_start_date,
            history_end_date=history_end_date,
            excluded_activity_count=len(excluded_activity_ids),
        )

    alpha = median(alpha_samples)
    return {
        "model": "personalized_minetti_normalized",
        "alpha": round(alpha, 3),
        "personalized": True,
        "sample_count": len(alpha_samples),
        "activity_count": used_activities,
        "history_start_date": history_start_date.isoformat(),
        "history_end_date": history_end_date.isoformat() if history_end_date else None,
        "excluded_activity_count": len(excluded_activity_ids),
        "notes": [
            "Fatigue estimee sur sorties longues en comparant allure reelle et allure iso-effort Minetti.",
            "Fallback automatique si les streams grade/vitesse/temps sont insuffisants.",
        ],
    }


def fatigue_summary(
    alpha: float = 0.12,
    *,
    history_start_date: datetime | None = None,
    history_end_date: datetime | None = None,
    excluded_activity_count: int = 0,
) -> dict:
    return {
        "model": "default_time_vertical_load",
        "alpha": alpha,
        "personalized": False,
        "sample_count": 0,
        "activity_count": 0,
        "history_start_date": history_start_date.isoformat() if history_start_date else None,
        "history_end_date": history_end_date.isoformat() if history_end_date else None,
        "excluded_activity_count": excluded_activity_count,
        "notes": [
            "La fatigue personnelle avancee sera calibree avec les longues sorties normalisees Minetti.",
            "La V2 actuelle applique une degradation progressive selon temps, D+ et D- cumules.",
        ],
    }
