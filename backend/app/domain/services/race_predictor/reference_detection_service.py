"""Automatic race-reference candidate detection.

The detector is intentionally conservative: it proposes candidates with a
score and a suggested category, but it does not create
``RaceValidationReference`` rows by itself. A human can accept, normalize or
reject the candidate from Analytics.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.entities.race_prediction import (
    RaceReferenceCandidate,
    RaceValidationReference,
)


POSITIVE_NAME_TERMS = {
    "race",
    "course",
    "trail",
    "marathon",
    "semi",
    "10k",
    "5k",
    "utmj",
    "canyon",
    "relais",
    "foulee",
    "foulée",
}
NEGATIVE_NAME_TERMS = {
    "easy",
    "recovery",
    "recup",
    "récup",
    "footing",
    "endurance",
    "warm",
    "echauffement",
    "échauffement",
    "rando",
    "walk",
    "marche",
    "reprise",
    "blessure",
}
INCIDENT_TERMS = {
    "crampe",
    "crampes",
    "blessure",
    "douleur",
    "abandon",
    "chute",
    "incident",
    "malade",
}


@dataclass(frozen=True)
class CandidateDecision:
    category: str
    confidence: str
    score: float
    reasons: dict[str, Any]
    features: dict[str, Any]
    potential_gain_min_low: float | None = None
    potential_gain_min_high: float | None = None


def detect_reference_candidates(
    session: Session,
    user_id: UUID,
    *,
    history_start_date: Optional[datetime] = None,
    as_of_date: Optional[datetime] = None,
    limit: int = 200,
    force: bool = False,
) -> list[RaceReferenceCandidate]:
    """Detect and upsert race-reference candidates for one user."""
    now = datetime.utcnow()
    upper = as_of_date or now
    lower = history_start_date or (upper - timedelta(days=366 * 3))

    existing_candidates = {
        candidate.activity_id: candidate
        for candidate in session.exec(
            select(RaceReferenceCandidate).where(
                RaceReferenceCandidate.user_id == user_id
            )
        ).all()
    }
    existing_references = {
        reference.activity_id
        for reference in session.exec(
            select(RaceValidationReference).where(
                RaceValidationReference.user_id == user_id
            )
        ).all()
    }

    activities = list(
        session.exec(
            select(Activity)
            .where(
                Activity.user_id == user_id,
                Activity.source == ActivitySource.GARMIN.value,
                Activity.start_date >= lower,
                Activity.start_date < upper,
            )
            .order_by(Activity.start_date.desc())
            .limit(limit)
        ).all()
    )
    fcmax_estimate = _estimate_fcmax(activities)
    updated: list[RaceReferenceCandidate] = []
    for activity in activities:
        if activity.id is None or activity.id in existing_references:
            continue
        existing = existing_candidates.get(activity.id)
        if existing is not None and existing.status != "pending" and not force:
            continue
        decision = score_activity_as_reference(activity, fcmax_estimate=fcmax_estimate)
        if decision.score < 35 and decision.category != "incident_non_scoring":
            continue
        if existing is None:
            existing = RaceReferenceCandidate(
                user_id=user_id,
                activity_id=activity.id,
                created_at=now,
            )
            session.add(existing)
        existing.suggested_category = decision.category
        existing.confidence = decision.confidence
        existing.score = round(decision.score, 1)
        existing.status = "pending"
        existing.reasons = decision.reasons
        existing.features = decision.features
        existing.potential_gain_min_low = decision.potential_gain_min_low
        existing.potential_gain_min_high = decision.potential_gain_min_high
        existing.updated_at = now
        updated.append(existing)

    session.commit()
    for candidate in updated:
        session.refresh(candidate)
    return sorted(updated, key=lambda candidate: candidate.score, reverse=True)


def score_activity_as_reference(
    activity: Activity,
    *,
    fcmax_estimate: float | None = None,
) -> CandidateDecision:
    """Return the automatic candidate category and score for an activity."""
    features = _activity_features(activity, fcmax_estimate=fcmax_estimate)
    reasons: dict[str, Any] = {"positive": [], "negative": [], "anomalies": []}

    if not features["is_running"]:
        return CandidateDecision(
            category="unclassified",
            confidence="low",
            score=0.0,
            reasons={"negative": ["non_running_activity"]},
            features=features,
        )

    score = 0.0

    if features["has_event_name"]:
        score += 24
        reasons["positive"].append("event_like_name")
    if features["has_negative_name"]:
        score -= 20
        reasons["negative"].append("training_or_recovery_name")
    if features["typical_race_distance"]:
        score += 14
        reasons["positive"].append("typical_race_distance")
    if features["is_trail_like"]:
        score += 8
        reasons["positive"].append("trail_profile")
    if features["streams_complete"]:
        score += 12
        reasons["positive"].append("complete_garmin_streams")
    if features["hr_intensity"] is not None:
        if features["hr_intensity"] >= 0.82:
            score += 15
            reasons["positive"].append("high_hr_intensity")
        elif features["hr_intensity"] >= 0.74:
            score += 8
            reasons["positive"].append("moderate_hr_intensity")
        else:
            score -= 8
            reasons["negative"].append("low_hr_intensity")
    if features["duration_min"] >= 45:
        score += 8
        reasons["positive"].append("meaningful_duration")
    if features["moving_speed_percentile"] is not None and features["moving_speed_percentile"] >= 0.70:
        score += 10
        reasons["positive"].append("fast_for_user_history")

    long_pause = bool(features["pause_min"] >= max(8.0, features["duration_min"] * 0.06))
    severe_fade = bool(features["late_speed_ratio"] is not None and features["late_speed_ratio"] < 0.72)
    if features["has_incident_name"]:
        score -= 30
        reasons["anomalies"].append("incident_keyword")
    if long_pause:
        score -= 14
        reasons["anomalies"].append("long_pause_detected")
    if severe_fade:
        score -= 16
        reasons["anomalies"].append("severe_late_fade")

    score = max(0.0, min(100.0, score))

    category = "training_control"
    potential_low = None
    potential_high = None
    if features["has_incident_name"] and score < 50:
        category = "incident_non_scoring"
    elif score >= 68 and (long_pause or severe_fade):
        category = "official_normalized"
        if long_pause:
            potential_low = round(max(3.0, features["pause_min"] * 0.45), 1)
            potential_high = round(max(potential_low + 2.0, features["pause_min"] * 0.85), 1)
    elif score >= 62:
        category = "official_clean"
    elif score >= 42:
        category = "training_control"

    confidence = "high" if score >= 72 else "medium" if score >= 50 else "low"
    return CandidateDecision(
        category=category,
        confidence=confidence,
        score=score,
        reasons=reasons,
        features=features,
        potential_gain_min_low=potential_low,
        potential_gain_min_high=potential_high,
    )


def _activity_features(activity: Activity, *, fcmax_estimate: float | None) -> dict[str, Any]:
    name = (activity.name or "").lower()
    description = (activity.description or "").lower()
    text = f"{name} {description}"
    distance_m = float(activity.distance or 0)
    distance_km = distance_m / 1000.0 if distance_m > 0 else 0.0
    moving_s = float(activity.moving_time or 0)
    elapsed_s = float(activity.elapsed_time or moving_s or 0)
    duration_min = moving_s / 60.0 if moving_s > 0 else 0.0
    pause_min = max(0.0, elapsed_s - moving_s) / 60.0
    elevation_gain = float(activity.total_elevation_gain or 0)
    elevation_per_km = elevation_gain / distance_km if distance_km > 0 else 0.0
    average_speed = (
        float(activity.average_speed)
        if activity.average_speed is not None
        else (distance_m / moving_s if moving_s > 0 else 0.0)
    )
    hr_intensity = None
    if activity.average_heartrate and fcmax_estimate and fcmax_estimate > 0:
        hr_intensity = float(activity.average_heartrate) / float(fcmax_estimate)

    streams = _normalize_streams(activity.streams_data)
    late_speed_ratio = _late_speed_ratio(streams)
    has_latlng = bool(_stream_array(streams, "latlng")) if streams else False
    has_altitude = bool(_stream_array(streams, "altitude")) if streams else False
    has_hr = bool(_stream_array(streams, "heartrate")) if streams else False
    has_speed = bool(_stream_array(streams, "velocity_smooth")) if streams else False

    effective_type = activity.activity_type_override or activity.activity_type
    sport = effective_type.value if hasattr(effective_type, "value") else str(effective_type)
    is_running = sport in {ActivityType.RUN.value, ActivityType.TRAIL_RUN.value, ActivityType.VIRTUAL_RUN.value}
    is_trail_like = sport == ActivityType.TRAIL_RUN.value or elevation_per_km >= 15.0

    return {
        "activity_id": str(activity.id) if activity.id else None,
        "name": activity.name,
        "sport_type": sport,
        "start_date": activity.start_date.isoformat() if activity.start_date else None,
        "distance_km": round(distance_km, 2),
        "duration_min": round(duration_min, 1),
        "elapsed_min": round(elapsed_s / 60.0, 1) if elapsed_s else None,
        "pause_min": round(pause_min, 1),
        "elevation_gain_m": round(elevation_gain, 1),
        "elevation_per_km": round(elevation_per_km, 1),
        "average_speed_mps": round(average_speed, 3),
        "average_heartrate": activity.average_heartrate,
        "hr_intensity": round(hr_intensity, 3) if hr_intensity is not None else None,
        "is_running": is_running,
        "is_trail_like": is_trail_like,
        "has_event_name": any(term in text for term in POSITIVE_NAME_TERMS),
        "has_negative_name": any(term in text for term in NEGATIVE_NAME_TERMS),
        "has_incident_name": any(term in text for term in INCIDENT_TERMS),
        "typical_race_distance": _is_typical_race_distance(distance_km, is_trail_like),
        "streams_complete": has_latlng and has_altitude and has_hr and has_speed,
        "late_speed_ratio": round(late_speed_ratio, 3) if late_speed_ratio is not None else None,
        "moving_speed_percentile": None,
    }


def _estimate_fcmax(activities: list[Activity]) -> float | None:
    values = [float(a.max_heartrate) for a in activities if a.max_heartrate and 110 <= a.max_heartrate <= 218]
    if not values:
        return None
    values.sort()
    idx = min(len(values) - 1, max(0, int(len(values) * 0.95)))
    return values[idx]


def _is_typical_race_distance(distance_km: float, is_trail_like: bool) -> bool:
    if distance_km <= 0:
        return False
    road_targets = [5.0, 10.0, 21.1, 42.2]
    if any(abs(distance_km - target) <= max(0.6, target * 0.06) for target in road_targets):
        return True
    if is_trail_like and distance_km >= 8.0:
        return True
    return False


def _late_speed_ratio(streams: dict[str, Any] | None) -> float | None:
    if not streams:
        return None
    velocity = [float(v) for v in _stream_array(streams, "velocity_smooth") if v is not None]
    if len(velocity) < 300:
        return None
    n = len(velocity)
    early = sorted(v for v in velocity[int(n * 0.15): int(n * 0.35)] if 0.5 <= v <= 8.0)
    late = sorted(v for v in velocity[int(n * 0.75): int(n * 0.95)] if 0.5 <= v <= 8.0)
    if len(early) < 30 or len(late) < 30:
        return None
    return _median(late) / max(0.1, _median(early))


def _median(values: list[float]) -> float:
    values = sorted(values)
    n = len(values)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


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


def _stream_array(streams: dict[str, Any] | None, key: str) -> list[Any]:
    if not streams:
        return []
    value = streams.get(key)
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    return value if isinstance(value, list) else []


def candidate_to_dict(
    candidate: RaceReferenceCandidate,
    activity: Activity | None = None,
) -> dict[str, Any]:
    data = {
        "id": str(candidate.id),
        "activity_id": str(candidate.activity_id),
        "suggested_category": candidate.suggested_category,
        "confidence": candidate.confidence,
        "score": candidate.score,
        "status": candidate.status,
        "reasons": candidate.reasons,
        "features": candidate.features,
        "notes": candidate.notes,
        "potential_gain_min_low": candidate.potential_gain_min_low,
        "potential_gain_min_high": candidate.potential_gain_min_high,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }
    if activity is not None:
        data["activity"] = {
            "id": str(activity.id),
            "name": activity.name,
            "start_date": activity.start_date.isoformat(),
            "distance_km": round(float(activity.distance or 0) / 1000.0, 2),
            "moving_time_min": round(float(activity.moving_time or 0) / 60.0, 1),
            "elevation_gain_m": activity.total_elevation_gain,
        }
    return data


__all__ = [
    "detect_reference_candidates",
    "score_activity_as_reference",
    "candidate_to_dict",
]
