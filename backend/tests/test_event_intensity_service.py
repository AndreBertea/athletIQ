"""Tests for event_intensity_service (Race Predictor V2.2)."""

from __future__ import annotations

import math

import pytest

from app.domain.services.race_predictor.event_intensity_service import (
    ANCHOR_TABLE,
    EFFORT_MODE_MULTIPLIERS,
    MAX_FRACTION,
    MIN_FRACTION_EXTRAPOLATION,
    derive_event_power,
    iterate_event_power,
    sustainable_fraction,
)


# ---------------------------------------------------------------------------
# sustainable_fraction - anchor exactness
# ---------------------------------------------------------------------------


def test_sustainable_fraction_5k_duration_returns_one():
    """At 20 minutes (5K equivalent) the reference fraction is exactly 1.00."""
    assert sustainable_fraction(20, 0.12, "steady") == pytest.approx(1.00, abs=1e-6)


def test_sustainable_fraction_marathon_around_82pct():
    """At 180 minutes (marathon) the fraction is 0.82 +/- 0.02."""
    fraction = sustainable_fraction(180, 0.12, "steady")
    assert fraction == pytest.approx(0.82, abs=0.02)


def test_sustainable_fraction_each_anchor_point_matches():
    """Every anchor point in the table must be reproduced exactly."""
    for duration, expected in ANCHOR_TABLE:
        assert sustainable_fraction(duration, 0.12, "steady") == pytest.approx(
            expected, abs=1e-6
        ), f"Anchor mismatch at duration={duration}"


# ---------------------------------------------------------------------------
# sustainable_fraction - monotonicity and ordering
# ---------------------------------------------------------------------------


def test_sustainable_fraction_ultra_lower_than_marathon():
    """A 100K race (600 min) must yield a smaller fraction than a marathon."""
    marathon = sustainable_fraction(180, 0.12, "steady")
    hundred_k = sustainable_fraction(600, 0.12, "steady")
    assert hundred_k < marathon


def test_sustainable_fraction_monotonic_decreasing():
    """The fraction is non-increasing with duration on a fine grid."""
    durations = list(range(20, 1500, 10))
    prev = sustainable_fraction(durations[0], 0.12, "steady")
    for dur in durations[1:]:
        cur = sustainable_fraction(dur, 0.12, "steady")
        # Allow strict equality only at the floor; otherwise strictly decreasing.
        assert cur <= prev + 1e-9, f"Non-monotonic at duration={dur}: {prev} -> {cur}"
        prev = cur


def test_sustainable_fraction_below_20min_capped_at_max():
    """Durations below the 20-minute anchor are capped at the sprint ceiling."""
    sprint = sustainable_fraction(5, 0.12, "steady")
    assert sprint == pytest.approx(MAX_FRACTION, abs=1e-6)


def test_sustainable_fraction_extrapolation_above_anchor_has_floor():
    """Extrapolation past 960 min stays >= MIN_FRACTION_EXTRAPOLATION."""
    huge = sustainable_fraction(2880, 0.12, "steady")  # 48h race
    assert huge >= MIN_FRACTION_EXTRAPOLATION - 1e-9
    # And it stays below the last anchor's value (0.55).
    assert huge < 0.55


# ---------------------------------------------------------------------------
# sustainable_fraction - durability alpha modulation
# ---------------------------------------------------------------------------


def test_sustainable_fraction_durability_alpha_higher_reduces_ultra_more():
    """A less durable athlete (higher alpha) loses MORE fraction on ultras."""
    durable = sustainable_fraction(600, 0.06, "steady")
    reference = sustainable_fraction(600, 0.12, "steady")
    fragile = sustainable_fraction(600, 0.18, "steady")
    assert durable > reference > fragile


def test_sustainable_fraction_durability_alpha_doesnt_affect_short_much():
    """At 20 minutes the base loss is 0, so alpha modulation must be a no-op."""
    for alpha in (0.04, 0.06, 0.12, 0.18, 0.20):
        assert sustainable_fraction(20, alpha, "steady") == pytest.approx(1.0)


def test_sustainable_fraction_durability_alpha_reference_is_identity():
    """At the reference alpha (0.12) the modulation is the identity."""
    for duration, expected in ANCHOR_TABLE:
        assert sustainable_fraction(duration, 0.12, "steady") == pytest.approx(
            expected
        )


# ---------------------------------------------------------------------------
# sustainable_fraction - effort mode modulation
# ---------------------------------------------------------------------------


def test_effort_mode_endurance_returns_lower():
    """Endurance pacing is more conservative -> smaller fraction."""
    steady = sustainable_fraction(180, 0.12, "steady")
    endurance = sustainable_fraction(180, 0.12, "endurance")
    assert endurance < steady
    # The multiplier is 0.93, so endurance ~= steady * 0.93 (no extra clamps
    # at this duration).
    assert endurance == pytest.approx(steady * 0.93, abs=1e-6)


def test_effort_mode_aggressive_capped_at_one():
    """Aggressive mode multiplies by 1.05 but caps the result at 1.0."""
    # At a 50-min duration the base fraction is around 0.93, so 1.05 * 0.93
    # is 0.977 -> not yet capped.
    around_10k = sustainable_fraction(50, 0.12, "aggressive")
    assert around_10k <= 1.0

    # Anywhere above the 5K anchor, where base is 1.0, the cap must hold.
    around_5k = sustainable_fraction(20, 0.12, "aggressive")
    assert around_5k == pytest.approx(1.0, abs=1e-6)
    # And aggressive must never exceed 1.0 even on a fine grid.
    for dur in range(20, 200, 5):
        assert sustainable_fraction(dur, 0.12, "aggressive") <= 1.0 + 1e-9


def test_effort_mode_steady_is_identity_against_reference():
    """Steady mode + reference alpha reproduces the anchor table exactly."""
    for duration, expected in ANCHOR_TABLE:
        assert sustainable_fraction(duration, 0.12, "steady") == pytest.approx(
            expected
        )


def test_effort_mode_multipliers_consistent_with_constants():
    """The exposed multiplier table contains the expected values."""
    assert EFFORT_MODE_MULTIPLIERS == {
        "steady": 1.00,
        "endurance": 0.93,
        "aggressive": 1.05,
    }


# ---------------------------------------------------------------------------
# sustainable_fraction - input validation
# ---------------------------------------------------------------------------


def test_invalid_inputs_raise_value_error():
    """Negative durations, non-positive alphas and unknown effort modes raise."""
    with pytest.raises(ValueError):
        sustainable_fraction(0, 0.12, "steady")
    with pytest.raises(ValueError):
        sustainable_fraction(-10, 0.12, "steady")
    with pytest.raises(ValueError):
        sustainable_fraction(float("inf"), 0.12, "steady")
    with pytest.raises(ValueError):
        sustainable_fraction(float("nan"), 0.12, "steady")

    with pytest.raises(ValueError):
        sustainable_fraction(180, 0.0, "steady")
    with pytest.raises(ValueError):
        sustainable_fraction(180, -0.05, "steady")
    with pytest.raises(ValueError):
        sustainable_fraction(180, float("nan"), "steady")

    with pytest.raises(ValueError):
        sustainable_fraction(180, 0.12, "")
    with pytest.raises(ValueError):
        sustainable_fraction(180, 0.12, "wat")
    with pytest.raises(ValueError):
        sustainable_fraction(180, 0.12, "STEADY")  # case sensitive


# ---------------------------------------------------------------------------
# derive_event_power
# ---------------------------------------------------------------------------


def test_derive_event_power_consistent():
    """p_event must equal p_capacity * fraction; metadata must be echoed."""
    result = derive_event_power(4.0, 180, 0.12, "steady")
    fraction = result["sustainable_fraction"]
    assert result["p_event_wkg"] == pytest.approx(4.0 * fraction)
    assert result["duration_used_min"] == 180.0
    assert result["alpha_used"] == 0.12
    assert result["effort_mode"] == "steady"
    # Sanity: marathon fraction is ~0.82.
    assert fraction == pytest.approx(0.82, abs=0.02)


def test_derive_event_power_invalid_capacity_raises():
    """A non-positive or non-finite capacity must raise a ValueError."""
    with pytest.raises(ValueError):
        derive_event_power(0.0, 180, 0.12, "steady")
    with pytest.raises(ValueError):
        derive_event_power(-1.0, 180, 0.12, "steady")
    with pytest.raises(ValueError):
        derive_event_power(float("nan"), 180, 0.12, "steady")


def test_derive_event_power_propagates_validation_errors():
    """Underlying validation errors must surface from the wrapper."""
    with pytest.raises(ValueError):
        derive_event_power(4.0, -10, 0.12, "steady")
    with pytest.raises(ValueError):
        derive_event_power(4.0, 180, 0.12, "bogus")


# ---------------------------------------------------------------------------
# iterate_event_power - convergence
# ---------------------------------------------------------------------------


def test_iterate_event_power_converges_simple_case():
    """A constant duration callback must converge in 1-2 iterations."""
    result = iterate_event_power(4.0, 200, 0.12, lambda _p: 100.0)

    assert result["converged"] is True
    assert result["final_iteration"] <= 1
    # After convergence the reported state must use duration = 100.
    assert result["final_duration_min"] == pytest.approx(100.0)
    expected_fraction = sustainable_fraction(100.0, 0.12, "steady")
    assert result["sustainable_fraction"] == pytest.approx(expected_fraction)
    assert result["p_event_wkg"] == pytest.approx(4.0 * expected_fraction)


def test_iterate_event_power_converges_with_realistic_callback():
    """A pace-ish callback (duration ~ distance / power) must converge."""

    distance_km = 42.195

    def callback(p_event_wkg: float) -> float:
        # Toy model: speed scales linearly with p_event, so duration scales as
        # distance / p_event. The fixed-point iteration must still converge
        # within a few steps.
        speed_mps = max(0.5, p_event_wkg * 1.0)
        return (distance_km * 1000.0 / speed_mps) / 60.0

    result = iterate_event_power(4.0, 100, 0.12, callback, max_iterations=10)

    assert result["converged"] is True
    assert result["final_iteration"] <= 6
    # The converged state must be self-consistent: callback(p_event) ~ duration.
    final_dur = result["final_duration_min"]
    final_p = result["p_event_wkg"]
    assert callback(final_p) == pytest.approx(final_dur, rel=0.02)


def test_iterate_event_power_respects_max_iterations():
    """A diverging callback must stop after max_iterations without converging."""
    # A callback that keeps moving the duration significantly each step.
    durations_seen: list[float] = []

    def diverging(p_event_wkg: float) -> float:
        durations_seen.append(p_event_wkg)
        # Toggle between two far-apart durations so |new - old|/old stays > 1%.
        if len(durations_seen) % 2 == 1:
            return 50.0
        return 500.0

    result = iterate_event_power(
        4.0, 100, 0.12, diverging, max_iterations=4, tolerance=0.01
    )

    assert result["converged"] is False
    assert result["final_iteration"] == 3
    assert len(result["iterations"]) == 4


def test_iterate_event_power_returns_all_iterations_history():
    """Every iteration is recorded with the required fields."""

    def callback(p_event_wkg: float) -> float:
        # Slow convergence: each call returns a value half-way between the
        # previous one and 240 min.
        callback.last = (callback.last + 240) / 2.0  # type: ignore[attr-defined]
        return callback.last  # type: ignore[attr-defined]

    callback.last = 60.0  # type: ignore[attr-defined]

    result = iterate_event_power(4.0, 60, 0.12, callback, max_iterations=8)

    # iterations field is a list of dicts with the documented keys.
    assert isinstance(result["iterations"], list)
    assert len(result["iterations"]) >= 1
    for entry in result["iterations"]:
        assert set(entry.keys()) == {
            "iter",
            "duration_min",
            "fraction",
            "p_event_wkg",
            "predicted_duration_min",
        }

    # Iterations indices must be strictly increasing from 0.
    indices = [it["iter"] for it in result["iterations"]]
    assert indices == list(range(len(indices)))


# ---------------------------------------------------------------------------
# iterate_event_power - input validation
# ---------------------------------------------------------------------------


def test_iterate_event_power_invalid_inputs_raise():
    """All invalid arguments raise a ValueError."""
    cb = lambda _p: 100.0  # noqa: E731

    with pytest.raises(ValueError):
        iterate_event_power(0.0, 100, 0.12, cb)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 0.0, 0.12, cb)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.0, cb)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, "not_callable")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, cb, max_iterations=0)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, cb, tolerance=0.0)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, cb, effort_mode="oops")


def test_iterate_event_power_rejects_invalid_callback_return():
    """A callback returning a non-positive or non-finite value raises."""
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, lambda _p: -10.0)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, lambda _p: 0.0)
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, lambda _p: float("inf"))
    with pytest.raises(ValueError):
        iterate_event_power(4.0, 100, 0.12, lambda _p: float("nan"))


# ---------------------------------------------------------------------------
# Smoke: realistic end-to-end values
# ---------------------------------------------------------------------------


def test_marathon_capacity_to_event_realistic_values():
    """End-to-end sanity check on a marathon profile."""
    # Athlete with a 4 W/kg short-distance capacity (~ 19 min 5K) running a
    # marathon (~180 min) with reference durability should sit around the
    # 3.2-3.3 W/kg event-power band.
    out = derive_event_power(4.0, 180.0, 0.12, "steady")
    assert 3.1 < out["p_event_wkg"] < 3.4


def test_ultra_event_power_substantially_lower_than_marathon():
    """A 100K event must yield a markedly lower event power than a marathon."""
    marathon = derive_event_power(4.0, 180.0, 0.12, "steady")["p_event_wkg"]
    hundred_k = derive_event_power(4.0, 600.0, 0.12, "steady")["p_event_wkg"]
    assert hundred_k < marathon
    # And the gap should be physically meaningful (>= ~15 % drop).
    assert (marathon - hundred_k) / marathon >= 0.15
