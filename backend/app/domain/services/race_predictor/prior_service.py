"""Population-level priors for Race Predictor V2.2.

Pure functions that return demographic-derived parameter distributions based
on published literature. No database access, no network calls, no project
data. All inputs are optional: missing inputs widen the returned variance.

Each public function returns a dict with the same schema::

    {
        "mean": float,
        "std": float,
        "p10": float,
        "p90": float,
        "sources": list[str],
        "evidence_strength": str,  # one of:
            # "minimal"                       -> all inputs None
            # "demographic_only"              -> demographics only
            # "demographic_with_activity"     -> demographics + activity profile
        "notes": str,
    }

Priors widen when the literature equations do not apply (e.g. unknown age).
The std reflects between-individual variance reported in the source studies;
it is intentionally larger than a single test-derived posterior.

Sources of departure (see docs/RACE_PREDICTOR_V2_2_PLAN.md):

- Jackson, Blair, Mahar, Wier, Ross, Stuteville (1990). Prediction of
  Functional Aerobic Capacity Without Exercise Testing. Med Sci Sports Exerc.
  https://doi.org/10.1249/00005768-199012000-00021
- Tanaka, Monahan, Seals (2001). Age-Predicted Maximal Heart Rate Revisited.
  J Am Coll Cardiol. https://doi.org/10.1016/S0735-1097(00)01054-8
- Vernillo et al. (2017). Mechanics of running during a 100km trail race.
  Eur J Sport Sci.
- Pinheiro 2010 (energy cost on natural terrain).
- Genitrini 2022; Suter 2020 (ultra trail pacing, durability decay).
- Vihma 2010 (PMID 19774401). Effects of weather on marathon performance.
- Ely et al. (2007), PMID 17473775. Impact of Weather on Marathon-Running
  Performance.
- Daniels & Gilbert (1979). Daniels Running Formula. (vVO2max economy)
"""
from __future__ import annotations

from typing import Any

# Standard normal quantile used to derive p10/p90 from mean/std for a
# Gaussian-shaped prior. Phi^-1(0.9) ~= 1.2816.
_Z_P90 = 1.2816

# Activity-level mapping for Jackson 1990 NEPA equation.
# Reference: Jackson et al. 1990 used a 0-7 self-reported PAR score
# (NASA / Johnson Space Center physical activity questionnaire).
_PAR_BY_ACTIVITY_LEVEL: dict[str, float] = {
    "sedentary": 0.0,
    "light": 2.0,
    "moderate": 4.0,
    "active": 5.0,
    "very_active": 7.0,
}

# Bounds applied to PAR if a caller passes an unexpected string.
_DEFAULT_PAR = 4.0  # "moderate" equivalent, used when input is None or unknown.
_DEFAULT_BMI = 22.0  # Median healthy BMI used when height/weight are missing.

# Experience-level multipliers for flat capacity (literature consensus: elite
# road runners reach vVO2max well above generic equation; beginners run below
# their theoretical vVO2max).
_EXPERIENCE_FLAT_CAPACITY_MULTIPLIER: dict[str, float] = {
    "elite": 1.08,
    "competitor": 1.03,
    "regular": 1.00,
    "beginner": 0.95,
}


def _normal_dict(
    mean: float,
    std: float,
    sources: list[str],
    evidence_strength: str,
    notes: str,
) -> dict[str, Any]:
    """Build the standard prior dict with consistent p10/p90 from mean/std.

    The output dict is identical in shape across all public functions. p10
    and p90 use the standard normal quantile so they remain consistent with a
    Gaussian interpretation of the prior.
    """
    std = max(float(std), 1e-6)
    return {
        "mean": float(mean),
        "std": float(std),
        "p10": float(mean - _Z_P90 * std),
        "p90": float(mean + _Z_P90 * std),
        "sources": list(sources),
        "evidence_strength": evidence_strength,
        "notes": notes,
    }


def _safe_bmi(weight_kg: float | None, height_cm: float | None) -> float:
    """Return BMI from weight (kg) and height (cm), or median BMI if unknown."""
    if not weight_kg or not height_cm or height_cm <= 0:
        return _DEFAULT_BMI
    height_m = float(height_cm) / 100.0
    bmi = float(weight_kg) / (height_m * height_m)
    # Clamp to a physiological window to avoid runaway values.
    return max(15.0, min(45.0, bmi))


def _par_from_activity_level(activity_level: str | None) -> float:
    """Map a verbal activity level to the Jackson 1990 PAR score (0-7)."""
    if activity_level is None:
        return _DEFAULT_PAR
    key = str(activity_level).strip().lower()
    if key in _PAR_BY_ACTIVITY_LEVEL:
        return _PAR_BY_ACTIVITY_LEVEL[key]
    return _DEFAULT_PAR


def _normalize_sex(sex: str | None) -> str | None:
    """Return 'male', 'female', or None."""
    if sex is None:
        return None
    value = str(sex).strip().lower()
    if value in ("male", "m", "homme", "h"):
        return "male"
    if value in ("female", "f", "femme"):
        return "female"
    return None


def _jackson_bmi_vo2max(
    par: float,
    age: float,
    bmi: float,
    gender_flag: int,
) -> float:
    """Canonical BMI variant of Jackson 1990 NEPA equation (CDC NYFS form).

    Reference equation (estimand: VO2max in mL O2/(kg.min))::

        VO2max = 56.363
                 + 1.921 * (PA-R)
                 - 0.381 * age_years
                 - 0.754 * BMI
                 + 10.987 * gender

    with ``gender = 1`` for male and ``gender = 0`` for female. The female
    branch uses the **same** coefficients with ``gender = 0`` (so the only
    sex-specific term is the +10.987 offset). No ad-hoc replacement of the
    PA-R / age / BMI coefficients is applied.

    Sources
    -------
    - CDC National Youth Fitness Survey Treadmill Examination Manual,
      Appendix F (BMI variant, source primary used for the frozen numerical
      tests).
    - Jackson AS, Blair SN, Mahar MT, Wier LT, Ross RM, Stuteville JE.
      Prediction of Functional Aerobic Capacity Without Exercise Testing.
      Med Sci Sports Exerc 1990. DOI 10.1249/00005768-199012000-00021.

    Parameters
    ----------
    par
        Self-reported Physical Activity Rating (PA-R), expected in [0, 7].
    age
        Age in years (the canonical study covers roughly 18-65).
    bmi
        Body Mass Index in kg/m^2.
    gender_flag
        ``1`` for male, ``0`` for female. Any other value raises ``ValueError``
        to make accidental misuses explicit.
    """
    if gender_flag not in (0, 1):
        raise ValueError(
            f"gender_flag must be 0 (female) or 1 (male), got {gender_flag!r}"
        )
    return (
        56.363
        + 1.921 * float(par)
        - 0.381 * float(age)
        - 0.754 * float(bmi)
        + 10.987 * float(gender_flag)
    )


def estimate_vo2max_prior(
    sex: str | None,
    age_years: float | None,
    weight_kg: float | None,
    height_cm: float | None,
    activity_level: str | None,
) -> dict[str, Any]:
    """Estimate VO2max (mL/kg/min) from demographics using Jackson 1990 (BMI form).

    Estimand
    --------
    The returned ``mean`` estimates the population-conditional expectation of
    VO2max for an adult with the given demographics and self-reported activity
    rating, in mL O2 per kilogram of body weight per minute.

    Equation (canonical, both sexes share the same coefficients)::

        VO2max = 56.363 + 1.921 * PA-R - 0.381 * age - 0.754 * BMI
                 + 10.987 * gender

    with ``gender = 1`` for male and ``gender = 0`` for female. The female
    branch therefore differs from the male branch by exactly ``-10.987``
    mL/kg/min, not by a different set of coefficients. The implementation
    delegates to :func:`_jackson_bmi_vo2max` so the formula is asserted by the
    frozen numerical tests in ``tests/test_prior_service.py``.

    When inputs are missing the result widens:

    - all inputs None -> very wide prior (mean 35, std 15)
    - sex+age only    -> uses median BMI (22) and PA-R=4 (moderate)
    - full inputs     -> Jackson SEE ~= 5 mL/kg/min

    Sources
    -------
    - CDC National Youth Fitness Survey Treadmill Examination Manual,
      Appendix F (BMI variant, source primary used for the frozen tests).
    - Jackson AS, Blair SN, Mahar MT, Wier LT, Ross RM, Stuteville JE.
      Prediction of Functional Aerobic Capacity Without Exercise Testing.
      Med Sci Sports Exerc 1990. DOI 10.1249/00005768-199012000-00021.
    """
    sources = [
        "Jackson AS, Blair SN, Mahar MT, Wier LT, Ross RM, Stuteville JE. "
        "Prediction of Functional Aerobic Capacity Without Exercise Testing. "
        "Med Sci Sports Exerc 1990. DOI 10.1249/00005768-199012000-00021",
        "CDC National Youth Fitness Survey - Treadmill Examination Manual, "
        "Appendix F (BMI variant of Jackson 1990 NEPA equation).",
    ]

    normalized_sex = _normalize_sex(sex)

    # Case 1: no demographic inputs at all -> very wide prior centered on
    # general adult population median (~35 mL/kg/min for unconditioned adults).
    if (
        normalized_sex is None
        and age_years is None
        and weight_kg is None
        and height_cm is None
        and activity_level is None
    ):
        return _normal_dict(
            mean=35.0,
            std=15.0,
            sources=sources,
            evidence_strength="minimal",
            notes=(
                "No demographic input provided. Prior centered on general "
                "adult population with very wide variance."
            ),
        )

    # Count how many specific inputs are present to refine variance later.
    provided_specific = sum(
        1
        for value in (age_years, weight_kg, height_cm, activity_level)
        if value is not None
    )

    age = float(age_years) if age_years is not None else 35.0
    bmi = _safe_bmi(weight_kg, height_cm)
    par = _par_from_activity_level(activity_level)

    # Canonical Jackson 1990 BMI form (CDC NYFS Appendix F). Both sexes use
    # the SAME coefficients; only the +10.987 gender offset differs.
    # The female branch was previously implemented with ad-hoc PA-R / age /
    # BMI coefficients (50.513 + 1.589*PAR - 0.289*age - 0.552*BMI); this is
    # NOT the canonical BMI variant and is removed here. See R0 in
    # docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md.
    if normalized_sex == "male":
        mean = _jackson_bmi_vo2max(par=par, age=age, bmi=bmi, gender_flag=1)
    elif normalized_sex == "female":
        mean = _jackson_bmi_vo2max(par=par, age=age, bmi=bmi, gender_flag=0)
    else:
        # Sex unspecified -> use the canonical equation with a neutral mid
        # offset (half of +10.987). Variance is widened below to reflect the
        # extra uncertainty introduced by the unknown sex.
        mean = _jackson_bmi_vo2max(par=par, age=age, bmi=bmi, gender_flag=0) + 5.0

    # Clamp to a physiologically meaningful window to avoid implausible priors
    # for extreme combinations (very old + very high BMI).
    mean = max(15.0, min(85.0, mean))

    # Variance schedule:
    # - Jackson reports SEE ~= 5 mL/kg/min when all inputs are valid.
    # - Each missing input widens the prior.
    # - Unknown sex adds a meaningful extra spread.
    base_std = 5.5
    missing_inputs = 4 - provided_specific  # 0-4 missing among the 4 details
    std = base_std + 1.5 * missing_inputs
    if normalized_sex is None:
        std += 2.5

    has_activity = activity_level is not None
    has_demographics = (
        age_years is not None or weight_kg is not None or height_cm is not None
    )

    if has_activity and has_demographics:
        evidence_strength = "demographic_with_activity"
    elif has_demographics or has_activity or normalized_sex is not None:
        evidence_strength = "demographic_only"
    else:
        # Should not happen given the early-return above.
        evidence_strength = "minimal"

    notes_parts = [
        f"Jackson 1990 NEPA equation (sex={normalized_sex or 'unknown'}, "
        f"age={age:.0f}, BMI={bmi:.1f}, PAR={par:.1f})."
    ]
    if missing_inputs:
        notes_parts.append(
            f"{missing_inputs} demographic input(s) imputed with defaults; "
            "std widened accordingly."
        )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=" ".join(notes_parts),
    )


def estimate_flat_capacity_prior(
    vo2max_prior_dict: dict[str, Any] | None,
    experience_level: str | None,
) -> dict[str, Any]:
    """Estimate flat road running capacity at vVO2max (m/s).

    The conversion uses running economy ~= 210 mL O2/kg/km (Foster &
    Daniels), which gives vVO2max (m/s) ~= VO2max / 12.

    Experience modulates the conversion factor:
    - elite athletes run closer to or slightly above their theoretical
      vVO2max in a short race (+8%);
    - beginners are typically 5% below;
    - regular runners sit at the equation baseline.

    Variance is propagated from the VO2max prior plus an experience-related
    uncertainty term. Sources: Daniels-Gilbert tables; Foster economy of
    running.
    """
    sources = [
        "Daniels J, Gilbert J. Daniels Running Formula. Oxygen Power: Performance "
        "Tables for Distance Runners (1979).",
        "Foster C, Lucia A. Running economy: the forgotten factor in elite "
        "performance. Sports Med 2007.",
    ]

    # Defensive: accept None or partial dicts to stay pure.
    if not isinstance(vo2max_prior_dict, dict):
        vo2max_mean = 35.0
        vo2max_std = 15.0
        upstream_strength = "minimal"
    else:
        vo2max_mean = float(vo2max_prior_dict.get("mean", 35.0))
        vo2max_std = float(vo2max_prior_dict.get("std", 15.0))
        upstream_strength = str(vo2max_prior_dict.get("evidence_strength", "minimal"))

    # Base conversion VO2max -> vVO2max in m/s.
    base_speed = vo2max_mean / 12.0
    base_std_speed = vo2max_std / 12.0

    experience_key = (
        str(experience_level).strip().lower()
        if experience_level is not None
        else None
    )
    multiplier = _EXPERIENCE_FLAT_CAPACITY_MULTIPLIER.get(experience_key, 1.0)
    mean = base_speed * multiplier

    # Experience adds a small extra std (mismatch between declared level and
    # measured ability). Unknown experience adds slightly more.
    experience_extra_std = 0.05 * base_speed if experience_key is None else 0.03 * base_speed
    std = (base_std_speed ** 2 + experience_extra_std ** 2) ** 0.5

    # Floor mean to a physically plausible value (no negative speeds).
    mean = max(1.5, mean)

    if experience_key is not None and upstream_strength != "minimal":
        evidence_strength = "demographic_with_activity"
    elif upstream_strength != "minimal" or experience_key is not None:
        evidence_strength = "demographic_only"
    else:
        evidence_strength = "minimal"

    notes = (
        f"vVO2max derived as VO2max/12 (m/s) with experience multiplier "
        f"{multiplier:.2f} (level={experience_key or 'unknown'})."
    )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=notes,
    )


def estimate_fcmax_prior(
    age_years: float | None,
    sex: str | None,
) -> dict[str, Any]:
    """Estimate maximal heart rate (bpm) from age using Tanaka et al. 2001.

    Tanaka equation: FCmax = 208 - 0.7 * age. Reported SEE ~= 7 bpm but
    individual scatter is closer to 10-12 bpm, which is the std used here.

    If age is None, returns a wide prior (mean 180, std 20) consistent with
    the spread observed across adult runners.
    """
    sources = [
        "Tanaka H, Monahan KD, Seals DR. Age-predicted maximal heart rate "
        "revisited. J Am Coll Cardiol 2001. "
        "DOI 10.1016/S0735-1097(00)01054-8",
    ]

    if age_years is None:
        return _normal_dict(
            mean=180.0,
            std=20.0,
            sources=sources,
            evidence_strength="minimal",
            notes="No age provided. Wide adult prior used.",
        )

    age = float(age_years)
    mean = 208.0 - 0.7 * age
    # Bound between physiologically reasonable values.
    mean = max(110.0, min(220.0, mean))

    # Individual variance around Tanaka is ~10-12 bpm.
    std = 11.0

    # Slightly widen if sex is unknown (small effect; sex is not in Tanaka).
    if _normalize_sex(sex) is None:
        std += 1.0

    evidence_strength = "demographic_only"
    notes = (
        f"Tanaka 2001 equation (208 - 0.7 * age) applied at age={age:.0f}. "
        "Individual scatter ~11 bpm."
    )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=notes,
    )


def estimate_walk_threshold_prior(
    experience_level: str | None,
    practice_dominant: str | None,
) -> dict[str, Any]:
    """Estimate the run-to-walk gradient threshold (fraction of slope).

    A threshold of 0.22 means the athlete typically transitions from running
    to walking at ~22% grade. Trail-experienced athletes hold a higher
    threshold (they keep running on steeper terrain) because they have
    practiced uphill running.

    Inputs None -> 0.22 +/- 0.08 (wide).
    """
    sources = [
        "Minetti AE, Moia C, Roi GS, Susta D, Ferretti G. Energy cost of "
        "walking and running at extreme uphill and downhill slopes. "
        "J Appl Physiol 2002. PMID 12183501",
        "Genitrini M et al. Pacing and gait strategy in ultra-trail running, 2022.",
    ]

    # Lookup table: trail-dominant base values per experience level.
    trail_table = {
        "elite": (0.28, 0.05),
        "competitor": (0.25, 0.05),
        "regular": (0.22, 0.06),
        "beginner": (0.18, 0.08),
    }

    experience_key = (
        str(experience_level).strip().lower()
        if experience_level is not None
        else None
    )
    practice_key = (
        str(practice_dominant).strip().lower()
        if practice_dominant is not None
        else None
    )

    # Default for the "all None" case.
    if experience_key is None and practice_key is None:
        return _normal_dict(
            mean=0.22,
            std=0.08,
            sources=sources,
            evidence_strength="minimal",
            notes="Unknown experience and practice. Median runner used.",
        )

    base_mean, base_std = trail_table.get(experience_key, (0.22, 0.06))

    if practice_key == "road":
        # Road-dominant runners are less practiced at steep uphill running.
        mean = base_mean - 0.03
        std = base_std + 0.01
    elif practice_key == "mixed":
        mean = base_mean - 0.015
        std = base_std + 0.005
    elif practice_key == "trail":
        mean = base_mean
        std = base_std
    else:
        # Practice unknown -> mid value, widen std.
        mean = base_mean - 0.015
        std = base_std + 0.01

    # Clamp to physically plausible range (5% to 45%).
    mean = max(0.05, min(0.45, mean))

    if experience_key is not None and practice_key is not None:
        evidence_strength = "demographic_with_activity"
    else:
        evidence_strength = "demographic_only"

    notes = (
        f"Walk threshold for experience={experience_key or 'unknown'}, "
        f"practice={practice_key or 'unknown'}."
    )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=notes,
    )


def estimate_durability_alpha_prior(
    experience_level: str | None,
    practice_dominant: str | None,
    weekly_volume_band: str | None,
) -> dict[str, Any]:
    """Estimate durability alpha (capacity decay sensitivity with duration).

    Lower alpha means better durability (less fatigue per unit of time).
    Trail-trained, high-volume elites resist long efforts much better than
    beginners with low weekly volume.

    Inputs None -> 0.13 +/- 0.07 (wide, regular-runner median).
    """
    sources = [
        "Genitrini M et al. Pacing and gait strategy in ultra-trail running, 2022.",
        "Suter D et al. Performance trends in ultra-marathon running, 2020.",
    ]

    experience_key = (
        str(experience_level).strip().lower()
        if experience_level is not None
        else None
    )
    practice_key = (
        str(practice_dominant).strip().lower()
        if practice_dominant is not None
        else None
    )
    volume_key = (
        str(weekly_volume_band).strip().lower()
        if weekly_volume_band is not None
        else None
    )

    # If everything is None, return a wide regular-runner prior.
    if experience_key is None and practice_key is None and volume_key is None:
        return _normal_dict(
            mean=0.13,
            std=0.07,
            sources=sources,
            evidence_strength="minimal",
            notes="No experience/practice/volume inputs. Median runner used.",
        )

    # Base table by experience level.
    base_table = {
        "elite": (0.08, 0.03),
        "competitor": (0.10, 0.04),
        "regular": (0.13, 0.05),
        "beginner": (0.18, 0.08),
    }
    base_mean, base_std = base_table.get(experience_key, (0.13, 0.06))

    # Volume effect: high volume reduces alpha (better durability).
    volume_adjust = 0.0
    if volume_key in ("high", "very_high"):
        volume_adjust = -0.01
    elif volume_key in ("moderate",):
        volume_adjust = 0.0
    elif volume_key in ("low", "very_low"):
        volume_adjust = +0.02

    # Practice effect: trail runners have better long-effort durability when
    # the event itself is trail (the target use case for this prior).
    practice_adjust = 0.0
    if practice_key == "trail":
        practice_adjust = -0.005
    elif practice_key == "road":
        practice_adjust = +0.005
    # mixed -> no adjust

    mean = base_mean + volume_adjust + practice_adjust
    # Floor to a strictly positive value; alpha=0 would mean perfect durability.
    mean = max(0.03, mean)

    std = base_std
    # Widen variance for missing inputs.
    if volume_key is None:
        std += 0.01
    if practice_key is None:
        std += 0.005

    provided = sum(1 for v in (experience_key, practice_key, volume_key) if v is not None)
    evidence_strength = (
        "demographic_with_activity" if provided >= 2 else "demographic_only"
    )

    notes = (
        f"Durability alpha by experience={experience_key or 'unknown'}, "
        f"practice={practice_key or 'unknown'}, "
        f"volume={volume_key or 'unknown'}."
    )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=notes,
    )


def estimate_trail_cost_factor_prior(
    experience_level: str | None,
    practice_dominant: str | None,
) -> dict[str, Any]:
    """Estimate the trail surface factor multiplier (vs flat road Minetti).

    Trail running adds an energy cost beyond pure slope effect: technicity,
    surface compliance, attention/balance cost. Literature places this
    multiplier in 1.10-1.30 range. Athletes who train on trail incur a
    smaller penalty than road-dominant athletes.

    Inputs None -> 1.20 +/- 0.10 (mid literature value).
    """
    sources = [
        "Vernillo G et al. Mechanics of running during a 100km trail race. "
        "Eur J Sport Sci 2017.",
        "Pinheiro V et al. Energy cost of walking and running on natural terrain, 2010.",
    ]

    experience_key = (
        str(experience_level).strip().lower()
        if experience_level is not None
        else None
    )
    practice_key = (
        str(practice_dominant).strip().lower()
        if practice_dominant is not None
        else None
    )

    if experience_key is None and practice_key is None:
        return _normal_dict(
            mean=1.20,
            std=0.10,
            sources=sources,
            evidence_strength="minimal",
            notes="No experience/practice inputs. Literature midpoint used.",
        )

    skilled_levels = ("elite", "competitor")

    if practice_key == "trail":
        if experience_key in skilled_levels:
            mean, std = 1.15, 0.06
        else:
            mean, std = 1.18, 0.08
    elif practice_key == "mixed":
        mean, std = 1.20, 0.10
    elif practice_key == "road":
        mean, std = 1.25, 0.12
    else:
        # Practice unknown -> mid literature value, widen for skilled vs not.
        if experience_key in skilled_levels:
            mean, std = 1.18, 0.10
        else:
            mean, std = 1.22, 0.12

    # Clamp to literature plausibility range.
    mean = max(1.05, min(1.35, mean))

    if experience_key is not None and practice_key is not None:
        evidence_strength = "demographic_with_activity"
    else:
        evidence_strength = "demographic_only"

    notes = (
        f"Trail cost factor for experience={experience_key or 'unknown'}, "
        f"practice={practice_key or 'unknown'} (literature 1.10-1.30)."
    )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=notes,
    )


def estimate_heat_penalty_prior(
    experience_level: str | None,
    weekly_volume_band: str | None,
) -> dict[str, Any]:
    """Estimate heat sensitivity (% performance drop per deg C above ~11 C).

    Vihma 2010 found marathon performance degrades roughly linearly between
    ~11 C optimum and the high-stress regime, in a range of about 0.3-1.2
    %/deg C across populations. Fitter, higher-volume runners are less
    sensitive (better thermoregulation, lower relative intensity at any
    absolute pace).

    Inputs None -> 0.8 +/- 0.4 (population average).
    """
    sources = [
        "Vihma T. Effects of weather on the performance of marathon runners. "
        "Int J Biometeorol 2010. PMID 19774401",
        "Ely MR, Cheuvront SN, Roberts WO, Montain SJ. Impact of Weather on "
        "Marathon-Running Performance. Med Sci Sports Exerc 2007. PMID 17473775",
    ]

    experience_key = (
        str(experience_level).strip().lower()
        if experience_level is not None
        else None
    )
    volume_key = (
        str(weekly_volume_band).strip().lower()
        if weekly_volume_band is not None
        else None
    )

    if experience_key is None and volume_key is None:
        return _normal_dict(
            mean=0.8,
            std=0.4,
            sources=sources,
            evidence_strength="minimal",
            notes="No experience/volume inputs. Literature population average used.",
        )

    # Base by experience level.
    base_table = {
        "elite": (0.4, 0.20),
        "competitor": (0.6, 0.25),
        "regular": (0.8, 0.30),
        "beginner": (1.0, 0.40),
    }
    base_mean, base_std = base_table.get(experience_key, (0.85, 0.35))

    # Volume modulation: higher chronic volume reduces sensitivity.
    volume_adjust = 0.0
    if volume_key in ("high", "very_high"):
        volume_adjust = -0.10
    elif volume_key in ("moderate",):
        volume_adjust = 0.0
    elif volume_key in ("low", "very_low"):
        volume_adjust = +0.15

    mean = base_mean + volume_adjust
    # Clamp to literature range.
    mean = max(0.2, min(1.4, mean))

    std = base_std
    if volume_key is None:
        std += 0.05
    if experience_key is None:
        std += 0.05

    provided = sum(1 for v in (experience_key, volume_key) if v is not None)
    evidence_strength = (
        "demographic_with_activity" if provided >= 2 else "demographic_only"
    )

    notes = (
        f"Heat sensitivity (% per deg C above 11 C optimum) for "
        f"experience={experience_key or 'unknown'}, volume={volume_key or 'unknown'}."
    )

    return _normal_dict(
        mean=mean,
        std=std,
        sources=sources,
        evidence_strength=evidence_strength,
        notes=notes,
    )
