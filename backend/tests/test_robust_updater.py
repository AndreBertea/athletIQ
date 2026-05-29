"""Tests for the robust Bayesian updater (Race Predictor V2.2).

The critical contract for this module is that, when given contradictory
observations, the posterior variance must *increase* rather than falsely
shrink. ``test_robust_method_inflates_variance_on_contradictions`` is the
non-negotiable acceptance test for that property.
"""

from __future__ import annotations

import math

import pytest

from app.domain.services.race_predictor.robust_updater import (
    DEFAULT_Z_THRESHOLD,
    NORMAL_Q90,
    compute_posterior,
    detect_outliers,
    summarize_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prior(mean: float = 3.0, std: float = 1.0) -> dict:
    return {"mean": mean, "std": std, "sources": ["population_prior"]}


def _obs(mean: float, std: float, weight: float = 1.0, label: str = "obs") -> dict:
    return {"mean": mean, "std": std, "weight": weight, "source_label": label}


# ---------------------------------------------------------------------------
# Empty / degenerate inputs
# ---------------------------------------------------------------------------


def test_no_observations_returns_prior():
    posterior = compute_posterior(_prior(3.0, 1.0), [])

    assert posterior["mean"] == pytest.approx(3.0)
    assert posterior["std"] == pytest.approx(1.0)
    assert posterior["evidence_count"] == 0
    assert posterior["outliers"] == []
    assert posterior["prior_weight_pct"] == pytest.approx(1.0)
    assert posterior["evidence_weight_pct"] == pytest.approx(0.0)
    assert posterior["dispersion_factor"] == pytest.approx(0.0)


def test_no_observations_p10_p90_consistent():
    posterior = compute_posterior(_prior(5.0, 0.5), [])

    expected_p10 = 5.0 - NORMAL_Q90 * 0.5
    expected_p90 = 5.0 + NORMAL_Q90 * 0.5
    assert posterior["p10"] == pytest.approx(expected_p10, rel=1e-6)
    assert posterior["p90"] == pytest.approx(expected_p90, rel=1e-6)


# ---------------------------------------------------------------------------
# Consistent evidence: standard Bayesian shrinkage
# ---------------------------------------------------------------------------


def test_single_consistent_observation_narrows_posterior():
    prior = _prior(3.0, 1.0)
    obs = _obs(3.2, 0.3, label="single")

    posterior = compute_posterior(prior, [obs])

    # Mean should land between prior and observation, closer to the more
    # precise observation.
    assert 3.0 < posterior["mean"] < 3.2
    # Posterior std must be strictly smaller than the smallest input std.
    assert posterior["std"] < 0.3
    assert posterior["std"] < 1.0
    assert posterior["evidence_count"] == 1
    assert posterior["outliers"] == []


def test_three_consistent_observations_tight_posterior():
    prior = _prior(3.0, 1.0)
    obs_list = [_obs(3.05, 0.25, label="a"), _obs(2.95, 0.25, label="b"), _obs(3.0, 0.25, label="c")]

    posterior = compute_posterior(prior, obs_list)

    assert 2.95 < posterior["mean"] < 3.05
    assert posterior["std"] < 0.2
    assert posterior["evidence_count"] == 3
    assert posterior["outliers"] == []
    # Evidence should dominate when we have three precise consistent obs.
    assert posterior["evidence_weight_pct"] > 0.9


def test_robust_method_preserves_mean_when_observations_dont_contradict():
    prior = _prior(3.0, 0.8)
    obs_list = [_obs(3.1, 0.2, label="a"), _obs(2.95, 0.2, label="b")]

    posterior_robust = compute_posterior(prior, obs_list, use_robust=True)
    posterior_naive = compute_posterior(prior, obs_list, use_robust=False)

    # When the observations agree, robust and naive means should match.
    assert posterior_robust["mean"] == pytest.approx(posterior_naive["mean"], rel=1e-3)
    # No outliers should be flagged.
    assert posterior_robust["outliers"] == []


# ---------------------------------------------------------------------------
# Outlier detection
# ---------------------------------------------------------------------------


def test_outlier_among_consistent_observations_is_detected():
    prior = _prior(3.0, 1.0)
    obs_list = [
        _obs(3.0, 0.2, label="ok_a"),
        _obs(3.05, 0.2, label="ok_b"),
        _obs(2.95, 0.2, label="ok_c"),
        _obs(10.0, 0.2, label="spurious"),
    ]

    posterior = compute_posterior(prior, obs_list)

    assert posterior["evidence_count"] == 4
    labels = {o["source_label"] for o in posterior["outliers"]}
    assert "spurious" in labels
    # The three coherent observations should not be flagged.
    assert "ok_a" not in labels
    assert "ok_b" not in labels
    assert "ok_c" not in labels


def test_outlier_weight_reduced_in_posterior():
    prior = _prior(3.0, 1.0)
    coherent = [_obs(3.0, 0.2, label="a"), _obs(3.0, 0.2, label="b"), _obs(3.0, 0.2, label="c")]
    with_outlier = coherent + [_obs(10.0, 0.2, label="outlier")]

    posterior_clean = compute_posterior(prior, coherent)
    posterior_with_outlier = compute_posterior(prior, with_outlier)

    # The outlier shifts the mean far less than it would in naive fusion.
    naive_outlier = compute_posterior(prior, with_outlier, use_robust=False)
    drift_robust = abs(posterior_with_outlier["mean"] - posterior_clean["mean"])
    drift_naive = abs(naive_outlier["mean"] - posterior_clean["mean"])
    assert drift_robust < drift_naive


def test_detect_outliers_returns_expected_shape():
    obs_list = [
        _obs(3.0, 0.2, label="ok"),
        _obs(10.0, 0.2, label="far"),
    ]
    outliers = detect_outliers(obs_list, reference_mean=3.0, reference_std=0.2)

    assert len(outliers) == 1
    entry = outliers[0]
    assert entry["index"] == 1
    assert entry["source_label"] == "far"
    assert abs(entry["z_score"]) > DEFAULT_Z_THRESHOLD
    assert "reason" in entry


# ---------------------------------------------------------------------------
# Weight handling
# ---------------------------------------------------------------------------


def test_high_variance_observation_contributes_less():
    prior = _prior(3.0, 1.0)
    tight = _obs(2.5, 0.1, label="tight")
    loose = _obs(5.0, 5.0, label="loose")

    posterior = compute_posterior(prior, [tight, loose])

    # The posterior should sit close to the tight observation despite the
    # loose one being numerically far away.
    assert abs(posterior["mean"] - 2.5) < abs(posterior["mean"] - 5.0)


def test_weights_zero_observation_excluded():
    prior = _prior(3.0, 1.0)
    kept = _obs(2.5, 0.2, label="kept", weight=1.0)
    dropped = _obs(10.0, 0.2, label="dropped", weight=0.0)

    posterior = compute_posterior(prior, [kept, dropped])

    # evidence_count counts kept observations only (weight > 0 filter).
    assert posterior["evidence_count"] == 1
    # Posterior must ignore the zero-weight outlier entirely.
    assert posterior["mean"] < 3.0
    assert all(o["source_label"] != "dropped" for o in posterior["outliers"])


# ---------------------------------------------------------------------------
# CRITICAL: contradiction inflates variance (non-negotiable property)
# ---------------------------------------------------------------------------


def test_robust_method_inflates_variance_on_contradictions():
    prior = {"mean": 3.0, "std": 1.0}
    obs_a = {"mean": 2.0, "std": 0.2, "weight": 1.0, "source_label": "obs_a"}
    obs_b = {"mean": 4.0, "std": 0.2, "weight": 1.0, "source_label": "obs_b"}

    posterior_robust = compute_posterior(prior, [obs_a, obs_b], use_robust=True)
    posterior_naive = compute_posterior(prior, [obs_a, obs_b], use_robust=False)

    # The naive method falsely shrinks the variance.
    assert (
        posterior_naive["std"] < 0.3
    ), f"Naive std={posterior_naive['std']:.3f} unexpectedly wide"

    # The robust method detects the contradiction and keeps a wide interval.
    assert posterior_robust["std"] > posterior_naive["std"], (
        f"Robust std {posterior_robust['std']:.3f} should exceed naive std "
        f"{posterior_naive['std']:.3f}"
    )
    assert (
        posterior_robust["std"] > 0.5
    ), f"Robust std={posterior_robust['std']:.3f} not significantly inflated"
    assert (
        posterior_robust["dispersion_factor"] > 0.5
    ), f"Dispersion factor={posterior_robust['dispersion_factor']:.3f} too low"

    # The mean should sit between the two contradictory observations.
    assert 2.5 <= posterior_robust["mean"] <= 3.5


def test_naive_method_falls_into_trap_on_contradictions():
    """Document the unsafe behaviour of the naive update for regression tests.

    This test exists to keep an explicit reminder that ``use_robust=False`` is
    *not* safe for production: two contradictory observations shrink the
    posterior variance instead of widening it.
    """
    prior = {"mean": 3.0, "std": 1.0}
    obs_a = {"mean": 2.0, "std": 0.2, "weight": 1.0, "source_label": "a"}
    obs_b = {"mean": 4.0, "std": 0.2, "weight": 1.0, "source_label": "b"}

    posterior = compute_posterior(prior, [obs_a, obs_b], use_robust=False)

    # Naive fusion sits near prior mean by symmetry...
    assert posterior["mean"] == pytest.approx(3.0, abs=0.05)
    # ...but it returns a *tighter* interval than either input std.
    assert posterior["std"] < 0.2
    # And it reports no outliers despite the obvious contradiction.
    assert posterior["outliers"] == []
    assert posterior["method"] == "weighted_gaussian_naive"


# ---------------------------------------------------------------------------
# Output contract / shape
# ---------------------------------------------------------------------------


def test_p10_p90_consistent_with_normal_distribution():
    posterior = compute_posterior(_prior(2.0, 0.5), [_obs(2.0, 0.4, label="anchor")])

    half_width = NORMAL_Q90 * posterior["std"]
    assert posterior["p10"] == pytest.approx(posterior["mean"] - half_width, rel=1e-6)
    assert posterior["p90"] == pytest.approx(posterior["mean"] + half_width, rel=1e-6)
    assert posterior["p10"] < posterior["p90"]


def test_evidence_breakdown_includes_all_observations():
    prior = _prior(3.0, 1.0)
    obs_list = [_obs(3.1, 0.3, label="alpha"), _obs(2.9, 0.3, label="beta")]
    posterior = compute_posterior(prior, obs_list)

    summary = summarize_evidence(prior, obs_list, posterior)

    assert len(summary["evidence_breakdown"]) == 2
    labels = {entry["source_label"] for entry in summary["evidence_breakdown"]}
    assert labels == {"alpha", "beta"}


def test_summarize_evidence_returns_consistent_shape():
    prior = _prior(3.0, 1.0)
    obs_list = [_obs(3.0, 0.2, label="x")]
    posterior = compute_posterior(prior, obs_list)
    summary = summarize_evidence(prior, obs_list, posterior)

    expected_keys = {
        "prior_contribution_pct",
        "evidence_contribution_pct",
        "evidence_breakdown",
        "dispersion_between_observations",
        "narrative",
        "recommendation",
    }
    assert expected_keys.issubset(summary.keys())
    # Contributions are normalised shares of total precision.
    assert 0.0 <= summary["prior_contribution_pct"] <= 1.0
    assert 0.0 <= summary["evidence_contribution_pct"] <= 1.0
    total = summary["prior_contribution_pct"] + summary["evidence_contribution_pct"]
    assert math.isclose(total, 1.0, abs_tol=1e-6)


def test_summarize_evidence_narrative_on_balanced_case():
    prior = _prior(3.0, 0.4)
    # A single moderately precise observation produces a balanced posterior.
    obs_list = [_obs(3.1, 0.4, label="single")]
    posterior = compute_posterior(prior, obs_list)
    summary = summarize_evidence(prior, obs_list, posterior)

    assert summary["recommendation"] == "balanced"
    assert "similar proportions" in summary["narrative"].lower()


def test_summarize_evidence_narrative_on_contradictory_case():
    prior = {"mean": 3.0, "std": 1.0}
    obs_a = _obs(2.0, 0.2, label="a")
    obs_b = _obs(4.0, 0.2, label="b")
    posterior = compute_posterior(prior, [obs_a, obs_b])
    summary = summarize_evidence(prior, [obs_a, obs_b], posterior)

    assert summary["recommendation"] == "contradictory_evidence"
    assert "contradiction" in summary["narrative"].lower()
    # The breakdown should mark both observations as outliers.
    assert all(entry["outlier"] for entry in summary["evidence_breakdown"])
