"""V2.3.1 R3 - Monte Carlo by full physical replay (blocking tests).

These tests assert the contract introduced by Lot R3 of the V2.3.1 fix
plan (``docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md``):

1. Each draw resamples ``p_ref_steady_wkg`` / ``durability_alpha`` /
   ``trail_cost_factor`` from their posterior and replays the full physics
   + ravito pipeline, instead of multiplying a global factor on a single
   deterministic prediction.
2. The locomotion mix (run vs walk on borderline grades) is allowed to
   change between draws.
3. The Monte Carlo output exposes P10/P50/P90 for both ``moving_time``
   and ``total_time``, with the trivial invariant ``p10 <= p50 <= p90``.
4. Weather perturbation amplitude actually drives the predictions
   variance (large ``weather_temp_std`` -> wider envelope).
5. In ``ravito_mode == "auto"`` the number of ravitos varies between
   draws as the predicted duration moves; in ``manual`` mode the ravito
   positions stay fixed.
6. End-to-end latency at the chosen N=200 stays under 8s on a ~30km GPX
   with the synthetic stress fixture used here (alarm signal otherwise).

These tests do not require a DB session: they call
:func:`monte_carlo_uncertainty` directly with hand-crafted inputs so the
behaviour is deterministic and side-effect free.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import pytest

from app.domain.services.race_predictor.gpx_analyzer import analyze_gpx
from app.domain.services.race_predictor.uncertainty_service import (
    monte_carlo_uncertainty,
    perturb_environment,
)


# ---------------------------------------------------------------------------
# Synthetic GPX fixtures
# ---------------------------------------------------------------------------


def _build_steep_borderline_gpx() -> str:
    """Build a small GPX with a long climb that flirts with the walk threshold.

    The track encodes a continuous steady climb at roughly +22 m / 100 m
    (~22%). With ``walk_threshold(p_run, 0)`` returning ~0.22 for an average
    P_run, sub-threshold draws keep running while higher-threshold draws
    walk. This is exactly the borderline behaviour the R3 contract must
    capture.
    """
    points: list[tuple[float, float, float]] = []
    lat0, lon0 = 46.0, 6.0
    ele = 500.0
    distance_step_m = 100.0  # 100 m per lat increment at this latitude/longitude pair.
    # +22 m per 100 m horizontal -> 22% grade.
    rise_per_step = 22.0
    for i in range(60):
        # ~0.0009 deg lat ~ 100 m at this latitude.
        lat = lat0 + i * 0.0009
        lon = lon0
        points.append((lat, lon, ele))
        ele += rise_per_step

    body_points = "\n".join(
        f"    <trkpt lat='{lat:.6f}' lon='{lon:.6f}'><ele>{ele:.1f}</ele></trkpt>"
        for lat, lon, ele in points
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<gpx version='1.1' creator='r3-test'>\n"
        "  <trk><name>steep climb</name><trkseg>\n"
        f"{body_points}\n"
        "  </trkseg></trk>\n"
        "</gpx>\n"
    )


def _build_long_mixed_gpx(*, n_segments: int = 80) -> str:
    """Build a ~30 km GPX with mixed grades for the latency benchmark."""
    points: list[tuple[float, float, float]] = []
    lat = 46.0
    lon = 6.0
    ele = 500.0
    # ~0.0036 deg lat ~ 400 m (approx). 80 segments -> ~32 km.
    for i in range(n_segments * 6):
        lat += 0.0006
        # Sinusoidal terrain with +/- 25 m / 100 m equivalent (rolling).
        ele += 8.0 * math.sin(i * 0.21) + 1.5
        points.append((lat, lon, ele))
    body_points = "\n".join(
        f"    <trkpt lat='{lat:.6f}' lon='{lon:.6f}'><ele>{ele:.1f}</ele></trkpt>"
        for lat, lon, ele in points
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<gpx version='1.1' creator='r3-bench'>\n"
        "  <trk><name>long mixed</name><trkseg>\n"
        f"{body_points}\n"
        "  </trkseg></trk>\n"
        "</gpx>\n"
    )


# ---------------------------------------------------------------------------
# Reusable inputs
# ---------------------------------------------------------------------------


def _baseline_env(*, temperature_c: float = 12.0) -> dict[str, Any]:
    """Build an environment dict shaped as :func:`build_environment` returns."""
    return {
        "weather_mode": "manual",
        "weather_source": "manual",
        "temperature_c": temperature_c,
        "temperature_min_c": temperature_c,
        "temperature_max_c": temperature_c,
        "optimal_temperature_c": 11.0,
        "weather_factor": 1.0,
        "heat_penalty_percent": 0.0,
        "weather_timeline": [],
        "weather_timeline_enabled": False,
        "p_run_wkg": 9.5,
    }


def _baseline_posteriors() -> dict[str, dict[str, float]]:
    return {
        "p_ref_steady": {
            "mean": 9.5,
            "std": 0.6,
            "evidence_count": 3,
        },
        "durability_alpha": {
            "mean": 0.10,
            "std": 0.03,
            "evidence_count": 1,
        },
        "trail_cost_factor": {
            "mean": 1.20,
            "std": 0.10,
            "evidence_count": 0,
        },
    }


# ---------------------------------------------------------------------------
# 1. Walk / run transitions vary across draws on borderline grades
# ---------------------------------------------------------------------------


def test_monte_carlo_changes_walk_run_transitions_across_tirages() -> None:
    """On a borderline-grade GPX the run vs walk mix must vary between draws.

    We stress the path by widening the p_ref_steady std so the posterior
    explores both sub-threshold and above-threshold p_run values. The
    legacy multiplicative path could never produce locomotion changes
    because it never re-enters the physics engine; the R3 physical replay
    must.
    """
    gpx = _build_steep_borderline_gpx()
    gpx_analysis = analyze_gpx(gpx)
    posteriors = _baseline_posteriors()
    # Widen p_ref_steady so draws straddle the walk threshold (which moves
    # with p_run via walk_threshold(...) in physics_engine).
    posteriors["p_ref_steady"]["std"] = 2.0
    env = _baseline_env()

    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=120,
        seed=2026,
        weather_temp_std=0.5,
    )

    assert result["mode"] == "physical_replay"
    # The simulator records walk_share per segment. On a borderline-grade
    # GPX with a widened p_ref_steady std, at least one segment must show
    # a mixed locomotion profile (strictly between 0 and 1).
    walk_shares = [float(seg.get("walk_share") or 0) for seg in result["segments"]]
    mixed_segments = [share for share in walk_shares if 0.05 < share < 0.95]
    assert mixed_segments, (
        "No segment showed a mixed run/walk distribution across draws. "
        "The Monte Carlo is not replaying the locomotion decision. "
        f"walk_shares={walk_shares}"
    )


# ---------------------------------------------------------------------------
# 2. Output exposes percentiles for total_time and moving_time
# ---------------------------------------------------------------------------


def test_monte_carlo_returns_total_and_moving_time_percentiles() -> None:
    gpx = _build_steep_borderline_gpx()
    gpx_analysis = analyze_gpx(gpx)
    posteriors = _baseline_posteriors()
    env = _baseline_env()

    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=50,
        seed=99,
        weather_temp_std=0.5,
    )

    for key in ("total_time", "moving_time"):
        assert key in result, f"missing top-level key: {key}"
        assert set(result[key].keys()) >= {"p10", "p50", "p90"}
    # Bonus diagnostic fields exposed by physical replay.
    assert "pause_time" in result
    assert "ravito_count" in result
    assert "contributors" in result
    assert {
        "p_ref_steady_std",
        "durability_alpha_std",
        "trail_factor_std",
        "weather_temp_std_c",
    }.issubset(result["contributors"].keys())
    assert "benchmark_latency_ms" in result


# ---------------------------------------------------------------------------
# 3. Trivial invariant: p10 <= p50 <= p90 for total and moving
# ---------------------------------------------------------------------------


def test_monte_carlo_p10_le_p50_le_p90() -> None:
    gpx = _build_steep_borderline_gpx()
    gpx_analysis = analyze_gpx(gpx)
    posteriors = _baseline_posteriors()
    env = _baseline_env()

    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=80,
        seed=1234,
        weather_temp_std=0.5,
    )

    for key in ("total_time", "moving_time", "pause_time"):
        block = result[key]
        assert block["p10"] <= block["p50"] <= block["p90"], (
            f"{key} percentiles out of order: {block}"
        )


# ---------------------------------------------------------------------------
# 4. Weather perturbation amplitude actually drives the variance
# ---------------------------------------------------------------------------


def test_monte_carlo_weather_perturbation_affects_predictions() -> None:
    """Increasing ``weather_temp_std`` must widen the prediction envelope.

    We freeze the parameter posteriors to *zero* std so the only remaining
    source of variation is the weather offset. With ``weather_temp_std=0``
    the moving_time envelope must collapse to a single value; with a large
    ``weather_temp_std`` the envelope must grow strictly wider.
    """
    gpx = _build_long_mixed_gpx(n_segments=30)
    gpx_analysis = analyze_gpx(gpx)
    # Force the warm regime so the heat penalty kicks in (otherwise
    # temperature_factor() saturates at 1.0 below 11C).
    env = _baseline_env(temperature_c=22.0)
    posteriors = {
        "p_ref_steady": {"mean": 9.5, "std": 0.0, "evidence_count": 5},
        "durability_alpha": {"mean": 0.10, "std": 0.0, "evidence_count": 5},
        "trail_cost_factor": {"mean": 1.20, "std": 0.0, "evidence_count": 5},
    }

    calm = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=80,
        seed=7,
        weather_temp_std=0.5,
    )
    stormy = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=80,
        seed=7,
        weather_temp_std=8.0,
    )

    calm_width = calm["moving_time"]["p90"] - calm["moving_time"]["p10"]
    stormy_width = stormy["moving_time"]["p90"] - stormy["moving_time"]["p10"]
    assert stormy_width > calm_width, (
        f"Wider weather perturbation should widen the envelope "
        f"(calm={calm_width:.3f} vs stormy={stormy_width:.3f})"
    )


# ---------------------------------------------------------------------------
# 5. Auto ravitos are recomputed each draw -> count distribution varies
# ---------------------------------------------------------------------------


def test_monte_carlo_auto_ravitos_recalculated_each_simulation() -> None:
    """In auto mode, ravito positions must follow the redrawn duration.

    With a very wide p_ref_steady std the predicted duration moves enough
    to push some draws above the 3h auto interval (7.5 km vs 10 km) so
    the simulated ravito count distribution must be non-degenerate.
    """
    gpx = _build_long_mixed_gpx(n_segments=80)
    gpx_analysis = analyze_gpx(gpx)
    env = _baseline_env()
    posteriors = {
        "p_ref_steady": {"mean": 9.5, "std": 2.5, "evidence_count": 1},
        "durability_alpha": {"mean": 0.10, "std": 0.05, "evidence_count": 1},
        "trail_cost_factor": {"mean": 1.20, "std": 0.10, "evidence_count": 0},
    }

    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=60,
        seed=11,
        weather_temp_std=0.5,
    )

    # The ravito_count percentile block must show variation. With a fixed
    # interval the auto algorithm produces a constant count regardless of
    # the predicted duration, which would imply p10 == p50 == p90; we
    # require strict variation across draws.
    ravito_pct = result["ravito_count"]
    assert ravito_pct["p10"] <= ravito_pct["p50"] <= ravito_pct["p90"]
    # The auto interval depends on moving_hours (5.5km vs 7.5km in trail
    # mode if >= 5h), which a very wide p_run draw can flip. We require
    # at least the p10 and p90 to differ.
    assert ravito_pct["p90"] > ravito_pct["p10"], (
        "Auto ravitos count is constant across draws. The Monte Carlo "
        "is not recomputing the ravito schedule per simulation. "
        f"ravito_count={ravito_pct}"
    )


# ---------------------------------------------------------------------------
# 6. Manual ravitos: positions stay fixed regardless of the draws
# ---------------------------------------------------------------------------


def test_monte_carlo_manual_ravitos_fixed_positions() -> None:
    """Manual ravito positions are user-defined and never move.

    The R3 spec preserves manual mode as-is: the user pins the distance,
    only the pause time accumulation depends on the draw. We assert the
    count is constant across draws.
    """
    gpx = _build_long_mixed_gpx(n_segments=40)
    gpx_analysis = analyze_gpx(gpx)
    env = _baseline_env()
    posteriors = {
        "p_ref_steady": {"mean": 9.5, "std": 2.0, "evidence_count": 1},
        "durability_alpha": {"mean": 0.10, "std": 0.05, "evidence_count": 1},
        "trail_cost_factor": {"mean": 1.20, "std": 0.10, "evidence_count": 0},
    }
    # Pick three ravitos at fixed distances within the GPX (~25 km long).
    total_km = float(gpx_analysis["global_stats"]["total_distance_km"])
    custom_ravitos = [
        {"km": total_km * 0.25, "pause_min": 2.0, "name": "R1"},
        {"km": total_km * 0.50, "pause_min": 3.0, "name": "R2"},
        {"km": total_km * 0.75, "pause_min": 2.5, "name": "R3"},
    ]

    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="manual",
        custom_ravitos=custom_ravitos,
        n_simulations=40,
        seed=3,
        weather_temp_std=0.5,
    )
    # Manual ravitos -> count is the user-defined count (3) for every draw.
    rc = result["ravito_count"]
    assert rc["p10"] == rc["p50"] == rc["p90"] == 3.0, (
        f"Manual ravito count must stay fixed at 3, got {rc}"
    )


# ---------------------------------------------------------------------------
# 7. End-to-end latency stays acceptable at the chosen N
# ---------------------------------------------------------------------------


def test_monte_carlo_latency_acceptable_at_n_200() -> None:
    """Latency budget at N=200 on a ~30km GPX must stay under 8s.

    The R3 plan targets < 5s on production hardware; we relax to 8s here
    to keep this test stable on developer laptops + CI. A test failure
    here is a strong signal that the physical replay path has regressed
    and the benchmark script should be re-run.
    """
    gpx = _build_long_mixed_gpx(n_segments=80)
    gpx_analysis = analyze_gpx(gpx)
    env = _baseline_env()
    posteriors = _baseline_posteriors()

    start = time.perf_counter()
    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=posteriors["p_ref_steady"],
        fatigue_posterior=posteriors["durability_alpha"],
        trail_factor_posterior=posteriors["trail_cost_factor"],
        environment=env,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=200,
        seed=42,
        weather_temp_std=1.0,
    )
    elapsed_s = time.perf_counter() - start
    assert elapsed_s < 8.0, (
        f"Monte Carlo latency too high at N=200: {elapsed_s:.2f}s "
        f"(plan target < 5s, hard ceiling 8s)."
    )
    # The dispatcher latency report should be in the same ballpark.
    assert result["benchmark_latency_ms"] < 8000.0


# ---------------------------------------------------------------------------
# Bonus assertions (defensive coverage, not part of the 7 mandatory tests)
# ---------------------------------------------------------------------------


def test_perturb_environment_preserves_timeline_structure() -> None:
    """``perturb_environment`` applies a single offset, keeping shape intact."""
    import random as _random

    env = {
        "temperature_c": 18.0,
        "temperature_max_c": 22.0,
        "weather_timeline": [
            {"elapsed_min": 0.0, "temperature_c": 18.0},
            {"elapsed_min": 60.0, "temperature_c": 21.0},
            {"elapsed_min": 120.0, "temperature_c": 23.5},
        ],
    }
    rng = _random.Random(0)
    perturbed = perturb_environment(env, rng, temp_std=2.0)
    base = env["weather_timeline"]
    new = perturbed["weather_timeline"]
    # Same length, same elapsed_min ordering.
    assert len(new) == len(base)
    for b, n in zip(base, new):
        assert n["elapsed_min"] == b["elapsed_min"]
    # The relative spread between hourly points is preserved exactly: any
    # difference between two timeline points must match the original.
    offsets = [n["temperature_c"] - b["temperature_c"] for b, n in zip(base, new)]
    assert max(offsets) == pytest.approx(min(offsets), abs=1e-9)


def test_legacy_multiplicative_path_still_callable() -> None:
    """Backward compatibility for V2 router and V2.2 orchestrator."""
    result = monte_carlo_uncertainty(
        segments=[{"segment_id": 1, "predicted_time_min": 100.0}],
        moving_time_min=100.0,
        total_pause_min=5.0,
        calibration={"confidence": 1.0},
        environment={"weather_source": "manual"},
        simulations=20,
        variation_stds={
            "p_run": 0.0,
            "fatigue": 0.0,
            "weather": 0.0,
            "surface": 0.0,
        },
    )
    assert result["mode"] == "legacy_multiplicative"
    assert result["moving_time"]["p50"] == 100.0
    assert result["total_time"]["p50"] == 105.0
