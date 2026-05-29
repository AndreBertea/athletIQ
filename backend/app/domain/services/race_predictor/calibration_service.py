"""Personal calibration for Race Predictor V2."""
from __future__ import annotations

import json
import math
from datetime import datetime
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.domain.entities.activity import Activity, ActivitySource, ActivityType


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


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] * (upper - rank) + ordered[upper] * (rank - lower)


def _fallback_from_activity_averages(activities: list[Activity]) -> tuple[float, int]:
    speeds = [
        float(activity.average_speed)
        for activity in activities
        if activity.average_speed and 1.0 <= float(activity.average_speed) <= 6.5
    ]
    if speeds:
        return median(speeds), len(speeds)

    paces = [
        float(activity.average_pace)
        for activity in activities
        if activity.average_pace and 2.5 <= float(activity.average_pace) <= 10.0
    ]
    if paces:
        return 1000 / (median(paces) * 60), len(paces)

    return 2.65, 0


def _activity_elevation_per_km(activity: Activity) -> float:
    distance_km = float(activity.distance or 0) / 1000
    if distance_km <= 0:
        return 999.0
    return float(activity.total_elevation_gain or 0) / distance_km


def build_calibration(
    session: Session,
    user_id: UUID,
    *,
    history_start_date: datetime,
    history_end_date: datetime | None = None,
    excluded_activity_ids: set[UUID] | None = None,
    target_heartrate: float | None = None,
) -> dict[str, Any]:
    """Estimate flat-road metabolic power from clean historical Run streams."""
    excluded_activity_ids = excluded_activity_ids or set()
    statement = select(Activity).where(
        Activity.user_id == user_id,
        Activity.source == ActivitySource.GARMIN.value,
        Activity.start_date >= history_start_date,
        or_(
            Activity.activity_type_override == ActivityType.RUN,
            and_(Activity.activity_type_override.is_(None), Activity.activity_type == ActivityType.RUN),
        ),
    )
    if history_end_date is not None:
        statement = statement.where(Activity.start_date < history_end_date)
    if excluded_activity_ids:
        statement = statement.where(Activity.id.notin_(excluded_activity_ids))
    activities = session.exec(statement).all()
    run_activities = [activity for activity in activities if activity.distance and activity.distance >= 1000]

    all_hr_values: list[float] = []
    clean_speeds: list[float] = []
    clean_activity_ids: set[str] = set()

    for activity in run_activities:
        streams = _normalize_stream(activity.streams_data)
        if not streams:
            continue
        heartrate = [float(value) for value in _stream_array(streams, "heartrate") if value]
        velocity = [float(value) for value in _stream_array(streams, "velocity_smooth") if value is not None]
        grade_percent = [float(value) for value in _stream_array(streams, "grade_smooth") if value is not None]
        distance = [float(value) for value in _stream_array(streams, "distance") if value is not None]
        time = [float(value) for value in _stream_array(streams, "time") if value is not None]
        activity_is_flat_enough = _activity_elevation_per_km(activity) <= 25

        all_hr_values.extend([value for value in heartrate if 60 <= value <= 230])
        limit = min(len(heartrate), len(velocity))
        if limit < 60:
            continue

        for index in range(limit):
            hr = heartrate[index]
            speed = velocity[index]
            if not (60 <= hr <= 230 and 1.0 <= speed <= 6.5):
                continue
            if grade_percent and index < len(grade_percent) and abs(grade_percent[index]) > 2.0:
                continue
            if not grade_percent and not activity_is_flat_enough:
                continue
            if distance and time and index > 0 and index < min(len(distance), len(time)):
                distance_delta = distance[index] - distance[index - 1]
                time_delta = time[index] - time[index - 1]
                if time_delta <= 0 or distance_delta / time_delta < 1.0:
                    continue
            clean_speeds.append(speed)
            clean_activity_ids.add(str(activity.id))

    hrmax = _percentile(all_hr_values, 0.995)
    if hrmax is None:
        max_hr_values = [float(activity.max_heartrate) for activity in run_activities if activity.max_heartrate]
        hrmax = max(max_hr_values) if max_hr_values else 190.0

    if target_heartrate and 60 <= target_heartrate <= 220:
        lower_hr = target_heartrate - 5
        upper_hr = target_heartrate + 5
    else:
        lower_hr = 0.65 * hrmax
        upper_hr = 0.85 * hrmax

    filtered_clean_speeds: list[float] = []
    for activity in run_activities:
        streams = _normalize_stream(activity.streams_data)
        if not streams:
            continue
        heartrate = [float(value) for value in _stream_array(streams, "heartrate") if value]
        velocity = [float(value) for value in _stream_array(streams, "velocity_smooth") if value is not None]
        grade_percent = [float(value) for value in _stream_array(streams, "grade_smooth") if value is not None]
        activity_is_flat_enough = _activity_elevation_per_km(activity) <= 25
        limit = min(len(heartrate), len(velocity))
        for index in range(limit):
            hr = heartrate[index]
            speed = velocity[index]
            if not (lower_hr <= hr <= upper_hr and 1.0 <= speed <= 6.5):
                continue
            if grade_percent and index < len(grade_percent) and abs(grade_percent[index]) > 2.0:
                continue
            if not grade_percent and not activity_is_flat_enough:
                continue
            filtered_clean_speeds.append(speed)

    selected_speeds = filtered_clean_speeds if len(filtered_clean_speeds) >= 120 else clean_speeds
    source = "streams_flat_road"
    if len(selected_speeds) < 120:
        fallback_speed, fallback_count = _fallback_from_activity_averages(run_activities)
        selected_speeds = [fallback_speed]
        source = "activity_average_fallback" if fallback_count else "generic_fallback"

    flat_speed_mps = median(selected_speeds)
    p_run_wkg = 3.6 * flat_speed_mps
    sample_count = len(selected_speeds) if source == "streams_flat_road" else 0
    activity_count = len(clean_activity_ids) if clean_activity_ids else len(run_activities)

    if sample_count >= 1500 and activity_count >= 5:
        quality = "high"
        confidence = 0.85
    elif sample_count >= 300 and activity_count >= 3:
        quality = "medium"
        confidence = 0.68
    elif source.endswith("fallback"):
        quality = "low"
        confidence = 0.35
    else:
        quality = "low"
        confidence = 0.45

    return {
        "source": source,
        "p_run_wkg": round(p_run_wkg, 2),
        "p_walk_ratio": 0.75,
        "flat_speed_mps": round(flat_speed_mps, 3),
        "flat_pace_min_km": round((1000 / flat_speed_mps) / 60, 2) if flat_speed_mps > 0 else None,
        "hr_max_estimate": round(hrmax, 1),
        "target_hr_band": [round(lower_hr, 1), round(upper_hr, 1)],
        "sample_count": sample_count,
        "activity_count": activity_count,
        "calibration_quality": quality,
        "confidence": confidence,
        "history_start_date": history_start_date.isoformat(),
        "history_end_date": history_end_date.isoformat() if history_end_date else None,
        "excluded_activity_count": len(excluded_activity_ids),
    }
