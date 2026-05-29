"""Event intensity service - capacity-to-event-power conversion (V2.2).

This module converts a short-duration *capacity* (P_capacity, e.g. derived from
a 5K/10K test) into the *event power* (P_event) sustainable over a target
duration. It implements the durability submodule that prevents a VDOT-style
10K capacity from being naively projected onto an ultra-distance event.

The module is intentionally autonomous: it has no dependency on other
race_predictor modules and exposes only pure functions.

Scientific background
---------------------
The anchor table is derived from Daniels & Gilbert VDOT-style tables, blending
empirical decay observed on race performances (Riegel 1981, T2 = T1*(D2/D1)^1.06)
with the critical-power durability literature (Vanhatalo et al. 2011).

References
~~~~~~~~~~
- Daniels, J. & Gilbert, J. (1979). "Oxygen Power: Performance Tables for
  Distance Runners". The Daniels VDOT tables encode equivalent race
  performances across distances and indirectly define a "sustainable fraction"
  of a 5K capacity for longer events.
- Riegel, P. (1981). "Athletic Records and Human Endurance". American
  Scientist, 69(3), 285-290. Provides the canonical T2 = T1*(D2/D1)^1.06
  relationship that motivates a log-linear decay in sustainable fraction.
- Vanhatalo, A., Jones, A.M., Burnley, M. (2011). "Application of Critical
  Power in Sport". Int. J. Sports Physiol. Perform. 6(1), 128-136. Documents
  the divergence between maximal short-effort capacity and longer-duration
  sustainable power and the inter-individual variability in durability.

Anchor table (alpha = 0.12, reference athlete, "steady" effort)
---------------------------------------------------------------
    duration_min |  sustainable_fraction
              20 |  1.00      (~5K)
              40 |  0.95      (~10K)
              90 |  0.88      (~half marathon)
             150 |  0.84      (~30K)
             180 |  0.82      (marathon)
             270 |  0.75      (50K ultra)
             360 |  0.71      (60K ultra)
             480 |  0.68      (80K)
             600 |  0.63      (100K)
             960 |  0.55      (~100 miles, 160K)

Interpolation
-------------
Log-linear interpolation between anchor points (linear in log(duration)).
Outside the anchor table the function extrapolates conservatively:
  * Below 20 minutes the fraction is capped at 1.05 (sprints can transiently
    exceed an athlete's 5K capacity for ~1-2 km).
  * Above 960 minutes the slope of the last segment is continued but the
    result is clamped to >= 0.40 to avoid degenerate predictions on 24h+
    formats.

Modulation by durability_alpha
------------------------------
``durability_alpha`` ranges roughly from 0.04 (highly durable elite) to
0.20 (poor durability). The reference value is 0.12.

The modulation rescales the *loss* relative to a fresh capacity:
``alpha_factor = 0.12 / max(0.04, durability_alpha)``
``fraction_adjusted = 1.0 - (1.0 - fraction_default) * alpha_factor``

Consequence:
  * alpha = 0.06 (durable) -> alpha_factor = 2.0 -> loss is doubled? No!
    The intent is the *opposite*: a more durable athlete loses *less*. The
    correction is therefore:
       fraction_adjusted = 1.0 - (1.0 - fraction_default) / alpha_factor
    so that a higher ``alpha_factor`` (i.e. *lower* alpha) reduces the loss.
  * Implementation note: we follow the specification literally with
       fraction_adjusted = 1.0 - (1.0 - fraction_default) * alpha_factor
    where ``alpha_factor`` is *inverted* to encode "less durable -> more
    loss". See ``_alpha_modulation`` below for the actual code path.

Modulation by effort_mode
-------------------------
  * ``steady`` (default): no change.
  * ``endurance``: multiplied by 0.93 (slightly more conservative pacing).
  * ``aggressive``: multiplied by 1.05 then clamped to 1.0 (do not exceed
    raw capacity except in the explicit sub-20-minute sprint band).
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Tuple

# -- Constants ---------------------------------------------------------------

#: Anchor table used for log-linear interpolation. Each tuple is
#: ``(duration_minutes, sustainable_fraction)`` for the reference athlete
#: (``durability_alpha = 0.12``, ``effort_mode = "steady"``).
ANCHOR_TABLE: Tuple[Tuple[float, float], ...] = (
    (20.0, 1.00),
    (40.0, 0.95),
    (90.0, 0.88),
    (150.0, 0.84),
    (180.0, 0.82),
    (270.0, 0.75),
    (360.0, 0.71),
    (480.0, 0.68),
    (600.0, 0.63),
    (960.0, 0.55),
)

#: Reference durability alpha used to build the anchor table.
REFERENCE_ALPHA: float = 0.12

#: Lower bound on the durability alpha used in the modulation denominator. A
#: tighter clamp prevents division blow-up for unrealistic inputs.
MIN_ALPHA: float = 0.04

#: Hard cap above which an output fraction is impossible regardless of
#: effort_mode or alpha.
MAX_FRACTION: float = 1.05

#: Hard floor when extrapolating beyond the longest anchor (covers 24h+ races
#: which are not the intended target of this model).
MIN_FRACTION_EXTRAPOLATION: float = 0.40

#: Valid effort modes and their multiplicative effect on the fraction.
EFFORT_MODE_MULTIPLIERS: Dict[str, float] = {
    "steady": 1.00,
    "endurance": 0.93,
    "aggressive": 1.05,
}


# -- Public API --------------------------------------------------------------


def sustainable_fraction(
    duration_min: float,
    durability_alpha: float = 0.12,
    effort_mode: str = "steady",
) -> float:
    """Return the fraction of short-distance capacity sustainable over ``duration_min``.

    Parameters
    ----------
    duration_min:
        Target event duration in minutes. Must be strictly positive.
    durability_alpha:
        Athlete durability parameter. Reference value 0.12. Lower values
        (towards 0.04) describe more durable athletes who lose less fraction
        with duration. Higher values (towards 0.20) describe athletes who
        fade faster on long events. Must be > 0.
    effort_mode:
        Pacing intent. One of ``"steady"``, ``"endurance"`` or
        ``"aggressive"``.

    Returns
    -------
    float
        Fraction in ``[0.30, 1.05]``. Multiplying the short-distance capacity
        by this fraction yields the event-sustainable capacity.

    Raises
    ------
    ValueError
        If ``duration_min`` is not strictly positive, ``durability_alpha`` is
        not strictly positive, or ``effort_mode`` is unknown.
    """
    _validate_duration(duration_min)
    _validate_alpha(durability_alpha)
    _validate_effort_mode(effort_mode)

    base_fraction = _interpolate_anchor(duration_min)
    alpha_adjusted = _apply_alpha_modulation(base_fraction, durability_alpha)
    mode_adjusted = _apply_effort_mode(alpha_adjusted, effort_mode)

    # Final safety clamp: never exceed MAX_FRACTION, never drop below the
    # extrapolation floor.
    return max(MIN_FRACTION_EXTRAPOLATION, min(MAX_FRACTION, mode_adjusted))


def derive_event_power(
    p_capacity_wkg: float,
    duration_min: float,
    durability_alpha: float,
    effort_mode: str = "steady",
) -> Dict[str, float]:
    """Compute event-sustainable power from a short-distance capacity.

    Parameters
    ----------
    p_capacity_wkg:
        Short-distance capacity in W/kg (typically derived from a 5K or 10K
        test, i.e. roughly the 20-40 minute capacity).
    duration_min:
        Target event duration in minutes.
    durability_alpha:
        Athlete durability parameter; see ``sustainable_fraction``.
    effort_mode:
        Pacing intent; see ``sustainable_fraction``.

    Returns
    -------
    dict
        ``{
            "p_event_wkg": float,           # capacity * fraction
            "sustainable_fraction": float,  # the multiplier applied
            "duration_used_min": float,     # the duration that was provided
            "alpha_used": float,            # the alpha that was applied
            "effort_mode": str,             # the effort mode that was used
        }``

    Raises
    ------
    ValueError
        If ``p_capacity_wkg`` is non-positive, or any other input fails the
        validation performed by ``sustainable_fraction``.
    """
    if p_capacity_wkg is None or not math.isfinite(p_capacity_wkg) or p_capacity_wkg <= 0:
        raise ValueError(
            f"p_capacity_wkg must be a strictly positive finite number, got {p_capacity_wkg!r}"
        )

    fraction = sustainable_fraction(duration_min, durability_alpha, effort_mode)
    return {
        "p_event_wkg": p_capacity_wkg * fraction,
        "sustainable_fraction": fraction,
        "duration_used_min": float(duration_min),
        "alpha_used": float(durability_alpha),
        "effort_mode": effort_mode,
    }


def iterate_event_power(
    p_capacity_wkg: float,
    initial_duration_min: float,
    durability_alpha: float,
    predict_duration_callback: Callable[[float], float],
    max_iterations: int = 5,
    tolerance: float = 0.01,
    effort_mode: str = "steady",
) -> Dict[str, object]:
    """Iteratively converge the duration <-> sustainable-power coupling.

    The event power depends on the predicted duration, which itself depends on
    the event power through the physics engine. This routine implements the
    short fixed-point iteration documented in the V2.2 plan.

    Algorithm
    ---------
    Starting from ``initial_duration_min``:
      1. Compute the sustainable fraction for the current duration.
      2. Derive ``p_event = p_capacity * fraction``.
      3. Ask the physics-engine callback for a duration that matches
         ``p_event``.
      4. If the relative duration change is below ``tolerance``, return.
      5. Otherwise repeat with the new duration, up to ``max_iterations``.

    Parameters
    ----------
    p_capacity_wkg:
        Athlete short-distance capacity (W/kg).
    initial_duration_min:
        Initial guess for the event duration.
    durability_alpha:
        Athlete durability parameter.
    predict_duration_callback:
        Callable ``f(p_event_wkg) -> duration_min``. Wraps the physics engine
        so the service stays decoupled from it. The callback must return a
        strictly positive finite duration; otherwise a ``ValueError`` is
        raised.
    max_iterations:
        Hard cap on iterations. Must be >= 1.
    tolerance:
        Relative duration tolerance for convergence; e.g. ``0.01`` for 1 %.
        Must be strictly positive.
    effort_mode:
        Pacing intent; see ``sustainable_fraction``.

    Returns
    -------
    dict
        ``{
            "p_event_wkg": float,
            "sustainable_fraction": float,
            "final_duration_min": float,
            "iterations": [
                {"iter": int, "duration_min": float,
                 "fraction": float, "p_event_wkg": float,
                 "predicted_duration_min": float},
                ...
            ],
            "converged": bool,
            "final_iteration": int,
        }``

    Raises
    ------
    ValueError
        If any numeric input is invalid or if the callback returns an invalid
        duration.
    """
    if p_capacity_wkg is None or not math.isfinite(p_capacity_wkg) or p_capacity_wkg <= 0:
        raise ValueError(
            f"p_capacity_wkg must be a strictly positive finite number, got {p_capacity_wkg!r}"
        )
    _validate_duration(initial_duration_min)
    _validate_alpha(durability_alpha)
    _validate_effort_mode(effort_mode)
    if not callable(predict_duration_callback):
        raise ValueError("predict_duration_callback must be callable")
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError(
            f"max_iterations must be a positive integer, got {max_iterations!r}"
        )
    if tolerance is None or not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError(f"tolerance must be a strictly positive number, got {tolerance!r}")

    iterations: List[Dict[str, float]] = []
    duration = float(initial_duration_min)
    fraction = sustainable_fraction(duration, durability_alpha, effort_mode)
    p_event = p_capacity_wkg * fraction
    converged = False
    final_iter = 0

    for i in range(max_iterations):
        fraction = sustainable_fraction(duration, durability_alpha, effort_mode)
        p_event = p_capacity_wkg * fraction

        new_duration = predict_duration_callback(p_event)
        if (
            new_duration is None
            or not math.isfinite(new_duration)
            or new_duration <= 0
        ):
            raise ValueError(
                "predict_duration_callback must return a strictly positive finite duration, "
                f"got {new_duration!r}"
            )

        rel_change = abs(new_duration - duration) / duration
        iterations.append(
            {
                "iter": i,
                "duration_min": duration,
                "fraction": fraction,
                "p_event_wkg": p_event,
                "predicted_duration_min": float(new_duration),
            }
        )
        final_iter = i

        if rel_change < tolerance:
            # Final duration accepted: the converged state is the one that the
            # callback predicted from the current (consistent) p_event.
            duration = float(new_duration)
            # Recompute fraction/p_event from the converged duration so the
            # returned values describe a self-consistent solution.
            fraction = sustainable_fraction(duration, durability_alpha, effort_mode)
            p_event = p_capacity_wkg * fraction
            converged = True
            break

        duration = float(new_duration)

    return {
        "p_event_wkg": p_event,
        "sustainable_fraction": fraction,
        "final_duration_min": duration,
        "iterations": iterations,
        "converged": converged,
        "final_iteration": final_iter,
    }


# -- Internal helpers --------------------------------------------------------


def _validate_duration(duration_min: float) -> None:
    if (
        duration_min is None
        or not math.isfinite(duration_min)
        or duration_min <= 0
    ):
        raise ValueError(
            f"duration_min must be a strictly positive finite number, got {duration_min!r}"
        )


def _validate_alpha(durability_alpha: float) -> None:
    if (
        durability_alpha is None
        or not math.isfinite(durability_alpha)
        or durability_alpha <= 0
    ):
        raise ValueError(
            "durability_alpha must be a strictly positive finite number, "
            f"got {durability_alpha!r}"
        )


def _validate_effort_mode(effort_mode: str) -> None:
    if effort_mode not in EFFORT_MODE_MULTIPLIERS:
        raise ValueError(
            f"effort_mode must be one of {sorted(EFFORT_MODE_MULTIPLIERS)}, "
            f"got {effort_mode!r}"
        )


def _interpolate_anchor(duration_min: float) -> float:
    """Log-linear interpolation in the anchor table.

    Returns the *reference* sustainable fraction (alpha = REFERENCE_ALPHA,
    effort_mode = "steady"). The result is the input to alpha and
    effort_mode modulation.
    """
    # Anchors are sorted by construction; first/last are constants of the
    # module.
    first_dur, first_frac = ANCHOR_TABLE[0]
    last_dur, last_frac = ANCHOR_TABLE[-1]

    # Below the first anchor (sprint band): cap at MAX_FRACTION.
    if duration_min <= first_dur:
        return MAX_FRACTION if duration_min < first_dur else first_frac

    # Above the last anchor: continue the slope of the last segment in
    # log-duration space but clamp to the floor.
    if duration_min >= last_dur:
        prev_dur, prev_frac = ANCHOR_TABLE[-2]
        slope = (last_frac - prev_frac) / (math.log(last_dur) - math.log(prev_dur))
        extrapolated = last_frac + slope * (math.log(duration_min) - math.log(last_dur))
        return max(MIN_FRACTION_EXTRAPOLATION, extrapolated)

    # Interior: find the bracketing anchors and interpolate log-linearly.
    for (d_lo, f_lo), (d_hi, f_hi) in zip(ANCHOR_TABLE, ANCHOR_TABLE[1:]):
        if d_lo <= duration_min <= d_hi:
            log_lo = math.log(d_lo)
            log_hi = math.log(d_hi)
            log_d = math.log(duration_min)
            ratio = (log_d - log_lo) / (log_hi - log_lo)
            return f_lo + ratio * (f_hi - f_lo)

    # Should be unreachable because of bracketing above.
    raise RuntimeError(
        f"unexpected: duration_min={duration_min!r} not bracketed by ANCHOR_TABLE"
    )


def _apply_alpha_modulation(base_fraction: float, durability_alpha: float) -> float:
    """Scale the *loss* (1 - base_fraction) according to durability_alpha.

    For the reference alpha the function is the identity. For a less durable
    athlete (higher alpha) the loss grows; for a more durable athlete (lower
    alpha) the loss shrinks. The exact formula matches the V2.2 spec:

        alpha_factor = REFERENCE_ALPHA / max(MIN_ALPHA, durability_alpha)
        loss = (1 - base_fraction)
        fraction_adjusted = 1.0 - loss * (1 / alpha_factor)
                          = 1.0 - loss * (max(MIN_ALPHA, durability_alpha)
                                          / REFERENCE_ALPHA)

    The plan text uses ``fraction_adjusted = 1 - (1 - frac) * alpha_factor``
    with ``alpha_factor = 0.12 / max(0.04, alpha)``. Taken literally this
    would *increase* the loss when alpha decreases, which contradicts the
    plan's own example. We interpret the plan's intent and apply the
    physiologically correct sign: more durable -> less loss.
    """
    alpha = max(MIN_ALPHA, durability_alpha)
    # ratio > 1 means *less durable* than reference -> larger loss.
    # ratio < 1 means *more durable* than reference -> smaller loss.
    ratio = alpha / REFERENCE_ALPHA
    loss = 1.0 - base_fraction
    return 1.0 - loss * ratio


def _apply_effort_mode(fraction: float, effort_mode: str) -> float:
    """Apply pacing-intent multiplier, with the spec'd cap for ``aggressive``."""
    multiplier = EFFORT_MODE_MULTIPLIERS[effort_mode]
    adjusted = fraction * multiplier
    if effort_mode == "aggressive":
        # Per spec: aggressive multiplies by 1.05 but is capped at 1.0 so it
        # cannot promise *more* than raw capacity.
        adjusted = min(adjusted, 1.0)
    return adjusted
