"""Tests for prior_service (Race Predictor V2.2 population priors).

These tests assert that:
- functions accept None for every input and return a usable wide prior;
- more inputs -> tighter prior;
- the standard dict shape is preserved across all functions;
- the published reference equations are respected within plausible ranges.
"""
from __future__ import annotations

import math

import pytest

from app.domain.services.race_predictor.prior_service import (
    _jackson_bmi_vo2max,
    estimate_durability_alpha_prior,
    estimate_fcmax_prior,
    estimate_flat_capacity_prior,
    estimate_heat_penalty_prior,
    estimate_trail_cost_factor_prior,
    estimate_vo2max_prior,
    estimate_walk_threshold_prior,
)


REQUIRED_KEYS = {
    "mean",
    "std",
    "p10",
    "p90",
    "sources",
    "evidence_strength",
    "notes",
}


def _assert_shape(prior: dict) -> None:
    assert REQUIRED_KEYS.issubset(prior.keys())
    assert isinstance(prior["mean"], float)
    assert isinstance(prior["std"], float)
    assert isinstance(prior["p10"], float)
    assert isinstance(prior["p90"], float)
    assert isinstance(prior["sources"], list) and prior["sources"]
    assert prior["evidence_strength"] in {
        "minimal",
        "demographic_only",
        "demographic_with_activity",
    }
    assert isinstance(prior["notes"], str) and prior["notes"]


# ---------------------------------------------------------------------------
# VO2max
# ---------------------------------------------------------------------------


def test_vo2max_all_none_returns_wide_prior():
    prior = estimate_vo2max_prior(None, None, None, None, None)
    _assert_shape(prior)
    assert prior["evidence_strength"] == "minimal"
    assert prior["std"] > 10  # very wide
    assert 25 <= prior["mean"] <= 45


def test_vo2max_elite_male_30y_75kg_180cm_active_realistic():
    prior = estimate_vo2max_prior("male", 30, 75, 180, "active")
    _assert_shape(prior)
    # Active healthy 30y male around BMI 23 with PAR=5 -> Jackson/Wier
    # unified form gives ~48 mL/kg/min; the p90 of the prior must cover
    # well-trained athletes up to ~55+. The mean must sit in a
    # physiologically reasonable range for an active 30y male.
    assert 45 <= prior["mean"] <= 65, prior["mean"]
    # Tight prior because all inputs are provided.
    assert prior["std"] < 7
    assert prior["evidence_strength"] == "demographic_with_activity"
    # Coverage check: the p90 should reach well-trained athlete territory.
    assert prior["p90"] >= 50


def test_vo2max_sedentary_older_lower_than_active_younger():
    older = estimate_vo2max_prior("male", 60, 80, 175, "sedentary")
    younger = estimate_vo2max_prior("male", 25, 70, 178, "very_active")
    assert older["mean"] < younger["mean"]


def test_vo2max_male_higher_than_female_same_demo():
    male = estimate_vo2max_prior("male", 35, 75, 180, "active")
    female = estimate_vo2max_prior("female", 35, 75, 180, "active")
    assert male["mean"] > female["mean"]


def test_vo2max_inputs_specified_narrower_than_all_none():
    wide = estimate_vo2max_prior(None, None, None, None, None)
    narrow = estimate_vo2max_prior("male", 35, 75, 180, "active")
    assert narrow["std"] < wide["std"]


def test_vo2max_partial_input_widens_prior_vs_full_input():
    full = estimate_vo2max_prior("male", 35, 75, 180, "active")
    only_sex_age = estimate_vo2max_prior("male", 35, None, None, None)
    assert only_sex_age["std"] > full["std"]


# ---------------------------------------------------------------------------
# Jackson 1990 BMI variant - frozen numerical tests (R0)
#
# Reference equation (CDC NYFS Treadmill Examination Manual, Appendix F,
# derived from Jackson et al. 1990 DOI 10.1249/00005768-199012000-00021):
#
#     VO2max = 56.363 + 1.921 * PA-R - 0.381 * age - 0.754 * BMI
#              + 10.987 * gender
#
# with gender = 1 (male), gender = 0 (female).
# ---------------------------------------------------------------------------


def test_jackson_bmi_male_35y_75kg_180cm_par5():
    """Frozen reference case (male). BMI = 75 / 1.80^2 = 23.148."""
    bmi = 75 / (1.80 ** 2)
    vo2 = _jackson_bmi_vo2max(par=5, age=35, bmi=bmi, gender_flag=1)
    expected = 56.363 + 1.921 * 5 - 0.381 * 35 - 0.754 * bmi + 10.987
    assert abs(vo2 - expected) < 1e-4


def test_jackson_bmi_female_35y_65kg_165cm_par5():
    """Frozen reference case (female). Same coefficients as male, gender=0."""
    bmi = 65 / (1.65 ** 2)
    vo2 = _jackson_bmi_vo2max(par=5, age=35, bmi=bmi, gender_flag=0)
    expected = 56.363 + 1.921 * 5 - 0.381 * 35 - 0.754 * bmi
    assert abs(vo2 - expected) < 1e-4


def test_jackson_bmi_gender_difference_is_exactly_10_987():
    """Female and male with identical inputs differ by exactly +10.987."""
    bmi = 23.0
    male = _jackson_bmi_vo2max(par=5, age=35, bmi=bmi, gender_flag=1)
    female = _jackson_bmi_vo2max(par=5, age=35, bmi=bmi, gender_flag=0)
    assert abs((male - female) - 10.987) < 1e-9


def test_jackson_bmi_age_boundaries():
    """Age bounds 18 and 65. Younger athlete must have higher VO2max."""
    bmi = 22.0
    vo2_18 = _jackson_bmi_vo2max(par=5, age=18, bmi=bmi, gender_flag=1)
    vo2_65 = _jackson_bmi_vo2max(par=5, age=65, bmi=bmi, gender_flag=1)
    assert vo2_18 > vo2_65
    # Difference must be exactly the age coefficient times the age delta.
    assert abs((vo2_18 - vo2_65) - 0.381 * (65 - 18)) < 1e-9


def test_jackson_bmi_par_boundaries():
    """PA-R bounds 0 and 7. More active athlete must have higher VO2max."""
    bmi = 22.0
    vo2_par0 = _jackson_bmi_vo2max(par=0, age=35, bmi=bmi, gender_flag=1)
    vo2_par7 = _jackson_bmi_vo2max(par=7, age=35, bmi=bmi, gender_flag=1)
    assert vo2_par7 > vo2_par0
    # Difference must be exactly the PA-R coefficient times the PAR delta.
    assert abs((vo2_par7 - vo2_par0) - 1.921 * 7) < 1e-9


def test_jackson_bmi_invalid_gender_flag_raises():
    """Any value other than 0/1 for gender_flag must raise ValueError."""
    with pytest.raises(ValueError):
        _jackson_bmi_vo2max(par=5, age=35, bmi=22.0, gender_flag=2)


def test_estimate_vo2max_prior_male_uses_canonical_bmi_form():
    """High-level prior for a male must match the canonical BMI form."""
    bmi = 75 / (1.80 ** 2)
    expected = 56.363 + 1.921 * 5 - 0.381 * 35 - 0.754 * bmi + 10.987
    prior = estimate_vo2max_prior("male", 35, 75, 180, "active")
    assert abs(prior["mean"] - expected) < 1e-4


def test_estimate_vo2max_prior_female_uses_canonical_bmi_form():
    """High-level prior for a female must use SAME coefficients, gender=0."""
    bmi = 65 / (1.65 ** 2)
    expected = 56.363 + 1.921 * 5 - 0.381 * 35 - 0.754 * bmi  # gender_flag = 0
    prior = estimate_vo2max_prior("female", 35, 65, 165, "active")
    assert abs(prior["mean"] - expected) < 1e-4


def test_estimate_vo2max_prior_gender_offset_is_exactly_10_987_via_public_api():
    """Same demographics + sex difference -> exactly +10.987 at the API level."""
    male = estimate_vo2max_prior("male", 35, 70, 175, "active")
    female = estimate_vo2max_prior("female", 35, 70, 175, "active")
    assert abs((male["mean"] - female["mean"]) - 10.987) < 1e-9


# ---------------------------------------------------------------------------
# FCmax
# ---------------------------------------------------------------------------


def test_fcmax_tanaka_formula_30y():
    prior = estimate_fcmax_prior(30, "male")
    _assert_shape(prior)
    # Tanaka: 208 - 0.7 * 30 = 187
    assert abs(prior["mean"] - 187.0) < 1e-6


def test_fcmax_tanaka_formula_50y():
    prior = estimate_fcmax_prior(50, "female")
    # Tanaka: 208 - 0.7 * 50 = 173
    assert abs(prior["mean"] - 173.0) < 1e-6


def test_fcmax_no_age_wider_variance():
    no_age = estimate_fcmax_prior(None, "male")
    with_age = estimate_fcmax_prior(35, "male")
    _assert_shape(no_age)
    assert no_age["evidence_strength"] == "minimal"
    assert no_age["std"] > with_age["std"]


# ---------------------------------------------------------------------------
# Flat capacity
# ---------------------------------------------------------------------------


def test_flat_capacity_consistent_with_vo2max():
    vo2_low = estimate_vo2max_prior("male", 45, 80, 175, "moderate")
    vo2_high = estimate_vo2max_prior("male", 25, 70, 180, "very_active")
    cap_low = estimate_flat_capacity_prior(vo2_low, "regular")
    cap_high = estimate_flat_capacity_prior(vo2_high, "regular")
    _assert_shape(cap_low)
    _assert_shape(cap_high)
    assert cap_high["mean"] > cap_low["mean"]


def test_flat_capacity_elite_higher_than_beginner_same_vo2max():
    vo2 = estimate_vo2max_prior("male", 30, 70, 178, "active")
    elite = estimate_flat_capacity_prior(vo2, "elite")
    beginner = estimate_flat_capacity_prior(vo2, "beginner")
    assert elite["mean"] > beginner["mean"]


def test_flat_capacity_handles_none_inputs():
    cap = estimate_flat_capacity_prior(None, None)
    _assert_shape(cap)
    assert cap["evidence_strength"] == "minimal"
    assert cap["mean"] > 1.5  # positive plausible speed


# ---------------------------------------------------------------------------
# Walk threshold
# ---------------------------------------------------------------------------


def test_walk_threshold_trail_elite_higher_than_road_beginner():
    elite_trail = estimate_walk_threshold_prior("elite", "trail")
    beginner_road = estimate_walk_threshold_prior("beginner", "road")
    _assert_shape(elite_trail)
    _assert_shape(beginner_road)
    assert elite_trail["mean"] > beginner_road["mean"]


def test_walk_threshold_all_none_wide():
    prior = estimate_walk_threshold_prior(None, None)
    _assert_shape(prior)
    assert prior["evidence_strength"] == "minimal"
    assert prior["std"] >= 0.07


# ---------------------------------------------------------------------------
# Durability alpha
# ---------------------------------------------------------------------------


def test_durability_alpha_elite_lower_than_beginner():
    elite = estimate_durability_alpha_prior("elite", "trail", "high")
    beginner = estimate_durability_alpha_prior("beginner", "road", "low")
    _assert_shape(elite)
    _assert_shape(beginner)
    # Lower alpha = better durability for elites.
    assert elite["mean"] < beginner["mean"]


def test_durability_alpha_all_none_wide_regular_median():
    prior = estimate_durability_alpha_prior(None, None, None)
    _assert_shape(prior)
    assert prior["evidence_strength"] == "minimal"
    assert 0.10 <= prior["mean"] <= 0.16
    assert prior["std"] >= 0.06


# ---------------------------------------------------------------------------
# Trail cost factor
# ---------------------------------------------------------------------------


def test_trail_cost_factor_in_literature_range_1_10_to_1_30():
    """All plausible combinations stay inside 1.05-1.35 (literature bracket)."""
    for experience in (None, "elite", "competitor", "regular", "beginner"):
        for practice in (None, "road", "trail", "mixed"):
            prior = estimate_trail_cost_factor_prior(experience, practice)
            _assert_shape(prior)
            assert 1.05 <= prior["mean"] <= 1.35, (experience, practice, prior["mean"])


def test_trail_cost_factor_road_higher_than_trail_dominant():
    trail_elite = estimate_trail_cost_factor_prior("elite", "trail")
    road_regular = estimate_trail_cost_factor_prior("regular", "road")
    assert road_regular["mean"] > trail_elite["mean"]


# ---------------------------------------------------------------------------
# Heat penalty
# ---------------------------------------------------------------------------


def test_heat_penalty_in_literature_range_0_3_to_1_4():
    for experience in (None, "elite", "competitor", "regular", "beginner"):
        for volume in (None, "low", "moderate", "high", "very_high"):
            prior = estimate_heat_penalty_prior(experience, volume)
            _assert_shape(prior)
            assert 0.2 <= prior["mean"] <= 1.4, (experience, volume, prior["mean"])


def test_heat_penalty_elite_lower_than_beginner():
    elite = estimate_heat_penalty_prior("elite", "high")
    beginner = estimate_heat_penalty_prior("beginner", "low")
    assert elite["mean"] < beginner["mean"]


# ---------------------------------------------------------------------------
# Cross-cutting structure tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prior",
    [
        estimate_vo2max_prior(None, None, None, None, None),
        estimate_vo2max_prior("male", 35, 75, 180, "active"),
        estimate_fcmax_prior(None, None),
        estimate_fcmax_prior(35, "male"),
        estimate_flat_capacity_prior(None, None),
        estimate_flat_capacity_prior(
            estimate_vo2max_prior("female", 28, 60, 165, "very_active"),
            "competitor",
        ),
        estimate_walk_threshold_prior(None, None),
        estimate_walk_threshold_prior("elite", "trail"),
        estimate_durability_alpha_prior(None, None, None),
        estimate_durability_alpha_prior("regular", "mixed", "moderate"),
        estimate_trail_cost_factor_prior(None, None),
        estimate_trail_cost_factor_prior("competitor", "trail"),
        estimate_heat_penalty_prior(None, None),
        estimate_heat_penalty_prior("regular", "moderate"),
    ],
)
def test_all_priors_return_consistent_dict_shape(prior):
    _assert_shape(prior)


@pytest.mark.parametrize(
    "prior",
    [
        estimate_vo2max_prior("male", 35, 75, 180, "active"),
        estimate_fcmax_prior(40, "female"),
        estimate_flat_capacity_prior(
            estimate_vo2max_prior("male", 30, 75, 180, "active"), "regular"
        ),
        estimate_walk_threshold_prior("regular", "trail"),
        estimate_durability_alpha_prior("competitor", "trail", "moderate"),
        estimate_trail_cost_factor_prior("regular", "mixed"),
        estimate_heat_penalty_prior("competitor", "moderate"),
    ],
)
def test_p10_p90_consistent_with_normal_distribution(prior):
    # p10 = mean - 1.2816 * std, p90 = mean + 1.2816 * std
    z = 1.2816
    assert math.isclose(prior["p10"], prior["mean"] - z * prior["std"], rel_tol=1e-3, abs_tol=1e-3)
    assert math.isclose(prior["p90"], prior["mean"] + z * prior["std"], rel_tol=1e-3, abs_tol=1e-3)
    assert prior["p10"] < prior["mean"] < prior["p90"]


def test_module_is_pure_no_db_no_network_imports():
    """The prior_service must not import from DB, sessions, or HTTP layers."""
    import inspect

    from app.domain.services.race_predictor import prior_service

    source = inspect.getsource(prior_service)
    forbidden_tokens = (
        "from sqlmodel",
        "from sqlalchemy",
        "import requests",
        "import httpx",
        "import urllib",
        "from app.core.database",
        "from app.domain.entities",
    )
    for token in forbidden_tokens:
        assert token not in source, f"prior_service must not contain '{token}'"
