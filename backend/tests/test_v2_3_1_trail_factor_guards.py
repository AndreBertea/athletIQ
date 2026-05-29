"""V2.3.1 R5 garde-fous: trail_cost_factor activation safety net.

This suite locks the V2.3.1 contract that **no non-scoring activity may ever
contaminate the personalised** ``trail_cost_factor`` **parameter**, and that
the personalised posterior stays inactive (population prior 1.20 +/- 0.10)
until at least two ``official_clean`` trail races with cohérent residual
estimates have been collected.

It exercises three layers:

1. The leaf function :func:`extract_trail_cost_factor_observation` -- every
   excluded category and the missing-track guard must short-circuit before
   any computation.
2. The aggregator :func:`aggregate_observations` -- with 1 or 0 trail
   observations, the trail_cost_factor list returned to the fusion is
   empty; with 2 inconsistent observations, the list is still emptied but
   a different diagnostic mode is recorded; with 2 cohérent observations,
   the personalised mode is activated.
3. The orchestrator :func:`predict_v2_3` -- on the production user that
   has zero ``official_clean`` trail races, the engine applies the
   population prior 1.20 (no personalised calibration).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Importing the entities package registers every SQLModel table so the
# in-memory database has every table available.
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
    TRAIL_FACTOR_EXCLUDED_CATEGORIES,
    aggregate_observations,
    extract_trail_cost_factor_observation,
)
from app.domain.services.race_predictor.v2_3_prediction_service import (
    predict_v2_3,
)


# ---------------------------------------------------------------------------
# Shared in-memory database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def session() -> Session:
    """Fresh in-memory SQLite database for every test."""
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
        email="trail-factor-guards@example.com",
        full_name="Trail Guard Tester",
        hashed_password="not-a-real-hash",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id  # type: ignore[return-value]


def _persist(session: Session, *entities) -> None:
    for entity in entities:
        session.add(entity)
    session.commit()
    for entity in entities:
        if hasattr(entity, "id"):
            session.refresh(entity)


# ---------------------------------------------------------------------------
# Stream helpers
# ---------------------------------------------------------------------------


def _make_trail_streams(
    duration_s: int,
    distance_m: float,
    elevation_gain_m: float,
    *,
    include_latlng_altitude: bool = True,
    hr_bpm: float = 145.0,
) -> dict:
    """Build a streams payload representative of a trail race.

    By default the payload INCLUDES ``latlng`` + ``altitude`` so the R5
    reconstructable-track guard is satisfied. Set
    ``include_latlng_altitude=False`` to simulate an old / partial
    enrichment and prove the guard rejects the observation.
    """
    # 1 Hz cadence to keep the payload deterministic.
    n = max(1, int(duration_s))
    speed = distance_m / max(1.0, duration_s)
    velocity = [speed] * n
    time = [float(i) for i in range(n)]
    distance = [speed * i for i in range(n)]
    # Synthetic grade pulse: alternating climbs and descents averaging the
    # total elevation gain. We do not need physical realism for R5 guards.
    grade_pct = [3.0 if (i // 60) % 2 == 0 else -2.5 for i in range(n)]
    heartrate = [hr_bpm + ((i % 5) - 2) * 0.8 for i in range(n)]

    payload = {
        "heartrate": {"data": heartrate},
        "velocity_smooth": {"data": velocity},
        "grade_smooth": {"data": grade_pct},
        "distance": {"data": distance},
        "time": {"data": time},
    }
    if include_latlng_altitude:
        # Trivial trace that only needs to be non-empty and >= 10 samples.
        latlng = [[46.6 + i * 1e-4, 6.4 + i * 1e-4] for i in range(n)]
        altitude = [500.0 + (i % 100) for i in range(n)]
        payload["latlng"] = {"data": latlng}
        payload["altitude"] = {"data": altitude}
    return payload


def _make_trail_activity(
    user_id: UUID,
    *,
    name: str,
    start_date: datetime,
    distance_m: float = 25000.0,
    moving_time_s: int = 12000,  # 3h20
    elevation_gain_m: float = 1500.0,  # 60 m/km -> trail-like
    max_heartrate: Optional[float] = 185.0,
    include_latlng_altitude: bool = True,
    hr_bpm: float = 145.0,
) -> Activity:
    streams = _make_trail_streams(
        moving_time_s,
        distance_m,
        elevation_gain_m,
        include_latlng_altitude=include_latlng_altitude,
        hr_bpm=hr_bpm,
    )
    return Activity(
        source="garmin",
        user_id=user_id,
        name=name,
        activity_type=ActivityType.TRAIL_RUN,
        start_date=start_date,
        distance=distance_m,
        moving_time=moving_time_s,
        elapsed_time=moving_time_s + 60,
        total_elevation_gain=elevation_gain_m,
        average_speed=distance_m / moving_time_s,
        average_heartrate=hr_bpm,
        max_heartrate=max_heartrate,
        streams_data=streams,
    )


def _baseline_activity_no_streams(
    user_id: UUID,
    *,
    name: str = "Trail bare",
    start_date: datetime = datetime(2026, 1, 1, 9, 0),
    distance_m: float = 25000.0,
    moving_time_s: int = 12000,
    elevation_gain_m: float = 1500.0,
) -> Activity:
    """Return an activity with the minimum scalar fields but no streams.

    Used by the unit tests that exercise the leaf function directly: they
    cover the category-exclusion branches and never need streams.
    """
    return Activity(
        source="garmin",
        user_id=user_id,
        name=name,
        activity_type=ActivityType.TRAIL_RUN,
        start_date=start_date,
        distance=distance_m,
        moving_time=moving_time_s,
        elapsed_time=moving_time_s + 60,
        total_elevation_gain=elevation_gain_m,
    )


# ---------------------------------------------------------------------------
# 1. Hard-coded category exclusions on the leaf function
# ---------------------------------------------------------------------------


def test_trail_factor_excludes_incident_non_scoring():
    """A ``incident_non_scoring`` activity (e.g. Trail des tranchées) must
    NEVER produce a trail_cost_factor observation, regardless of streams.

    R5 garde-fous: the exclusion is HARD-CODED inside
    :func:`extract_trail_cost_factor_observation` so a future refactor of
    the aggregator routing cannot accidentally let it through.
    """
    activity = _baseline_activity_no_streams(uuid4())
    assert "incident_non_scoring" in TRAIL_FACTOR_EXCLUDED_CATEGORIES
    obs = extract_trail_cost_factor_observation(
        activity,
        "incident_non_scoring",
        has_reconstructable_track=True,
    )
    assert obs is None


def test_trail_factor_excludes_execution_degraded_non_scoring():
    """An ``execution_degraded_non_scoring`` activity (e.g. UTMJ relai 5)
    must NEVER produce a trail_cost_factor observation."""
    activity = _baseline_activity_no_streams(uuid4())
    assert "execution_degraded_non_scoring" in TRAIL_FACTOR_EXCLUDED_CATEGORIES
    obs = extract_trail_cost_factor_observation(
        activity,
        "execution_degraded_non_scoring",
        has_reconstructable_track=True,
    )
    assert obs is None


def test_trail_factor_excludes_training_control():
    """A ``training_control`` activity must NEVER produce a trail_cost_factor
    observation: by definition the effort was not maximal, so it would bias
    the surface penalty downward."""
    activity = _baseline_activity_no_streams(uuid4())
    assert "training_control" in TRAIL_FACTOR_EXCLUDED_CATEGORIES
    obs = extract_trail_cost_factor_observation(
        activity,
        "training_control",
        has_reconstructable_track=True,
    )
    assert obs is None


def test_trail_factor_excludes_submax_physiological():
    """A ``submax_physiological`` activity must NEVER produce a
    trail_cost_factor observation: it is a training session by construction."""
    activity = _baseline_activity_no_streams(uuid4())
    assert "submax_physiological" in TRAIL_FACTOR_EXCLUDED_CATEGORIES
    obs = extract_trail_cost_factor_observation(
        activity,
        "submax_physiological",
        has_reconstructable_track=True,
    )
    assert obs is None
    # The other excluded categories follow the same contract; check a few
    # extras to lock the full set.
    for excluded in ("diagnostic", "non_scoring", "performance_anchor"):
        assert excluded in TRAIL_FACTOR_EXCLUDED_CATEGORIES
        assert (
            extract_trail_cost_factor_observation(
                activity,
                excluded,
                has_reconstructable_track=True,
            )
            is None
        )


# ---------------------------------------------------------------------------
# 2. Reconstructable-track requirement
# ---------------------------------------------------------------------------


def test_trail_factor_requires_reconstructable_track():
    """Without streams ``latlng + altitude`` and without an explicit
    ``has_reconstructable_track=True`` hint, the function returns None.

    R5: the personalised surface penalty cannot be calibrated without a
    track to replay. The aggregator passes the flag explicitly; unit tests
    can rely on the implicit check when ``has_reconstructable_track`` is
    omitted.
    """
    user = uuid4()
    # Same trail race, two stream variants: with and without latlng/altitude.
    with_track = _make_trail_activity(
        user,
        name="Trail with track",
        start_date=datetime(2026, 1, 5, 9, 0),
        include_latlng_altitude=True,
    )
    without_track = _make_trail_activity(
        user,
        name="Trail no track",
        start_date=datetime(2026, 1, 6, 9, 0),
        include_latlng_altitude=False,
    )

    # Implicit check: the function detects the missing latlng/altitude
    # streams on its own and refuses the observation.
    obs_no_track = extract_trail_cost_factor_observation(
        without_track, "trail_anchor"
    )
    assert obs_no_track is None

    # With latlng/altitude streams an observation is produced.
    obs_with_track = extract_trail_cost_factor_observation(
        with_track, "trail_anchor"
    )
    assert obs_with_track is not None
    assert obs_with_track["category"] == "trail_anchor"

    # The explicit hint also short-circuits the check even when no streams
    # are available (e.g. when a GPX is supplied out-of-band).
    bare = _baseline_activity_no_streams(user, name="Bare trail")
    obs_explicit_false = extract_trail_cost_factor_observation(
        bare, "trail_anchor", has_reconstructable_track=False
    )
    assert obs_explicit_false is None


# ---------------------------------------------------------------------------
# 3. Single observation = diagnostic-only mode
# ---------------------------------------------------------------------------


def test_trail_factor_single_official_clean_diagnostic_only(
    session: Session, user_id: UUID
):
    """With exactly 1 ``official_clean`` trail race, the aggregator returns
    an EMPTY trail_cost_factor list and records the diagnostic mode in
    ``debug_trace.aggregator``.

    R5: the personalised fusion stays inactive when n < 2. The single
    observation is preserved as a diagnostic so an operator can audit which
    race was picked up, but it does not flow into the Bayesian update.
    """
    trail = _make_trail_activity(
        user_id,
        name="Lone Trail",
        start_date=datetime(2026, 2, 1, 9, 0),
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

    debug: dict = {}
    observations = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1),
        debug_trace=debug,
    )

    # The list must be empty so the Bayesian fusion sees no evidence.
    assert observations["trail_cost_factor"] == []

    aggregator_trace = debug["aggregator"]
    assert aggregator_trace["trail_factor_mode"] == "prior_only_single_observation"
    assert aggregator_trace["trail_factor_evidence_count"] == 1
    assert aggregator_trace["trail_factor_inconsistent_evidence"] is False
    # The single observation must be surfaced as diagnostic so the operator
    # can audit which race contributed.
    diagnostic = aggregator_trace["trail_factor_diagnostic_observations"]
    assert isinstance(diagnostic, list) and len(diagnostic) == 1
    assert "Lone Trail" in diagnostic[0]["source_label"]


# ---------------------------------------------------------------------------
# 4. Two cohérent observations = personalised mode activated
# ---------------------------------------------------------------------------


def test_trail_factor_two_consistent_official_clean_STAYS_PRIOR_ONLY_until_residual_implemented(
    session: Session, user_id: UUID
):
    """FIX 2 (V2.3.1) - regression : avec 2 ``official_clean`` trail races
    aux residus coherents, la fusion personnalisee reste **desactivee** en
    V2.3.1 (mode ``prior_only_pending_proper_residual_calculation``).

    Raison : l'extracteur courant utilise une vitesse populationnelle fixe
    (3.3 m/s) au lieu du ``p_ref_steady_posterior`` reel de l'athlete. Activer
    la fusion produirait une fausse personnalisation. La personnalisation
    sera reactivee dans un lot futur quand le calcul residuel correct (rejeu
    GPX avec p_ref_steady_posterior et surface_factor=1.0) sera implemente.

    Le diagnostic conserve les observations pour audit.
    """
    trail_a = _make_trail_activity(
        user_id,
        name="Cohérent Trail A",
        start_date=datetime(2026, 1, 10, 9, 0),
        distance_m=25000.0,
        moving_time_s=12000,
        elevation_gain_m=1500.0,
    )
    trail_b = _make_trail_activity(
        user_id,
        name="Cohérent Trail B",
        start_date=datetime(2026, 2, 10, 9, 0),
        distance_m=25000.0,
        moving_time_s=12100,  # 100 s later; same residual within +/- 0.15
        elevation_gain_m=1500.0,
    )
    _persist(session, trail_a, trail_b)
    for activity in (trail_a, trail_b):
        session.add(
            RaceValidationReference(
                user_id=user_id,
                activity_id=activity.id,
                category="official_clean",
            )
        )
    session.commit()

    debug: dict = {}
    observations = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1),
        debug_trace=debug,
    )

    # FIX 2 : meme avec 2 observations coherentes, la liste fusionnee reste
    # vide (activate_fusion=False) en V2.3.1.
    assert observations["trail_cost_factor"] == []
    aggregator_trace = debug["aggregator"]
    assert aggregator_trace["trail_factor_mode"] == (
        "prior_only_pending_proper_residual_calculation"
    )
    assert "prior_only" in aggregator_trace["trail_factor_mode"]
    assert aggregator_trace["trail_factor_evidence_count"] == 2
    assert aggregator_trace["trail_factor_inconsistent_evidence"] is False
    # Les observations sont conservees comme diagnostic pour traçabilite.
    diagnostic = aggregator_trace["trail_factor_diagnostic_observations"]
    assert isinstance(diagnostic, list) and len(diagnostic) == 2


def test_trail_factor_personalization_documented_as_deferred():
    """FIX 2 (V2.3.1) : la docstring de ``_decide_trail_factor_activation``
    doit explicitement documenter l'intention de differer la personnalisation
    jusqu'a l'implementation du calcul residuel correct."""
    from app.domain.services.race_predictor.observation_aggregator import (
        _decide_trail_factor_activation,
    )

    doc = _decide_trail_factor_activation.__doc__ or ""
    assert "prior_only" in doc
    # Le mot 'differer' / 'deferred' / 'future' / 'lot' est attendu pour
    # signaler que la personnalisation est volontairement reportee.
    lowered = doc.lower()
    assert (
        "deferred" in lowered
        or "lot futur" in lowered
        or "réactiv" in lowered
        or "reactiv" in lowered
        or "désactivée" in lowered
        or "desactivee" in lowered
    ), (
        "La docstring doit signaler que la personnalisation est differee "
        f"jusqu'au lot futur. Docstring courante: {doc[:300]}"
    )


# ---------------------------------------------------------------------------
# 5. Two inconsistent observations = fallback prior + diagnostic
# ---------------------------------------------------------------------------


def test_trail_factor_two_inconsistent_official_clean_fallback_prior(
    session: Session, user_id: UUID
):
    """When two trail observations are >0.15 apart on the residual mean,
    the aggregator clears the list and records the
    ``inconsistent_evidence_fallback_prior`` diagnostic.

    Constructing two races whose computed residuals diverge by > 0.15 is
    fragile because the leaf function clamps to [1.0, 1.6]. We bypass the
    natural extraction by calling :func:`_decide_trail_factor_activation`
    indirectly: we monkey-patch the aggregator state through a custom
    observation list to exercise the cohérence check deterministically.
    """
    from app.domain.services.race_predictor.observation_aggregator import (
        _decide_trail_factor_activation,
    )

    diverging = [
        {
            "mean": 1.10,
            "std": 0.08,
            "weight": 1.0,
            "source_label": "trail:Low residual",
            "source_id": None,
            "source_type": "activity",
            "performed_at": None,
            "category": "trail_anchor",
            "quality_flags": ["uncertain_extraction"],
        },
        {
            "mean": 1.45,  # 0.35 apart -> clearly > 0.15 threshold
            "std": 0.08,
            "weight": 1.0,
            "source_label": "trail:High residual",
            "source_id": None,
            "source_type": "activity",
            "performed_at": None,
            "category": "trail_anchor",
            "quality_flags": ["uncertain_extraction"],
        },
    ]
    decision = _decide_trail_factor_activation(diverging)
    assert decision["activate_fusion"] is False
    assert decision["mode"] == "inconsistent_evidence_fallback_prior"
    assert decision["inconsistent_evidence"] is True
    assert decision["evidence_count"] == 2
    diag = decision["diagnostic_observations"]
    assert isinstance(diag, list) and len(diag) == 2
    # FIX 2 (V2.3.1) : meme avec 2 observations coherentes (+/- 0.15), la
    # fusion personnalisee reste desactivee en V2.3.1 (mode
    # ``prior_only_pending_proper_residual_calculation``). Les observations
    # sont conservees en diagnostic. Voir
    # ``test_trail_factor_two_consistent_official_clean_STAYS_PRIOR_ONLY_until_residual_implemented``.
    consistent = [
        {**diverging[0], "mean": 1.20},
        {**diverging[1], "mean": 1.30},
    ]
    decision_ok = _decide_trail_factor_activation(consistent)
    assert decision_ok["activate_fusion"] is False
    assert decision_ok["mode"] == "prior_only_pending_proper_residual_calculation"
    assert decision_ok["inconsistent_evidence"] is False
    assert isinstance(decision_ok["diagnostic_observations"], list)
    assert len(decision_ok["diagnostic_observations"]) == 2


# ---------------------------------------------------------------------------
# 6. Aggregator integration: real user (no official_clean) -> prior only
# ---------------------------------------------------------------------------


def test_aggregate_with_real_user_no_official_clean_uses_prior_only(
    session: Session, user_id: UUID
):
    """A user with only non-scoring trail races (incident / degraded /
    training_control) must end up with an empty trail_cost_factor list and
    the ``prior_only`` diagnostic mode, mirroring the production user
    ``b5727f6086db41ab86e2bc803460b868`` for whom no ``official_clean``
    race has been tagged.
    """
    incident = _make_trail_activity(
        user_id,
        name="Trail des tranchees",
        start_date=datetime(2026, 1, 20, 9, 0),
    )
    degraded = _make_trail_activity(
        user_id,
        name="UTMJ relai 5",
        start_date=datetime(2026, 2, 20, 9, 0),
    )
    training = _make_trail_activity(
        user_id,
        name="Sortie longue contrôle",
        start_date=datetime(2026, 3, 20, 9, 0),
    )
    _persist(session, incident, degraded, training)
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=incident.id,
            category="incident_non_scoring",
        )
    )
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=degraded.id,
            category="execution_degraded_non_scoring",
        )
    )
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=training.id,
            category="training_control",
        )
    )
    session.commit()

    debug: dict = {}
    observations = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1),
        debug_trace=debug,
    )

    assert observations["trail_cost_factor"] == []
    aggregator_trace = debug["aggregator"]
    assert aggregator_trace["trail_factor_mode"] == "prior_only"
    assert aggregator_trace["trail_factor_evidence_count"] == 0
    assert aggregator_trace["trail_factor_inconsistent_evidence"] is False
    # The diagnostic_observations field is None when no observation was
    # collected at all.
    assert aggregator_trace["trail_factor_diagnostic_observations"] is None


# ---------------------------------------------------------------------------
# 7. End-to-end: predict_v2_3 on a no-history user uses the prior
# ---------------------------------------------------------------------------


_TRAIL_GPX = """<?xml version='1.0' encoding='UTF-8'?>
<gpx version='1.1' creator='test'>
  <trk><name>trail</name><trkseg>
""" + "\n".join(
    f"    <trkpt lat='46.{6000 + i:04d}' lon='6.{4000 + i:04d}'>"
    f"<ele>{500 + (i * 7) % 60}</ele></trkpt>"
    for i in range(60)
) + """
  </trkseg></trk>
</gpx>
"""


def test_predict_v2_3_uses_prior_trail_factor_when_no_clean_evidence(
    session: Session, user_id: UUID
):
    """End-to-end on a user with zero ``official_clean`` trail races:
    ``predict_v2_3`` must apply the population prior on the trail factor.

    Mirrors the production user ``b5727f6086db41ab86e2bc803460b868`` for
    whom only non-scoring trail races are tagged. The expected behaviour
    is:

    - ``physics_inputs["trail_factor_used"]`` falls in the population
      prior range (centered on 1.20 with the configured trail-tilt for the
      profile), well within [1.05, 1.45].
    - ``athlete_model.debug_trace.trail_factor.mode == "prior_only"``.
    - ``athlete_model.debug_trace.trail_factor.applied_factor_source ==
      "population_prior"``.
    - ``athlete_model.posterior.trail_cost_factor.evidence_count == 0``.
    """
    # Seed only non-scoring trails so the aggregator finds zero
    # ``official_clean`` evidence (mirrors the real user).
    incident = _make_trail_activity(
        user_id,
        name="Trail des tranchees",
        start_date=datetime(2025, 10, 20, 9, 0),
    )
    degraded = _make_trail_activity(
        user_id,
        name="UTMJ relai 5",
        start_date=datetime(2025, 11, 20, 9, 0),
    )
    _persist(session, incident, degraded)
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=incident.id,
            category="incident_non_scoring",
        )
    )
    session.add(
        RaceValidationReference(
            user_id=user_id,
            activity_id=degraded.id,
            category="execution_degraded_non_scoring",
        )
    )
    session.commit()

    response = predict_v2_3(
        session,
        user_id,
        _TRAIL_GPX,
        race_datetime=None,
        effort_mode="steady",
        analysis_mode="trail",
        target_heartrate=None,
        weather_mode="manual",
        manual_temperature_c=12.0,
        ravito_mode="auto",
        custom_ravitos=None,
        as_of_date=datetime(2026, 6, 1, 0, 0),
    )

    # The population prior must be the one applied.
    physics_inputs = response["physics_inputs"]
    assert 1.05 <= physics_inputs["trail_factor_used"] <= 1.45

    # The athlete_model.debug_trace must reflect the prior-only mode.
    athlete_debug = response["athlete_model"]["debug_trace"]["trail_factor"]
    assert athlete_debug["mode"] == "prior_only"
    assert athlete_debug["evidence_count"] == 0
    assert athlete_debug["inconsistent_evidence"] is False
    assert athlete_debug["applied_factor_source"] == "population_prior"

    # The posterior reflects zero evidence so the prior fully dominates.
    posterior = response["athlete_model"]["posterior"]["trail_cost_factor"]
    assert int(posterior["evidence_count"]) == 0
