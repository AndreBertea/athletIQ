"""Automatic V3 residual training.

The residual layer is deliberately simple and robust: V3 first runs the
physical Bayesian engine, then this service learns a small multiplicative
moving-time correction from the top 25% scored reference candidates in the
last year. It is not a replacement for the physics model; it only corrects
the athlete-specific bias that remains after P_ref, fatigue and trail factor
have been calibrated.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.activity import Activity
from app.domain.entities.race_prediction import (
    RacePredictorV3ResidualModel,
    RaceReferenceCandidate,
    RaceValidationReference,
)
from app.domain.services.race_predictor.reference_detection_service import (
    detect_reference_candidates,
)
from app.domain.services.race_predictor.trail_history_factor_service import (
    _activity_to_gpx,
    _is_trail_activity,
)
from app.domain.services.race_predictor.v2_3_prediction_service import predict_v2_3


MODEL_VERSION = "v3_residual_v1"
DEFAULT_HISTORY_DAYS = 366
TOP_SCORE_FRACTION = 0.25
MIN_OBSERVATIONS = 5
MAX_TRAINING_CASES = 30
NON_SCORING_CATEGORIES = {"incident_non_scoring", "execution_degraded_non_scoring"}


def train_v3_residual_model(
    session: Session,
    user_id: UUID,
    *,
    as_of_date: Optional[datetime] = None,
    history_start_date: Optional[datetime] = None,
    top_fraction: float = TOP_SCORE_FRACTION,
    auto_accept_top: bool = True,
    force_detect: bool = True,
) -> RacePredictorV3ResidualModel:
    """Train and persist the V3 residual model for one user."""
    upper = as_of_date or datetime.utcnow()
    lower = history_start_date or (upper - timedelta(days=DEFAULT_HISTORY_DAYS))
    if force_detect:
        detect_reference_candidates(
            session,
            user_id,
            history_start_date=lower,
            as_of_date=upper,
            limit=300,
            force=False,
        )

    selected = _select_top_candidate_rows(
        session,
        user_id,
        lower=lower,
        upper=upper,
        top_fraction=top_fraction,
    )
    if auto_accept_top:
        _accept_candidates_as_references(session, user_id, selected)

    observations: list[dict[str, Any]] = []
    excluded_reasons: dict[str, int] = {}
    for candidate, activity in selected[:MAX_TRAINING_CASES]:
        observation = _candidate_to_residual_observation(
            session,
            user_id,
            candidate,
            activity,
            as_of_date=upper,
            history_start_date=lower,
        )
        if observation is None:
            reason = "unusable_reference_replay"
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            continue
        observations.append(observation)

    model_data = _fit_residual_model(observations)
    model_data.update(
        {
            "model_version": MODEL_VERSION,
            "history_days": int((upper - lower).days),
            "top_fraction": float(top_fraction),
            "eligible_count": _eligible_candidate_count(
                session, user_id, lower=lower, upper=upper
            ),
            "selected_count": len(selected),
            "observation_count": len(observations),
            "excluded_reasons": excluded_reasons,
            "observations": observations,
        }
    )
    status = "active" if len(observations) >= MIN_OBSERVATIONS else "insufficient_data"
    model_data["status"] = status

    now = datetime.utcnow()
    model = session.exec(
        select(RacePredictorV3ResidualModel).where(
            RacePredictorV3ResidualModel.user_id == user_id
        )
    ).first()
    if model is None:
        model = RacePredictorV3ResidualModel(
            user_id=user_id,
            created_at=now,
        )
        session.add(model)

    model.model_version = MODEL_VERSION
    model.status = status
    model.eligible_count = int(model_data["eligible_count"])
    model.selected_count = len(selected)
    model.observation_count = len(observations)
    model.model_data = model_data
    model.history_start_date = lower
    model.history_end_date = upper
    model.trained_at = now
    model.updated_at = now
    session.commit()
    session.refresh(model)
    return model


def get_or_train_v3_residual_model(
    session: Session,
    user_id: UUID,
    *,
    as_of_date: Optional[datetime] = None,
    history_start_date: Optional[datetime] = None,
) -> RacePredictorV3ResidualModel:
    """Return a fresh-enough residual model, training on demand if needed."""
    upper = as_of_date or datetime.utcnow()
    lower = history_start_date or (upper - timedelta(days=DEFAULT_HISTORY_DAYS))
    model = session.exec(
        select(RacePredictorV3ResidualModel).where(
            RacePredictorV3ResidualModel.user_id == user_id
        )
    ).first()
    if model is None:
        return train_v3_residual_model(
            session,
            user_id,
            as_of_date=upper,
            history_start_date=lower,
        )
    if model.history_start_date and model.history_start_date > lower + timedelta(days=7):
        return train_v3_residual_model(
            session,
            user_id,
            as_of_date=upper,
            history_start_date=lower,
        )
    if model.trained_at < upper - timedelta(hours=12):
        return train_v3_residual_model(
            session,
            user_id,
            as_of_date=upper,
            history_start_date=lower,
        )
    return model


def apply_v3_residual_correction(
    result: dict[str, Any],
    model: RacePredictorV3ResidualModel | None,
) -> dict[str, Any]:
    """Apply a trained residual factor to a V3 prediction response."""
    trace = _model_trace(model)
    if model is None or model.status != "active":
        result.setdefault("hybrid_model", {})["residual_correction"] = trace
        result.setdefault("debug_trace", {}).setdefault("hybrid_model", {})[
            "residual_correction"
        ] = trace
        return result

    model_data = model.model_data or {}
    analysis_mode = str(result.get("analysis_mode") or "").lower()
    factor = float(model_data.get("global_factor") or 1.0)
    factor_source = "global_factor"
    if analysis_mode == "trail" and model_data.get("trail_factor") is not None:
        factor = float(model_data["trail_factor"])
        factor_source = "trail_factor"
    elif analysis_mode == "route" and model_data.get("route_factor") is not None:
        factor = float(model_data["route_factor"])
        factor_source = "route_factor"

    factor = max(0.85, min(1.18, factor))
    if abs(factor - 1.0) < 0.005:
        trace.update({"applied": False, "applied_factor": 1.0, "factor_source": factor_source})
        result.setdefault("hybrid_model", {})["residual_correction"] = trace
        result.setdefault("debug_trace", {}).setdefault("hybrid_model", {})[
            "residual_correction"
        ] = trace
        return result

    original_moving = float(result.get("moving_time_min") or 0)
    original_pause = float(result.get("total_pause_min") or 0)
    corrected_moving = original_moving * factor
    corrected_total = corrected_moving + original_pause
    distance = float(result.get("total_distance_km") or 0)

    result["moving_time_min"] = round(corrected_moving, 1)
    result["moving_time_formatted"] = _format_minutes(corrected_moving)
    result["total_time_min"] = round(corrected_total, 1)
    result["total_time_formatted"] = _format_minutes(corrected_total)
    if distance > 0:
        result["avg_moving_pace"] = round(corrected_moving / distance, 2)
        result["avg_pace"] = round(corrected_total / distance, 2)

    summary = result.get("summary")
    if isinstance(summary, dict):
        summary["moving_time_min"] = result["moving_time_min"]
        summary["moving_time_formatted"] = result["moving_time_formatted"]
        summary["total_time_min"] = result["total_time_min"]
        summary["total_time_formatted"] = result["total_time_formatted"]
        if distance > 0:
            summary["avg_moving_pace"] = result["avg_moving_pace"]
            summary["avg_pace"] = result["avg_pace"]
        for key in ("p10_total_time_min", "p50_total_time_min", "p90_total_time_min"):
            if isinstance(summary.get(key), (int, float)):
                summary[key] = round(float(summary[key]) * factor, 2)

    uncertainty = result.get("uncertainty")
    if isinstance(uncertainty, dict):
        _scale_uncertainty_block(uncertainty.get("moving_time"), factor)
        _scale_uncertainty_block(uncertainty.get("total_time"), factor)

    for segment in result.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        distance_km = float(segment.get("distance_km") or segment.get("end_km") or 0)
        for key in ("predicted_time_min", "segment_time_min", "time_min"):
            if isinstance(segment.get(key), (int, float)):
                segment[key] = round(float(segment[key]) * factor, 3)
        for key in ("predicted_pace", "pace_min_per_km"):
            if distance_km > 0 and isinstance(segment.get("predicted_time_min"), (int, float)):
                segment[key] = round(float(segment["predicted_time_min"]) / distance_km, 3)

    trace.update(
        {
            "applied": True,
            "applied_factor": round(factor, 4),
            "factor_source": factor_source,
            "moving_delta_min": round(corrected_moving - original_moving, 1),
        }
    )
    result.setdefault("hybrid_model", {})["residual_correction"] = trace
    debug_trace = result.setdefault("debug_trace", {})
    debug_trace.setdefault("hybrid_model", {})["residual_correction"] = trace
    debug_trace["v3_residual_model"] = trace
    warnings = result.setdefault("warnings", [])
    warnings.append(
        f"V3 residual correction appliquee ({factor_source}={factor:.3f}) "
        f"depuis {model.observation_count} reference(s) auto top 25%."
    )
    return result


def _select_top_candidate_rows(
    session: Session,
    user_id: UUID,
    *,
    lower: datetime,
    upper: datetime,
    top_fraction: float,
) -> list[tuple[RaceReferenceCandidate, Activity]]:
    rows = session.exec(
        select(RaceReferenceCandidate, Activity)
        .join(Activity, Activity.id == RaceReferenceCandidate.activity_id)
        .where(
            RaceReferenceCandidate.user_id == user_id,
            RaceReferenceCandidate.status != "rejected",
            RaceReferenceCandidate.suggested_category.notin_(NON_SCORING_CATEGORIES),
            Activity.start_date >= lower,
            Activity.start_date < upper,
        )
        .order_by(RaceReferenceCandidate.score.desc(), Activity.start_date.desc())
    ).all()
    if not rows:
        return []
    keep = max(1, int(math.ceil(len(rows) * max(0.05, min(1.0, top_fraction)))))
    return list(rows[:keep])


def _eligible_candidate_count(
    session: Session,
    user_id: UUID,
    *,
    lower: datetime,
    upper: datetime,
) -> int:
    return len(
        session.exec(
            select(RaceReferenceCandidate.id)
            .join(Activity, Activity.id == RaceReferenceCandidate.activity_id)
            .where(
                RaceReferenceCandidate.user_id == user_id,
                RaceReferenceCandidate.status != "rejected",
                RaceReferenceCandidate.suggested_category.notin_(NON_SCORING_CATEGORIES),
                Activity.start_date >= lower,
                Activity.start_date < upper,
            )
        ).all()
    )


def _accept_candidates_as_references(
    session: Session,
    user_id: UUID,
    rows: list[tuple[RaceReferenceCandidate, Activity]],
) -> None:
    now = datetime.utcnow()
    changed = False
    for candidate, activity in rows:
        if activity.id is None:
            continue
        reference = session.exec(
            select(RaceValidationReference).where(
                RaceValidationReference.user_id == user_id,
                RaceValidationReference.activity_id == activity.id,
            )
        ).first()
        if reference is None:
            reference = RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category=candidate.suggested_category,
                notes="Auto V3 top 25% score reference",
                potential_gain_min_low=candidate.potential_gain_min_low,
                potential_gain_min_high=candidate.potential_gain_min_high,
                created_at=now,
                updated_at=now,
            )
            session.add(reference)
            changed = True
        if candidate.status != "accepted":
            candidate.status = "accepted"
            candidate.updated_at = now
            session.add(candidate)
            changed = True
    if changed:
        session.commit()


def _candidate_to_residual_observation(
    session: Session,
    user_id: UUID,
    candidate: RaceReferenceCandidate,
    activity: Activity,
    *,
    as_of_date: datetime,
    history_start_date: datetime,
) -> dict[str, Any] | None:
    if activity.id is None:
        return None
    gpx_text, point_count = _activity_to_gpx(activity)
    if not gpx_text or point_count < 20:
        return None
    real_moving_min = float(activity.moving_time or 0) / 60.0
    if real_moving_min < 20:
        return None
    try:
        base = predict_v2_3(
            session,
            user_id,
            gpx_text,
            race_datetime=activity.start_date,
            effort_mode="steady",
            analysis_mode="trail" if _is_trail_activity(activity) else "route",
            target_heartrate=None,
            weather_mode="manual",
            manual_temperature_c=11.0,
            ravito_mode="auto",
            custom_ravitos=None,
            as_of_date=as_of_date,
            excluded_activity_ids={activity.id},
            history_start_date=history_start_date,
            filename=activity.name,
            evidence_policy="weighted_sparse",
        )
    except Exception:
        return None

    predicted_moving_min = float(base.get("moving_time_min") or 0)
    if predicted_moving_min <= 0:
        return None
    ratio = real_moving_min / predicted_moving_min
    if not math.isfinite(ratio) or not (0.65 <= ratio <= 1.45):
        return None

    category = str(candidate.suggested_category or "training_control")
    score = float(candidate.score or 0)
    weight = max(0.2, min(1.4, score / 75.0))
    if category == "official_clean":
        weight *= 1.15
    elif category == "official_normalized":
        weight *= 0.95
    elif category == "training_control":
        weight *= 0.75

    return {
        "activity_id": str(activity.id),
        "name": activity.name,
        "date": activity.start_date.isoformat() if activity.start_date else None,
        "category": category,
        "score": round(score, 1),
        "mode": "trail" if _is_trail_activity(activity) else "route",
        "distance_km": round(float(activity.distance or 0) / 1000.0, 2),
        "elevation_gain_m": round(float(activity.total_elevation_gain or 0), 1),
        "real_moving_min": round(real_moving_min, 2),
        "predicted_moving_min": round(predicted_moving_min, 2),
        "ratio": round(ratio, 5),
        "weight": round(weight, 4),
        "point_count": point_count,
    }


def _fit_residual_model(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        return {
            "global_factor": 1.0,
            "trail_factor": None,
            "route_factor": None,
            "confidence": "none",
        }

    global_factor = _weighted_median(
        [(float(obs["ratio"]), float(obs["weight"])) for obs in observations]
    )
    trail_obs = [obs for obs in observations if obs.get("mode") == "trail"]
    route_obs = [obs for obs in observations if obs.get("mode") == "route"]
    trail_factor = (
        _weighted_median([(float(obs["ratio"]), float(obs["weight"])) for obs in trail_obs])
        if len(trail_obs) >= 4
        else None
    )
    route_factor = (
        _weighted_median([(float(obs["ratio"]), float(obs["weight"])) for obs in route_obs])
        if len(route_obs) >= 4
        else None
    )
    abs_errors = [abs(float(obs["ratio"]) - global_factor) for obs in observations]
    dispersion = _median(abs_errors) if abs_errors else 0.0
    confidence = (
        "high"
        if len(observations) >= 15 and dispersion <= 0.06
        else "medium"
        if len(observations) >= MIN_OBSERVATIONS
        else "low"
    )
    return {
        "global_factor": round(max(0.85, min(1.18, global_factor)), 5),
        "trail_factor": round(max(0.85, min(1.18, trail_factor)), 5)
        if trail_factor is not None
        else None,
        "route_factor": round(max(0.85, min(1.18, route_factor)), 5)
        if route_factor is not None
        else None,
        "confidence": confidence,
        "ratio_dispersion_mad": round(dispersion, 5),
    }


def _weighted_median(values: list[tuple[float, float]]) -> float:
    clean = sorted(
        [(value, max(0.0, weight)) for value, weight in values if math.isfinite(value)],
        key=lambda item: item[0],
    )
    total = sum(weight for _, weight in clean)
    if not clean or total <= 0:
        return 1.0
    cursor = 0.0
    for value, weight in clean:
        cursor += weight
        if cursor >= total / 2:
            return value
    return clean[-1][0]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _scale_uncertainty_block(block: Any, factor: float) -> None:
    if not isinstance(block, dict):
        return
    for key in ("p10", "p50", "p90"):
        if isinstance(block.get(key), (int, float)):
            block[key] = round(float(block[key]) * factor, 2)


def _model_trace(model: RacePredictorV3ResidualModel | None) -> dict[str, Any]:
    if model is None:
        return {
            "model": MODEL_VERSION,
            "status": "missing",
            "applied": False,
            "applied_factor": 1.0,
            "required_references": MIN_OBSERVATIONS,
            "eligible_references": 0,
        }
    data = model.model_data or {}
    public_status = (
        "inactive_insufficient_qualified_references"
        if model.status == "insufficient_data"
        else model.status
    )
    return {
        "model": MODEL_VERSION,
        "status": public_status,
        "applied": False,
        "applied_factor": 1.0,
        "required_references": MIN_OBSERVATIONS,
        "eligible_references": int(model.observation_count or 0),
        "selected_count": int(model.selected_count or 0),
        "eligible_count": int(model.eligible_count or 0),
        "confidence": data.get("confidence"),
        "global_factor": data.get("global_factor"),
        "trail_factor": data.get("trail_factor"),
        "route_factor": data.get("route_factor"),
        "trained_at": model.trained_at.isoformat() if model.trained_at else None,
        "top_fraction": data.get("top_fraction", TOP_SCORE_FRACTION),
    }


def _format_minutes(minutes: float) -> str:
    if not math.isfinite(minutes) or minutes <= 0:
        return "--"
    hours = int(minutes // 60)
    mins = int(round(minutes % 60))
    if mins == 60:
        hours += 1
        mins = 0
    if hours <= 0:
        return f"{mins} min"
    return f"{hours}h{mins:02d}"


__all__ = [
    "train_v3_residual_model",
    "get_or_train_v3_residual_model",
    "apply_v3_residual_correction",
    "MODEL_VERSION",
]
