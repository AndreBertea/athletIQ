"""Monte Carlo uncertainty for Race Predictor V2 / V2.2 / V2.3 / V2.3.1.

Two modes are supported by :func:`monte_carlo_uncertainty`:

* **Legacy multiplicative mode** (V2 router, V2.2 orchestrator) - the caller
  passes the deterministic ``moving_time_min`` / ``total_pause_min`` produced
  by a single physics pass and we multiply by a global random factor sampled
  from per-source distributions. This is preserved for backward compatibility
  but is biased: it cannot change the locomotion mix (run vs walk) on
  borderline grades and it cannot move auto ravitos as the predicted
  duration shifts.

* **V2.3.1 R3 physical replay mode** - the caller passes ``gpx_analysis``
  plus the posterior distributions for ``p_ref_steady_wkg``,
  ``durability_alpha`` and ``trail_cost_factor`` plus the (timeline-aware)
  environment and the ravito configuration. For each of ``n_simulations``
  draws we resample these parameters, perturb the weather timeline, replay
  the full :func:`physics_engine.predict_segments`, recompute the ravito
  schedule (auto positions follow the redrawn duration) and report
  percentiles on both the moving time and the total time (with pauses).
  See ``docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md`` section R3.
"""
from __future__ import annotations

import logging
import random
import time
import warnings
from statistics import median
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Percentile helper (shared between legacy and physical replay paths)
# ---------------------------------------------------------------------------


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _percentiles(samples: list[float], *, ndigits: int = 2) -> dict[str, float]:
    """Return ``{p10, p50, p90}`` from a sample list."""
    if not samples:
        return {"p10": 0.0, "p50": 0.0, "p90": 0.0}
    return {
        "p10": round(_percentile(samples, 0.10), ndigits),
        "p50": round(_percentile(samples, 0.50), ndigits),
        "p90": round(_percentile(samples, 0.90), ndigits),
    }


# ---------------------------------------------------------------------------
# Environment perturbation
# ---------------------------------------------------------------------------


def perturb_environment(
    env: dict[str, Any], rng: random.Random, *, temp_std: float = 1.0
) -> dict[str, Any]:
    """Return a shallow copy of ``env`` with the temperature timeline shifted.

    A single global offset is sampled from ``N(0, temp_std)`` (in degrees C)
    and added to every hourly temperature in ``weather_timeline`` and to the
    scalar ``temperature_c`` / ``temperature_min_c`` / ``temperature_max_c``
    fields. This preserves the hourly structure (relative variations stay
    intact) while letting the simulation explore alternative climates.

    Notes
    -----
    - We deliberately apply a single offset rather than independent Gaussian
      noise per hour. Per-hour independent noise would amount to applying
      ``sqrt(n)`` of cancellation when ``physics_engine`` interpolates over
      a long race and would silently shrink the simulated weather variance
      seen by the model. A single offset is a conservative upper bound.
    - We do **not** touch humidity / wind / precipitation: the physics
      engine only consumes temperature today (see
      :func:`environment_service.temperature_factor`).
    """
    offset = rng.gauss(0.0, max(0.0, temp_std))
    perturbed = dict(env)
    timeline = env.get("weather_timeline") or []
    new_timeline: list[dict[str, Any]] = []
    for point in timeline:
        new_point = dict(point)
        try:
            new_point["temperature_c"] = float(point.get("temperature_c") or 0) + offset
        except (TypeError, ValueError):
            new_point["temperature_c"] = point.get("temperature_c")
        new_timeline.append(new_point)
    if new_timeline:
        perturbed["weather_timeline"] = new_timeline
    for key in ("temperature_c", "temperature_min_c", "temperature_max_c"):
        if key in perturbed and perturbed[key] is not None:
            try:
                perturbed[key] = float(perturbed[key]) + offset
            except (TypeError, ValueError):
                pass
    return perturbed


# ---------------------------------------------------------------------------
# Posterior sampling helpers
# ---------------------------------------------------------------------------


def _sample_truncated_normal(
    rng: random.Random,
    *,
    mean: float,
    std: float,
    low: float | None = None,
    high: float | None = None,
) -> float:
    """Sample from N(mean, std) and clamp to ``[low, high]`` when provided."""
    value = rng.gauss(mean, max(0.0, std))
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


# ---------------------------------------------------------------------------
# V2.3.1 R3: full physical replay Monte Carlo
# ---------------------------------------------------------------------------


def _physical_replay_monte_carlo(
    *,
    gpx_analysis: dict[str, Any],
    calibration_posterior: dict[str, Any],
    fatigue_posterior: dict[str, Any],
    trail_factor_posterior: dict[str, Any],
    environment: dict[str, Any],
    analysis_mode: str,
    effort_mode: str,
    ravito_mode: str,
    custom_ravitos: list[dict[str, Any]] | None,
    n_simulations: int,
    seed: int,
    weather_temp_std: float,
) -> dict[str, Any]:
    """Replay the full physics+ravito pipeline ``n_simulations`` times.

    Imports are deferred so the module remains importable in contexts where
    the physics engine is not yet on ``sys.path`` (e.g. lightweight unit
    tests that only exercise the legacy multiplicative mode).
    """
    # Local imports to avoid a circular dependency at module import time.
    from app.domain.services.race_predictor.physics_engine import predict_segments
    from app.domain.services.race_predictor.ravito_service import (
        auto_ravitos,
        manual_ravitos,
    )

    rng = random.Random(seed)
    base_segments = gpx_analysis.get("segments") or []
    global_stats = gpx_analysis.get("global_stats") or {}
    total_distance_km = float(global_stats.get("total_distance_km") or 0)

    moving_samples: list[float] = []
    total_samples: list[float] = []
    pause_samples: list[float] = []
    ravito_count_samples: list[int] = []
    segment_samples: list[list[float]] = [[] for _ in base_segments]
    locomotion_samples: list[list[str]] = [[] for _ in base_segments]

    p_ref_mean = float(calibration_posterior.get("mean") or 9.5)
    p_ref_std = max(0.0, float(calibration_posterior.get("std") or 0.5))
    alpha_mean = max(0.0, float(fatigue_posterior.get("mean") or 0.10))
    alpha_std = max(0.0, float(fatigue_posterior.get("std") or 0.03))
    trail_mean = max(1.0, float(trail_factor_posterior.get("mean") or 1.20))
    trail_std = max(0.0, float(trail_factor_posterior.get("std") or 0.10))
    base_p_walk_ratio = 0.75

    normalized_ravito_mode = (ravito_mode or "auto").strip().lower()
    normalized_analysis_mode = (analysis_mode or "trail").strip().lower()

    start = time.perf_counter()

    for _ in range(max(0, n_simulations)):
        p_ref_sample = _sample_truncated_normal(
            rng, mean=p_ref_mean, std=p_ref_std, low=5.0, high=25.0
        )
        alpha_sample = _sample_truncated_normal(
            rng, mean=alpha_mean, std=alpha_std, low=0.0, high=0.35
        )
        trail_sample = _sample_truncated_normal(
            rng, mean=trail_mean, std=trail_std, low=1.0, high=1.7
        )
        env_perturbed = perturb_environment(environment, rng, temp_std=weather_temp_std)

        # Compute a per-sample p_run_wkg confidence (used by physics engine
        # downstream traces only).
        relative_p_std = p_ref_std / max(p_ref_sample, 1e-3)
        confidence = max(0.10, min(0.95, 1.0 - relative_p_std))

        calibration = {
            "engine_version": "v2_3_bayesian_mc_sample",
            "p_run_wkg": p_ref_sample,
            "p_walk_ratio": base_p_walk_ratio,
            "confidence": confidence,
        }
        fatigue_profile = {
            "model": "v2_3_posterior_alpha_mc_sample",
            "alpha": alpha_sample,
            "personalized": True,
        }
        trail_surface_factor = (
            trail_sample if normalized_analysis_mode == "trail" else None
        )

        physics_result = predict_segments(
            base_segments,
            calibration=calibration,
            environment=env_perturbed,
            fatigue_profile=fatigue_profile,
            trail_surface_factor=trail_surface_factor,
            analysis_mode=normalized_analysis_mode,
            effort_mode=effort_mode,
        )
        sim_segments = physics_result["segments"]
        moving_min = float(physics_result["moving_time_min"])

        if normalized_ravito_mode == "manual":
            ravitos = manual_ravitos(
                sim_segments, custom_ravitos, total_distance_km
            )
        else:
            ravitos = (
                manual_ravitos(
                    sim_segments,
                    custom_ravitos,
                    total_distance_km,
                    source="auto_known",
                )
                if custom_ravitos
                else []
            )
            if not ravitos:
                ravitos = auto_ravitos(
                    sim_segments,
                    global_stats,
                    moving_min,
                    analysis_mode=normalized_analysis_mode,
                    temperature_c=float(
                        env_perturbed.get("temperature_max_c")
                        or env_perturbed.get("temperature_c")
                        or 11.0
                    ),
                )

        pause_min = sum(float(r.get("pause_min") or 0) for r in ravitos)
        total_min = moving_min + pause_min

        moving_samples.append(moving_min)
        total_samples.append(total_min)
        pause_samples.append(pause_min)
        ravito_count_samples.append(len(ravitos))
        for idx, seg in enumerate(sim_segments):
            if idx < len(segment_samples):
                segment_samples[idx].append(float(seg.get("predicted_time_min") or 0))
                locomotion_samples[idx].append(str(seg.get("locomotion") or "run"))

    latency_ms = (time.perf_counter() - start) * 1000.0

    segments_output: list[dict[str, Any]] = []
    for idx, seg in enumerate(base_segments):
        sample_locs = locomotion_samples[idx] if idx < len(locomotion_samples) else []
        walk_share = (
            sum(1 for loc in sample_locs if loc == "walk") / max(1, len(sample_locs))
            if sample_locs
            else 0.0
        )
        seg_pct = _percentiles(
            segment_samples[idx] if idx < len(segment_samples) else [], ndigits=2
        )
        segments_output.append(
            {
                "segment_id": seg.get("segment_id"),
                **seg_pct,
                "walk_share": round(walk_share, 3),
            }
        )

    return {
        "mode": "physical_replay",
        "simulations": int(max(0, n_simulations)),
        "seed": seed,
        "total_time": _percentiles(total_samples, ndigits=2),
        "moving_time": _percentiles(moving_samples, ndigits=2),
        "pause_time": _percentiles(pause_samples, ndigits=2),
        "ravito_count": _percentiles(
            [float(c) for c in ravito_count_samples], ndigits=2
        ),
        "segments": segments_output,
        "contributors": {
            "p_ref_steady_std": round(p_ref_std, 4),
            "durability_alpha_std": round(alpha_std, 4),
            "trail_factor_std": round(trail_std, 4),
            "weather_temp_std_c": round(weather_temp_std, 3),
        },
        "benchmark_latency_ms": round(latency_ms, 1),
    }


# ---------------------------------------------------------------------------
# Legacy multiplicative path (kept for V2 router + V2.2 orchestrator)
# ---------------------------------------------------------------------------


def _legacy_multiplicative_monte_carlo(
    *,
    segments: list[dict[str, Any]],
    moving_time_min: float,
    total_pause_min: float,
    calibration: dict[str, Any],
    environment: dict[str, Any],
    simulations: int,
    variation_stds: dict[str, float] | None,
) -> dict[str, Any]:
    """Original V2 / V2.2 multiplicative implementation, preserved verbatim.

    This path does not change between V2 and V2.3.1; it is the **only**
    behaviour previously available and is invoked when the caller passes
    ``segments`` / ``moving_time_min`` / ``total_pause_min`` (the legacy
    contract). The V2.3.1 R3 plan explicitly preserves V2.2 against this
    path so the V2.2 benchmark remains comparable.
    """
    rng = random.Random(42)
    confidence = float(calibration.get("confidence") or 0.4)
    p_std = 0.04 + (1.0 - confidence) * 0.10
    weather_std = 0.015 if environment.get("weather_source") == "manual" else 0.025
    fatigue_std = 0.035
    surface_std = 0.03
    if variation_stds:
        p_std = float(variation_stds.get("p_run", p_std))
        fatigue_std = float(variation_stds.get("fatigue", fatigue_std))
        weather_std = float(variation_stds.get("weather", weather_std))
        surface_std = float(variation_stds.get("surface", surface_std))

    total_samples: list[float] = []
    moving_samples: list[float] = []
    segment_samples: list[list[float]] = [[] for _ in segments]

    for _ in range(simulations):
        p_variation = max(0.75, min(1.30, rng.gauss(1.0, p_std)))
        fatigue_variation = max(0.92, min(1.10, rng.gauss(1.0, fatigue_std)))
        weather_variation = max(0.95, min(1.05, rng.gauss(1.0, weather_std)))
        surface_variation = max(0.95, min(1.06, rng.gauss(1.0, surface_std)))
        global_variation = (
            (1.0 / p_variation) * fatigue_variation * weather_variation * surface_variation
        )
        moving_sample = moving_time_min * global_variation
        moving_samples.append(moving_sample)
        total_samples.append(moving_sample + total_pause_min)

        for index, segment in enumerate(segments):
            segment_time = float(segment.get("predicted_time_min") or 0)
            local_factor = max(0.80, min(1.25, rng.gauss(global_variation, 0.025)))
            segment_samples[index].append(segment_time * local_factor)

    return {
        "mode": "legacy_multiplicative",
        "simulations": simulations,
        "total_time": {
            "p10": round(_percentile(total_samples, 0.10), 1),
            "p50": round(median(total_samples), 1),
            "p90": round(_percentile(total_samples, 0.90), 1),
        },
        "moving_time": {
            "p10": round(_percentile(moving_samples, 0.10), 1),
            "p50": round(median(moving_samples), 1),
            "p90": round(_percentile(moving_samples, 0.90), 1),
        },
        "segments": [
            {
                "segment_id": segments[index].get("segment_id"),
                "p10": round(_percentile(samples, 0.10), 2),
                "p50": round(median(samples), 2),
                "p90": round(_percentile(samples, 0.90), 2),
            }
            for index, samples in enumerate(segment_samples)
        ],
        "contributors": {
            "p_run_std": round(p_std, 3),
            "fatigue_std": fatigue_std,
            "weather_std": weather_std,
            "surface_std": surface_std,
        },
    }


# ---------------------------------------------------------------------------
# Public dispatch entry point
# ---------------------------------------------------------------------------


def monte_carlo_uncertainty(
    *,
    # ---- Legacy multiplicative inputs (V2 / V2.2) ------------------------
    segments: list[dict[str, Any]] | None = None,
    moving_time_min: float | None = None,
    total_pause_min: float | None = None,
    calibration: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    simulations: int = 300,
    variation_stds: dict[str, float] | None = None,
    # ---- V2.3.1 R3 physical replay inputs --------------------------------
    gpx_analysis: dict[str, Any] | None = None,
    calibration_posterior: dict[str, Any] | None = None,
    fatigue_posterior: dict[str, Any] | None = None,
    trail_factor_posterior: dict[str, Any] | None = None,
    analysis_mode: str | None = None,
    effort_mode: str | None = None,
    ravito_mode: str | None = None,
    custom_ravitos: list[dict[str, Any]] | None = None,
    n_simulations: int | None = None,
    seed: int = 42,
    weather_temp_std: float = 1.0,
) -> dict[str, Any]:
    """Run a Monte Carlo uncertainty pass.

    Two calling conventions are supported (the dispatcher detects which one
    is in use from the parameters provided):

    1. **Legacy multiplicative** (V2 router and V2.2 orchestrator) - pass
       ``segments``, ``moving_time_min``, ``total_pause_min`` plus
       ``calibration`` and ``environment``. The result is a percentile
       envelope around the deterministic prediction obtained by multiplying
       a global random factor sampled from ``variation_stds``.

       *Returned dict shape*::

           {
               "mode": "legacy_multiplicative",
               "simulations": int,
               "total_time": {"p10", "p50", "p90"},
               "moving_time": {"p10", "p50", "p90"},
               "segments": [{"segment_id", "p10", "p50", "p90"}, ...],
               "contributors": {p_run_std, fatigue_std, weather_std, surface_std},
           }

    2. **V2.3.1 R3 physical replay** (V2.3.1 orchestrator) - pass
       ``gpx_analysis`` plus the posterior triplet
       (``calibration_posterior``, ``fatigue_posterior``,
       ``trail_factor_posterior``) plus ``environment``, ``analysis_mode``,
       ``effort_mode``, ``ravito_mode`` and ``n_simulations``. Each draw
       resamples the parameters, perturbs the weather timeline and replays
       the **full** physics + ravito pipeline. This means the locomotion
       mix (run vs walk on borderline grades) and the auto ravito positions
       are recomputed per draw, which the legacy path cannot do.

       *Returned dict shape*::

           {
               "mode": "physical_replay",
               "simulations": int,
               "seed": int,
               "total_time": {"p10", "p50", "p90"},
               "moving_time": {"p10", "p50", "p90"},
               "pause_time": {"p10", "p50", "p90"},
               "ravito_count": {"p10", "p50", "p90"},
               "segments": [{"segment_id", "p10", "p50", "p90", "walk_share"}, ...],
               "contributors": {
                   "p_ref_steady_std", "durability_alpha_std",
                   "trail_factor_std", "weather_temp_std_c",
               },
               "benchmark_latency_ms": float,
           }

    A ``DeprecationWarning`` is **not** emitted for the legacy path because
    V2.2 must keep using it for benchmark stability (see V2.3.1 plan R3).

    Parameters
    ----------
    gpx_analysis
        Output of :func:`gpx_analyzer.analyze_gpx`. Must contain ``segments``
        and ``global_stats``. Selecting this argument enables physical
        replay mode.
    calibration_posterior / fatigue_posterior / trail_factor_posterior
        Each is the dict returned by :func:`robust_updater.compute_posterior`
        and must expose ``mean`` and ``std``.
    n_simulations
        Number of draws. Default is 200 (chosen after the R3 benchmark on
        UTMJ; see :mod:`scripts.benchmark_monte_carlo_N`).
    seed
        RNG seed for reproducibility.
    weather_temp_std
        Std of the gaussian offset applied to the weather timeline (degrees
        C). Default 1.0 (~ 68% of draws within plus or minus 1 C).

    Returns
    -------
    dict
        See shapes above.
    """
    physical_replay_signal = any(
        arg is not None
        for arg in (
            gpx_analysis,
            calibration_posterior,
            fatigue_posterior,
            trail_factor_posterior,
        )
    )
    legacy_signal = any(
        arg is not None for arg in (segments, moving_time_min, total_pause_min)
    )

    if physical_replay_signal:
        missing = [
            name
            for name, value in (
                ("gpx_analysis", gpx_analysis),
                ("calibration_posterior", calibration_posterior),
                ("fatigue_posterior", fatigue_posterior),
                ("trail_factor_posterior", trail_factor_posterior),
                ("environment", environment),
            )
            if value is None
        ]
        if missing:
            raise TypeError(
                "monte_carlo_uncertainty(physical_replay) requires: "
                + ", ".join(missing)
            )
        if legacy_signal:
            warnings.warn(
                "monte_carlo_uncertainty received both physical-replay and "
                "legacy arguments; legacy arguments are ignored.",
                stacklevel=2,
            )
        n = int(n_simulations) if n_simulations is not None else 200
        return _physical_replay_monte_carlo(
            gpx_analysis=gpx_analysis,
            calibration_posterior=calibration_posterior,
            fatigue_posterior=fatigue_posterior,
            trail_factor_posterior=trail_factor_posterior,
            environment=environment,
            analysis_mode=analysis_mode or "trail",
            effort_mode=effort_mode or "steady",
            ravito_mode=ravito_mode or "auto",
            custom_ravitos=custom_ravitos,
            n_simulations=n,
            seed=seed,
            weather_temp_std=weather_temp_std,
        )

    # Legacy multiplicative path. All required arguments are positional in
    # the old contract; preserve the original defaults.
    if segments is None or moving_time_min is None or total_pause_min is None:
        raise TypeError(
            "monte_carlo_uncertainty(legacy) requires segments, "
            "moving_time_min and total_pause_min"
        )
    if calibration is None:
        calibration = {}
    if environment is None:
        environment = {}
    return _legacy_multiplicative_monte_carlo(
        segments=segments,
        moving_time_min=float(moving_time_min),
        total_pause_min=float(total_pause_min),
        calibration=calibration,
        environment=environment,
        simulations=int(simulations),
        variation_stds=variation_stds,
    )


__all__ = [
    "monte_carlo_uncertainty",
    "perturb_environment",
]
