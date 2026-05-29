"""Rapprochement des imports représentant une même activité réelle."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import inspect as sqlalchemy_inspect, or_
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.domain.entities.activity import Activity
from app.domain.entities.activity_weather import ActivityWeather
from app.domain.entities.enrichment_queue import EnrichmentQueue
from app.domain.entities.fit_metrics import FitMetrics
from app.domain.entities.segment import Segment
from app.domain.entities.segment_features import SegmentFeatures
from app.domain.entities.workout_plan import WorkoutPlan

logger = logging.getLogger(__name__)

DEDUP_TIME_TOLERANCE_S = 300
DEDUP_DISTANCE_TOLERANCE_M = 200

_STRAVA_DETAIL_FIELDS = (
    "description",
    "calories",
    "workout_type",
    "trainer",
    "commute",
    "manual",
    "suffer_score",
    "average_watts",
    "max_watts",
    "weighted_average_watts",
    "kilojoules",
    "start_latlng",
    "end_latlng",
    "summary_polyline",
    "polyline",
    "gear_id",
    "location_city",
    "location_country",
    "timezone",
)
_GARMIN_STREAM_KEYS = {
    "stance_time",
    "vertical_oscillation",
    "step_length",
    "vertical_ratio",
}


def _normalise_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Return the UTC-naive form used by existing Activity timestamps."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def activity_time_candidates(
    start_date: Optional[datetime],
    start_date_local: Optional[datetime] = None,
) -> list[datetime]:
    """Build unique UTC/local timestamps suitable for cross-source matching."""
    candidates: list[datetime] = []
    for value in (start_date, start_date_local):
        normalised = _normalise_datetime(value)
        if normalised is not None and normalised not in candidates:
            candidates.append(normalised)
    return candidates


def find_unlinked_provider_activity(
    session: Session,
    user_id: UUID,
    *,
    provider: str,
    start_date: datetime,
    distance: float,
    start_date_local: Optional[datetime] = None,
    exclude_activity_id: Optional[UUID] = None,
) -> Optional[Activity]:
    """Find a unique unlinked row from the other provider for one workout."""
    timestamps = activity_time_candidates(start_date, start_date_local)
    if not timestamps:
        return None

    windows = []
    for candidate in timestamps:
        lower = candidate - timedelta(seconds=DEDUP_TIME_TOLERANCE_S)
        upper = candidate + timedelta(seconds=DEDUP_TIME_TOLERANCE_S)
        windows.extend(
            [
                Activity.start_date.between(lower, upper),
                Activity.start_date_local.between(lower, upper),
            ]
        )

    query = select(Activity).where(
        Activity.user_id == user_id,
        Activity.distance.between(
            distance - DEDUP_DISTANCE_TOLERANCE_M,
            distance + DEDUP_DISTANCE_TOLERANCE_M,
        ),
        or_(*windows),
    )
    if provider == "strava":
        query = query.where(
            Activity.strava_id.is_not(None),
            Activity.garmin_activity_id.is_(None),
        )
    elif provider == "garmin":
        query = query.where(
            Activity.garmin_activity_id.is_not(None),
            Activity.strava_id.is_(None),
        )
    else:
        raise ValueError(f"Unknown activity provider: {provider}")
    if exclude_activity_id is not None:
        query = query.where(Activity.id != exclude_activity_id)

    candidates = session.exec(query).all()
    if not candidates:
        return None

    def score(activity: Activity) -> tuple[float, float]:
        activity_times = activity_time_candidates(
            activity.start_date, activity.start_date_local
        )
        time_delta = min(
            abs((actual - expected).total_seconds())
            for actual in activity_times
            for expected in timestamps
        )
        return (time_delta, abs((activity.distance or 0.0) - distance))

    candidates.sort(key=score)
    if len(candidates) > 1 and score(candidates[0]) == score(candidates[1]):
        logger.warning(
            "Rapprochement %s ambigu pour user_id=%s start_date=%s distance=%s",
            provider,
            user_id,
            start_date,
            distance,
        )
        return None
    return candidates[0]


def attach_strava_data(
    activity: Activity,
    incoming: Any,
    *,
    include_identity: bool = True,
) -> None:
    """Attach a Strava identity and non-destructive presentation details."""
    if include_identity:
        activity.strava_id = incoming.strava_id
    for field_name in _STRAVA_DETAIL_FIELDS:
        value = getattr(incoming, field_name, None)
        if value is not None and getattr(activity, field_name, None) is None:
            setattr(activity, field_name, value)
    activity.updated_at = datetime.utcnow()


def _merge_streams(garmin_streams: Any, strava_streams: Any) -> Any:
    if not strava_streams:
        return garmin_streams
    if not garmin_streams:
        return strava_streams

    merged = dict(strava_streams)
    for key, value in dict(garmin_streams).items():
        if key not in merged or key in _GARMIN_STREAM_KEYS:
            merged[key] = value
    return merged


def _table_exists(session: Session, model: type) -> bool:
    return sqlalchemy_inspect(session.connection()).has_table(model.__tablename__)


def _merge_unique_relation(
    session: Session,
    model: type,
    primary_id: UUID,
    duplicate_id: UUID,
) -> None:
    if not _table_exists(session, model):
        return
    primary_row = session.exec(
        select(model).where(model.activity_id == primary_id)
    ).first()
    duplicate_row = session.exec(
        select(model).where(model.activity_id == duplicate_id)
    ).first()
    if duplicate_row is None:
        return
    if primary_row is not None:
        session.delete(duplicate_row)
    else:
        duplicate_row.activity_id = primary_id
        session.add(duplicate_row)


def _move_many_relation(
    session: Session,
    model: type,
    primary_id: UUID,
    duplicate_id: UUID,
    field_name: str = "activity_id",
) -> None:
    if not _table_exists(session, model):
        return
    field = getattr(model, field_name)
    for row in session.exec(
        select(model).where(field == duplicate_id)
    ).all():
        setattr(row, field_name, primary_id)
        session.add(row)


def _merge_segment_relations(
    session: Session,
    primary_id: UUID,
    duplicate_id: UUID,
) -> None:
    if not _table_exists(session, Segment):
        return
    primary_segments = session.exec(
        select(Segment).where(Segment.activity_id == primary_id)
    ).all()
    duplicate_segments = session.exec(
        select(Segment).where(Segment.activity_id == duplicate_id)
    ).all()
    duplicate_features = []
    if _table_exists(session, SegmentFeatures):
        duplicate_features = session.exec(
            select(SegmentFeatures).where(SegmentFeatures.activity_id == duplicate_id)
        ).all()

    if not duplicate_segments:
        return
    if not primary_segments:
        for segment in duplicate_segments:
            segment.activity_id = primary_id
            session.add(segment)
        for feature in duplicate_features:
            feature.activity_id = primary_id
            session.add(feature)
        return

    for feature in duplicate_features:
        session.delete(feature)
    for segment in duplicate_segments:
        session.delete(segment)


def consolidate_strava_duplicate_into_garmin(
    session: Session,
    garmin_activity: Activity,
    strava_activity: Activity,
) -> Activity:
    """Merge an already duplicated Strava row into its Garmin counterpart."""
    if not garmin_activity.id or not strava_activity.id:
        raise ValueError("Persisted activities are required for consolidation")
    if not garmin_activity.garmin_activity_id or not strava_activity.strava_id:
        raise ValueError("Expected a Garmin row and a Strava row")

    strava_id = strava_activity.strava_id
    attach_strava_data(garmin_activity, strava_activity, include_identity=False)
    if strava_activity.name:
        garmin_activity.name = strava_activity.name
    if (
        garmin_activity.activity_type_override is None
        and strava_activity.activity_type_override is not None
    ):
        garmin_activity.activity_type_override = strava_activity.activity_type_override

    merged_streams = _merge_streams(
        garmin_activity.streams_data, strava_activity.streams_data
    )
    if merged_streams is not garmin_activity.streams_data:
        garmin_activity.streams_data = merged_streams
        flag_modified(garmin_activity, "streams_data")
    if not garmin_activity.laps_data and strava_activity.laps_data:
        garmin_activity.laps_data = strava_activity.laps_data
        flag_modified(garmin_activity, "laps_data")

    _merge_unique_relation(session, FitMetrics, garmin_activity.id, strava_activity.id)
    _merge_unique_relation(session, ActivityWeather, garmin_activity.id, strava_activity.id)
    _merge_segment_relations(session, garmin_activity.id, strava_activity.id)
    _move_many_relation(session, EnrichmentQueue, garmin_activity.id, strava_activity.id)
    _move_many_relation(
        session,
        WorkoutPlan,
        garmin_activity.id,
        strava_activity.id,
        field_name="actual_activity_id",
    )

    try:
        from app.domain.entities.race_prediction import (
            RacePredictionComparison,
            RaceValidationReference,
        )

        _move_many_relation(
            session, RacePredictionComparison, garmin_activity.id, strava_activity.id
        )
        _merge_unique_relation(
            session, RaceValidationReference, garmin_activity.id, strava_activity.id
        )
    except ImportError:
        pass

    session.add(garmin_activity)
    session.flush()
    session.delete(strava_activity)
    session.flush()
    garmin_activity.strava_id = strava_id
    session.add(garmin_activity)
    return garmin_activity
