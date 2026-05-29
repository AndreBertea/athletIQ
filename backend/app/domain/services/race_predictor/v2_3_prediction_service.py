"""Race Predictor V2.3 orchestrator (``v2_3_bayesian``).

V2.3 = V2 (moteur physique + calibration directe historique) + V2.2 (couche
bayesienne : prior populationnel, robust_updater, Monte Carlo enrichi).

V2.3.1 (R1)
-----------
Le moteur consomme desormais ``p_ref_steady_wkg`` (puissance plate filtree
par bande FC etroite [0.72, 0.78] x FCmax) et expose un parametre latent
distinct ``p_capacity_test_wkg`` (capacite peak issue des tests 5/10 km) qui
n'est pas consomme par le moteur. Cf. ``docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md``
section R1.

Difference fondamentale vs V2.2
------------------------------
V2.2 utilisait ``iterate_event_power`` + ``sustainable_fraction`` (inversion
Daniels-VDOT) **a la fois** sur l'historique (pour deduire une capacite peak
a partir d'efforts sub-max) ET sur la prediction (pour redescendre vers une
P_event soutenable). Ce double comptage produisait des sur-estimations de
30-60% sur le golden set.

V2.3.1 calibre ``p_ref_steady_wkg`` DIRECTEMENT a partir de l'allure plate
observee dans l'historique a effort de reference defini (bande FC etroite).
La couche bayesienne fusionne un prior populationnel avec des observations
directes pour resserrer l'intervalle.

Pipeline (cf. ``docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md``) :

```
profile (optional) -> prior_service -> p_ref_steady_wkg prior (W/kg),
                                       fc_max, alpha, trail_factor, plus
                                       prior identique pour p_capacity_test_wkg
       |
       v
historique + tests de reference -> observation_aggregator (V2.3.1)
       -> dict {"p_ref_steady_wkg": [...], "p_capacity_test_wkg": [...], ...}
       |
       v
prior + obs -> robust_updater.compute_posterior -> posterior par parametre
       (incluant p_capacity_test_wkg avec consumed_by_engine=false)
       |
       v  PAS d'iteration capacity -> event_power
       v
physics_engine.predict_segments(p_run_wkg=p_ref_steady_posterior.mean,
                                trail_factor=..., alpha=...)
       |
       v
ravitos + Monte Carlo avec variation_stds depuis posteriors
       |
       v
reponse JSON V2.3.1
```

Retro-compatibilite legacy (R1)
-------------------------------
Si l'aggregator (tres ancienne version V1) retourne encore la cle
``p_run_wkg`` ou ``flat_capacity_mps`` sans publier ``p_ref_steady_wkg``,
:func:`_normalize_p_ref_steady_observations` les accepte et les convertit
(W/kg directement pour ``p_run_wkg``, multiplication par Minetti pour
``flat_capacity_mps``). Un warning est emis pour signaler la conversion.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.athletic_profile import AthleticProfile
from app.domain.services.race_predictor.environment_service import (
    build_environment,
    summarize_weather_exposure,
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
from app.domain.services.race_predictor.trail_history_factor_service import (
    build_user_trail_factor_observations,
)
from app.domain.services.race_predictor.uncertainty_service import (
    monte_carlo_uncertainty,
)

logger = logging.getLogger(__name__)

ENGINE_VERSION = "v2_3_1_bayesian"
#: Engine label of the V2.3 release (pre-V2.3.1 fixes). Kept exported for the
#: Analytics filter and migration scripts that still need to read predictions
#: saved with the legacy label without flattening them to the V1 default.
LEGACY_ENGINE_VERSION = "v2_3_bayesian"
MODEL_CONFIG_VERSION = "v2_3_mvp"

# Cout Minetti plat (J/(kg.m)) a pente 0. Verrouille sur la valeur que le
# moteur physique V2 utilise pour rester coherent avec la conversion
# vitesse <-> puissance flatlands (P_run_wkg = cost * speed_mps).
MINETTI_FLAT_COST_J_PER_KG_M: float = minetti_run_cost(0.0)

# Conservatisme: P_run sustainable plat est inferieur a vVO2max (un coureur
# ne tient pas vVO2max plus de quelques minutes). Le prior populationnel
# `estimate_flat_capacity_prior` renvoie une vitesse en m/s assimilable
# a vVO2max. Pour eviter qu'un utilisateur sans historique parte sur une
# capacite irrealiste (~15-20 W/kg), on applique un facteur populationnel
# de soutenabilite long.
#
# Justification : sustainable_fraction Daniels-VDOT pour une duree de 60 min
# vaut ~0.83; pour 120 min ~0.76; en moyenne ~0.80 pour la cible d'usage
# (trail/road 10-30 km). On utilise 0.80 comme prior moyen (note: ce n'est
# PAS un equivalent du double comptage V2.2; on ne reapplique pas cette
# fraction lors de la prediction, c'est juste la centralisation du prior
# autour d'une valeur P_run plausible).
_PRIOR_SUSTAINABLE_FRACTION: float = 0.80

# Std multiplicatif sur l'incertitude du prior P_run en W/kg : la dispersion
# inter-individus reste large sans observation, on conserve un std relatif
# important pour laisser les observations dominer rapidement.
_PRIOR_P_RUN_RELATIVE_STD: float = 0.15

# Default Monte Carlo stds (clamps applied below).
_MIN_P_RUN_MC_STD: float = 0.04
_MAX_P_RUN_MC_STD: float = 0.30
_MIN_FATIGUE_MC_STD: float = 0.02
_MAX_FATIGUE_MC_STD: float = 0.10
_MIN_SURFACE_MC_STD: float = 0.02
_MAX_SURFACE_MC_STD: float = 0.10


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


def _build_p_run_prior_wkg(
    vo2max_prior: dict[str, Any],
    flat_capacity_prior_mps: dict[str, Any],
) -> dict[str, Any]:
    """Build a P_run prior expressed directly in W/kg.

    Strategy
    --------
    The V2.2 ``estimate_flat_capacity_prior`` returns a vVO2max-equivalent
    speed (m/s) which corresponds to a short-distance peak speed, not a
    sustainable race pace. Converting it through Minetti (``W/kg = J/kg/m *
    m/s = 3.6 * speed``) yields a prior centered too high for a steady race
    effort.

    To stay coherent with the V2 historical extractor (which produces
    ``P_run = 3.6 * median(flat_speed_mps)`` from sub-max running portions),
    we center the prior on a sustainable fraction of vVO2max. This is *not*
    the V2.2 double-counting: the fraction is only applied to the prior,
    never to observations, and never re-applied during prediction. It is
    purely a way to express the prior on the same quantity the observations
    measure.

    The resulting prior is wide enough (>~15% relative std) so historical
    observations dominate the posterior as soon as they exist, and the
    population prior only carries weight for users with no history.
    """
    speed_mean = max(1.5, float(flat_capacity_prior_mps["mean"]))
    speed_std = max(0.01, float(flat_capacity_prior_mps["std"]))

    # W/kg = J/(kg*m) * m/s; apply the sustainability factor on the speed
    # before multiplying so we operate on the same quantity as observations.
    p_run_mean = MINETTI_FLAT_COST_J_PER_KG_M * speed_mean * _PRIOR_SUSTAINABLE_FRACTION
    # Std grows linearly with speed_std (mean transformation) plus a relative
    # floor to account for the additional uncertainty introduced by the
    # sustainability assumption.
    base_std = MINETTI_FLAT_COST_J_PER_KG_M * speed_std * _PRIOR_SUSTAINABLE_FRACTION
    relative_floor = _PRIOR_P_RUN_RELATIVE_STD * p_run_mean
    p_run_std = max(base_std, relative_floor)

    return {
        "mean": float(p_run_mean),
        "std": float(p_run_std),
        "p10": float(p_run_mean - 1.2816 * p_run_std),
        "p90": float(p_run_mean + 1.2816 * p_run_std),
        "sources": [
            "Daniels J, Gilbert J. Daniels Running Formula (1979) - vVO2max economy.",
            "Minetti et al. 2002 - flat run cost 3.6 J/(kg.m).",
            "V2.3 design: sustainable_fraction populationnelle 0.80 appliquee uniquement au prior.",
        ],
        "evidence_strength": str(flat_capacity_prior_mps.get("evidence_strength", "minimal")),
        "notes": (
            "P_run prior en W/kg derive du prior vVO2max (m/s) "
            f"via P_run = {MINETTI_FLAT_COST_J_PER_KG_M:.1f} * v * "
            f"{_PRIOR_SUSTAINABLE_FRACTION:.2f}. La fraction de soutenabilite "
            "n'est appliquee qu'au prior (V2.3 - pas de double comptage)."
        ),
        # Garde la trace de la vitesse equivalente pour le debug.
        "underlying_vo2max_mean": float(vo2max_prior.get("mean", 35.0)),
        "underlying_flat_speed_mps_mean": float(speed_mean),
    }


def _build_p_capacity_test_prior_wkg(
    vo2max_prior: dict[str, Any],
    flat_capacity_prior_mps: dict[str, Any],
) -> dict[str, Any]:
    """Build the prior for ``p_capacity_test_wkg`` (informative-only, R1).

    The peak-capacity prior is the same vVO2max-equivalent speed (m/s)
    converted by Minetti, **without** the sustainable_fraction factor that
    we apply to ``p_ref_steady_wkg``. This stays consistent with how the
    aggregator builds ``p_capacity_test_wkg`` observations: tests are
    maximal-effort measurements of the peak capacity itself.
    """
    speed_mean = max(1.5, float(flat_capacity_prior_mps["mean"]))
    speed_std = max(0.01, float(flat_capacity_prior_mps["std"]))

    p_cap_mean = MINETTI_FLAT_COST_J_PER_KG_M * speed_mean
    base_std = MINETTI_FLAT_COST_J_PER_KG_M * speed_std
    relative_floor = _PRIOR_P_RUN_RELATIVE_STD * p_cap_mean
    p_cap_std = max(base_std, relative_floor)

    return {
        "mean": float(p_cap_mean),
        "std": float(p_cap_std),
        "p10": float(p_cap_mean - 1.2816 * p_cap_std),
        "p90": float(p_cap_mean + 1.2816 * p_cap_std),
        "sources": [
            "Daniels J, Gilbert J. Daniels Running Formula (1979) - vVO2max economy.",
            "Minetti et al. 2002 - flat run cost 3.6 J/(kg.m).",
        ],
        "evidence_strength": str(flat_capacity_prior_mps.get("evidence_strength", "minimal")),
        "notes": (
            "Peak capacity prior en W/kg derive du prior vVO2max (m/s) "
            f"via P_cap = {MINETTI_FLAT_COST_J_PER_KG_M:.1f} * v. "
            "Parametre informatif uniquement (V2.3.1): non consomme par "
            "le moteur, expose en diagnostic."
        ),
        "underlying_vo2max_mean": float(vo2max_prior.get("mean", 35.0)),
        "underlying_flat_speed_mps_mean": float(speed_mean),
    }


def _normalize_p_ref_steady_observations(
    observations: dict[str, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], str]:
    """Return p_ref_steady observations in W/kg, handling legacy keys.

    Returns ``(observation_list, source_label)`` where ``source_label`` is
    one of ``"v2_3_1"`` (canonical R1 key present, including an empty
    prior-only evidence list), ``"legacy_p_run_wkg"``
    (the V2.3 ``p_run_wkg`` key is still used), ``"legacy_flat_capacity_mps"``
    (very old V2.2 m/s key), or ``"empty"``.

    Legacy normalisation (transition only)
    --------------------------------------
    - ``p_ref_steady_wkg`` present : returned as-is.
    - ``p_run_wkg`` only : returned as-is (already in W/kg). A warning is
      added downstream so the debug trace can flag the legacy aggregator.
    - ``flat_capacity_mps`` only : multiplied by Minetti flat cost (3.6) to
      convert m/s -> W/kg, with a ``legacy_aggregator_converted`` quality
      flag injected for traceability.
    - Empty in all three : empty list returned with source ``"empty"``.
    """
    if "p_ref_steady_wkg" in observations:
        return (list(observations["p_ref_steady_wkg"]), "v2_3_1")

    if "p_run_wkg" in observations and observations["p_run_wkg"]:
        legacy = list(observations["p_run_wkg"])
        for obs in legacy:
            flags = list(obs.get("quality_flags") or [])
            if "legacy_p_run_wkg" not in flags:
                flags.append("legacy_p_run_wkg")
            obs["quality_flags"] = flags
        return (legacy, "legacy_p_run_wkg")

    legacy = observations.get("flat_capacity_mps") or []
    if not legacy:
        return ([], "empty")

    converted: list[dict[str, Any]] = []
    for obs in legacy:
        try:
            mean_mps = float(obs.get("mean"))
        except (TypeError, ValueError):
            continue
        std_mps = float(obs.get("std") or 0.4)
        mean_wkg = MINETTI_FLAT_COST_J_PER_KG_M * mean_mps
        std_wkg = MINETTI_FLAT_COST_J_PER_KG_M * std_mps
        new_obs = dict(obs)
        new_obs["mean"] = mean_wkg
        new_obs["std"] = std_wkg
        # Flag so the debug trace can show the conversion happened.
        flags = list(new_obs.get("quality_flags") or [])
        flags.append("legacy_aggregator_converted")
        new_obs["quality_flags"] = flags
        converted.append(new_obs)
    return (converted, "legacy_flat_capacity_mps")


def _summarise_observations(
    observations: dict[str, list[dict[str, Any]]],
    *,
    p_ref_steady_obs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compact summary of the observation set used in the response.

    ``p_ref_steady_obs`` is the canonical list passed by the orchestrator
    (after :func:`_normalize_p_ref_steady_observations`). Other parameters
    are summarised straight from ``observations``. The legacy keys
    ``p_run_wkg`` / ``flat_capacity_mps`` are skipped to avoid
    double-counting them.
    """
    by_category: dict[str, int] = {}
    by_parameter: dict[str, int] = {"p_ref_steady_wkg": len(p_ref_steady_obs)}
    total = 0
    for obs in p_ref_steady_obs:
        total += 1
        cat = str(obs.get("category") or "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
    for param, obs_list in observations.items():
        if param in {"p_ref_steady_wkg", "p_run_wkg", "flat_capacity_mps"}:
            continue
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
    p_run_evidence_count: int,
    has_road_test_evidence: bool,
    has_trail_anchor_evidence: bool,
    has_long_evidence: bool,
) -> list[dict[str, Any]]:
    """Order the next pieces of evidence by expected interval reduction.

    V2.3 valorise l'historique en premier : sans observations historiques,
    le posterior est domine par le prior populationnel (intervalle large).
    Les tests de reference ne sont qu'un complement.
    """
    recommendations: list[dict[str, Any]] = []
    if not has_profile:
        recommendations.append(
            {
                "action": "complete_profile",
                "rationale": (
                    "Pas de profil athletique. Saisir sexe/age/poids/taille "
                    "calibre le prior populationnel (P_run, FCmax, durability)."
                ),
                "expected_interval_reduction_pct": 18,
            }
        )
    # V2.3 specific: si peu d'observations historiques, recommander la sync.
    if p_run_evidence_count == 0:
        recommendations.append(
            {
                "action": "synchronize_garmin_activities",
                "rationale": (
                    "Aucune activite historique propre disponible : la P_run "
                    "n'est calibree que sur le prior populationnel. Synchroniser "
                    "Garmin (avec streams) est la facon la plus efficace de "
                    "personnaliser la prediction."
                ),
                "expected_interval_reduction_pct": 25,
            }
        )
    if not has_road_test_evidence and p_run_evidence_count < 5:
        recommendations.append(
            {
                "action": "submit_road_10k_test",
                "rationale": (
                    "Un 5/10 km route propre enregistre une capacite de pointe "
                    "informative. En V2.3.1 elle n'ajuste pas encore l'allure "
                    "soutenable ni l'intervalle de prediction."
                ),
                "expected_interval_reduction_pct": 0,
            }
        )
    if not has_trail_anchor_evidence:
        recommendations.append(
            {
                "action": "tag_recent_trail_race_as_official_clean",
                "rationale": (
                    "Qualifier une course trail recente en `official_clean` "
                    "cree une reference de validation. Le facteur trail reste "
                    "base sur le prior tant que le rejeu residuel n'est pas valide."
                ),
                "expected_interval_reduction_pct": 0,
            }
        )
    if not has_long_evidence:
        recommendations.append(
            {
                "action": "log_long_steady_run",
                "rationale": (
                    "Synchroniser une sortie de plus de 2 h avec streams complets "
                    "permet d'estimer la durabilite par derive iso-effort."
                ),
                "expected_interval_reduction_pct": 8,
            }
        )
    return recommendations


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


def predict_v2_3(
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
    history_start_date: Optional[datetime] = None,
    filename: Optional[str] = None,
    evidence_policy: str = "strict",
) -> dict[str, Any]:
    """Run the V2.3 Bayesian prediction pipeline (no Daniels inversion).

    Parameters
    ----------
    session, user_id, gpx_text
        See V2.2 docstring.
    race_datetime
        Optional event datetime used to fetch the temporal weather timeline.
    effort_mode
        ``steady`` / ``endurance`` / ``aggressive`` - forwarded as-is to the
        physics engine (no iterate_event_power loop in V2.3).
    analysis_mode
        ``auto`` / ``trail`` / ``route``.
    target_heartrate
        Optional FC cible, kept for response symmetry (not consumed in V2.3).
    weather_mode
        ``auto`` or ``manual``.
    manual_temperature_c
        Used when ``weather_mode == "manual"`` or as a fallback if Open-Meteo
        is unreachable.
    ravito_mode
        ``auto`` or ``manual``.
    custom_ravitos
        Aid stations list. In manual mode it is user-defined; in auto mode it
        can carry official known course ravitos while keeping the auto label.
    as_of_date
        Strict upper bound on the historical evidence window.
    excluded_activity_ids
        Activities to drop from the aggregator (backtest replay).
    history_start_date
        Optional lower bound on the historical evidence window (V2.3.1, R1).
        Forwarded to :func:`aggregate_observations`. When None, the
        aggregator applies a default 3-year window ending at ``as_of_date``.
    filename
        Optional original filename, copied into the response.
    evidence_policy
        Internal calibration policy. ``strict`` is the V2.3.1 contract;
        V3 passes ``weighted_sparse`` to retain isolated high-quality Garmin
        evidence with widened uncertainty.

    Returns
    -------
    dict
        Full V2.3 prediction response (see
        ``docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md``).
    """
    warnings: list[str] = []

    # --- 1. GPX analysis ------------------------------------------------------
    gpx_analysis = analyze_gpx(gpx_text, custom_ravitos=custom_ravitos)
    segments = gpx_analysis["segments"]
    global_stats = gpx_analysis["global_stats"]
    total_distance_km = float(global_stats.get("total_distance_km") or 0)

    elevation_per_km = float(global_stats.get("elevation_per_km") or 0)
    resolved_analysis_mode = _resolve_analysis_mode(analysis_mode, elevation_per_km)
    if (analysis_mode or "auto").lower() == "auto":
        warnings.append(
            f"Mode auto resolu en {resolved_analysis_mode} via D+/km={elevation_per_km:.1f}."
        )

    # --- 2. Athletic profile --------------------------------------------------
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
            "Aucun profil athletique : le prior populationnel reste large. "
            "Completer le profil affine la distribution initiale."
        )

    # --- 3. Population priors -------------------------------------------------
    vo2max_prior = estimate_vo2max_prior(
        sex=sex,
        age_years=age_years,
        weight_kg=weight_kg,
        height_cm=height_cm,
        activity_level=activity_level,
    )
    flat_capacity_prior_mps = estimate_flat_capacity_prior(vo2max_prior, experience_level)
    # V2.3 : prior P_run en W/kg, reutilise pour p_ref_steady_wkg.
    p_run_prior = _build_p_run_prior_wkg(vo2max_prior, flat_capacity_prior_mps)
    # V2.3.1 (R1) : prior independant pour le parametre informatif
    # p_capacity_test_wkg (peak capacity issue des tests).
    p_capacity_test_prior = _build_p_capacity_test_prior_wkg(
        vo2max_prior, flat_capacity_prior_mps
    )
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
        # V2.3.1 : prior canonique consomme par le moteur.
        "p_ref_steady_wkg": p_run_prior,
        # V2.3.1 : prior informatif, non consomme par le moteur.
        "p_capacity_test_wkg": p_capacity_test_prior,
        # Conserve sous l'ancien nom pour les clients/scripts legacy qui
        # lisent encore "p_run_wkg" dans le prior_snapshot. Pointeur vers
        # le meme dict que p_ref_steady_wkg.
        "p_run_wkg": p_run_prior,
        "durability_alpha": durability_alpha_prior,
        "trail_cost_factor": trail_cost_factor_prior,
        "fc_max_bpm": fcmax_prior,
        "walk_threshold_grade_fraction": walk_threshold_prior,
        "heat_penalty_pct_per_degc": heat_penalty_prior,
        # Conserver la version m/s pour traceability (utilisee par le debug).
        "flat_capacity_mps_legacy_for_debug": flat_capacity_prior_mps,
    }

    # --- 4. Observations ------------------------------------------------------
    excluded_set: set[UUID] = set(excluded_activity_ids or [])
    aggregator_debug: dict[str, Any] = {}
    observations = aggregate_observations(
        session,
        user_id,
        as_of_date=effective_as_of_date,
        excluded_activity_ids=excluded_set,
        history_start_date=history_start_date,
        debug_trace=aggregator_debug,
        evidence_policy=evidence_policy,
    )
    # Adapter: prefer R1 ``p_ref_steady_wkg``; fall back to legacy
    # ``p_run_wkg`` (V2.3) or ``flat_capacity_mps`` (V2.2) when the
    # aggregator has not yet been refactored.
    p_ref_steady_observations, p_ref_steady_source = (
        _normalize_p_ref_steady_observations(observations)
    )
    p_capacity_test_observations = list(
        observations.get("p_capacity_test_wkg") or []
    )

    using_legacy_aggregator = p_ref_steady_source not in {"v2_3_1", "empty"}
    prior_only_no_p_ref_evidence = (
        p_ref_steady_source == "v2_3_1" and not p_ref_steady_observations
    )
    if p_ref_steady_source == "legacy_p_run_wkg":
        warnings.append(
            "observation_aggregator legacy detecte (cle p_run_wkg) : R1 "
            "n'est pas encore livre cote aggregator, les observations sont "
            "consommees telles quelles (W/kg)."
        )
    elif p_ref_steady_source == "legacy_flat_capacity_mps":
        warnings.append(
            "observation_aggregator legacy detecte (cle flat_capacity_mps) : "
            "conversion m/s -> W/kg appliquee. Le bug d'inversion Daniels "
            "reste present tant que R1 n'est pas livre."
        )

    observations_summary = _summarise_observations(
        observations, p_ref_steady_obs=p_ref_steady_observations
    )

    has_road_test_evidence = bool(p_capacity_test_observations) or any(
        (
            (obs.get("source_type") == "reference_test")
            and ("flat" in str(obs.get("source_label") or ""))
        )
        or (obs.get("category") in {"performance_anchor", "reference_test"})
        for obs in p_ref_steady_observations
    )
    has_trail_anchor_evidence = any(
        obs.get("category") == "trail_anchor"
        for obs in observations.get("trail_cost_factor", [])
    )
    has_long_evidence = bool(observations.get("durability_alpha"))

    # --- 5. Bayesian update ---------------------------------------------------
    # V2.3.1 (R1): p_ref_steady_wkg is the canonical engine input.
    p_ref_steady_posterior = compute_posterior(p_run_prior, p_ref_steady_observations)
    # V2.3.1 (R1): p_capacity_test_wkg posterior is computed for diagnostics
    # only. We tag it with consumed_by_engine=false so the response makes the
    # contract explicit, and we do NOT feed it into the physics engine.
    p_capacity_test_posterior = compute_posterior(
        p_capacity_test_prior, p_capacity_test_observations
    )
    p_capacity_test_posterior["consumed_by_engine"] = False
    p_capacity_test_posterior["informative_only"] = True

    durability_alpha_posterior = compute_posterior(
        durability_alpha_prior, observations.get("durability_alpha", [])
    )
    trail_cost_factor_posterior = compute_posterior(
        trail_cost_factor_prior, observations.get("trail_cost_factor", [])
    )
    v3_trail_history_debug: dict[str, Any] = {}
    v3_trail_history_observations: list[dict[str, Any]] = []
    if evidence_policy == "weighted_sparse" and resolved_analysis_mode == "trail":
        # V3-specific layer: blend the physical V2 engine with the athlete's
        # own historical trail performance. V2.3.1 strict mode keeps the
        # population prior only; V3 is allowed to replay Garmin trail tracks
        # and infer a personal surface penalty with wide uncertainty.
        v3_trail_history_observations, v3_trail_history_debug = (
            build_user_trail_factor_observations(
                session,
                user_id,
                as_of_date=effective_as_of_date,
                history_start_date=history_start_date,
                excluded_activity_ids=excluded_set,
                p_ref_steady_wkg=float(p_ref_steady_posterior["mean"]),
                durability_alpha=float(durability_alpha_posterior["mean"]),
            )
        )
        if v3_trail_history_observations:
            observations["trail_cost_factor"] = list(v3_trail_history_observations)
            trail_cost_factor_posterior = compute_posterior(
                trail_cost_factor_prior,
                observations["trail_cost_factor"],
            )
        aggregator_debug.setdefault("aggregator", {})
        aggregator_debug["aggregator"].update(
            {
                "trail_factor_mode": v3_trail_history_debug.get(
                    "mode", "v3_historical_trail_prior_only"
                ),
                "trail_factor_evidence_count": len(v3_trail_history_observations),
                "trail_factor_inconsistent_evidence": bool(
                    trail_cost_factor_posterior.get("outliers")
                ),
                "trail_factor_excluded_reasons": dict(
                    v3_trail_history_debug.get("excluded_reasons") or {}
                ),
                "trail_factor_diagnostic_observations": list(
                    v3_trail_history_observations
                )
                if v3_trail_history_observations
                else None,
                "v3_user_trail_history": v3_trail_history_debug,
            }
        )

    fcmax_posterior = compute_posterior(
        fcmax_prior, observations.get("fc_max_bpm", [])
    )

    # Recompute summaries after the V3 historical trail layer may have
    # injected observations. The earlier summary is intentionally overwritten
    # so Analytics and the UI see the actual evidence consumed by the engine.
    observations_summary = _summarise_observations(
        observations, p_ref_steady_obs=p_ref_steady_observations
    )
    has_trail_anchor_evidence = bool(observations.get("trail_cost_factor"))

    # The legacy "p_run_wkg" key in posterior_snapshot is kept for backward
    # compatibility (consumers / saved JSON predictions read it). It points
    # to the same dict as p_ref_steady_wkg.
    posterior_snapshot: dict[str, Any] = {
        "p_ref_steady_wkg": p_ref_steady_posterior,
        "p_capacity_test_wkg": p_capacity_test_posterior,
        "p_run_wkg": p_ref_steady_posterior,  # legacy alias
        "durability_alpha": durability_alpha_posterior,
        "trail_cost_factor": trail_cost_factor_posterior,
        "fc_max_bpm": fcmax_posterior,
    }

    evidence_summary_breakdown: dict[str, Any] = {
        "p_ref_steady_wkg": summarize_evidence(
            p_run_prior, p_ref_steady_observations, p_ref_steady_posterior
        ),
        "p_capacity_test_wkg": summarize_evidence(
            p_capacity_test_prior,
            p_capacity_test_observations,
            p_capacity_test_posterior,
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

    # Count outliers across the parameters consumed by the engine (skip the
    # legacy alias to avoid double-counting and the informative-only test).
    engine_posterior_keys = (
        "p_ref_steady_wkg",
        "durability_alpha",
        "trail_cost_factor",
        "fc_max_bpm",
    )
    total_outliers_detected = sum(
        len(posterior_snapshot[param].get("outliers") or [])
        for param in engine_posterior_keys
    )

    # --- 6. Build physics inputs DIRECTEMENT (pas d'iteration capacity ->
    #        event_power; pas d'application de sustainable_fraction).
    # V2.3.1 : le moteur consomme uniquement p_ref_steady_wkg.
    p_run_wkg = max(3.0, float(p_ref_steady_posterior["mean"]))
    p_run_std = max(1e-3, float(p_ref_steady_posterior["std"]))
    durability_alpha_mean = max(0.04, float(durability_alpha_posterior["mean"]))
    trail_cost_factor_mean = max(1.0, float(trail_cost_factor_posterior["mean"]))
    if v3_trail_history_observations:
        warnings.append(
            "V3 utilise un trail_factor personnalise depuis "
            f"{len(v3_trail_history_observations)} activite(s) trail Garmin "
            f"(posterior={trail_cost_factor_mean:.2f})."
        )

    relative_p_run_std = p_run_std / max(p_run_wkg, 1e-3)
    # Confidence used by physics engine: 1 - relative std, clamped.
    confidence = max(0.10, min(0.95, 1.0 - relative_p_run_std))

    calibration = {
        "engine_version": ENGINE_VERSION,
        "p_run_wkg": round(p_run_wkg, 3),
        "p_walk_ratio": 0.75,
        "confidence": round(confidence, 3),
        "p_run_std_wkg": round(p_run_std, 3),
        "calibration_quality": (
            "high"
            if p_ref_steady_posterior["evidence_count"] >= 2
            and total_outliers_detected == 0
            else "medium"
            if p_ref_steady_posterior["evidence_count"] >= 1
            else "prior_only"
        ),
        "source": "v2_3_1_bayesian_posterior",
        # Marqueur explicite que la fraction Daniels n'a PAS ete appliquee.
        "applied_sustainable_fraction": False,
        # V2.3.1 : trace que le moteur ignore p_capacity_test_wkg.
        "p_capacity_test_consumed": False,
    }

    fatigue_profile = {
        "model": "v2_3_posterior_alpha",
        "alpha": round(durability_alpha_mean, 4),
        "alpha_std": round(float(durability_alpha_posterior["std"]), 4),
        "personalized": bool(durability_alpha_posterior["evidence_count"] > 0),
        "sample_count": int(durability_alpha_posterior["evidence_count"]),
        "history_start_date": (
            history_start_date.isoformat() if history_start_date else None
        ),
        "history_end_date": effective_as_of_date.isoformat(),
        "excluded_activity_count": len(excluded_set),
        "notes": [
            "Alpha derive du posterior bayesien V2.3 sans inversion Daniels.",
        ],
    }

    environment = build_environment(
        global_stats,
        race_datetime=race_datetime,
        weather_mode=weather_mode,
        manual_temperature_c=manual_temperature_c,
        p_run_wkg=p_run_wkg,
    )
    if environment.get("weather_source") in {"default", "auto_failed"}:
        warnings.append(
            "Meteo automatique indisponible : temperature neutre ou manuelle utilisee."
        )

    # --- 7. Physics engine (single pass; no iterate_event_power loop) ---------
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

    # --- 8. Ravitos -----------------------------------------------------------
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

    # --- 9. Monte Carlo uncertainty (V2.3.1 R3: full physical replay) --------
    # Each draw resamples p_ref_steady / alpha / trail_factor from their
    # posterior, perturbs the weather timeline, and replays the full
    # physics + ravito pipeline. The legacy multiplicative path is kept in
    # uncertainty_service for V2 / V2.2 callers but is no longer used here.
    #
    # The R3 benchmark on UTMJ (cf. scripts/benchmark_monte_carlo_N.py) led
    # to choosing n_simulations=200 as the smallest N that achieves stable
    # P10/P90 within the < 5s end-to-end target for a ~30km GPX.
    weather_temp_std_c = (
        0.5 if environment.get("weather_source") == "manual" else 1.0
    )
    uncertainty = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=p_ref_steady_posterior,
        fatigue_posterior=durability_alpha_posterior,
        trail_factor_posterior=trail_cost_factor_posterior,
        environment=environment,
        analysis_mode=resolved_analysis_mode,
        effort_mode=effort_mode,
        ravito_mode=normalized_ravito_mode,
        custom_ravitos=custom_ravitos,
        n_simulations=200,
        seed=42,
        weather_temp_std=weather_temp_std_c,
    )

    # --- 10. Final response ---------------------------------------------------
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
        "avg_moving_pace": round(moving_time_min / total_distance_km, 2)
        if total_distance_km > 0
        else 0,
        "avg_pace": round(total_time_min / total_distance_km, 2)
        if total_distance_km > 0
        else 0,
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
        p_run_evidence_count=int(p_ref_steady_posterior["evidence_count"]),
        has_road_test_evidence=has_road_test_evidence,
        has_trail_anchor_evidence=has_trail_anchor_evidence,
        has_long_evidence=has_long_evidence,
    )

    # V2.3.1 R5 garde-fous: surface the trail_factor diagnostic produced by
    # the aggregator so consumers (UI, analytics, comparison scripts) can
    # tell at a glance whether the engine is using the personalised
    # posterior or the population prior. The aggregator emits these keys
    # under ``aggregator_debug["aggregator"]``; we copy them into
    # ``athlete_model.debug_trace`` with a stable contract so the front-end
    # does not have to dig into the orchestrator debug bag.
    aggregator_block = aggregator_debug.get("aggregator", {}) if isinstance(
        aggregator_debug, dict
    ) else {}
    athlete_model_debug_trace = {
        "trail_factor": {
            "mode": aggregator_block.get("trail_factor_mode", "prior_only"),
            "evidence_count": int(
                aggregator_block.get("trail_factor_evidence_count", 0)
            ),
            "inconsistent_evidence": bool(
                aggregator_block.get("trail_factor_inconsistent_evidence", False)
            ),
            "excluded_reasons": dict(
                aggregator_block.get("trail_factor_excluded_reasons", {})
            ),
            "diagnostic_observations": aggregator_block.get(
                "trail_factor_diagnostic_observations"
            ),
            # The actual value used by the engine for the response, kept
            # here so a UI can compare "prior used" vs "personalised".
            "applied_factor": round(trail_cost_factor_mean, 3),
            "applied_factor_source": (
                "personalized_posterior"
                if aggregator_block.get("trail_factor_mode")
                in {
                    "personalized_from_clean_races",
                    "v3_historical_trail_performance",
                }
                else "population_prior"
            ),
        }
    }

    athlete_model = {
        "prior": {
            # V2.3.1 canonical parameters.
            "p_ref_steady_wkg": p_run_prior,
            "p_capacity_test_wkg": p_capacity_test_prior,
            # Legacy alias for downstream code that still reads "p_run_wkg".
            "p_run_wkg": p_run_prior,
            "durability_alpha": durability_alpha_prior,
            "trail_cost_factor": trail_cost_factor_prior,
            "fc_max_bpm": fcmax_prior,
        },
        "posterior": posterior_snapshot,
        "evidence_summary": evidence_summary,
        "evidence_breakdown": evidence_summary_breakdown,
        "recommended_next_evidence": recommendations,
        "profile_present": has_profile,
        # V2.3.1 R5 garde-fous diagnostic. See module docstring.
        "debug_trace": athlete_model_debug_trace,
    }

    physics_inputs = {
        "p_run_wkg_used": round(p_run_wkg, 3),
        "trail_factor_used": round(trail_cost_factor_mean, 3),
        "fatigue_alpha_used": round(durability_alpha_mean, 4),
        "p_walk_ratio_used": 0.75,
    }

    debug_trace = {
        "engine_version": ENGINE_VERSION,
        "model_config_version": MODEL_CONFIG_VERSION,
        "as_of_date": effective_as_of_date.isoformat(),
        "history_start_date": (
            history_start_date.isoformat() if history_start_date else None
        ),
        "excluded_activity_ids": sorted(str(uid) for uid in excluded_set),
        "requested_analysis_mode": analysis_mode,
        "resolved_analysis_mode": resolved_analysis_mode,
        "effort_mode": effort_mode,
        "target_heartrate": target_heartrate,
        "prior_snapshot": prior_snapshot,
        "observations_summary": observations_summary,
        "posterior_snapshot": posterior_snapshot,
        "physics_inputs": physics_inputs,
        "uncertainty_trace": uncertainty.get("contributors", {}),
        "physics": physics_result["physics"],
        "calibration": calibration,
        "fatigue": fatigue_profile,
        "environment": environment,
        "warnings": list(warnings),
        # Marqueurs V2.3 explicites pour les comparateurs golden set.
        "no_iterate_event_power": True,
        "no_daniels_inversion_on_p_run": True,
        "using_legacy_observation_aggregator": bool(using_legacy_aggregator),
        "prior_only_no_p_ref_evidence": bool(prior_only_no_p_ref_evidence),
        "p_ref_steady_source": p_ref_steady_source,
        "evidence_policy": evidence_policy,
        # V2.3.1 (R1): trace de la bande FC et de la fenetre historique.
        "aggregator": aggregator_debug.get("aggregator", {}),
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
        "physics_inputs": physics_inputs,
        "warnings": warnings,
        "debug_trace": debug_trace,
        "prediction_date": datetime.utcnow().isoformat(),
    }
    return response


__all__ = [
    "predict_v2_3",
    "ENGINE_VERSION",
    "LEGACY_ENGINE_VERSION",
    "MODEL_CONFIG_VERSION",
    "MINETTI_FLAT_COST_J_PER_KG_M",
]
