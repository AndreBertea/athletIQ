"""User-specific trail surface factor extraction for Race Predictor V3.

V2/V2.3.1 deliberately keep ``trail_cost_factor`` conservative: without
validated clean races, they fall back to the literature prior (~1.20). V3 is
the production hybrid engine, so it may use lower-confidence historical trail
evidence. This module derives that evidence by replaying each Garmin trail
activity through the physics engine with ``surface_factor=1.0`` and measuring
the residual:

``trail_factor_observed = adjusted_real_moving_time / minetti_only_time``.

The observation is not a replacement for the physics model. It is a personal
correction layer on top of Minetti, weighted by data quality and reference
category.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.entities.race_prediction import RaceValidationReference
from app.domain.services.race_predictor.gpx_analyzer import analyze_gpx
from app.domain.services.race_predictor.physics_engine import predict_segments


DEFAULT_HISTORY_DAYS = 366 * 3
TRAIL_ELEVATION_PER_KM_THRESHOLD = 15.0
MAX_TRAIL_FACTOR_ACTIVITIES = 24

NON_SCORING_CATEGORIES = {
    "incident_non_scoring",
    "execution_degraded_non_scoring",
}


def build_user_trail_factor_observations(
    session: Session,
    user_id: UUID,
    *,
    as_of_date: datetime,
    history_start_date: Optional[datetime],
    excluded_activity_ids: Iterable[UUID] | None,
    p_ref_steady_wkg: float,
    durability_alpha: float,
    max_activities: int = MAX_TRAIL_FACTOR_ACTIVITIES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return V3 historical trail-factor observations for one athlete.

    The extractor consumes Garmin trail activities only. Official clean /
    normalised races receive the strongest weight; ordinary trail training is
    accepted with wider uncertainty because effort may be sub-maximal. This is
    exactly the intended V3 behaviour: user history guides the model, but the
    uncertainty stays honest.
    """
    debug: dict[str, Any] = {
        "mode": "v3_historical_trail_performance",
        "requested_max_activities": int(max_activities),
        "p_ref_steady_wkg": round(float(p_ref_steady_wkg), 3),
        "durability_alpha": round(float(durability_alpha), 4),
        "excluded_reasons": {},
        "observations": [],
    }

    if not (3.0 <= float(p_ref_steady_wkg) <= 25.0):
        _inc(debug, "invalid_p_ref")
        return [], debug

    lower_bound = history_start_date or (as_of_date - timedelta(days=DEFAULT_HISTORY_DAYS))
    excluded = set(excluded_activity_ids or [])

    statement = (
        select(Activity)
        .where(
            Activity.user_id == user_id,
            Activity.source == ActivitySource.GARMIN.value,
            Activity.start_date < as_of_date,
            Activity.start_date >= lower_bound,
        )
        .order_by(Activity.start_date.desc())
    )
    if excluded:
        statement = statement.where(Activity.id.notin_(excluded))
    activities = list(session.exec(statement).all())

    validation_index = _validation_index(
        session, user_id, {activity.id for activity in activities if activity.id}
    )

    observations: list[dict[str, Any]] = []
    considered = 0
    for activity in activities:
        if len(observations) >= max_activities:
            break
        if not _is_trail_activity(activity):
            _inc(debug, "not_trail_like")
            continue

        validation = validation_index.get(activity.id) if activity.id else None
        category = (validation.category if validation else "historical_training") or "historical_training"
        category = str(category).strip().lower()
        if category in NON_SCORING_CATEGORIES:
            _inc(debug, f"category={category}")
            continue

        considered += 1
        observation = _activity_to_trail_factor_observation(
            activity,
            validation,
            category=category,
            p_ref_steady_wkg=float(p_ref_steady_wkg),
            durability_alpha=float(durability_alpha),
        )
        if observation is None:
            _inc(debug, "unusable_track_or_ratio")
            continue
        observations.append(observation)
        debug["observations"].append(
            {
                "source_label": observation["source_label"],
                "mean": round(float(observation["mean"]), 3),
                "std": round(float(observation["std"]), 3),
                "weight": round(float(observation["weight"]), 3),
                "category": observation["category"],
                "quality_flags": observation.get("quality_flags", []),
            }
        )

    selected = _select_performance_envelope(observations)

    debug["activities_scanned"] = len(activities)
    debug["trail_candidates_considered"] = considered
    debug["all_observations_count"] = len(observations)
    debug["evidence_count"] = len(selected)
    debug["selection_policy"] = (
        "official_references_plus_performance_envelope"
        if observations
        else "none"
    )
    debug["selected_observations"] = [
        {
            "source_label": obs["source_label"],
            "mean": round(float(obs["mean"]), 3),
            "std": round(float(obs["std"]), 3),
            "weight": round(float(obs["weight"]), 3),
            "category": obs["category"],
        }
        for obs in selected
    ]
    if not selected:
        debug["mode"] = "v3_historical_trail_prior_only"
    return selected, debug


def _activity_to_trail_factor_observation(
    activity: Activity,
    validation: RaceValidationReference | None,
    *,
    category: str,
    p_ref_steady_wkg: float,
    durability_alpha: float,
) -> dict[str, Any] | None:
    distance_m = float(activity.distance or 0)
    moving_time_s = float(activity.moving_time or 0)
    if distance_m < 5000 or moving_time_s < 30 * 60:
        return None

    gpx_text, point_count = _activity_to_gpx(activity)
    if not gpx_text or point_count < 20:
        return None

    try:
        gpx_analysis = analyze_gpx(gpx_text)
        physics = predict_segments(
            gpx_analysis["segments"],
            calibration={"p_run_wkg": p_ref_steady_wkg, "p_walk_ratio": 0.75},
            environment={
                "weather_mode": "manual",
                "weather_source": "neutral_history_replay",
                "temperature_c": 11.0,
                "weather_factor": 1.0,
                "weather_timeline": [],
                "weather_timeline_enabled": False,
                "p_run_wkg": p_ref_steady_wkg,
            },
            fatigue_profile={"alpha": durability_alpha},
            trail_surface_factor=1.0,
            analysis_mode="trail",
            effort_mode="steady",
        )
    except Exception:
        return None

    predicted_s = float(physics.get("moving_time_min") or 0) * 60.0
    if predicted_s <= 0:
        return None

    adjusted_moving_s = _adjusted_moving_time_s(activity, validation)
    raw_factor = adjusted_moving_s / predicted_s
    if not math.isfinite(raw_factor) or not (0.75 <= raw_factor <= 2.0):
        return None

    # Surface penalty is a multiplicative cost; values below 1.0 usually mean
    # P_ref is under-estimated, not that the trail surface is magically faster
    # than road. Keep them at 1.0 and let p_ref handle speed.
    factor = max(1.0, min(1.6, raw_factor))

    std, weight, quality_flags = _observation_quality(
        activity, validation, category=category, point_count=point_count
    )
    if weight <= 0:
        return None

    quality_flags.extend(
        [
            "v3_user_trail_history",
            "physics_replay_surface_1_0",
            f"raw_factor_{raw_factor:.3f}",
        ]
    )

    return {
        "mean": float(factor),
        "std": float(std),
        "weight": float(weight),
        "source_label": _activity_label(activity),
        "source_id": str(activity.id) if activity.id is not None else None,
        "source_type": "activity",
        "performed_at": activity.start_date,
        "category": category,
        "quality_flags": quality_flags,
    }


def _adjusted_moving_time_s(
    activity: Activity, validation: RaceValidationReference | None
) -> float:
    moving_s = float(activity.moving_time or 0)
    if validation is None:
        return moving_s
    category = (validation.category or "").strip().lower()
    if category != "official_normalized":
        return moving_s
    gains = [
        value
        for value in (validation.potential_gain_min_low, validation.potential_gain_min_high)
        if value is not None
    ]
    if not gains:
        return moving_s
    gain_min = sum(float(value) for value in gains) / len(gains)
    return max(60.0, moving_s - gain_min * 60.0)


def _observation_quality(
    activity: Activity,
    validation: RaceValidationReference | None,
    *,
    category: str,
    point_count: int,
) -> tuple[float, float, list[str]]:
    flags: list[str] = []
    duration_h = float(activity.moving_time or 0) / 3600.0
    distance_km = float(activity.distance or 0) / 1000.0

    if category == "official_clean":
        std = 0.08
        weight = 1.2
        flags.append("official_clean")
    elif category == "official_normalized":
        std = 0.10
        weight = 0.9
        flags.append("official_normalized_adjusted")
    elif category == "training_control":
        std = 0.15
        weight = 0.45
        flags.append("training_control")
    else:
        std = 0.18
        weight = 0.30
        flags.append("historical_training")

    if duration_h < 1.0:
        std *= 1.25
        weight *= 0.65
        flags.append("short_trail")
    elif duration_h >= 2.0:
        weight *= 1.15
        flags.append("long_trail")

    if distance_km < 10.0:
        std *= 1.15
        weight *= 0.75
        flags.append("short_distance")

    if point_count < 250:
        std *= 1.25
        weight *= 0.65
        flags.append("sparse_track")
    else:
        flags.append("reconstructed_track")

    if validation and validation.potential_gain_min_low is not None:
        flags.append("potential_gain_low_recorded")
    if validation and validation.potential_gain_min_high is not None:
        flags.append("potential_gain_high_recorded")

    return std, weight, flags


def _select_performance_envelope(
    observations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep trail observations that represent predictive performance.

    Training trails are often intentionally easy. Averaging them would model
    the athlete's training habits, not what they can reasonably predict for a
    race. V3 therefore uses a lower-cost performance envelope for non-official
    history: the fastest ~35% of historical trail residuals, with a minimum of
    three observations when available. Official clean/normalised references are
    always kept.
    """
    if not observations:
        return []

    official_categories = {"official_clean", "official_normalized"}
    official = [
        obs for obs in observations if str(obs.get("category") or "") in official_categories
    ]
    training = [
        obs for obs in observations if str(obs.get("category") or "") not in official_categories
    ]

    if not training:
        return official

    training_sorted = sorted(training, key=lambda obs: float(obs.get("mean") or 9.0))
    keep_count = max(3, int(math.ceil(len(training_sorted) * 0.35)))
    keep_count = min(len(training_sorted), keep_count)
    envelope = training_sorted[:keep_count]
    for obs in envelope:
        flags = list(obs.get("quality_flags") or [])
        if "performance_envelope" not in flags:
            flags.append("performance_envelope")
        obs["quality_flags"] = flags
    return official + envelope


def _activity_to_gpx(activity: Activity) -> tuple[str | None, int]:
    streams = _normalize_streams(activity.streams_data)
    if streams is None:
        return None, 0
    latlng = _stream_array(streams, "latlng")
    altitude = _stream_array(streams, "altitude")
    if not latlng or not altitude:
        return None, 0
    n = min(len(latlng), len(altitude))
    if n < 20:
        return None, 0

    # Keep runtime bounded; GPX shape is preserved well enough for the
    # surface-factor residual with <= 1500 points.
    stride = max(1, n // 1500)
    points: list[str] = []
    for index in range(0, n, stride):
        coord = latlng[index]
        if not isinstance(coord, (list, tuple)) or len(coord) < 2:
            continue
        try:
            lat = float(coord[0])
            lon = float(coord[1])
            ele = float(altitude[index])
        except (TypeError, ValueError, IndexError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        points.append(f'<trkpt lat="{lat:.8f}" lon="{lon:.8f}"><ele>{ele:.2f}</ele></trkpt>')

    if len(points) < 20:
        return None, len(points)
    gpx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="agon-v3-trail-history">'
        "<trk><name>historical_activity</name><trkseg>"
        + "".join(points)
        + "</trkseg></trk></gpx>"
    )
    return gpx, len(points)


def _validation_index(
    session: Session,
    user_id: UUID,
    activity_ids: set[UUID],
) -> dict[UUID, RaceValidationReference]:
    if not activity_ids:
        return {}
    rows = session.exec(
        select(RaceValidationReference).where(
            RaceValidationReference.user_id == user_id,
            RaceValidationReference.activity_id.in_(activity_ids),
        )
    ).all()
    return {row.activity_id: row for row in rows}


def _is_trail_activity(activity: Activity) -> bool:
    if not _is_running_activity(activity):
        return False
    effective_type = activity.activity_type_override or activity.activity_type
    if effective_type is not None:
        value = effective_type.value if hasattr(effective_type, "value") else str(effective_type)
        if value == ActivityType.TRAIL_RUN.value:
            return True
    distance_km = float(activity.distance or 0) / 1000.0
    if distance_km <= 0:
        return False
    elevation_per_km = float(activity.total_elevation_gain or 0) / distance_km
    return elevation_per_km >= TRAIL_ELEVATION_PER_KM_THRESHOLD


def _is_running_activity(activity: Activity) -> bool:
    effective_type = activity.activity_type_override or activity.activity_type
    if effective_type is None:
        return False
    value = effective_type.value if hasattr(effective_type, "value") else str(effective_type)
    return value in {
        ActivityType.RUN.value,
        ActivityType.TRAIL_RUN.value,
        getattr(ActivityType, "VIRTUAL_RUN", ActivityType.RUN).value
        if hasattr(getattr(ActivityType, "VIRTUAL_RUN", None), "value")
        else "VirtualRun",
    }


def _normalize_streams(raw: Any) -> Optional[dict[str, Any]]:
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


def _stream_array(streams: dict[str, Any], key: str) -> list[Any]:
    value = streams.get(key)
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    return value if isinstance(value, list) else []


def _activity_label(activity: Activity) -> str:
    name = activity.name or "Activity"
    iso_date = activity.start_date.date().isoformat() if activity.start_date else "?"
    return f"activity:{name}@{iso_date}"


def _inc(debug: dict[str, Any], reason: str) -> None:
    reasons = debug.setdefault("excluded_reasons", {})
    reasons[reason] = int(reasons.get(reason, 0)) + 1


__all__ = ["build_user_trail_factor_observations"]
