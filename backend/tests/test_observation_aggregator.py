"""Tests for observation_aggregator (Race Predictor V2.3.1).

These tests assert:

- the non-negotiable chronological backtest contract (as_of_date is a strict
  upper bound, excluded_activity_ids are removed, non-scoring activities never
  contribute to capacity-like parameters);
- the V2.3.1 contract on the observation dictionary key set, which exposes
  ``p_ref_steady_wkg`` (canonical engine input) and ``p_capacity_test_wkg``
  (informative-only, fed by ReferenceTest);
- the V2.3.1 extraction rule for ``p_ref_steady_wkg``: median of flat-road
  speed inside a narrow FC band, converted to power via the Minetti cost
  (no Daniels VDOT inversion on historical activities);
- the Daniels VDOT inversion is still applied to reference tests (5K / 10K)
  but feeds ``p_capacity_test_wkg`` only (not ``p_ref_steady_wkg``).

Each test uses an isolated SQLite in-memory database via the ``session``
fixture so no developer database is touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

# Importing the entities package triggers all SQLModel.metadata registrations
# so the in-memory database has every table available.
from app.domain.entities import (  # noqa: F401
    Activity,
    AthleticProfile,
    RaceValidationReference,
    ReferenceTest,
    ReferenceTestQuality,
    ReferenceTestSurface,
    ReferenceTestType,
    User,
)
from app.domain.entities.activity import ActivityType
from app.domain.services.race_predictor.observation_aggregator import (
    aggregate_observations,
    categorize_activity,
    convert_reference_test_to_observations,
    extract_durability_alpha_observation,
    extract_p_ref_steady_observation,
    extract_p_run_observation,
    extract_trail_cost_factor_observation,
)


REQUIRED_OBSERVATION_KEYS = {
    "mean",
    "std",
    "weight",
    "source_label",
    "source_id",
    "source_type",
    "performed_at",
    "category",
    "quality_flags",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def session() -> Session:
    """Fresh in-memory database for every test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def user_id(session: Session) -> UUID:
    user = User(
        email="aggregator@example.com",
        full_name="Aggregator User",
        hashed_password="not-a-real-hash",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_streams_full(
    duration_s: int,
    speed_mps: float = 3.0,
    hr_bpm: float = 140.0,
    hr_std: float = 3.0,
    grade_pct: float = 0.5,
    peak_evidence_bpm: Optional[float] = 161.0,
) -> dict:
    """Build a stream payload with HR + velocity + grade + time + distance.

    HR samples oscillate around ``hr_bpm`` with ``hr_std`` random-like
    variation (deterministic sequence so tests stay reproducible). The grade
    is stored in **percent**, as Strava/Garmin do, because the aggregator now
    explicitly relies on that unit (and converts to a fraction internally).

    Default ``hr_bpm=140`` puts the HR samples inside the principal FC band
    ``[0.72, 0.78] * 185 = [133, 144]`` (V2.3.1 R1). A short block around
    161 bpm makes the summary ``max_heartrate=185`` compatible with a real
    stream history under the anti-spike FCmax rule. Set ``peak_evidence_bpm``
    to ``None`` for tests that require a pure constant-HR stream.
    """
    velocity = [speed_mps] * duration_s
    grade = [grade_pct] * duration_s  # mild flat road, in percent
    distance = [speed_mps * i for i in range(duration_s)]
    time = [float(i) for i in range(duration_s)]
    # Deterministic HR oscillation around hr_bpm.
    heartrate = [
        hr_bpm + ((i % 7) - 3) * (hr_std / 3.0) for i in range(duration_s)
    ]
    if peak_evidence_bpm is not None:
        for index in range(min(duration_s, max(6, duration_s // 100))):
            heartrate[index] = max(heartrate[index], peak_evidence_bpm)
    return {
        "heartrate": {"data": heartrate},
        "velocity_smooth": {"data": velocity},
        "grade_smooth": {"data": grade},
        "distance": {"data": distance},
        "time": {"data": time},
    }


def _make_activity(
    user_id: UUID,
    *,
    name: str = "Test Activity",
    start_date: datetime = datetime(2026, 1, 1, 9, 0),
    distance_m: float = 10000.0,
    moving_time_s: int = 2400,  # 40 minutes (~10K @ 4:00/km)
    elevation_gain_m: float = 50.0,
    activity_type: ActivityType = ActivityType.RUN,
    max_heartrate: Optional[float] = 185.0,
    streams: Optional[dict] = None,
) -> Activity:
    return Activity(
        source="garmin",
        user_id=user_id,
        name=name,
        activity_type=activity_type,
        start_date=start_date,
        distance=distance_m,
        moving_time=moving_time_s,
        elapsed_time=moving_time_s + 30,
        total_elevation_gain=elevation_gain_m,
        average_speed=distance_m / moving_time_s,
        max_heartrate=max_heartrate,
        streams_data=streams,
    )


def _persist(session: Session, *entities) -> None:
    for entity in entities:
        session.add(entity)
    session.commit()
    for entity in entities:
        session.refresh(entity)


def _assert_observation_shape(obs: dict) -> None:
    assert REQUIRED_OBSERVATION_KEYS.issubset(obs.keys()), obs
    assert isinstance(obs["mean"], float)
    assert isinstance(obs["std"], float) and obs["std"] > 0
    assert isinstance(obs["weight"], float) and obs["weight"] >= 0
    assert isinstance(obs["source_label"], str) and obs["source_label"]
    assert isinstance(obs["source_type"], str) and obs["source_type"]
    assert isinstance(obs["category"], str) and obs["category"]
    assert isinstance(obs["quality_flags"], list)


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


def test_empty_history_returns_empty_observations(session: Session, user_id: UUID):
    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    assert isinstance(observations, dict)
    # All expected V2.3.1 keys are present even with no evidence.
    assert set(observations.keys()) >= {
        "p_ref_steady_wkg",
        "p_capacity_test_wkg",
        "durability_alpha",
        "trail_cost_factor",
        "fc_max_bpm",
        "walk_power_ratio",
    }
    # The legacy V2.2 key must NOT be exposed by the V2.3.1 aggregator.
    assert "flat_capacity_mps" not in observations
    # The V2.3 fused key must NOT be exposed by the V2.3.1 aggregator.
    assert "p_run_wkg" not in observations
    for param, obs_list in observations.items():
        assert obs_list == [], f"{param} should be empty when no history exists"


def test_strava_history_does_not_feed_garmin_only_predictions(
    session: Session, user_id: UUID
):
    garmin_activities = [
        _make_activity(
            user_id,
            name=f"Garmin evidence {index}",
            start_date=datetime(2026, 1, day, 9, 0),
            streams=_make_streams_full(2400, speed_mps=3.6, hr_bpm=140.0),
        )
        for index, day in enumerate((10, 12, 14), start=1)
    ]
    strava_activity = _make_activity(
        user_id,
        name="Strava excluded evidence",
        start_date=datetime(2026, 1, 16, 9, 0),
        streams=_make_streams_full(2400, speed_mps=4.2, hr_bpm=140.0),
    )
    strava_activity.source = "strava"
    _persist(session, *garmin_activities, strava_activity)
    for activity in (*garmin_activities, strava_activity):
        session.add(
            RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category="official_clean",
            )
        )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )

    sources = {o["source_label"] for o in observations["p_ref_steady_wkg"]}
    assert any("Garmin evidence 1" in source for source in sources)
    assert any("Garmin evidence 2" in source for source in sources)
    assert any("Garmin evidence 3" in source for source in sources)
    assert not any("Strava excluded evidence" in source for source in sources)


# ---------------------------------------------------------------------------
# Chronological backtest contract
# ---------------------------------------------------------------------------


def test_as_of_date_strictly_filters_future_activities(
    session: Session, user_id: UUID
):
    """Activities >= as_of_date must never appear in the observations.

    Three past activities are seeded so the R1 FC band threshold
    (MIN_ACTIVITIES_IN_BAND = 3) is satisfied on the principal band.
    """
    past_a = _make_activity(
        user_id,
        name="Past 10K A",
        start_date=datetime(2026, 1, 10, 9, 0),
        streams=_make_streams_full(2400, speed_mps=3.6, hr_bpm=140.0),
    )
    past_b = _make_activity(
        user_id,
        name="Past 10K B",
        start_date=datetime(2026, 1, 12, 9, 0),
        streams=_make_streams_full(2400, speed_mps=3.6, hr_bpm=140.0),
    )
    past_c = _make_activity(
        user_id,
        name="Past 10K C",
        start_date=datetime(2026, 1, 14, 9, 0),
        streams=_make_streams_full(2400, speed_mps=3.6, hr_bpm=140.0),
    )
    future = _make_activity(
        user_id,
        name="Future 10K",
        start_date=datetime(2026, 3, 1, 9, 0),
        streams=_make_streams_full(2400, speed_mps=3.6, hr_bpm=140.0),
    )
    boundary = _make_activity(
        user_id,
        name="Boundary 10K",
        # exactly equal to as_of_date -> excluded (strict <)
        start_date=datetime(2026, 2, 15, 0, 0),
        streams=_make_streams_full(2400, speed_mps=3.6, hr_bpm=140.0),
    )
    _persist(session, past_a, past_b, past_c, future, boundary)
    # Validate all as performance_anchor races to make sure they would
    # otherwise contribute.
    for activity in (past_a, past_b, past_c, future, boundary):
        session.add(
            RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category="official_clean",
            )
        )
    session.commit()

    as_of = datetime(2026, 2, 15, 0, 0)
    observations = aggregate_observations(session, user_id, as_of_date=as_of)

    sources = {o["source_label"] for o in observations["p_ref_steady_wkg"]}
    assert any("Past 10K A" in s for s in sources)
    assert any("Past 10K B" in s for s in sources)
    assert any("Past 10K C" in s for s in sources)
    assert not any("Future 10K" in s for s in sources)
    assert not any("Boundary 10K" in s for s in sources)


def test_excluded_activity_ids_excluded(session: Session, user_id: UUID):
    """Activities in excluded_activity_ids must not appear in observations.

    Four activities seeded; one is excluded. The three remaining satisfy the
    R1 ``MIN_ACTIVITIES_IN_BAND`` threshold.
    """
    keepers = []
    for i, day in enumerate((1, 2, 3)):
        keepers.append(
            _make_activity(
                user_id,
                name=f"Keeper {i}",
                start_date=datetime(2026, 1, day, 9, 0),
                streams=_make_streams_full(2400, hr_bpm=140.0),
            )
        )
    excluded = _make_activity(
        user_id,
        name="Excluded",
        start_date=datetime(2026, 1, 5, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0),
    )
    _persist(session, *keepers, excluded)
    for activity in (*keepers, excluded):
        session.add(
            RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category="official_clean",
            )
        )
    session.commit()

    observations = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1),
        excluded_activity_ids={excluded.id},
    )
    sources = {o["source_label"] for o in observations["p_ref_steady_wkg"]}
    assert any("Keeper 0" in s for s in sources)
    assert any("Keeper 1" in s for s in sources)
    assert any("Keeper 2" in s for s in sources)
    assert not any("Excluded" in s for s in sources)


def test_replay_chronological_does_not_use_future_activities(
    session: Session, user_id: UUID
):
    """A replay at date D must produce identical evidence to a fresh aggregate
    where future activities are absent.

    Three past activities are seeded (so R1 MIN_ACTIVITIES_IN_BAND is
    satisfied) plus one future activity that must be filtered out.
    """
    a1 = _make_activity(
        user_id,
        name="A1",
        start_date=datetime(2025, 6, 1, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0),
    )
    a2 = _make_activity(
        user_id,
        name="A2",
        start_date=datetime(2025, 9, 1, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0),
    )
    a3_past = _make_activity(
        user_id,
        name="A3-past",
        start_date=datetime(2025, 11, 1, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0),
    )
    a_future = _make_activity(
        user_id,
        name="A-future",
        start_date=datetime(2026, 4, 1, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0),
    )
    # Use a default 3-year history window so all past activities qualify.
    _persist(session, a1, a2, a3_past, a_future)
    for activity in (a1, a2, a3_past, a_future):
        session.add(
            RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category="official_clean",
            )
        )
    session.commit()

    replay = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 1, 1),
        history_start_date=datetime(2025, 1, 1),
    )
    sources = {o["source_label"] for o in replay["p_ref_steady_wkg"]}
    assert any("A1" in s for s in sources)
    assert any("A2" in s for s in sources)
    assert any("A3-past" in s for s in sources)
    assert not any("A-future" in s for s in sources)


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------


def test_observation_categorize_function_returns_expected_values():
    """Smoke test on the public categorize_activity function."""
    user_uuid = uuid4()
    flat_run = _make_activity(
        user_uuid,
        name="Flat 10K",
        distance_m=10000.0,
        moving_time_s=2400,
        elevation_gain_m=30.0,  # ~3 m/km -> not trail
        streams=_make_streams_full(2400),
    )
    trail = _make_activity(
        user_uuid,
        name="Trail 20K",
        distance_m=20000.0,
        moving_time_s=8000,
        elevation_gain_m=1200.0,  # 60 m/km -> trail
        streams=_make_streams_full(8000),
    )
    short_easy = _make_activity(
        user_uuid,
        name="Recovery 20min",
        distance_m=4000.0,
        moving_time_s=1200,  # 20 min < SUBMAX_MIN_DURATION_S
        elevation_gain_m=10.0,
        streams=_make_streams_full(1200, hr_std=2.0),
    )
    long_submax = _make_activity(
        user_uuid,
        name="Long endurance",
        distance_m=15000.0,
        moving_time_s=3600,  # 60 min > 30 min
        elevation_gain_m=80.0,
        streams=_make_streams_full(3600, hr_std=2.0),
    )

    official_clean = RaceValidationReference(
        user_id=user_uuid, activity_id=flat_run.id, category="official_clean"
    )
    incident = RaceValidationReference(
        user_id=user_uuid,
        activity_id=flat_run.id,
        category="incident_non_scoring",
    )
    normalized = RaceValidationReference(
        user_id=user_uuid,
        activity_id=flat_run.id,
        category="official_normalized",
    )

    assert categorize_activity(flat_run, official_clean) == "performance_anchor"
    assert categorize_activity(trail, official_clean) == "trail_anchor"
    assert categorize_activity(flat_run, incident) == "non_scoring"
    assert categorize_activity(flat_run, normalized) == "non_scoring"
    # No validation reference + clean streams + long enough -> submax
    assert categorize_activity(long_submax, None) == "submax_physiological"
    # No validation + short activity -> diagnostic (streams ok but too short)
    assert categorize_activity(short_easy, None) == "diagnostic"


# ---------------------------------------------------------------------------
# Per-parameter extraction
# ---------------------------------------------------------------------------


def test_official_clean_road_race_produces_p_ref_steady_observation(
    session: Session, user_id: UUID
):
    """A clean road 10K must produce a ``p_ref_steady_wkg`` observation
    derived directly from the median flat speed (no Daniels inversion).

    To satisfy the R1 ``MIN_ACTIVITIES_IN_BAND = 3`` threshold, we seed
    three identical activities. The aggregator returns one observation per
    qualifying activity.
    """
    speed = 10000.0 / 2400  # 4.17 m/s
    races = []
    for i in range(3):
        race = _make_activity(
            user_id,
            name=f"10K Officiel #{i + 1}",
            start_date=datetime(2026, 1, 15 + i, 9, 0),
            distance_m=10000.0,
            moving_time_s=2400,  # 40 min => 4:00 min/km
            elevation_gain_m=30.0,
            # hr_bpm=140 lands inside [0.72, 0.78]*185 = [133, 144].
            streams=_make_streams_full(2400, speed_mps=speed, hr_bpm=140.0, hr_std=4.0),
        )
        races.append(race)
    _persist(session, *races)
    # Only the first race is "official_clean"; the other two are
    # submax_physiological. All three feed p_ref_steady_wkg.
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=races[0].id,
            category="official_clean",
        )
    )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    p_ref_obs = observations["p_ref_steady_wkg"]
    assert len(p_ref_obs) >= 1
    anchor_obs = next(
        o for o in p_ref_obs if "10K Officiel #1" in o["source_label"]
    )
    _assert_observation_shape(anchor_obs)
    assert anchor_obs["category"] == "performance_anchor"
    # 10K at 4.17 m/s on flat road -> p_ref = 3.6 * 4.17 = ~15.0 W/kg.
    # NO Daniels inversion applied here.
    expected = 3.6 * speed
    assert abs(anchor_obs["mean"] - expected) < 0.5, (
        f"Observation mean {anchor_obs['mean']} should be close to direct "
        f"Minetti product {expected}, not an inflated capacity."
    )
    # Std per V2.3 plan: 0.4 W/kg for performance_anchor.
    assert anchor_obs["std"] <= 0.6
    assert anchor_obs["weight"] >= 0.5
    # FC band filtering must be reflected in the quality flags.
    assert "fc_band_filtered" in anchor_obs["quality_flags"]


def test_official_clean_trail_race_produces_trail_anchor_not_p_ref_steady(
    session: Session, user_id: UUID
):
    """A clean trail race never feeds p_ref_steady_wkg.

    V2.3.1 (R5 garde-fous): a single ``official_clean`` trail observation
    is now surfaced as a diagnostic only — the aggregator clears the
    ``trail_cost_factor`` list so the Bayesian fusion downstream sees
    nothing and the population prior dominates. The full assertions on
    the diagnostic mode live in
    :mod:`tests.test_v2_3_1_trail_factor_guards`.
    """
    trail = _make_activity(
        user_id,
        name="Trail 25K",
        start_date=datetime(2026, 2, 1, 9, 0),
        distance_m=25000.0,
        moving_time_s=12000,  # 3h20
        elevation_gain_m=1500.0,  # 60 m/km -> trail
        streams=_make_streams_full(12000, speed_mps=25000.0 / 12000),
    )
    _persist(session, trail)
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=trail.id,
            category="official_clean",
        )
    )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )

    # Trail anchor must NOT produce a p_ref_steady_wkg observation.
    assert not any(
        "Trail 25K" in o["source_label"] for o in observations["p_ref_steady_wkg"]
    )
    # V2.3.1 R5: even a clean trail produces an EMPTY trail_cost_factor
    # list when only one observation is available (or when streams lack a
    # reconstructable track). The personalised posterior remains inactive
    # until >= 2 cohérent observations are collected (R7 backlog).
    assert observations["trail_cost_factor"] == []


def test_unlabelled_trail_training_cannot_calibrate_road_p_ref(
    session: Session, user_id: UUID
):
    """Flat samples from explicit TrailRun activities stay out of route P_ref."""
    trails = [
        _make_activity(
            user_id,
            name=f"Flat trail training #{index}",
            start_date=datetime(2026, 2, 2 + index, 9, 0),
            distance_m=9000.0,
            moving_time_s=3000,
            elevation_gain_m=20.0,
            activity_type=ActivityType.TRAIL_RUN,
            streams=_make_streams_full(3000, speed_mps=3.0, hr_bpm=140.0),
        )
        for index in range(3)
    ]
    _persist(session, *trails)

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )

    assert observations["p_ref_steady_wkg"] == []


def test_incident_non_scoring_excluded_from_observations(
    session: Session, user_id: UUID
):
    """An incident race must never contribute to capacity-like parameters."""
    incident = _make_activity(
        user_id,
        name="Trail des tranchees",
        start_date=datetime(2026, 1, 15, 9, 0),
        distance_m=25000.0,
        moving_time_s=18000,  # 5h
        elevation_gain_m=1500.0,
        streams=_make_streams_full(18000, speed_mps=25000.0 / 18000),
    )
    _persist(session, incident)
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=incident.id,
            category="incident_non_scoring",
        )
    )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    for param, obs_list in observations.items():
        for obs in obs_list:
            assert "Trail des tranchees" not in obs["source_label"], (
                f"non_scoring activity leaked into {param}: {obs}"
            )


def test_training_activity_produces_lower_weight_than_anchor(
    session: Session, user_id: UUID
):
    """A submax training activity must weigh less than a performance anchor.

    A third filler activity is seeded so the R1 ``MIN_ACTIVITIES_IN_BAND``
    threshold is satisfied on the principal band.
    """
    anchor = _make_activity(
        user_id,
        name="Race 10K",
        start_date=datetime(2026, 1, 10, 9, 0),
        distance_m=10000.0,
        moving_time_s=2400,
        elevation_gain_m=30.0,
        streams=_make_streams_full(2400, speed_mps=10000.0 / 2400, hr_bpm=140.0, hr_std=4.0),
    )
    training = _make_activity(
        user_id,
        name="Easy Run",
        start_date=datetime(2026, 1, 20, 9, 0),
        distance_m=10000.0,
        moving_time_s=3000,  # 50 min easy
        elevation_gain_m=30.0,
        streams=_make_streams_full(3000, speed_mps=10000.0 / 3000, hr_bpm=140.0, hr_std=3.0),
    )
    filler = _make_activity(
        user_id,
        name="Filler",
        start_date=datetime(2026, 1, 25, 9, 0),
        distance_m=10000.0,
        moving_time_s=2400,
        elevation_gain_m=30.0,
        streams=_make_streams_full(2400, hr_bpm=140.0, hr_std=3.0),
    )
    _persist(session, anchor, training, filler)
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=anchor.id,
            category="official_clean",
        )
    )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    p_ref_obs = {o["source_label"]: o for o in observations["p_ref_steady_wkg"]}
    anchor_obs = next(o for k, o in p_ref_obs.items() if "Race 10K" in k)
    training_obs = next(o for k, o in p_ref_obs.items() if "Easy Run" in k)

    assert anchor_obs["weight"] > training_obs["weight"], (
        f"Anchor weight={anchor_obs['weight']} should exceed training "
        f"weight={training_obs['weight']}"
    )


def test_reference_test_road_10k_produces_high_weight_p_capacity(
    session: Session, user_id: UUID
):
    """A 10K reference test must produce a high-weight
    ``p_capacity_test_wkg`` observation (NOT ``p_ref_steady_wkg``).

    V2.3.1 (R1): tests no longer feed the reference steady power. They
    populate a distinct, informative-only latent parameter.
    """
    test = ReferenceTest(
        user_id=user_id,
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=datetime(2026, 1, 10, 9, 0),
        duration_seconds=2400,
        distance_m=10000.0,
        elevation_gain_m=10.0,
        surface=ReferenceTestSurface.ASPHALT,
        quality_status=ReferenceTestQuality.VALID,
    )
    session.add(test)
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    # V2.3.1 contract: NO p_ref_steady_wkg observation from tests.
    assert observations["p_ref_steady_wkg"] == []
    p_capacity_obs = observations["p_capacity_test_wkg"]
    assert len(p_capacity_obs) == 1
    obs = p_capacity_obs[0]
    _assert_observation_shape(obs)
    assert obs["source_type"] == "reference_test"
    # The reference test weight must dominate any activity-based observation.
    assert obs["weight"] >= 1.0
    # Std should be reasonable (0.4 W/kg per V2.3 plan) and tighter than the
    # diagnostic activity baseline.
    assert obs["std"] <= 0.5
    # For a 10K in 40 min: speed = 4.17 m/s, sustainable_fraction(40min) ~0.95.
    # P_capacity = 4.17 * 3.6 / 0.95 ~= 15.8 W/kg.
    assert 14.5 <= obs["mean"] <= 17.0
    # Informative-only flag must be set.
    assert "informative_only" in obs["quality_flags"]


def test_reference_test_long_steady_is_informative_only_without_streams() -> None:
    """A duration-only long test cannot manufacture a durability observation."""
    test = ReferenceTest(
        user_id=uuid4(),
        test_type=ReferenceTestType.LONG_STEADY,
        performed_at=datetime(2026, 1, 10, 9, 0),
        duration_seconds=3 * 3600,
        distance_m=28000.0,
        quality_status=ReferenceTestQuality.VALID,
    )

    assert convert_reference_test_to_observations(
        test, as_of_date=datetime(2026, 5, 26)
    ) == {}


def test_long_continuous_activity_produces_durability_observation(
    session: Session, user_id: UUID
):
    """A long activity with clear pace decline must produce a durability obs."""
    duration = 3 * 3600  # 3h
    # Build a stream where the first half is faster than the second half.
    velocity = [3.5] * (duration // 2) + [2.8] * (duration - duration // 2)
    heartrate = [150 + ((i % 5) - 2) for i in range(duration)]
    grade = [0.5] * duration  # percent
    distance = []
    cumulative = 0.0
    for v in velocity:
        cumulative += v
        distance.append(cumulative)
    time = [float(i) for i in range(duration)]
    streams = {
        "heartrate": {"data": heartrate},
        "velocity_smooth": {"data": velocity},
        "grade_smooth": {"data": grade},
        "distance": {"data": distance},
        "time": {"data": time},
    }
    activity = _make_activity(
        user_id,
        name="Long Run 3h",
        start_date=datetime(2026, 1, 5, 8, 0),
        distance_m=distance[-1],
        moving_time_s=duration,
        elevation_gain_m=80.0,
        streams=streams,
    )
    _persist(session, activity)
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=activity.id,
            category="official_clean",
        )
    )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    durability_obs = [
        o for o in observations["durability_alpha"] if "Long Run 3h" in o["source_label"]
    ]
    assert len(durability_obs) == 1
    obs = durability_obs[0]
    _assert_observation_shape(obs)
    # Decline ~20% over ~1h beyond 2h => alpha estimate well above the
    # reference 0.12.
    assert obs["mean"] > 0.12
    assert obs["mean"] <= 0.30


def test_streams_required_for_p_ref_steady_extraction(session: Session, user_id: UUID):
    """V2.3.1 (R1): activities WITHOUT streams cannot feed p_ref_steady_wkg.

    The FC-band filter operates per-sample on the HR + velocity streams. An
    activity without streams therefore has zero samples in the band and is
    skipped. This is the V2.3.1 contract: streams are mandatory to publish
    an evidence-based observation on the reference power.

    Three activities are seeded so the MIN_ACTIVITIES_IN_BAND threshold is
    met. We then verify that a fourth activity without streams adds no
    observation but does not break the others.
    """
    common = dict(
        distance_m=10000.0,
        moving_time_s=2400,
        elevation_gain_m=30.0,
    )
    a1 = _make_activity(
        user_id,
        name="With streams 1",
        start_date=datetime(2026, 1, 10, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0, hr_std=3.0),
        **common,
    )
    a2 = _make_activity(
        user_id,
        name="With streams 2",
        start_date=datetime(2026, 1, 12, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0, hr_std=3.0),
        **common,
    )
    a3 = _make_activity(
        user_id,
        name="With streams 3",
        start_date=datetime(2026, 1, 14, 9, 0),
        streams=_make_streams_full(2400, hr_bpm=140.0, hr_std=3.0),
        **common,
    )
    bare = _make_activity(
        user_id,
        name="No streams",
        start_date=datetime(2026, 1, 20, 9, 0),
        streams=None,
        **common,
    )
    _persist(session, a1, a2, a3, bare)
    for activity in (a1, a2, a3, bare):
        session.add(
            RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category="official_clean",
            )
        )
    session.commit()
    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )["p_ref_steady_wkg"]
    sources = {o["source_label"] for o in observations}
    assert any("With streams 1" in s for s in sources)
    assert any("With streams 2" in s for s in sources)
    assert any("With streams 3" in s for s in sources)
    assert not any("No streams" in s for s in sources)


def test_all_observations_have_required_fields(session: Session, user_id: UUID):
    """Every observation produced must carry the canonical key set."""
    race = _make_activity(
        user_id,
        name="Road 10K",
        start_date=datetime(2026, 1, 10, 9, 0),
        distance_m=10000.0,
        moving_time_s=2400,
        streams=_make_streams_full(2400, hr_std=3.0),
    )
    trail = _make_activity(
        user_id,
        name="Trail 20K",
        start_date=datetime(2026, 1, 25, 9, 0),
        distance_m=20000.0,
        moving_time_s=9000,
        elevation_gain_m=1200.0,
        streams=_make_streams_full(9000, hr_std=4.0),
    )
    long = _make_activity(
        user_id,
        name="Long Submax",
        start_date=datetime(2026, 2, 1, 9, 0),
        distance_m=24000.0,
        moving_time_s=2 * 3600 + 600,
        streams=_make_streams_full(2 * 3600 + 600, hr_std=2.5),
    )
    _persist(session, race, trail, long)
    session.add(
        RaceValidationReference(
            user_id=user_id, activity_id=race.id, category="official_clean"
        )
    )
    session.add(
        RaceValidationReference(
            user_id=user_id, activity_id=trail.id, category="official_clean"
        )
    )
    session.commit()

    # Add a reference test as well.
    session.add(
        ReferenceTest(
            user_id=user_id,
            test_type=ReferenceTestType.ROAD_5K,
            performed_at=datetime(2026, 1, 1, 9, 0),
            duration_seconds=1100,
            distance_m=5000.0,
            quality_status=ReferenceTestQuality.VALID,
        )
    )
    session.commit()

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )

    total = 0
    for param, obs_list in observations.items():
        for obs in obs_list:
            _assert_observation_shape(obs)
            total += 1
    assert total >= 3, observations


# ---------------------------------------------------------------------------
# V2.3 specific: direct flat-speed extraction, no Daniels inversion
# ---------------------------------------------------------------------------


def test_p_ref_steady_observation_does_not_use_sustainable_fraction_inversion(
    session: Session, user_id: UUID
):
    """For a historical activity, the extracted p_ref_steady must equal
    ``3.6 * median(flat_speed_mps)``, not ``speed / sustainable_fraction``.

    Three 50-min submax runs at 3.0 m/s with HR in the principal FC band.
    If the V2.2 Daniels inversion was still applied, the observation would
    land in the ~11.5-12.5 W/kg band (speed / 0.92). With the V2.3.1 direct
    extraction, it must instead be ~10.8 W/kg (3.6 * 3.0).
    """
    speed = 3.0
    duration = 50 * 60  # 50 min
    activities = []
    for i in range(3):
        # hr_bpm=140 + max_heartrate=185 -> band [133, 144] contains samples.
        streams = _make_streams_full(duration, speed_mps=speed, hr_bpm=140.0, hr_std=3.0)
        activities.append(
            _make_activity(
                user_id,
                name=f"Submax 50min #{i}",
                start_date=datetime(2026, 1, 10 + i, 9, 0),
                distance_m=speed * duration,
                moving_time_s=duration,
                elevation_gain_m=30.0,  # flat
                streams=streams,
            )
        )
    _persist(session, *activities)
    # No validation reference -> submax_physiological category.

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    p_ref = observations["p_ref_steady_wkg"]
    assert len(p_ref) >= 1
    obs = p_ref[0]
    expected = 3.6 * speed  # 10.8 W/kg
    assert abs(obs["mean"] - expected) < 0.3, (
        f"p_ref_steady = {obs['mean']} should be ~{expected} (direct Minetti). "
        "V2.2 inversion would have produced ~11.7 W/kg."
    )
    # And in any case, must not exceed the implausible inverted value.
    assert obs["mean"] < 12.0


def test_reference_test_road_10k_uses_sustainable_fraction_inversion_correctly():
    """For a 10K test, the inversion via sustainable_fraction is legitimate
    (effort maximal by construction). The result must converge on the
    plan's worked example: ~15.8 W/kg for a 40-min 10K.

    V2.3.1 (R1): the observation now lives under ``p_capacity_test_wkg``,
    NOT ``p_ref_steady_wkg`` (no fusion with steady-effort historical
    observations).
    """
    test = ReferenceTest(
        user_id=uuid4(),
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=datetime(2026, 1, 10, 9, 0),
        duration_seconds=2400,
        distance_m=10000.0,
        quality_status=ReferenceTestQuality.VALID,
    )
    out = convert_reference_test_to_observations(test)
    # V2.3.1 (R1): the test no longer feeds p_ref_steady_wkg or p_run_wkg.
    assert "p_ref_steady_wkg" not in out
    assert "p_run_wkg" not in out
    assert "p_capacity_test_wkg" in out
    obs_list = out["p_capacity_test_wkg"]
    assert len(obs_list) == 1
    obs = obs_list[0]
    # Test 10K @ 40 min: 4.17 m/s, sustainable_fraction(40 min) ~= 0.95.
    # P_capacity = 4.17 * 3.6 / 0.95 ~= 15.8 W/kg.
    assert 14.5 <= obs["mean"] <= 17.0
    # Tight std for a controlled protocol.
    assert obs["std"] <= 0.5
    assert obs["weight"] >= 1.0


def test_p_ref_steady_observation_realistic_for_typical_athlete(
    session: Session, user_id: UUID
):
    """An athlete with a historical flat pace of 5:30 min/km (~3.03 m/s)
    must produce a p_ref_steady observation around ``3.6 * 3.03 = 10.9 W/kg``,
    NOT a Daniels-inverted value.

    Three 1h runs seeded so the MIN_ACTIVITIES_IN_BAND threshold is met.
    """
    speed = 1000.0 / (5.5 * 60)  # 5:30 min/km = 3.03 m/s
    duration = 60 * 60  # 1h
    activities = []
    for i in range(3):
        # hr_bpm=140 places samples inside the principal FC band [133, 144].
        streams = _make_streams_full(duration, speed_mps=speed, hr_bpm=140.0, hr_std=3.0)
        activities.append(
            _make_activity(
                user_id,
                name=f"Endurance 1h #{i}",
                start_date=datetime(2026, 1, 5 + i, 9, 0),
                distance_m=speed * duration,
                moving_time_s=duration,
                elevation_gain_m=20.0,
                streams=streams,
            )
        )
    _persist(session, *activities)

    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    p_ref = observations["p_ref_steady_wkg"]
    assert len(p_ref) >= 1
    obs = p_ref[0]
    expected = 3.6 * speed  # ~10.9 W/kg
    assert abs(obs["mean"] - expected) < 0.3, (
        f"Realistic athlete p_ref_steady should be ~{expected}, got {obs['mean']}. "
        "V2.2 inversion would have produced ~12.3 W/kg."
    )


def test_p_run_extraction_drops_steep_grade_samples():
    """When the streams contain steep-grade segments, only the flat samples
    must feed the median. A run that is 50 % flat (at speed S1) and 50 %
    uphill (at slower speed S2) must yield a P_run consistent with S1, not
    with the mean of S1 and S2."""
    user_uuid = uuid4()
    duration = 60 * 60  # 1h
    half = duration // 2
    fast_flat = 3.5  # m/s on flat road
    slow_uphill = 2.0  # m/s on a steep section
    velocity = [fast_flat] * half + [slow_uphill] * (duration - half)
    # Grade in percent: 0.5% on the flat portion, 8% on the uphill portion.
    grade = [0.5] * half + [8.0] * (duration - half)
    heartrate = [150 + ((i % 5) - 2) for i in range(duration)]
    cumulative = 0.0
    distance = []
    for v in velocity:
        cumulative += v
        distance.append(cumulative)
    time = [float(i) for i in range(duration)]
    streams = {
        "heartrate": {"data": heartrate},
        "velocity_smooth": {"data": velocity},
        "grade_smooth": {"data": grade},
        "distance": {"data": distance},
        "time": {"data": time},
    }
    activity = _make_activity(
        user_uuid,
        name="Hilly run",
        start_date=datetime(2026, 1, 1, 9, 0),
        distance_m=cumulative,
        moving_time_s=duration,
        elevation_gain_m=300.0,
        streams=streams,
    )
    obs = extract_p_run_observation(activity, "submax_physiological")
    assert obs is not None
    expected_flat = 3.6 * fast_flat  # ~12.6 W/kg
    expected_mean_speed = 3.6 * (fast_flat + slow_uphill) / 2  # ~9.9 W/kg
    # Observation must follow the flat-only median, not the mixed average.
    assert abs(obs["mean"] - expected_flat) < 0.5
    assert abs(obs["mean"] - expected_mean_speed) > 1.0
    assert "flat_grade_filtered" in obs["quality_flags"]


# ---------------------------------------------------------------------------
# Edge cases and additional guards
# ---------------------------------------------------------------------------


def test_invalidated_reference_test_is_skipped(session: Session, user_id: UUID):
    """A reference test marked INVALIDATED never feeds observations."""
    session.add(
        ReferenceTest(
            user_id=user_id,
            test_type=ReferenceTestType.ROAD_10K,
            performed_at=datetime(2026, 1, 10, 9, 0),
            duration_seconds=2400,
            distance_m=10000.0,
            quality_status=ReferenceTestQuality.INVALIDATED,
        )
    )
    session.commit()
    observations = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1)
    )
    # V2.3.1: tests feed p_capacity_test_wkg (informative), not p_ref_steady.
    # Invalidated tests must not feed either.
    assert observations["p_ref_steady_wkg"] == []
    assert observations["p_capacity_test_wkg"] == []


def test_non_running_activity_classified_as_non_scoring():
    """A ride or weight session must be classified non_scoring (no run params)."""
    activity = Activity(
        user_id=uuid4(),
        name="Bike",
        activity_type=ActivityType.RIDE,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=30000,
        moving_time=3600,
        elapsed_time=3600,
        total_elevation_gain=200,
    )
    assert categorize_activity(activity, None) == "non_scoring"


def test_extract_p_run_returns_none_for_trail_anchor():
    activity = Activity(
        user_id=uuid4(),
        name="Trail",
        activity_type=ActivityType.TRAIL_RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=20000,
        moving_time=9000,
        elapsed_time=9100,
        total_elevation_gain=1500,
    )
    assert extract_p_run_observation(activity, "trail_anchor") is None


def test_extract_p_run_returns_none_for_non_scoring():
    activity = Activity(
        user_id=uuid4(),
        name="Incident",
        activity_type=ActivityType.RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=10000,
        moving_time=2400,
        elapsed_time=2400,
        total_elevation_gain=30,
    )
    assert extract_p_run_observation(activity, "non_scoring") is None


def test_extract_trail_cost_factor_returns_none_for_non_trail_categories():
    activity = Activity(
        user_id=uuid4(),
        name="Road race",
        activity_type=ActivityType.RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=10000,
        moving_time=2400,
        elapsed_time=2400,
        total_elevation_gain=30,
    )
    assert extract_trail_cost_factor_observation(activity, "performance_anchor") is None
    assert extract_trail_cost_factor_observation(activity, "submax_physiological") is None
    assert extract_trail_cost_factor_observation(activity, "non_scoring") is None


def test_extract_durability_alpha_returns_none_for_short_activities():
    activity = Activity(
        user_id=uuid4(),
        name="Short Run",
        activity_type=ActivityType.RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=10000,
        moving_time=2400,  # 40 min, well below the 2h threshold
        elapsed_time=2400,
        total_elevation_gain=30,
    )
    assert extract_durability_alpha_observation(activity, "performance_anchor") is None


def test_convert_reference_test_5k_to_p_capacity_test_observation():
    """A 5K reference test produces exactly one p_capacity_test_wkg observation.

    V2.3.1 (R1): the 5K/10K tests feed the capacity parameter, not the
    reference steady parameter.
    """
    test = ReferenceTest(
        user_id=uuid4(),
        test_type=ReferenceTestType.ROAD_5K,
        performed_at=datetime(2026, 1, 1, 9, 0),
        duration_seconds=1100,  # ~18:20 -> ~4.55 m/s
        distance_m=5000.0,
        quality_status=ReferenceTestQuality.VALID,
    )
    out = convert_reference_test_to_observations(test)
    # V2.3.1: the test must not produce any p_ref_steady_wkg observation.
    assert "p_ref_steady_wkg" not in out
    assert "p_run_wkg" not in out
    assert "p_capacity_test_wkg" in out
    obs_list = out["p_capacity_test_wkg"]
    assert len(obs_list) == 1
    obs = obs_list[0]
    _assert_observation_shape(obs)
    # 5K at 18:20 -> ~4.55 m/s observed; sustainable_fraction(~18 min)
    # sits at the sprint cap (~1.0) -> P_cap ~ 4.55 * 3.6 / 1.0 = 16.4 W/kg.
    # Implementation caps the duration interpolation at MAX_FRACTION 1.05, so
    # the value can be slightly below the raw 16.4 number.
    assert 14.5 <= obs["mean"] <= 18.0
    assert obs["weight"] >= 1.0
    assert "controlled_protocol" in obs["quality_flags"]
    assert "informative_only" in obs["quality_flags"]


# ---------------------------------------------------------------------------
# FIX 5 (V2.3.1) - FCmax robuste vs pic capteur isole
# ---------------------------------------------------------------------------


def test_fcmax_estimation_ignores_isolated_sensor_spike() -> None:
    """FIX 5 (V2.3.1) : un pic capteur isole dans ``activity.max_heartrate``
    (210 bpm) ne doit pas fausser l'estimation FCmax si les streams
    contiennent >= 500 echantillons et que la divergence entre le
    percentile et max_heartrate depasse la tolerance de pic (25 bpm).

    Avant le fix, ``_estimate_fcmax_from_history`` retournait
    ``max(percentile_estimate, activity.max_heartrate)`` sans question ; le
    pic remontait et faussait les seuils de la bande FC.
    Apres : la divergence > 25 bpm declenche le retour au percentile seul,
    avec la source ``streams_p995``.
    """
    from app.domain.services.race_predictor.observation_aggregator import (
        _estimate_fcmax_from_history,
    )

    user = uuid4()
    # Streams : 1000 samples HR entre 100-180 bpm, distribution uniforme.
    # Le percentile 99.5 sera ~ 180. La tolerance de pic est 25 bpm =>
    # max_heartrate=210 (qui est 30 bpm au-dessus) declenche le filtre.
    n_samples = 1000
    hr_stream = [100.0 + (i % 81) for i in range(n_samples)]  # max ~ 180
    streams = {
        "heartrate": {"data": hr_stream},
        "velocity_smooth": {"data": [3.0] * n_samples},
        "grade_smooth": {"data": [0.0] * n_samples},
        "distance": {"data": [3.0 * i for i in range(n_samples)]},
        "time": {"data": [float(i) for i in range(n_samples)]},
    }
    activity = Activity(
        source="garmin",
        user_id=user,
        name="Tempo run with sensor spike",
        activity_type=ActivityType.RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=3000.0,
        moving_time=n_samples,
        elapsed_time=n_samples + 30,
        total_elevation_gain=10.0,
        average_speed=3.0,
        # FIX 5 : pic capteur isole 210 bpm qui doit etre ignore meme s'il est
        # sous une borne absolue de saturation.
        max_heartrate=210.0,
        streams_data=streams,
    )

    debug: dict = {}
    fcmax = _estimate_fcmax_from_history(
        [(activity, "submax_physiological")], debug_trace=debug
    )
    # Percentile 99.5 du pool : ~ 180 (saturation de la sequence).
    assert fcmax is not None
    assert fcmax < 200.0, (
        f"Le pic capteur 220 bpm ne doit pas remonter. fcmax={fcmax}"
    )
    # La trace doit identifier que le pic capteur a ete neutralise.
    assert debug.get("fcmax_source") == "streams_p995"


def test_fcmax_falls_back_to_activity_max_when_streams_insufficient() -> None:
    """FIX 5 (V2.3.1) : avec moins de 500 echantillons streams, le fallback
    sur ``activity.max_heartrate`` reste actif. La source est annotee
    ``activity_max_fallback`` dans le debug_trace.
    """
    from app.domain.services.race_predictor.observation_aggregator import (
        _estimate_fcmax_from_history,
    )

    user = uuid4()
    # Tres peu d'echantillons HR (< 500) pour forcer le fallback.
    n_samples = 100
    hr_stream = [140.0] * n_samples
    streams = {
        "heartrate": {"data": hr_stream},
        "velocity_smooth": {"data": [3.0] * n_samples},
        "grade_smooth": {"data": [0.0] * n_samples},
        "distance": {"data": [3.0 * i for i in range(n_samples)]},
        "time": {"data": [float(i) for i in range(n_samples)]},
    }
    activity = Activity(
        source="garmin",
        user_id=user,
        name="Short run",
        activity_type=ActivityType.RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=300.0,
        moving_time=n_samples,
        elapsed_time=n_samples + 5,
        total_elevation_gain=2.0,
        average_speed=3.0,
        max_heartrate=185.0,
        streams_data=streams,
    )

    debug: dict = {}
    fcmax = _estimate_fcmax_from_history(
        [(activity, "submax_physiological")], debug_trace=debug
    )
    # Fallback sur activity.max_heartrate -> 185 bpm.
    assert fcmax == 185.0
    assert debug.get("fcmax_source") == "activity_max_fallback"


def test_fcmax_combines_percentile_and_activity_max_when_coherent() -> None:
    """FIX 5 (V2.3.1) : si le pool >= 500 et que ``activity.max_heartrate``
    est coherent avec le percentile (divergence <= 25 bpm), les deux sources
    sont combinees via ``max(percentile, activity.max_heartrate)``.

    Ce cas couvre un pool tempo dont le percentile sous-estime la vraie
    FCmax : ``activity.max_heartrate`` (atteint un jour de seance intense)
    completait le percentile et reste valide quand il n'est pas aberrant.
    """
    from app.domain.services.race_predictor.observation_aggregator import (
        _estimate_fcmax_from_history,
    )

    user = uuid4()
    # Pool tempo : 1000 samples a 140-145 bpm. Percentile 99.5 ~ 145.
    n_samples = 1000
    hr_stream = [140.0 + (i % 6) for i in range(n_samples)]
    streams = {
        "heartrate": {"data": hr_stream},
        "velocity_smooth": {"data": [3.0] * n_samples},
        "grade_smooth": {"data": [0.0] * n_samples},
        "distance": {"data": [3.0 * i for i in range(n_samples)]},
        "time": {"data": [float(i) for i in range(n_samples)]},
    }
    activity = Activity(
        source="garmin",
        user_id=user,
        name="Tempo run",
        activity_type=ActivityType.RUN,
        start_date=datetime(2026, 1, 1, 9, 0),
        distance=3000.0,
        moving_time=n_samples,
        elapsed_time=n_samples + 5,
        total_elevation_gain=2.0,
        average_speed=3.0,
        # Coherent avec le percentile (~145) : 165 bpm est 20 bpm au-dessus,
        # sous la tolerance pic de 25 bpm.
        max_heartrate=165.0,
        streams_data=streams,
    )
    debug: dict = {}
    fcmax = _estimate_fcmax_from_history(
        [(activity, "submax_physiological")], debug_trace=debug
    )
    # max(145, 165) = 165 : la couverture sur pool tempo est preservee.
    assert fcmax == 165.0
    assert debug.get("fcmax_source") == "streams_p995_with_activity_max"


# ---------------------------------------------------------------------------
# FIX 6a (V2.3.1) - decroissance d'anciennete ReferenceTest
# ---------------------------------------------------------------------------


def test_reference_test_age_decay() -> None:
    """FIX 6a (V2.3.1) : un test de reference >24 mois voit son poids divise
    par 2 chaque 12 mois supplementaires (decroissance exponentielle douce).
    """
    from datetime import timedelta

    now = datetime(2026, 5, 26, 12, 0)

    # Test "recent" (12 mois) -> age_weight = 1.0 (pas de decroissance).
    test_12mo = ReferenceTest(
        user_id=uuid4(),
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=now - timedelta(days=365),
        duration_seconds=2400,  # 40 min @ 4:00/km
        distance_m=10000.0,
        quality_status=ReferenceTestQuality.VALID,
        created_at=now,
        updated_at=now,
    )
    obs_12mo = convert_reference_test_to_observations(test_12mo, as_of_date=now)
    assert "p_capacity_test_wkg" in obs_12mo
    weight_12mo = obs_12mo["p_capacity_test_wkg"][0]["weight"]
    # weight nominal pour reference_test = 1.5 (constante _REFERENCE_TEST_WEIGHT).
    assert weight_12mo == pytest.approx(1.5, rel=0.01)

    # Test "ancien" (36 mois) -> age_weight = 0.5 ** ((36-24)/12) = 0.5.
    test_36mo = ReferenceTest(
        user_id=uuid4(),
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=now - timedelta(days=365 * 3),
        duration_seconds=2400,
        distance_m=10000.0,
        quality_status=ReferenceTestQuality.VALID,
        created_at=now,
        updated_at=now,
    )
    obs_36mo = convert_reference_test_to_observations(test_36mo, as_of_date=now)
    assert "p_capacity_test_wkg" in obs_36mo
    weight_36mo = obs_36mo["p_capacity_test_wkg"][0]["weight"]

    assert weight_36mo < weight_12mo, "Test plus vieux doit avoir un poids reduit."
    ratio = weight_36mo / weight_12mo
    # ~0.5 attendu (decroissance exponentielle :
    # 0.5 ** ((36-24)/12) = 0.5 ** 1 = 0.5).
    assert 0.4 < ratio < 0.6, f"Ratio age_weight={ratio:.3f}, attendu ~0.5"

    # Verifier qu'un flag age_weight_<value> apparait dans quality_flags.
    flags_36mo = obs_36mo["p_capacity_test_wkg"][0]["quality_flags"]
    assert any(flag.startswith("age_weight_") for flag in flags_36mo), (
        f"Le flag age_weight_<value> doit apparaitre dans les quality_flags "
        f"d'un test ancien. flags={flags_36mo}"
    )
    # Le test recent (12 mois) ne doit PAS avoir le flag age_weight_*.
    flags_12mo = obs_12mo["p_capacity_test_wkg"][0]["quality_flags"]
    assert not any(flag.startswith("age_weight_") for flag in flags_12mo), (
        f"Un test recent ne doit pas porter le flag age_weight_*. "
        f"flags={flags_12mo}"
    )


def test_reference_test_age_decay_is_replay_date_driven() -> None:
    """A historical replay uses its as_of date, not today's wall clock."""
    test = ReferenceTest(
        user_id=uuid4(),
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=datetime(2022, 1, 1, 9, 0),
        duration_seconds=2400,
        distance_m=10000.0,
        quality_status=ReferenceTestQuality.VALID,
    )
    replay_date = datetime(2024, 7, 1, 12, 0)

    first = convert_reference_test_to_observations(test, as_of_date=replay_date)
    second = convert_reference_test_to_observations(test, as_of_date=replay_date)

    assert first["p_capacity_test_wkg"][0]["weight"] == pytest.approx(
        second["p_capacity_test_wkg"][0]["weight"]
    )
