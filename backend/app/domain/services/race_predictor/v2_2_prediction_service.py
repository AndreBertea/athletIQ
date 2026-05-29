"""Race Predictor V2.2 orchestrator (`v2_2_bayesian`).

End-to-end pipeline that assembles every module produced in the previous
waves:

profil athlete (optional)  --(prior_service)-->  prior distributions
       |
       v
historique + tests de reference  --(observation_aggregator)-->  weighted obs
       |
       v
prior + obs  --(robust_updater.compute_posterior)-->  posterior distributions
       |
       v
capacite + duree initiale  --(event_intensity_service.iterate_event_power)
       |                       (with a fast in-orchestrator duration callback)
       v
P_event_wkg + sustainable_fraction --(physics_engine.predict_segments)
       |                              (full Minetti + altitude + weather + fatigue)
       v
predicted segments + ravitos + Monte Carlo uncertainty + full debug trace

Critical contracts honoured by this module
------------------------------------------
- The V2 physics engine, environment service, ravito service, fatigue model,
  GPX analyzer and uncertainty service are reused **unchanged**.
- ``as_of_date`` is a strict upper bound on every piece of evidence
  (activities + reference tests). The aggregator already enforces this; the
  orchestrator simply propagates the parameter without weakening it.
- Engine version is ``v2_2_bayesian`` everywhere in the response and the
  saveable trace, distinct from ``v1_random_forest`` / ``v2_physics``.
- ``excluded_activity_ids`` removes the target activity from any backtest
  replay (no self-comparison).
- The orchestrator never silently swallows a missing profile or empty
  evidence: it returns the prior unchanged when no observation exists, and
  surfaces a ``recommended_next_evidence`` plan ordered by expected interval
  reduction.

Two callbacks live in this file:

- ``_fast_duration_estimator``: a cheap closed-form duration estimate used by
  ``iterate_event_power`` so the convergence loop does **not** trigger a full
  physics-engine run at every iteration. The complete physics engine is only
  invoked once, on the converged ``p_event_wkg``.
- ``_format_minutes`` / ``_format_pause``: copies of the small helpers used by
  the V2 router to keep the response shape identical.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.athletic_profile import AthleticProfile
from app.domain.services.race_predictor.environment_service import (
    build_environment,
    summarize_weather_exposure,
)
from app.domain.services.race_predictor.event_intensity_service import (
    iterate_event_power,
    sustainable_fraction,
)
from app.domain.services.race_predictor.gpx_analyzer import analyze_gpx
from app.domain.services.race_predictor.observation_aggregator import (
    aggregate_observations,
)
from app.domain.services.race_predictor.physics_engine import (
    minetti_run_cost,
    predict_segments,
)
from app.domain.services.race_predictor.prior_service import (
    estimate_durability_alpha_prior,
    estimate_fcmax_prior,
    estimate_flat_capacity_prior,
    estimate_heat_penalty_prior,
    estimate_trail_cost_factor_prior,
    estimate_vo2max_prior,
    estimate_walk_threshold_prior,
)
from app.domain.services.race_predictor.ravito_service import (
    apply_pauses_to_segments,
    auto_ravitos,
    manual_ravitos,
    ravito_config_from_points,
)
from app.domain.services.race_predictor.robust_updater import (
    compute_posterior,
    summarize_evidence,
)
from app.domain.services.race_predictor.uncertainty_service import (
    monte_carlo_uncertainty,
)

logger = logging.getLogger(__name__)

ENGINE_VERSION = "v2_2_bayesian"
MODEL_CONFIG_VERSION = "v2_2_mvp"

# Flat Minetti cost (J/(kg.m)) at grade=0. Hard-locked to the V2 physics
# engine value so the capacity->power conversion stays consistent with the
# downstream Minetti polynomial.
MINETTI_FLAT_COST_J_PER_KG_M: float = minetti_run_cost(0.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_minutes(minutes: float) -> str:
    """Render a positive duration in minutes as ``HhMM`` (matches V2 router)."""
    if minutes is None or not math.isfinite(minutes) or minutes < 0:
        return "0h00"
    return f"{int(minutes // 60)}h{int(minutes % 60):02d}"


def _format_pause(minutes: float) -> str:
    """Pause format: ``Xmin`` or ``X.Ymin`` (matches V2 router)."""
    if minutes <= 0:
        return "0min"
    if float(minutes).is_integer():
        return f"{int(minutes)}min"
    return f"{minutes:.1f}min"


def _compute_age_years(birth_date: Optional[date], as_of: datetime) -> Optional[float]:
    """Return the athlete age (in years) at ``as_of``, or None when unknown."""
    if birth_date is None:
        return None
    try:
        ref_date = as_of.date() if isinstance(as_of, datetime) else as_of
        years = ref_date.year - birth_date.year
        # Adjust if the birthday has not been reached yet this year.
        if (ref_date.month, ref_date.day) < (birth_date.month, birth_date.day):
            years -= 1
        return float(max(0, years))
    except Exception:  # pragma: no cover - defensive
        return None


def _enum_value(enum_or_none: Any) -> Optional[str]:
    """Return the ``value`` attribute of an Enum, or the raw string, or None."""
    if enum_or_none is None:
        return None
    if hasattr(enum_or_none, "value"):
        return str(enum_or_none.value)
    return str(enum_or_none)


# R6 final: 3-key adapter validated (V2.3.1 ``p_ref_steady_wkg`` + ``p_capacity_test_wkg``,
# V2.3 legacy ``p_run_wkg``, V2.2 historique ``flat_capacity_mps``). Conserve par exigence
# du plan V2.3.1 R6 final pour garder V2.2 callable comme moteur de benchmark.
def _flat_capacity_observations_compat(
    observations: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Read V2.2 ``flat_capacity_mps`` observations with V2.3 retro-compatibility.

    Background
    ----------
    V2.2 historically consumed observations under the key ``flat_capacity_mps``
    (speed in m/s). The V2.3 refactor of :mod:`observation_aggregator` renamed
    the published key to ``p_run_wkg`` (power in W/kg) and changed the
    extraction formula to drop the Daniels-VDOT inversion that V2.2 relied on.

    To keep V2.2 callable (archived as a debug / comparison engine), this
    helper accepts both keys:

    - When the aggregator publishes ``flat_capacity_mps`` directly (legacy
      contract), the list is returned as-is.
    - When the aggregator only publishes ``p_run_wkg`` (V2.3 contract), every
      observation is converted to the V2.2 m/s contract via
      ``flat_capacity_mps = p_run_wkg / MINETTI_FLAT_COST_J_PER_KG_M`` (i.e.
      divide by ~3.6). Each converted observation keeps its category, weight,
      source metadata and quality flags, and is tagged with the
      ``v2_3_aggregator_converted`` flag so the debug trace can show the
      conversion happened.

    Caveat: the V2.3 aggregator no longer applies the Daniels-VDOT
    sustainable_fraction on historical activities. The converted V2.2 input is
    therefore a *direct* flat-speed observation; the V2.2 downstream pipeline
    still calls :func:`iterate_event_power` with the resulting capacity, which
    re-applies sustainable_fraction. This restores the V2.2 double-counting
    bias that V2.3 fixes; this is acceptable because V2.2 is now archive-only
    (see ``docs/RACE_PREDICTOR_V2_STATUS.md``).
    """
    if "flat_capacity_mps" in observations and observations["flat_capacity_mps"]:
        return list(observations["flat_capacity_mps"])

    # V2.3 contract (legacy intermediate): single fused "p_run_wkg" key.
    # V2.3.1 contract (R1): the canonical engine input is renamed to
    # "p_ref_steady_wkg" and a distinct "p_capacity_test_wkg" carries the
    # peak capacity from tests. V2.2 still benchmarks against the union
    # (historical + tests) of W/kg observations, so we concatenate both
    # sources when V2.3.1 is in effect.
    p_run_obs: list[dict[str, Any]] = []
    if observations.get("p_run_wkg"):
        p_run_obs.extend(observations["p_run_wkg"])
    if observations.get("p_ref_steady_wkg"):
        p_run_obs.extend(observations["p_ref_steady_wkg"])
    if observations.get("p_capacity_test_wkg"):
        # V2.2 used to treat tests as flat_capacity observations. Keep that
        # benchmark behaviour so the legacy engine has the same evidence
        # surface as before R1.
        p_run_obs.extend(observations["p_capacity_test_wkg"])
    if not p_run_obs:
        return []

    converted: list[dict[str, Any]] = []
    for obs in p_run_obs:
        try:
            mean_wkg = float(obs.get("mean"))
        except (TypeError, ValueError):
            continue
        try:
            std_wkg = float(obs.get("std") or 0.0)
        except (TypeError, ValueError):
            std_wkg = 0.0
        mean_mps = mean_wkg / MINETTI_FLAT_COST_J_PER_KG_M
        std_mps = std_wkg / MINETTI_FLAT_COST_J_PER_KG_M
        new_obs = dict(obs)
        new_obs["mean"] = mean_mps
        new_obs["std"] = std_mps
        flags = list(new_obs.get("quality_flags") or [])
        flags.append("v2_3_aggregator_converted")
        new_obs["quality_flags"] = flags
        converted.append(new_obs)
    return converted


def _summarise_observations(
    observations: dict[str, list[dict[str, Any]]],
    *,
    flat_capacity_obs: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Compact summary of the observation set used in the response.

    Counts observations per category across all parameters, plus the number of
    outliers flagged in each parameter posterior (filled later by the
    orchestrator since outliers come from the updater output).

    When ``flat_capacity_obs`` is provided, the canonical V2.2
    ``flat_capacity_mps`` count reflects the retro-compatible list returned by
    :func:`_flat_capacity_observations_compat` rather than the raw key in
    ``observations`` (which may be absent under the V2.3 aggregator contract).
    """
    by_category: dict[str, int] = {}
    by_parameter: dict[str, int] = {}
    total = 0
    # Iterate on a custom shape so we can override the flat_capacity list.
    keys = set(observations.keys())
    if flat_capacity_obs is not None:
        keys.add("flat_capacity_mps")
        # Skip the V2.3/V2.3.1 W/kg lists when we already converted them
        # into flat_capacity_obs.
        keys.discard("p_run_wkg")
        keys.discard("p_ref_steady_wkg")
        keys.discard("p_capacity_test_wkg")
    for param in keys:
        if param == "flat_capacity_mps" and flat_capacity_obs is not None:
            obs_list = flat_capacity_obs
        else:
            obs_list = observations.get(param, [])
        by_parameter[param] = len(obs_list)
        for obs in obs_list:
            total += 1
            cat = str(obs.get("category") or "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total_observations_count": total,
        "by_category": by_category,
        "by_parameter": by_parameter,
    }


def _build_recommendations(
    *,
    has_profile: bool,
    has_road_test_evidence: bool,
    has_trail_anchor_evidence: bool,
    has_long_evidence: bool,
) -> list[dict[str, Any]]:
    """Order the next pieces of evidence by expected interval reduction.

    The percentages encode the rule-of-thumb impact described in the V2.2
    plan: completing the profile narrows the prior modestly, while a clean
    road 10K is the single most impactful piece of evidence for
    ``flat_capacity_mps`` and therefore for the final P50 interval.
    """
    recommendations: list[dict[str, Any]] = []
    if not has_profile:
        recommendations.append(
            {
                "action": "complete_profile",
                "rationale": (
                    "Pas de profil athletique renseigne; le prior reste tres "
                    "large. Saisir sexe/age/poids/taille resserre la "
                    "distribution initiale."
                ),
                "expected_interval_reduction_pct": 25,
            }
        )
    if not has_road_test_evidence:
        recommendations.append(
            {
                "action": "submit_road_10k_test",
                "rationale": (
                    "Un 5/10 km route propre est l'unique observation a "
                    "fort poids sur la capacite plate; en ajouter un reduit "
                    "fortement l'intervalle de prediction."
                ),
                "expected_interval_reduction_pct": 30,
            }
        )
    if not has_trail_anchor_evidence:
        recommendations.append(
            {
                "action": "tag_recent_trail_race_as_official_clean",
                "rationale": (
                    "Qualifier une course trail recente en `official_clean` "
                    "alimente le facteur trail personnel et la durabilite."
                ),
                "expected_interval_reduction_pct": 15,
            }
        )
    if not has_long_evidence:
        recommendations.append(
            {
                "action": "log_long_steady_run",
                "rationale": (
                    "Une sortie continue de 75-120 min sans pause renseigne "
                    "la durabilite (alpha)."
                ),
                "expected_interval_reduction_pct": 10,
            }
        )
    return recommendations


def _fast_duration_estimator_factory(
    *,
    total_distance_m: float,
    avg_grade_fraction: float,
    avg_altitude_m: float,
    trail_cost_factor_mean: float,
    surface_factor_in_pipeline: float,
) -> Callable[[float], float]:
    """Build a cheap closed-form duration estimator for the fixed-point loop.

    The estimator translates ``P_event_wkg`` into a duration through:

        speed_mps = P_event / (Minetti(grade) * surface * altitude_factor)
        duration_min = total_distance / speed / 60

    ``iterate_event_power`` only needs the **order of magnitude** of the
    duration to converge; the full physics engine is then called once on the
    converged ``P_event``. This avoids running the segment-by-segment Minetti
    + weather + fatigue pipeline inside the convergence loop.
    """
    safe_distance = max(1.0, float(total_distance_m))
    safe_grade = max(-0.45, min(0.45, float(avg_grade_fraction)))
    safe_altitude_factor = 1.0 + 0.06 * max(0.0, (float(avg_altitude_m) - 1500.0) / 1000.0)
    # ``trail_cost_factor_mean`` is the multiplicative penalty above Minetti.
    # ``surface_factor_in_pipeline`` is the factor the physics engine will
    # apply (1.0 on road, trail_cost_factor_mean on trail). Use whichever the
    # pipeline will actually use so the orchestrator and the engine agree.
    safe_surface = max(0.5, min(2.0, float(surface_factor_in_pipeline)))
    cost_flat_at_grade = minetti_run_cost(safe_grade)

    def predict(p_event_wkg: float) -> float:
        # Defensive: iterate_event_power guarantees a positive input, but the
        # callback contract still requires us to refuse 0 or non-finite values.
        if p_event_wkg is None or not math.isfinite(p_event_wkg) or p_event_wkg <= 0:
            return 1.0
        speed_mps = p_event_wkg / (cost_flat_at_grade * safe_surface * safe_altitude_factor)
        # Clip to a physiologically possible speed range to avoid the
        # iteration drifting into nonsensical territory under tiny P_event.
        speed_mps = max(0.35, min(8.0, speed_mps))
        duration_min = (safe_distance / speed_mps) / 60.0
        # Avoid returning zero/negative durations (would break the next
        # sustainable_fraction call).
        return max(1.0, duration_min)

    return predict


def _resolve_analysis_mode(requested: Optional[str], elevation_per_km: float) -> str:
    """Resolve ``auto`` to either ``trail`` or ``route``."""
    normalized = (requested or "auto").strip().lower()
    if normalized == "trail":
        return "trail"
    if normalized in {"route", "road", "run"}:
        return "route"
    # auto: trail when D+/km >= 15 m (matches V2 router heuristic).
    return "trail" if elevation_per_km >= 15.0 else "route"


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def predict_v2_2(
    session: Session,
    user_id: UUID,
    gpx_text: str,
    *,
    race_datetime: Optional[datetime],
    effort_mode: str,
    analysis_mode: str,
    target_heartrate: Optional[float],
    weather_mode: str,
    manual_temperature_c: Optional[float],
    ravito_mode: str,
    custom_ravitos: Optional[list[dict[str, Any]]] = None,
    as_of_date: Optional[datetime] = None,
    excluded_activity_ids: Optional[Iterable[UUID]] = None,
    filename: Optional[str] = None,
) -> dict[str, Any]:
    """Run the full Race Predictor V2.2 Bayesian pipeline.

    Parameters
    ----------
    session
        SQLModel session used to read the optional ``AthleticProfile`` and the
        athlete's history.
    user_id
        Identifier of the athlete the prediction is computed for.
    gpx_text
        GPX file content (already decoded as UTF-8).
    race_datetime
        Optional event date/time used to fetch a temporal weather timeline.
    effort_mode
        One of ``steady``, ``endurance``, ``aggressive`` (forwarded to both
        :mod:`event_intensity_service` and :mod:`physics_engine`).
    analysis_mode
        ``auto``, ``trail`` or ``route``.
    target_heartrate
        Optional FC cible (kept for response symmetry with V2; not consumed by
        the V2.2 calibration anymore).
    weather_mode
        ``auto`` or ``manual``.
    manual_temperature_c
        Used when ``weather_mode == "manual"`` or as a fallback if Open-Meteo
        is unreachable.
    ravito_mode
        ``auto`` or ``manual``.
    custom_ravitos
        Aid stations list. In manual mode it is user-defined; in auto mode it
        can carry official known course ravitos and drive segment cuts in
        ``analyze_gpx``.
    as_of_date
        Strict upper bound on the historical evidence window. Defaults to
        ``datetime.utcnow()`` when omitted.
    excluded_activity_ids
        Activity IDs to drop from the aggregator (used in backtests so the
        target activity itself cannot vote on its own prediction).
    filename
        Optional original filename, copied into the response.

    Returns
    -------
    dict
        A fully shaped V2.2 prediction (see ``docs/RACE_PREDICTOR_V2_2_PLAN.md``
        section "API cible / Reponse").
    """
    warnings: list[str] = []

    # --- 1. GPX analysis --------------------------------------------------
    gpx_analysis = analyze_gpx(gpx_text, custom_ravitos=custom_ravitos)
    segments = gpx_analysis["segments"]
    global_stats = gpx_analysis["global_stats"]
    total_distance_km = float(global_stats.get("total_distance_km") or 0)
    total_distance_m = total_distance_km * 1000.0

    elevation_per_km = float(global_stats.get("elevation_per_km") or 0)
    resolved_analysis_mode = _resolve_analysis_mode(analysis_mode, elevation_per_km)
    if (analysis_mode or "auto").lower() == "auto":
        warnings.append(
            f"Mode auto resolu en {resolved_analysis_mode} via D+/km={elevation_per_km:.1f}."
        )

    # --- 2. Athletic profile ---------------------------------------------
    profile = session.exec(
        select(AthleticProfile).where(AthleticProfile.user_id == user_id)
    ).first()
    effective_as_of_date = as_of_date or datetime.utcnow()
    has_profile = profile is not None

    sex = _enum_value(profile.sex) if profile else None
    age_years = _compute_age_years(
        profile.birth_date if profile else None, effective_as_of_date
    )
    weight_kg = float(profile.weight_kg) if profile and profile.weight_kg else None
    height_cm = float(profile.height_cm) if profile and profile.height_cm else None
    activity_level = _enum_value(profile.activity_level) if profile else None
    experience_level = _enum_value(profile.experience_level) if profile else None
    practice_dominant = _enum_value(profile.practice_dominant) if profile else None
    weekly_volume_band = _enum_value(profile.weekly_volume_band) if profile else None

    if not has_profile:
        warnings.append(
            "Aucun profil athletique: le prior reste tres large. "
            "Completer le profil affine la distribution initiale."
        )

    # --- 3. Population priors --------------------------------------------
    vo2max_prior = estimate_vo2max_prior(
        sex=sex,
        age_years=age_years,
        weight_kg=weight_kg,
        height_cm=height_cm,
        activity_level=activity_level,
    )
    flat_capacity_prior = estimate_flat_capacity_prior(vo2max_prior, experience_level)
    fcmax_prior = estimate_fcmax_prior(age_years=age_years, sex=sex)
    walk_threshold_prior = estimate_walk_threshold_prior(
        experience_level=experience_level, practice_dominant=practice_dominant
    )
    durability_alpha_prior = estimate_durability_alpha_prior(
        experience_level=experience_level,
        practice_dominant=practice_dominant,
        weekly_volume_band=weekly_volume_band,
    )
    trail_cost_factor_prior = estimate_trail_cost_factor_prior(
        experience_level=experience_level, practice_dominant=practice_dominant
    )
    heat_penalty_prior = estimate_heat_penalty_prior(
        experience_level=experience_level, weekly_volume_band=weekly_volume_band
    )

    prior_snapshot: dict[str, Any] = {
        "vo2max_ml_kg_min": vo2max_prior,
        "flat_capacity_mps": flat_capacity_prior,
        "durability_alpha": durability_alpha_prior,
        "trail_cost_factor": trail_cost_factor_prior,
        "fc_max_bpm": fcmax_prior,
        "walk_threshold_grade_fraction": walk_threshold_prior,
        "heat_penalty_pct_per_degc": heat_penalty_prior,
    }

    # --- 4. Observations -------------------------------------------------
    excluded_set: set[UUID] = set(excluded_activity_ids or [])
    observations = aggregate_observations(
        session,
        user_id,
        as_of_date=effective_as_of_date,
        excluded_activity_ids=excluded_set,
    )
    # V2.3 / V2.3.1 retro-compatibility: observation_aggregator publishes
    # under ``p_ref_steady_wkg`` + ``p_capacity_test_wkg`` (V2.3.1, R1) or
    # ``p_run_wkg`` (V2.3) in W/kg. V2.2 still reasons in
    # ``flat_capacity_mps`` (m/s). The helper normalises every contract
    # into the V2.2-native shape; see
    # :func:`_flat_capacity_observations_compat`.
    flat_capacity_obs = _flat_capacity_observations_compat(observations)
    using_v2_3_aggregator = (
        bool(observations.get("p_ref_steady_wkg"))
        or bool(observations.get("p_run_wkg"))
        or bool(observations.get("p_capacity_test_wkg"))
    ) and not observations.get("flat_capacity_mps")
    if using_v2_3_aggregator:
        warnings.append(
            "Observations converties depuis observation_aggregator V2.3+ "
            "(W/kg -> flat_capacity_mps m/s). V2.2 reste appelable pour "
            "archive ; voir docs/RACE_PREDICTOR_V2_STATUS.md."
        )
    observations_summary = _summarise_observations(
        observations, flat_capacity_obs=flat_capacity_obs
    )

    has_road_test_evidence = any(
        ((obs.get("source_type") == "reference_test") and ("flat" in str(obs.get("source_label") or "")))
        or (obs.get("category") in {"performance_anchor", "reference_test"})
        for obs in flat_capacity_obs
    )
    has_trail_anchor_evidence = any(
        obs.get("category") == "trail_anchor"
        for obs in observations.get("trail_cost_factor", [])
    )
    has_long_evidence = bool(observations.get("durability_alpha"))

    # --- 5. Bayesian update ----------------------------------------------
    flat_capacity_posterior = compute_posterior(
        flat_capacity_prior, flat_capacity_obs
    )
    durability_alpha_posterior = compute_posterior(
        durability_alpha_prior, observations.get("durability_alpha", [])
    )
    trail_cost_factor_posterior = compute_posterior(
        trail_cost_factor_prior, observations.get("trail_cost_factor", [])
    )
    fcmax_posterior = compute_posterior(
        fcmax_prior, observations.get("fc_max_bpm", [])
    )

    posterior_snapshot: dict[str, Any] = {
        "flat_capacity_mps": flat_capacity_posterior,
        "durability_alpha": durability_alpha_posterior,
        "trail_cost_factor": trail_cost_factor_posterior,
        "fc_max_bpm": fcmax_posterior,
    }

    evidence_summary_breakdown: dict[str, Any] = {
        "flat_capacity_mps": summarize_evidence(
            flat_capacity_prior,
            flat_capacity_obs,
            flat_capacity_posterior,
        ),
        "durability_alpha": summarize_evidence(
            durability_alpha_prior,
            observations.get("durability_alpha", []),
            durability_alpha_posterior,
        ),
        "trail_cost_factor": summarize_evidence(
            trail_cost_factor_prior,
            observations.get("trail_cost_factor", []),
            trail_cost_factor_posterior,
        ),
        "fc_max_bpm": summarize_evidence(
            fcmax_prior,
            observations.get("fc_max_bpm", []),
            fcmax_posterior,
        ),
    }

    total_outliers_detected = sum(
        len(posterior_snapshot[param].get("outliers") or [])
        for param in posterior_snapshot
    )

    # --- 6. Capacity -> event power conversion ---------------------------
    flat_capacity_mean = max(0.5, float(flat_capacity_posterior["mean"]))  # m/s
    durability_alpha_mean = max(0.04, float(durability_alpha_posterior["mean"]))
    trail_cost_factor_mean = max(1.0, float(trail_cost_factor_posterior["mean"]))

    # Capacity in W/kg: P = cost (J/kg/m) * speed (m/s)
    p_capacity_wkg = MINETTI_FLAT_COST_J_PER_KG_M * flat_capacity_mean

    # Initial duration estimate: distance / capacity speed, padded for trail.
    initial_duration_min = (total_distance_m / max(0.5, flat_capacity_mean)) / 60.0
    if resolved_analysis_mode == "trail":
        initial_duration_min *= 1.2
    initial_duration_min = max(5.0, initial_duration_min)

    avg_grade_fraction = float(global_stats.get("avg_grade_percent") or 0) / 100.0
    avg_altitude_m = sum(
        float(seg.get("altitude_m") or 0) for seg in segments
    ) / max(1, len(segments))

    surface_factor_for_iter = (
        trail_cost_factor_mean if resolved_analysis_mode == "trail" else 1.0
    )
    duration_callback = _fast_duration_estimator_factory(
        total_distance_m=total_distance_m,
        avg_grade_fraction=avg_grade_fraction,
        avg_altitude_m=avg_altitude_m,
        trail_cost_factor_mean=trail_cost_factor_mean,
        surface_factor_in_pipeline=surface_factor_for_iter,
    )

    event_intensity_result = iterate_event_power(
        p_capacity_wkg=p_capacity_wkg,
        initial_duration_min=initial_duration_min,
        durability_alpha=durability_alpha_mean,
        predict_duration_callback=duration_callback,
        max_iterations=5,
        tolerance=0.02,
        effort_mode=effort_mode if effort_mode in {"steady", "endurance", "aggressive"} else "steady",
    )
    if not event_intensity_result["converged"]:
        warnings.append(
            "Convergence event_intensity non atteinte; valeur de la derniere "
            "iteration utilisee pour la prediction."
        )

    p_event_wkg = float(event_intensity_result["p_event_wkg"])
    sustainable_frac = float(event_intensity_result["sustainable_fraction"])

    # --- 7. Build calibration / fatigue / environment for physics engine -
    flat_capacity_std = max(1e-3, float(flat_capacity_posterior["std"]))
    relative_capacity_std = flat_capacity_std / max(flat_capacity_mean, 1e-3)
    # Confidence proxy used by the physics engine: 1 - relative std,
    # clamped to a usable [0.1, 0.95] window.
    confidence = max(0.10, min(0.95, 1.0 - relative_capacity_std))

    calibration = {
        "engine_version": ENGINE_VERSION,
        "p_run_wkg": round(p_event_wkg, 3),
        "p_capacity_wkg": round(p_capacity_wkg, 3),
        "p_walk_ratio": 0.75,
        "confidence": round(confidence, 3),
        "sustainable_fraction": round(sustainable_frac, 4),
        "flat_capacity_mean_mps": round(flat_capacity_mean, 3),
        "flat_capacity_std_mps": round(flat_capacity_std, 3),
        "calibration_quality": (
            "high" if flat_capacity_posterior["evidence_count"] >= 2 and total_outliers_detected == 0
            else "medium" if flat_capacity_posterior["evidence_count"] >= 1
            else "prior_only"
        ),
        "source": "v2_2_bayesian_posterior",
    }

    fatigue_profile = {
        "model": "v2_2_posterior_alpha",
        "alpha": round(durability_alpha_mean, 4),
        "alpha_std": round(float(durability_alpha_posterior["std"]), 4),
        "personalized": bool(durability_alpha_posterior["evidence_count"] > 0),
        "sample_count": int(durability_alpha_posterior["evidence_count"]),
        "history_start_date": None,
        "history_end_date": effective_as_of_date.isoformat(),
        "excluded_activity_count": len(excluded_set),
        "notes": [
            "Alpha derive du posterior bayesien V2.2 (capacite + observations).",
        ],
    }

    environment = build_environment(
        global_stats,
        race_datetime=race_datetime,
        weather_mode=weather_mode,
        manual_temperature_c=manual_temperature_c,
        p_run_wkg=p_event_wkg,
    )
    if environment.get("weather_source") in {"default", "auto_failed"}:
        warnings.append(
            "Meteo automatique indisponible: temperature neutre ou manuelle utilisee."
        )

    # --- 8. Physics engine (called once on the converged P_event) ---------
    trail_surface_factor = (
        trail_cost_factor_mean if resolved_analysis_mode == "trail" else None
    )
    physics_result = predict_segments(
        segments,
        calibration=calibration,
        environment=environment,
        fatigue_profile=fatigue_profile,
        trail_surface_factor=trail_surface_factor,
        analysis_mode=resolved_analysis_mode,
        effort_mode=effort_mode,
    )
    predicted_segments = physics_result["segments"]
    moving_time_min = float(physics_result["moving_time_min"])
    environment = summarize_weather_exposure(environment, moving_time_min)

    # --- 9. Ravitos -------------------------------------------------------
    normalized_ravito_mode = (ravito_mode or "auto").lower()
    if normalized_ravito_mode == "manual":
        ravito_points = manual_ravitos(
            predicted_segments,
            custom_ravitos,
            total_distance_km,
        )
    else:
        ravito_points = (
            manual_ravitos(
                predicted_segments,
                custom_ravitos,
                total_distance_km,
                source="auto_known",
            )
            if custom_ravitos
            else []
        )
        if not ravito_points:
            ravito_points = auto_ravitos(
                predicted_segments,
                global_stats,
                moving_time_min,
                analysis_mode=resolved_analysis_mode,
                temperature_c=float(
                    environment.get("temperature_max_c")
                    or environment.get("temperature_c")
                    or 11.0
                ),
            )
    total_pause_min = sum(float(r.get("pause_min") or 0) for r in ravito_points)
    total_time_min = moving_time_min + total_pause_min
    apply_pauses_to_segments(predicted_segments, ravito_points)
    saved_ravito_config = ravito_config_from_points(ravito_points)

    # --- 10. Monte Carlo uncertainty (with posterior-driven stds) ---------
    # Propagate posterior dispersion into the Monte Carlo standard deviations
    # so that a wider posterior -> wider P10/P90 envelope. We clamp each std
    # to a minimum so the uncertainty pipeline never silently flatlines, and
    # to a maximum so a single pathological posterior cannot blow up the
    # simulator.
    p_run_std = max(0.04, min(0.30, relative_capacity_std))
    fatigue_relative_std = max(
        0.0, float(durability_alpha_posterior["std"]) / max(1e-3, durability_alpha_mean)
    )
    fatigue_std = max(0.02, min(0.10, fatigue_relative_std * 0.35))
    surface_relative_std = max(
        0.0,
        float(trail_cost_factor_posterior["std"]) / max(1e-3, trail_cost_factor_mean),
    )
    surface_std = max(0.02, min(0.10, surface_relative_std))
    weather_std = 0.015 if environment.get("weather_source") == "manual" else 0.025

    uncertainty = monte_carlo_uncertainty(
        segments=predicted_segments,
        moving_time_min=moving_time_min,
        total_pause_min=total_pause_min,
        calibration=calibration,
        environment=environment,
        simulations=300,
        variation_stds={
            "p_run": p_run_std,
            "fatigue": fatigue_std,
            "weather": weather_std,
            "surface": surface_std,
        },
    )

    # --- 11. Final response ----------------------------------------------
    summary = {
        "total_distance_km": total_distance_km,
        "total_elevation_gain_m": global_stats["total_elevation_gain_m"],
        "total_elevation_loss_m": global_stats["total_elevation_loss_m"],
        "moving_time_min": round(moving_time_min, 1),
        "moving_time_formatted": _format_minutes(moving_time_min),
        "total_pause_min": round(total_pause_min, 1),
        "total_pause_formatted": _format_pause(round(total_pause_min, 1)),
        "total_time_min": round(total_time_min, 1),
        "total_time_formatted": _format_minutes(total_time_min),
        "p10_total_time_min": uncertainty["total_time"]["p10"],
        "p50_total_time_min": uncertainty["total_time"]["p50"],
        "p90_total_time_min": uncertainty["total_time"]["p90"],
        "avg_moving_pace": round(moving_time_min / total_distance_km, 2) if total_distance_km > 0 else 0,
        "avg_pace": round(total_time_min / total_distance_km, 2) if total_distance_km > 0 else 0,
    }

    evidence_summary = {
        **observations_summary,
        "outliers_detected": int(total_outliers_detected),
        "breakdown_by_parameter": {
            param: {
                "evidence_count": int(post["evidence_count"]),
                "prior_weight_pct": float(post.get("prior_weight_pct", 1.0)),
                "evidence_weight_pct": float(post.get("evidence_weight_pct", 0.0)),
                "outliers": post.get("outliers", []),
                "dispersion_factor": float(post.get("dispersion_factor", 0.0)),
            }
            for param, post in posterior_snapshot.items()
        },
    }

    recommendations = _build_recommendations(
        has_profile=has_profile,
        has_road_test_evidence=has_road_test_evidence,
        has_trail_anchor_evidence=has_trail_anchor_evidence,
        has_long_evidence=has_long_evidence,
    )

    athlete_model = {
        "prior": prior_snapshot,
        "posterior": posterior_snapshot,
        "evidence_summary": evidence_summary,
        "evidence_breakdown": evidence_summary_breakdown,
        "recommended_next_evidence": recommendations,
        "profile_present": has_profile,
    }

    event_intensity_block = {
        "capacity_wkg": round(p_capacity_wkg, 3),
        "sustainable_fraction": round(sustainable_frac, 4),
        "target_power_wkg": round(p_event_wkg, 3),
        "iterations": event_intensity_result["iterations"],
        "converged": bool(event_intensity_result["converged"]),
        "final_iteration": int(event_intensity_result["final_iteration"]),
        "duration_used_min": round(float(event_intensity_result["final_duration_min"]), 2),
        "alpha_used": round(durability_alpha_mean, 4),
        "effort_mode": effort_mode,
    }

    debug_trace = {
        "engine_version": ENGINE_VERSION,
        "model_config_version": MODEL_CONFIG_VERSION,
        "as_of_date": effective_as_of_date.isoformat(),
        "excluded_activity_ids": sorted(str(uid) for uid in excluded_set),
        "requested_analysis_mode": analysis_mode,
        "resolved_analysis_mode": resolved_analysis_mode,
        "effort_mode": effort_mode,
        "target_heartrate": target_heartrate,
        "prior_snapshot": prior_snapshot,
        "observations_summary": observations_summary,
        "posterior_snapshot": posterior_snapshot,
        "event_intensity_trace": event_intensity_result["iterations"],
        "uncertainty_trace": uncertainty.get("contributors", {}),
        "physics": physics_result["physics"],
        "calibration": calibration,
        "fatigue": fatigue_profile,
        "environment": environment,
        "warnings": list(warnings),
    }

    response = {
        "engine_version": ENGINE_VERSION,
        "filename": filename,
        "analysis_mode": resolved_analysis_mode,
        "requested_analysis_mode": analysis_mode,
        "effort_mode": effort_mode,
        "ravito_mode": normalized_ravito_mode,
        "race_datetime": race_datetime.isoformat() if race_datetime else None,
        "as_of_date": effective_as_of_date.isoformat(),
        "total_distance_km": total_distance_km,
        "total_elevation_gain_m": global_stats["total_elevation_gain_m"],
        "total_elevation_loss_m": global_stats["total_elevation_loss_m"],
        "net_elevation_m": global_stats["net_elevation_m"],
        "avg_grade_percent": global_stats["avg_grade_percent"],
        "moving_time_min": summary["moving_time_min"],
        "moving_time_formatted": summary["moving_time_formatted"],
        "total_pause_min": summary["total_pause_min"],
        "total_pause_formatted": summary["total_pause_formatted"],
        "total_time_min": summary["total_time_min"],
        "total_time_formatted": summary["total_time_formatted"],
        "avg_moving_pace": summary["avg_moving_pace"],
        "avg_pace": summary["avg_pace"],
        "summary": summary,
        "calibration": calibration,
        "environment": environment,
        "fatigue": fatigue_profile,
        "ravitos": {
            "mode": normalized_ravito_mode,
            "points": ravito_points,
            "total_pause_min": round(total_pause_min, 1),
        },
        "ravito_points": ravito_points,
        "custom_ravitos": custom_ravitos if normalized_ravito_mode == "manual" else [],
        "ravito_config": saved_ravito_config,
        "segments": predicted_segments,
        "elevation_points": gpx_analysis["elevation_points"],
        "uncertainty": uncertainty,
        "athlete_model": athlete_model,
        "event_intensity": event_intensity_block,
        "warnings": warnings,
        "debug_trace": debug_trace,
        "prediction_date": datetime.utcnow().isoformat(),
    }
    return response


__all__ = [
    "predict_v2_2",
    "ENGINE_VERSION",
    "MODEL_CONFIG_VERSION",
    "MINETTI_FLAT_COST_J_PER_KG_M",
]
