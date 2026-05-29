"""R1 V2.3.1 blocking tests for the p_ref_steady / p_capacity_test split.

These tests assert the contract introduced by Lot R1 of the V2.3.1 fix plan
(`docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md`):

1. ``p_ref_steady_wkg`` is extracted from the historical activity stream
   filtered by a narrow FC band ``[0.72, 0.78] x FCmax`` (V2.3.1 R1).
2. ``p_capacity_test_wkg`` is alimented by ``ReferenceTest`` only and is
   **never consumed by the V2.3.1 engine** (``consumed_by_engine = false``).
3. Adding a 10K test does not accelerate a long V2.3.1 prediction.
4. Two histories with the same physiological capacity but different
   training compositions converge on the same ``p_ref_steady_wkg``.
5. ``history_start_date`` is applied by the aggregator.
6. When samples in the principal band are too few, the aggregator falls
   back to the wider band ``[0.68, 0.82]`` and inflates the std by 1.5x.
7. The aggregator publishes the FC band metadata in ``debug_trace``.

Every test uses an isolated in-memory SQLite database via the ``session``
fixture so no developer database is touched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.domain.entities import (  # noqa: F401 -- registers SQLModel tables
    Activity,
    AthleticProfile,
    RaceValidationReference,
    ReferenceTest,
    ReferenceTestQuality,
    ReferenceTestType,
    User,
)
from app.domain.entities.activity import ActivityType
from app.domain.entities.athletic_profile import (
    ActivityLevel,
    AthleticSex,
    ExperienceLevel,
    PracticeDominant,
    WeeklyVolumeBand,
)
from app.domain.services.race_predictor.observation_aggregator import (
    FC_BAND_FALLBACK,
    FC_BAND_PRIMARY,
    aggregate_observations,
)
from app.domain.services.race_predictor.v2_3_prediction_service import predict_v2_3
from app.domain.services.race_predictor.v3_prediction_service import predict_v3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_SAMPLE_GPX = """<?xml version='1.0' encoding='UTF-8'?>
<gpx version='1.1' creator='test'>
  <trk><name>test</name><trkseg>
    <trkpt lat='46.6000' lon='6.4000'><ele>500</ele></trkpt>
    <trkpt lat='46.6010' lon='6.4010'><ele>505</ele></trkpt>
    <trkpt lat='46.6020' lon='6.4020'><ele>510</ele></trkpt>
    <trkpt lat='46.6030' lon='6.4030'><ele>515</ele></trkpt>
    <trkpt lat='46.6040' lon='6.4040'><ele>520</ele></trkpt>
    <trkpt lat='46.6050' lon='6.4050'><ele>525</ele></trkpt>
    <trkpt lat='46.6060' lon='6.4060'><ele>530</ele></trkpt>
    <trkpt lat='46.6070' lon='6.4070'><ele>540</ele></trkpt>
    <trkpt lat='46.6080' lon='6.4080'><ele>545</ele></trkpt>
    <trkpt lat='46.6090' lon='6.4090'><ele>540</ele></trkpt>
    <trkpt lat='46.6100' lon='6.4100'><ele>535</ele></trkpt>
    <trkpt lat='46.6110' lon='6.4110'><ele>530</ele></trkpt>
    <trkpt lat='46.6120' lon='6.4120'><ele>525</ele></trkpt>
    <trkpt lat='46.6130' lon='6.4130'><ele>520</ele></trkpt>
    <trkpt lat='46.6140' lon='6.4140'><ele>515</ele></trkpt>
    <trkpt lat='46.6150' lon='6.4150'><ele>510</ele></trkpt>
    <trkpt lat='46.6160' lon='6.4160'><ele>505</ele></trkpt>
    <trkpt lat='46.6170' lon='6.4170'><ele>500</ele></trkpt>
    <trkpt lat='46.6180' lon='6.4180'><ele>495</ele></trkpt>
    <trkpt lat='46.6190' lon='6.4190'><ele>500</ele></trkpt>
    <trkpt lat='46.6200' lon='6.4200'><ele>505</ele></trkpt>
    <trkpt lat='46.6210' lon='6.4210'><ele>510</ele></trkpt>
    <trkpt lat='46.6220' lon='6.4220'><ele>515</ele></trkpt>
    <trkpt lat='46.6230' lon='6.4230'><ele>510</ele></trkpt>
    <trkpt lat='46.6240' lon='6.4240'><ele>505</ele></trkpt>
    <trkpt lat='46.6250' lon='6.4250'><ele>500</ele></trkpt>
    <trkpt lat='46.6260' lon='6.4260'><ele>495</ele></trkpt>
    <trkpt lat='46.6270' lon='6.4270'><ele>490</ele></trkpt>
    <trkpt lat='46.6280' lon='6.4280'><ele>485</ele></trkpt>
    <trkpt lat='46.6290' lon='6.4290'><ele>480</ele></trkpt>
    <trkpt lat='46.6300' lon='6.4300'><ele>475</ele></trkpt>
    <trkpt lat='46.6310' lon='6.4310'><ele>470</ele></trkpt>
    <trkpt lat='46.6320' lon='6.4320'><ele>475</ele></trkpt>
    <trkpt lat='46.6330' lon='6.4330'><ele>480</ele></trkpt>
    <trkpt lat='46.6340' lon='6.4340'><ele>485</ele></trkpt>
    <trkpt lat='46.6350' lon='6.4350'><ele>490</ele></trkpt>
    <trkpt lat='46.6360' lon='6.4360'><ele>495</ele></trkpt>
    <trkpt lat='46.6370' lon='6.4370'><ele>500</ele></trkpt>
    <trkpt lat='46.6380' lon='6.4380'><ele>505</ele></trkpt>
    <trkpt lat='46.6390' lon='6.4390'><ele>510</ele></trkpt>
    <trkpt lat='46.6400' lon='6.4400'><ele>515</ele></trkpt>
    <trkpt lat='46.6410' lon='6.4410'><ele>520</ele></trkpt>
    <trkpt lat='46.6420' lon='6.4420'><ele>525</ele></trkpt>
    <trkpt lat='46.6430' lon='6.4430'><ele>530</ele></trkpt>
  </trkseg></trk>
</gpx>
"""


@pytest.fixture()
def session() -> Session:
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
        email="r1-tester@example.com",
        full_name="R1 Tester",
        hashed_password="not-a-real-hash",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _common_kwargs(as_of_date: datetime = datetime(2026, 6, 1, 0, 0)) -> dict:
    return dict(
        race_datetime=None,
        effort_mode="steady",
        analysis_mode="trail",
        target_heartrate=None,
        weather_mode="manual",
        manual_temperature_c=12.0,
        ravito_mode="auto",
        custom_ravitos=None,
        as_of_date=as_of_date,
    )


def _seed_tempo_history(
    session: Session,
    user_id: UUID,
    *,
    n_activities: int = 5,
    speed_mps: float = 3.0,
    hr_bpm: float = 140.0,
    max_heartrate: float = 185.0,
    start_date: datetime = datetime(2026, 1, 1, 9, 0),
) -> list[UUID]:
    """Seed several tempo runs whose HR sits in the principal FC band.

    With ``max_heartrate=185`` the principal band ``[0.72, 0.78] * 185``
    spans ``[133, 144]``, so ``hr_bpm=140`` falls inside.
    """
    ids: list[UUID] = []
    duration_s = 60 * 60  # 60 min
    distance_m = speed_mps * duration_s
    for i in range(n_activities):
        activity = Activity(
            source="garmin",
            user_id=user_id,
            name=f"Tempo run {i + 1}",
            activity_type=ActivityType.RUN,
            start_date=start_date + timedelta(days=i),
            distance=distance_m,
            moving_time=duration_s,
            elapsed_time=duration_s + 30,
            total_elevation_gain=20.0,
            average_speed=speed_mps,
            average_heartrate=hr_bpm,
            max_heartrate=max_heartrate,
            streams_data={
                "heartrate": {"data": [
                    161.0 if j < max(6, duration_s // 100) else hr_bpm - 1 + (j % 5)
                    for j in range(duration_s)
                ]},
                "velocity_smooth": {"data": [speed_mps for _ in range(duration_s)]},
                "grade_smooth": {"data": [0.4 for _ in range(duration_s)]},
                "time": {"data": [float(j) for j in range(duration_s)]},
                "distance": {"data": [speed_mps * j for j in range(duration_s)]},
            },
        )
        session.add(activity)
        session.commit()
        session.refresh(activity)
        ids.append(activity.id)  # type: ignore[arg-type]
    return ids


def _add_profile(session: Session, user_id: UUID) -> None:
    now = datetime.utcnow()
    profile = AthleticProfile(
        user_id=user_id,
        created_at=now,
        updated_at=now,
        sex=AthleticSex.MALE,
        birth_date=date(1990, 1, 1),
        height_cm=178.0,
        weight_kg=72.0,
        activity_level=ActivityLevel.ACTIVE,
        experience_level=ExperienceLevel.REGULAR,
        practice_dominant=PracticeDominant.TRAIL,
        weekly_volume_band=WeeklyVolumeBand.BAND_40_60KM,
    )
    session.add(profile)
    session.commit()


# ---------------------------------------------------------------------------
# 1. A maximal 10K test must not accelerate the long V2.3.1 prediction.
# ---------------------------------------------------------------------------


def test_add_max_10k_test_does_not_accelerate_long_prediction(
    session: Session, user_id: UUID
) -> None:
    """Bug V2.2 reproduit: ajouter un 10K maximal ne doit pas faire baisser
    le temps predit V2.3.1.

    1. Configure an athlete with a stable historical tempo (5 sessions at
       3.0 m/s, HR 140 -- inside the principal FC band).
    2. Run predict_v2_3 without ReferenceTest -> moving_time_min = X.
    3. Add a road_10k ReferenceTest at a much faster speed (4.5 m/s) that
       would inflate the V2.2 capacity by ~50%.
    4. Run predict_v2_3 again -> moving_time_min = Y.
    5. Assert Y >= X * 0.95 (no significant acceleration). The test is
       informative only and must not move the predicted time.
    """
    _seed_tempo_history(session, user_id, n_activities=5, speed_mps=3.0, hr_bpm=140.0)

    # Step 2: prediction without any reference test.
    baseline = predict_v2_3(session, user_id, _SAMPLE_GPX, **_common_kwargs())
    moving_baseline = float(baseline["summary"]["moving_time_min"])
    assert moving_baseline > 0

    # Step 3: add a *very fast* 10K maximal test.
    fast_test = ReferenceTest(
        user_id=user_id,
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=datetime(2026, 1, 20, 9, 0),
        duration_seconds=2222,  # 37min - quite fast 10K ~ 4.5 m/s
        distance_m=10000.0,
        quality_status=ReferenceTestQuality.VALID,
    )
    session.add(fast_test)
    session.commit()

    with_test = predict_v2_3(session, user_id, _SAMPLE_GPX, **_common_kwargs())
    moving_with_test = float(with_test["summary"]["moving_time_min"])

    # The 10K test must populate p_capacity_test_wkg (informative).
    posterior_test = with_test["athlete_model"]["posterior"]["p_capacity_test_wkg"]
    assert posterior_test["evidence_count"] == 1
    assert posterior_test.get("consumed_by_engine") is False

    # No acceleration: the predicted moving time must not drop by more than 5 %
    # (it should not drop at all, but we tolerate a small numerical wobble).
    assert moving_with_test >= moving_baseline * 0.95, (
        f"V2.3.1 must not accelerate the prediction after adding a maximal "
        f"10K test (was {moving_baseline:.1f} min, became "
        f"{moving_with_test:.1f} min)."
    )
    # Engine input must stay the same: p_ref_steady_wkg only.
    p_run_baseline = baseline["physics_inputs"]["p_run_wkg_used"]
    p_run_with_test = with_test["physics_inputs"]["p_run_wkg_used"]
    assert p_run_with_test == pytest.approx(p_run_baseline, rel=1e-6), (
        f"physics_inputs.p_run_wkg_used must not be affected by the "
        f"maximal 10K test (baseline {p_run_baseline:.3f}, with_test "
        f"{p_run_with_test:.3f})."
    )


# ---------------------------------------------------------------------------
# 2. Two histories with same capacity but different composition -> same p_ref.
# ---------------------------------------------------------------------------


def test_same_capacity_different_training_composition_yield_same_p_ref(
    session: Session, user_id: UUID
) -> None:
    """Two histories with the same physiological capacity but different
    training compositions must converge on the same p_ref_steady_wkg.

    Athlete A: 10 sessions at HR ~120 bpm (Z2, BELOW the principal band).
    Athlete B: 5 sessions at HR ~140 bpm (Z3-Z4, INSIDE the band) plus
                5 sessions at HR ~120 bpm (Z2).

    The FC band filter must reject the Z2 samples from both athletes. Only
    the band-fitting samples drive the observation. If athlete A produces a
    posterior anyway (via fallback band) it must still be in a comparable
    range because the underlying treadmill speed is identical.
    """
    # Athlete B (has band-fitting samples).
    _seed_tempo_history(
        session,
        user_id,
        n_activities=5,
        speed_mps=3.0,
        hr_bpm=140.0,
        max_heartrate=185.0,
        start_date=datetime(2026, 1, 1, 9, 0),
    )
    # Additional Z2 sessions for athlete B.
    _seed_tempo_history(
        session,
        user_id,
        n_activities=5,
        speed_mps=3.0,
        hr_bpm=120.0,  # below band
        max_heartrate=185.0,
        start_date=datetime(2026, 2, 1, 9, 0),
    )

    obs_b = aggregate_observations(
        session, user_id, as_of_date=datetime(2026, 6, 1, 0, 0)
    )
    obs_b_list = obs_b["p_ref_steady_wkg"]
    assert len(obs_b_list) >= 1, "Athlete B should produce evidence in the band"
    means_b = [o["mean"] for o in obs_b_list]
    median_b = sorted(means_b)[len(means_b) // 2]

    # Athlete A: only Z2 sessions, same underlying speed.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s2:
        u = User(email="a@a.com", full_name="A", hashed_password="x")
        s2.add(u)
        s2.commit()
        s2.refresh(u)
        _seed_tempo_history(
            s2,
            u.id,
            n_activities=10,
            speed_mps=3.0,
            hr_bpm=120.0,
            max_heartrate=185.0,
        )
        obs_a = aggregate_observations(
            s2, u.id, as_of_date=datetime(2026, 6, 1, 0, 0)
        )["p_ref_steady_wkg"]
        # When athlete A has no band-fitting samples, the principal band
        # check fails AND the fallback band also fails (HR=120 sits below
        # 0.68*185=125.8). The aggregator returns an empty list, and the
        # prior dominates the posterior, which is the expected behaviour:
        # the contract guarantees we don't make up evidence.
        assert obs_a == [], (
            "Athlete A's HR is below the fallback band; the aggregator must "
            "not publish any evidence-based p_ref_steady_wkg."
        )

    # Athlete B's posterior centers on 3.6 * 3.0 = 10.8 W/kg regardless of
    # the additional Z2 sessions (Z2 contributes 0 samples in the band).
    expected_p_ref = 3.6 * 3.0
    assert abs(median_b - expected_p_ref) < 0.5, (
        f"Athlete B's p_ref_steady median {median_b:.2f} should be close "
        f"to {expected_p_ref:.2f} W/kg, independent of the Z2 padding."
    )


# ---------------------------------------------------------------------------
# 3. history_start_date filter must be applied.
# ---------------------------------------------------------------------------


def test_history_start_date_filter_applied(session: Session, user_id: UUID) -> None:
    """Changing history_start_date must change the list of observations."""
    # Seed 4 activities at different dates.
    activity_ids: list[UUID] = []
    for i, day in enumerate((1, 15, 60, 90)):  # day 1, 15, 60, 90 of 2026
        ids = _seed_tempo_history(
            session,
            user_id,
            n_activities=1,
            speed_mps=3.0,
            hr_bpm=140.0,
            max_heartrate=185.0,
            start_date=datetime(2026, 1, 1) + timedelta(days=day),
        )
        activity_ids.extend(ids)

    # Full window: all 4 activities in band (need >= 3 for principal band).
    obs_full = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        history_start_date=datetime(2025, 12, 31),
    )
    sources_full = {o["source_label"] for o in obs_full["p_ref_steady_wkg"]}

    # Tight window: only activities >= 2026-03-01 (day 60+) -> only 2 left,
    # which fails MIN_ACTIVITIES_IN_BAND -> aggregator falls back, but the
    # fallback also fails (still only 2 activities) -> empty list, but the
    # window must be reflected in debug_trace.
    debug: dict = {}
    obs_tight = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        history_start_date=datetime(2026, 3, 1),
        debug_trace=debug,
    )
    sources_tight = {o["source_label"] for o in obs_tight["p_ref_steady_wkg"]}

    # Full window has more (or equal) sources than the tight window.
    assert len(sources_full) > len(sources_tight)
    # Activities before 2026-03-01 must not appear in tight.
    assert not any("Tempo run 1" in s for s in sources_tight)  # day 1
    assert not any("Tempo run 2" in s for s in sources_tight)  # day 15

    # Debug trace must reflect the applied window.
    aggregator_debug = debug["aggregator"]
    assert aggregator_debug["history_start_date_applied"].startswith("2026-03-01")
    assert aggregator_debug["history_start_date_explicit"] is True
    assert aggregator_debug["history_period_days"] >= 0


# ---------------------------------------------------------------------------
# 4. p_capacity_test_wkg is exposed but not consumed by the engine.
# ---------------------------------------------------------------------------


def test_p_capacity_test_wkg_exposed_but_not_consumed_by_engine(
    session: Session, user_id: UUID
) -> None:
    """An athlete with one 10K reference test but no historical activities
    must expose p_capacity_test_wkg with ``consumed_by_engine = false`` and
    use ONLY the prior for the engine's p_ref_steady_wkg input.
    """
    test = ReferenceTest(
        user_id=user_id,
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=datetime(2026, 1, 10, 9, 0),
        duration_seconds=2400,
        distance_m=10000.0,
        quality_status=ReferenceTestQuality.VALID,
    )
    session.add(test)
    session.commit()

    result = predict_v2_3(session, user_id, _SAMPLE_GPX, **_common_kwargs())
    posterior = result["athlete_model"]["posterior"]

    # p_capacity_test_wkg present with the informative-only flag.
    assert "p_capacity_test_wkg" in posterior
    p_cap = posterior["p_capacity_test_wkg"]
    assert p_cap["evidence_count"] == 1
    assert p_cap.get("consumed_by_engine") is False
    assert p_cap.get("informative_only") is True

    # p_ref_steady_wkg must remain prior-driven (no historical activity).
    p_ref = posterior["p_ref_steady_wkg"]
    assert p_ref["evidence_count"] == 0
    assert p_ref["evidence_weight_pct"] == 0.0

    # Engine consumed the prior mean (no test contamination).
    prior_p_ref_mean = result["athlete_model"]["prior"]["p_ref_steady_wkg"]["mean"]
    assert result["physics_inputs"]["p_run_wkg_used"] == pytest.approx(
        prior_p_ref_mean, rel=1e-3
    )
    # Calibration trace marker.
    assert result["calibration"]["p_capacity_test_consumed"] is False


# ---------------------------------------------------------------------------
# 5. Fallback band when samples in [0.72, 0.78] are insufficient.
# ---------------------------------------------------------------------------


def test_fc_band_fallback_used_when_insufficient_samples(
    session: Session, user_id: UUID
) -> None:
    """Athlete history outside the principal band must trigger the fallback.

    HR=130 sits inside ``[0.68, 0.82]*185 = [125.8, 151.7]`` but below the
    principal band ``[133, 144]``. Three activities provide enough fallback
    samples (60+) and enough activities (3+) so the aggregator publishes
    fallback-grade observations with std inflated by 1.5x.
    """
    _seed_tempo_history(
        session,
        user_id,
        n_activities=3,
        speed_mps=3.0,
        hr_bpm=130.0,  # within fallback band but outside principal
        max_heartrate=185.0,
    )

    debug: dict = {}
    obs = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        debug_trace=debug,
    )
    p_ref = obs["p_ref_steady_wkg"]
    assert len(p_ref) >= 1, "Fallback band should still publish observations"

    aggregator_debug = debug["aggregator"]
    assert aggregator_debug["fc_band_fallback"] is True
    assert list(aggregator_debug["fc_band_used"]) == list(FC_BAND_FALLBACK)
    assert aggregator_debug["samples_in_band"] >= 60
    assert aggregator_debug["activities_in_band"] >= 3

    # Every observation carries the fallback flag and an inflated std.
    for obs_dict in p_ref:
        assert "fc_band_fallback" in obs_dict["quality_flags"]


def test_principal_band_used_when_enough_samples(
    session: Session, user_id: UUID
) -> None:
    """Sanity check: HR inside the principal band must NOT trigger fallback."""
    _seed_tempo_history(
        session,
        user_id,
        n_activities=3,
        speed_mps=3.0,
        hr_bpm=140.0,  # inside principal band
        max_heartrate=185.0,
    )

    debug: dict = {}
    obs = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        debug_trace=debug,
    )
    assert len(obs["p_ref_steady_wkg"]) >= 1
    aggregator_debug = debug["aggregator"]
    assert aggregator_debug["fc_band_fallback"] is False
    assert list(aggregator_debug["fc_band_used"]) == list(FC_BAND_PRIMARY)
    for obs_dict in obs["p_ref_steady_wkg"]:
        assert "fc_band_fallback" not in obs_dict["quality_flags"]


# ---------------------------------------------------------------------------
# 6. Aggregator must log FC band + history metadata in debug_trace.
# ---------------------------------------------------------------------------


def test_p_ref_steady_wkg_aggregator_logs_debug_metadata(
    session: Session, user_id: UUID
) -> None:
    """The aggregator must populate every R1-required debug field."""
    _seed_tempo_history(
        session, user_id, n_activities=3, speed_mps=3.0, hr_bpm=140.0
    )

    debug: dict = {}
    aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        debug_trace=debug,
    )
    aggregator_debug = debug["aggregator"]
    required_keys = {
        "fc_band_used",
        "fc_band_fallback",
        "samples_in_band",
        "activities_in_band",
        "history_start_date_applied",
        "history_period_days",
        "fcmax_estimate_bpm",
    }
    assert required_keys.issubset(aggregator_debug.keys()), (
        f"Missing debug keys: {required_keys - aggregator_debug.keys()}"
    )
    assert isinstance(aggregator_debug["fc_band_used"], list)
    assert len(aggregator_debug["fc_band_used"]) == 2
    assert isinstance(aggregator_debug["fc_band_fallback"], bool)
    assert isinstance(aggregator_debug["samples_in_band"], int)
    assert isinstance(aggregator_debug["activities_in_band"], int)
    assert isinstance(aggregator_debug["history_period_days"], int)
    assert aggregator_debug["history_period_days"] > 0
    # FCmax in plausible range.
    fcmax = aggregator_debug["fcmax_estimate_bpm"]
    assert fcmax is None or 110.0 <= float(fcmax) <= 230.0


def test_v3_accepts_single_well_sampled_garmin_activity_with_wider_uncertainty(
    session: Session, user_id: UUID
) -> None:
    """V3 uses isolated Garmin evidence; V2.3.1 remains strict."""
    _seed_tempo_history(
        session, user_id, n_activities=1, speed_mps=3.0, hr_bpm=140.0
    )
    strict_debug: dict = {}
    strict = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        debug_trace=strict_debug,
    )
    v3_debug: dict = {}
    sparse = aggregate_observations(
        session,
        user_id,
        as_of_date=datetime(2026, 6, 1, 0, 0),
        debug_trace=v3_debug,
        evidence_policy="weighted_sparse",
    )

    assert strict["p_ref_steady_wkg"] == []
    assert len(sparse["p_ref_steady_wkg"]) == 1
    assert "sparse_evidence" in sparse["p_ref_steady_wkg"][0]["quality_flags"]
    assert v3_debug["aggregator"]["sparse_evidence_accepted"] is True


def test_v3_sparse_evidence_accelerates_prior_only_prediction_without_rf_correction(
    session: Session, user_id: UUID
) -> None:
    _seed_tempo_history(
        session, user_id, n_activities=1, speed_mps=3.2, hr_bpm=140.0
    )
    strict = predict_v2_3(session, user_id, _SAMPLE_GPX, **_common_kwargs())
    v3 = predict_v3(session, user_id, _SAMPLE_GPX, **_common_kwargs())

    assert v3["engine_version"] == "v3_hybrid"
    assert v3["debug_trace"]["v3_sparse_evidence"] is True
    assert v3["summary"]["moving_time_min"] < strict["summary"]["moving_time_min"]
    residual = v3["hybrid_model"]["residual_correction"]
    assert residual["applied"] is False
    assert residual["status"] == "inactive_insufficient_qualified_references"
