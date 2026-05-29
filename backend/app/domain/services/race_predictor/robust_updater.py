"""Robust Bayesian updater for Race Predictor V2.2.

Combines a (population/profile) prior with a list of weighted observations to
produce a posterior distribution for a single latent parameter (e.g.
``flat_capacity_mps``, ``durability_alpha``, ``trail_cost_factor``,
``fc_max_bpm``, ``walk_power_ratio``).

Motivation
----------
A naive inverse-variance Gaussian fusion is *unsafe* when two observations
contradict each other. With fixed variances, fusing ``mean=2, std=0.2`` and
``mean=4, std=0.2`` collapses to a tightly peaked posterior centred near 3 with
``std ~= 0.14`` -- the model becomes *more* confident even though the evidence
is in flat-out conflict. This module implements a robust update that detects
that contradiction, down-weights the offending observations and *inflates* the
posterior variance instead of shrinking it.

Algorithm (compact summary)
---------------------------
1. Compute a tentative posterior via inverse-variance weighted fusion.
2. **Iterate (Iteratively Reweighted Least Squares, IRLS)** -- up to a small
   number of passes -- the following two steps until the assignment of
   outliers stabilises:
     a. Score each observation against the tentative posterior with a Welch
        statistic ``z_i = (m_i - mean) / sqrt(std^2 + std_obs_i^2)``.
     b. For every ``|z_i| > z_threshold`` (default 2.0), down-weight the
        observation with a Gaussian roll-off
        ``w_adj = w * exp(-(|z| - z_threshold)^2 / 2)`` (Huber-style soft
        rejection), and recompute the fusion with the adjusted weights.
   Iterating is what protects the algorithm from a single very large outlier
   that would otherwise drag the tentative mean far enough to make the
   consistent observations look like outliers.
3. Estimate inter-observation dispersion (weighted, with adjusted weights).
4. **Inflate** the posterior standard deviation when dispersion is significant:
   ``std_final = std_robust * max(1.0, dispersion / std_robust)``. This is the
   property that distinguishes the robust updater from the naive fusion.
5. Compute ``p10``/``p90`` from the final Gaussian approximation.

References
----------
- Huber, P.J. (1964). *Robust Estimation of a Location Parameter.* Annals of
  Mathematical Statistics, 35(1):73--101.
- West, M. (1981). *Robust Sequential Approximate Bayesian Estimation.* Journal
  of the Royal Statistical Society B, 43(2):157--166.
- Bishop, C.M. (2006). *Pattern Recognition and Machine Learning*, chap. 2
  (conjugate Gaussian updates and their failure modes under contradiction).
- Gelman et al. (2013). *Bayesian Data Analysis*, chap. 17 (robust regression,
  Student-t likelihoods, dispersion-aware updates).

The implementation only relies on ``numpy`` (no scipy dependency). All
functions are pure: no I/O, no shared state.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

#: Minimum std clamp to avoid divisions by zero when callers pass exactly 0.
MIN_STD: float = 1e-3

#: Default Huber-style z threshold above which an observation is treated as an
#: outlier and softly down-weighted.
DEFAULT_Z_THRESHOLD: float = 2.0

#: Maximum number of IRLS passes used to stabilise the outlier assignment.
#: Three passes are sufficient in practice for the asymmetric-outlier regime
#: described in Huber (1964) and West (1981); the per-iteration work is O(n).
MAX_IRLS_ITERATIONS: int = 5

#: 1.282 ~= Phi^{-1}(0.9) for the standard normal -- used to map (mean, std)
#: to symmetric P10/P90 bounds without depending on scipy.
NORMAL_Q90: float = 1.2815515655446004


# ---------------------------------------------------------------------------
# Small numerical helpers
# ---------------------------------------------------------------------------


def _safe_std(value: float) -> float:
    """Clamp a standard deviation away from zero and reject NaN/inf inputs."""
    if value is None or not math.isfinite(value):
        return MIN_STD
    return max(float(value), MIN_STD)


def _safe_weight(weight: Any) -> float:
    """Return a non-negative finite weight, defaulting to 1.0."""
    if weight is None:
        return 1.0
    try:
        w = float(weight)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(w) or w < 0.0:
        return 0.0
    return w


def _percentiles_from_normal(mean: float, std: float) -> tuple[float, float]:
    """Symmetric P10/P90 from a Gaussian approximation."""
    std = _safe_std(std)
    return (mean - NORMAL_Q90 * std, mean + NORMAL_Q90 * std)


def _gaussian_fusion(
    prior_mean: float,
    prior_std: float,
    obs_means: np.ndarray,
    obs_stds: np.ndarray,
    obs_weights: np.ndarray,
) -> tuple[float, float, float, float]:
    """Inverse-variance fusion of a prior and weighted observations.

    Returns ``(mean_post, std_post, prior_precision, evidence_precision)``.
    Observations with zero weight or non-finite variance are ignored.
    """
    prior_std = _safe_std(prior_std)
    prior_precision = 1.0 / (prior_std ** 2)

    # Sanitize observation arrays.
    if obs_means.size == 0:
        return prior_mean, prior_std, prior_precision, 0.0

    safe_stds = np.array([_safe_std(s) for s in obs_stds], dtype=float)
    safe_weights = np.array([_safe_weight(w) for w in obs_weights], dtype=float)
    safe_means = np.array(obs_means, dtype=float)

    obs_precisions = safe_weights / (safe_stds ** 2)
    # Drop any non-finite entry to stay safe under pathological inputs.
    finite = np.isfinite(obs_precisions) & np.isfinite(safe_means)
    obs_precisions = np.where(finite, obs_precisions, 0.0)

    evidence_precision = float(obs_precisions.sum())
    total_precision = prior_precision + evidence_precision

    weighted_mean_sum = prior_mean * prior_precision + float(
        (obs_precisions * safe_means).sum()
    )
    mean_post = weighted_mean_sum / total_precision
    std_post = math.sqrt(1.0 / total_precision)
    return mean_post, std_post, prior_precision, evidence_precision


def _weighted_dispersion(
    means: np.ndarray, weights: np.ndarray, centre: float
) -> float:
    """Weighted RMS deviation of observation means around ``centre``.

    ``sqrt(sum w_i (m_i - centre)^2 / sum w_i)``. Returns 0 when no
    observation has positive weight or fewer than two observations contribute.
    """
    if means.size == 0:
        return 0.0
    valid = weights > 0
    if valid.sum() < 2:
        # A single observation has no inter-observation dispersion.
        return 0.0
    w = weights[valid]
    m = means[valid]
    total = float(w.sum())
    if total <= 0.0:
        return 0.0
    var = float(((m - centre) ** 2 * w).sum() / total)
    if var < 0.0 or not math.isfinite(var):
        return 0.0
    return math.sqrt(var)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_outliers(
    observations: list[dict],
    reference_mean: float,
    reference_std: float,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> list[dict]:
    """Detect observations that disagree with a reference distribution.

    Parameters
    ----------
    observations
        List of dicts with at least ``"mean"`` and ``"std"`` keys. Optional:
        ``"source_label"``.
    reference_mean, reference_std
        Centre and spread of the reference (typically a tentative posterior).
    z_threshold
        Observations whose ``|z|`` exceeds this threshold are returned.

    Returns
    -------
    list of dicts ``[{"index", "source_label", "z_score", "reason"}, ...]``.
    """
    if not observations:
        return []

    ref_std = _safe_std(reference_std)
    outliers: list[dict] = []
    for idx, obs in enumerate(observations):
        weight = _safe_weight(obs.get("weight", 1.0))
        if weight <= 0.0:
            continue
        obs_std = _safe_std(obs.get("std", MIN_STD))
        scale = math.sqrt(ref_std ** 2 + obs_std ** 2)
        if scale <= 0.0:
            continue
        z = (float(obs["mean"]) - reference_mean) / scale
        if abs(z) > z_threshold:
            outliers.append(
                {
                    "index": idx,
                    "source_label": obs.get("source_label", f"obs_{idx}"),
                    "z_score": float(z),
                    "reason": (
                        f"|z|={abs(z):.2f} exceeds threshold {z_threshold:.2f}"
                    ),
                }
            )
    return outliers


def compute_posterior(
    prior: dict,
    observations: list[dict],
    use_robust: bool = True,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> dict:
    """Combine a prior and weighted observations into a posterior.

    Parameters
    ----------
    prior
        ``{"mean": float, "std": float, "sources": list[str] (optional)}``.
    observations
        Each entry must contain ``"mean"`` and ``"std"``. Optional keys:
        ``"weight"`` (default 1.0), ``"source_label"``, ``"source_id"``,
        ``"performed_at"``.
    use_robust
        ``True`` (default) runs the Huber/dispersion-inflated update.
        ``False`` runs a strict inverse-variance Gaussian fusion (provided
        only for comparison; this is the unsafe behaviour we want to detect
        and avoid in production).
    z_threshold
        Threshold above which an observation is treated as an outlier and
        softly down-weighted.

    Returns
    -------
    dict with keys ``mean``, ``std``, ``p10``, ``p90``,
    ``prior_weight_pct``, ``evidence_weight_pct``, ``evidence_count``,
    ``outliers``, ``method``, ``dispersion_factor``.
    """
    prior_mean = float(prior["mean"])
    prior_std = _safe_std(prior.get("std", 1.0))
    method = "robust_t" if use_robust else "weighted_gaussian_naive"

    # --- Empty-evidence shortcut --------------------------------------------
    if not observations:
        p10, p90 = _percentiles_from_normal(prior_mean, prior_std)
        return {
            "mean": prior_mean,
            "std": prior_std,
            "p10": p10,
            "p90": p90,
            "prior_weight_pct": 1.0,
            "evidence_weight_pct": 0.0,
            "evidence_count": 0,
            "outliers": [],
            "method": method,
            "dispersion_factor": 0.0,
        }

    # Filter observations: weight must be > 0 and core fields must be finite.
    kept_obs: list[dict] = []
    kept_indices: list[int] = []
    for idx, obs in enumerate(observations):
        weight = _safe_weight(obs.get("weight", 1.0))
        if weight <= 0.0:
            continue
        if "mean" not in obs or "std" not in obs:
            continue
        if not math.isfinite(float(obs["mean"])):
            continue
        kept_obs.append(obs)
        kept_indices.append(idx)

    if not kept_obs:
        # All observations were filtered out; behave as no-evidence case.
        p10, p90 = _percentiles_from_normal(prior_mean, prior_std)
        return {
            "mean": prior_mean,
            "std": prior_std,
            "p10": p10,
            "p90": p90,
            "prior_weight_pct": 1.0,
            "evidence_weight_pct": 0.0,
            "evidence_count": 0,
            "outliers": [],
            "method": method,
            "dispersion_factor": 0.0,
        }

    obs_means = np.array([float(o["mean"]) for o in kept_obs], dtype=float)
    obs_stds = np.array([_safe_std(o.get("std", MIN_STD)) for o in kept_obs], dtype=float)
    obs_weights = np.array(
        [_safe_weight(o.get("weight", 1.0)) for o in kept_obs], dtype=float
    )

    # --- Step 1: tentative naive fusion -------------------------------------
    mean_init, std_init, prior_prec, evid_prec = _gaussian_fusion(
        prior_mean, prior_std, obs_means, obs_stds, obs_weights
    )

    # --- Naive mode: stop here ----------------------------------------------
    if not use_robust:
        p10, p90 = _percentiles_from_normal(mean_init, std_init)
        total_prec = prior_prec + evid_prec
        prior_weight_pct = prior_prec / total_prec if total_prec > 0 else 1.0
        evidence_weight_pct = evid_prec / total_prec if total_prec > 0 else 0.0
        dispersion = _weighted_dispersion(obs_means, obs_weights, mean_init)
        return {
            "mean": mean_init,
            "std": std_init,
            "p10": p10,
            "p90": p90,
            "prior_weight_pct": float(prior_weight_pct),
            "evidence_weight_pct": float(evidence_weight_pct),
            "evidence_count": int(len(kept_obs)),
            "outliers": [],
            "method": method,
            "dispersion_factor": float(dispersion),
        }

    # --- Step 2: IRLS loop to stabilise outlier assignment ------------------
    # A single outlier with a precision similar to the consistent observations
    # can drag the tentative mean far enough to flag the consistent points as
    # outliers themselves. Iterating until the down-weighting converges fixes
    # this; in practice the inner loop converges within 2-3 iterations.
    mean_current = mean_init
    std_current = std_init
    mean_robust = mean_init
    std_robust = std_init
    prior_prec_r = prior_prec
    evid_prec_r = evid_prec
    adjusted_weights = obs_weights.copy()
    z_scores = np.zeros_like(obs_means)
    roll_offs = np.ones_like(obs_means)

    for _ in range(MAX_IRLS_ITERATIONS):
        # Recompute the soft weights based on the *current* tentative posterior.
        new_weights = obs_weights.copy()
        new_roll_offs = np.ones_like(obs_means)
        new_z_scores = np.zeros_like(obs_means)
        for i in range(len(kept_obs)):
            scale = math.sqrt(std_current ** 2 + obs_stds[i] ** 2)
            if scale <= 0.0 or obs_weights[i] <= 0.0:
                continue
            z = (obs_means[i] - mean_current) / scale
            new_z_scores[i] = z
            abs_z = abs(z)
            if abs_z > z_threshold:
                roll_off = math.exp(-((abs_z - z_threshold) ** 2) / 2.0)
                new_weights[i] = obs_weights[i] * roll_off
                new_roll_offs[i] = roll_off

        # Refit with the freshly adjusted weights.
        mean_robust, std_robust, prior_prec_r, evid_prec_r = _gaussian_fusion(
            prior_mean, prior_std, obs_means, obs_stds, new_weights
        )

        # Convergence: stop when the centre moves negligibly between passes.
        if (
            abs(mean_robust - mean_current) < 1e-6
            and abs(std_robust - std_current) < 1e-6
        ):
            adjusted_weights = new_weights
            z_scores = new_z_scores
            roll_offs = new_roll_offs
            mean_current = mean_robust
            std_current = std_robust
            break

        adjusted_weights = new_weights
        z_scores = new_z_scores
        roll_offs = new_roll_offs
        mean_current = mean_robust
        std_current = std_robust

    # Build the outlier records from the *final* z-scores and roll-offs.
    outlier_records: list[dict] = []
    for i in range(len(kept_obs)):
        if obs_weights[i] <= 0.0:
            continue
        abs_z = abs(z_scores[i])
        if abs_z > z_threshold:
            outlier_records.append(
                {
                    "index": kept_indices[i],
                    "source_label": kept_obs[i].get(
                        "source_label", f"obs_{kept_indices[i]}"
                    ),
                    "z_score": float(z_scores[i]),
                    "reason": (
                        f"|z|={abs_z:.2f} > {z_threshold:.2f}; "
                        f"weight x{roll_offs[i]:.3f}"
                    ),
                }
            )

    # --- Step 5: weighted inter-observation dispersion -----------------------
    dispersion = _weighted_dispersion(obs_means, adjusted_weights, mean_robust)

    # --- Step 6: inflate variance when observations disagree -----------------
    # Conservative multiplicative inflation. The naive posterior std reflects
    # the *precision* the weights would assert; if the cloud of observations
    # is wider than that, we propagate the cloud width instead.
    inflation_factor = max(1.0, dispersion / std_robust) if std_robust > 0 else 1.0
    std_final = std_robust * inflation_factor
    std_final = _safe_std(std_final)

    # --- Step 7: percentiles + provenance ------------------------------------
    p10, p90 = _percentiles_from_normal(mean_robust, std_final)
    total_prec_r = prior_prec_r + evid_prec_r
    if total_prec_r > 0:
        prior_weight_pct = prior_prec_r / total_prec_r
        evidence_weight_pct = evid_prec_r / total_prec_r
    else:
        prior_weight_pct = 1.0
        evidence_weight_pct = 0.0

    return {
        "mean": float(mean_robust),
        "std": float(std_final),
        "p10": float(p10),
        "p90": float(p90),
        "prior_weight_pct": float(prior_weight_pct),
        "evidence_weight_pct": float(evidence_weight_pct),
        "evidence_count": int(len(kept_obs)),
        "outliers": outlier_records,
        "method": method,
        "dispersion_factor": float(dispersion),
    }


def summarize_evidence(
    prior: dict, observations: list[dict], posterior: dict
) -> dict:
    """Produce a human-readable provenance breakdown of a posterior.

    Mirrors the structure consumed by the V2.2 debug trace and UI: how much
    the prior and each observation contributed, whether contradictions were
    detected, and a short narrative + recommendation tag.
    """
    prior_mean = float(prior["mean"])
    prior_std = _safe_std(prior.get("std", 1.0))
    prior_precision = 1.0 / (prior_std ** 2)

    posterior_mean = float(posterior["mean"])
    posterior_std = _safe_std(posterior["std"])
    use_robust = posterior.get("method", "robust_t") == "robust_t"
    z_threshold = DEFAULT_Z_THRESHOLD

    # --- Compute per-observation breakdown using the same adjustment rule ---
    # We replay the IRLS loop locally so the contribution numbers reflect what
    # compute_posterior actually used.
    breakdown: list[dict] = []
    if observations:
        obs_means = np.array(
            [float(o["mean"]) for o in observations], dtype=float
        )
        obs_stds = np.array(
            [_safe_std(o.get("std", MIN_STD)) for o in observations], dtype=float
        )
        obs_weights = np.array(
            [_safe_weight(o.get("weight", 1.0)) for o in observations], dtype=float
        )
        mean_current, std_current, _, _ = _gaussian_fusion(
            prior_mean, prior_std, obs_means, obs_stds, obs_weights
        )

        adjusted_weights = obs_weights.copy()
        final_z = np.zeros_like(obs_means)
        if use_robust:
            for _ in range(MAX_IRLS_ITERATIONS):
                new_weights = obs_weights.copy()
                new_z = np.zeros_like(obs_means)
                for i in range(len(observations)):
                    if obs_weights[i] <= 0.0:
                        continue
                    scale = math.sqrt(std_current ** 2 + obs_stds[i] ** 2)
                    if scale <= 0.0:
                        continue
                    z = (obs_means[i] - mean_current) / scale
                    new_z[i] = z
                    if abs(z) > z_threshold:
                        new_weights[i] = obs_weights[i] * math.exp(
                            -((abs(z) - z_threshold) ** 2) / 2.0
                        )
                mean_next, std_next, _, _ = _gaussian_fusion(
                    prior_mean, prior_std, obs_means, obs_stds, new_weights
                )
                adjusted_weights = new_weights
                final_z = new_z
                if (
                    abs(mean_next - mean_current) < 1e-6
                    and abs(std_next - std_current) < 1e-6
                ):
                    mean_current = mean_next
                    std_current = std_next
                    break
                mean_current = mean_next
                std_current = std_next
        else:
            # Naive mode: z scored against the naive fusion centre.
            for i in range(len(observations)):
                if obs_weights[i] <= 0.0:
                    continue
                scale = math.sqrt(std_current ** 2 + obs_stds[i] ** 2)
                if scale > 0.0:
                    final_z[i] = (obs_means[i] - mean_current) / scale

        adjusted_precisions = adjusted_weights / (obs_stds ** 2)
        total_precision = prior_precision + float(adjusted_precisions.sum())

        for i, obs in enumerate(observations):
            outlier_flag = use_robust and abs(final_z[i]) > z_threshold
            contribution = (
                float(adjusted_precisions[i] / total_precision)
                if total_precision > 0
                else 0.0
            )
            breakdown.append(
                {
                    "source_label": obs.get("source_label", f"obs_{i}"),
                    "mean": float(obs_means[i]),
                    "std": float(obs_stds[i]),
                    "weight_used": float(adjusted_weights[i]),
                    "z_score": float(final_z[i]),
                    "outlier": bool(outlier_flag),
                    "contribution_pct": contribution,
                }
            )

    # --- Dispersion + prior / evidence shares -------------------------------
    dispersion = float(posterior.get("dispersion_factor", 0.0))
    prior_contribution_pct = float(posterior.get("prior_weight_pct", 1.0))
    evidence_contribution_pct = float(posterior.get("evidence_weight_pct", 0.0))
    outliers = posterior.get("outliers", [])

    # --- Narrative + recommendation ----------------------------------------
    # Order matters: contradictory evidence is the loudest signal.
    if outliers or (
        len(observations) >= 2 and dispersion > max(posterior_std, prior_std)
    ):
        narrative = (
            "Contradictions detected between observations: posterior variance "
            "has been inflated to reflect disagreement. Investigate flagged "
            "outliers before trusting a tight interval."
        )
        recommendation = "contradictory_evidence"
    elif evidence_contribution_pct >= 0.66:
        narrative = (
            "Evidence dominates the posterior: observations carry most of the "
            "informational weight relative to the prior."
        )
        recommendation = "evidence_dominant"
    elif prior_contribution_pct >= 0.66:
        narrative = (
            "Prior dominates the posterior: the supplied evidence is sparse or "
            "imprecise. A reference test would tighten the interval."
        )
        recommendation = "prior_dominant"
    else:
        narrative = (
            "Prior and evidence contribute in similar proportions to the "
            "posterior."
        )
        recommendation = "balanced"

    return {
        "prior_contribution_pct": prior_contribution_pct,
        "evidence_contribution_pct": evidence_contribution_pct,
        "evidence_breakdown": breakdown,
        "dispersion_between_observations": dispersion,
        "narrative": narrative,
        "recommendation": recommendation,
        "posterior_mean": float(posterior_mean),
        "posterior_std": float(posterior_std),
    }


__all__ = [
    "compute_posterior",
    "detect_outliers",
    "summarize_evidence",
    "DEFAULT_Z_THRESHOLD",
    "MIN_STD",
    "NORMAL_Q90",
]
