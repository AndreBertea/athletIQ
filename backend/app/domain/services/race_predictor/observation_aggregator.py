"""Observation aggregator for Race Predictor V2.3.1.

Extract weighted observations for latent athlete parameters from the user's
history. Used by the V2.3 Bayesian pipeline to combine a population prior with
personalised evidence. Backtests are strictly chronological: a prediction
computed for an event at ``as_of_date`` may only consume observations
*before* that date.

The module is consumed by :mod:`robust_updater` (which fuses the prior with
the observations) and by :mod:`v2_3_prediction_service` (the orchestrator).

V2.3.1 refactor (R1 - separation of capacity and reference)
-----------------------------------------------------------
V2.3 fused two distinct quantities under a single ``p_run_wkg`` key: the
flat-road power observed at sub-maximal effort in training, and the maximal
aerobic capacity derived from short race tests (5K / 10K). The Bayesian
fusion of those two grandeurs is invalid (cf. R0 audit), so adding a
ReferenceTest could distort the historical posterior.

V2.3.1 splits them into two latent parameters:

- ``p_ref_steady_wkg`` (consumed by the engine): flat-road power observed
  at a documented reference intensity, fed by the historical aggregator
  filtered through a narrow FC band ``[0.72, 0.78] x FCmax`` (Z3 / lower
  Z4). When the band yields too few samples (< 60 OR < 3 activities), a
  fallback band ``[0.68, 0.82] x FCmax`` is used with an inflated std
  (multiplied by 1.5) and the ``fc_band_fallback`` flag set in debug.
  The legacy band ``[0.65, 0.85]`` is **forbidden** in production
  (V2.3.1) and only kept as an audit baseline
  (cf. ``scripts/audit_fc_band_coverage.py``).

- ``p_capacity_test_wkg`` (informative only - NOT consumed by the engine):
  maximal aerobic capacity (W/kg) derived from short maximal tests
  (5K / 10K) via the Daniels VDOT ``sustainable_fraction`` inversion. The
  V2.3.1 engine ignores this parameter; it is exposed in the response with
  ``consumed_by_engine = false`` so the UI can show it as diagnostic
  information. A later release will introduce a validated
  capacity -> reference transfer function.

Historical activities extracted via :func:`extract_p_ref_steady_observation`
also use the same flat-grade and speed filters as V2 calibration (cf.
:mod:`calibration_service`), so the two services agree on what counts as
"flat enough". The FC band is applied at the aggregator level on the *total*
sample/activity count: if the principal band yields enough evidence, every
contributing activity gets a normal-precision observation; otherwise the
aggregator switches to the fallback band globally and inflates every
observation std by 1.5x.

Latent parameters covered by this MVP
-------------------------------------
- ``p_ref_steady_wkg`` -- sustainable running power on flat road at the
  reference FC band (W/kg). **Consumed by the V2.3.1 engine.**
- ``p_capacity_test_wkg`` -- peak aerobic capacity from maximal tests
  (W/kg). Informative only; **NOT consumed by the V2.3.1 engine.**
- ``durability_alpha`` -- decay of sustainable fraction with duration/D+.
- ``trail_cost_factor`` -- multiplicative surface penalty beyond Minetti.
- ``fc_max_bpm`` -- positioning anchor for relative HR intensities.
- ``walk_power_ratio`` -- placeholder; reserved for hill_climb / KV tests.

Categorisation of activities
----------------------------
Each activity is classified into one of:

- ``performance_anchor`` -- ``official_clean`` road race (D+/km < 15).
- ``trail_anchor`` -- ``official_clean`` race on trail (D+/km >= 15).
- ``submax_physiological`` -- stable HR, streams ok, duration > 30 min.
- ``diagnostic`` -- streams ok but the activity is too short/irregular.
- ``non_scoring`` -- incident or execution_degraded; never feeds capacity.

Critical contract
-----------------
The ``as_of_date`` filter is **strict**: ``Activity.start_date < as_of_date``.
The same rule applies to ``ReferenceTest.performed_at``. Excluded activity
IDs are removed from the query so that a self-comparison cannot use the
target activity itself as evidence. These guarantees are tested in
``test_as_of_date_strictly_filters_future_activities`` and
``test_excluded_activity_ids_excluded``.

The optional ``history_start_date`` parameter (V2.3.1, R1) applies a strict
lower bound on activities AND on reference tests; activities before that
date are dropped. When None, a default 3-year window ending at ``as_of_date``
is applied. Both bounds and the resulting period are logged in
``debug_trace.history_period_days`` / ``history_start_date_applied``.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.entities.race_prediction import RaceValidationReference
from app.domain.entities.reference_test import (
    ReferenceTest,
    ReferenceTestQuality,
    ReferenceTestType,
)
from app.domain.services.race_predictor.event_intensity_service import (
    sustainable_fraction,
)
# V2.3.1 (R2): durability_alpha extraction must normalise the observed
# pace by the Minetti iso-effort pace at the same grade. This removes the
# spurious effect of late uphills on the alpha estimate. We import the
# canonical Minetti running cost from the V2 fatigue_model so the two
# services agree byte-for-byte on the cost polynomial.
from app.domain.services.race_predictor.fatigue_model import (
    _minetti_run_cost,
    stream_grade_fraction,
    default_fatigue_level,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Threshold (D+/km in meters) above which a race is considered trail-like.
TRAIL_ELEVATION_PER_KM_THRESHOLD: float = 15.0

#: Minimum duration (in seconds) for an activity to be considered a viable
#: submax_physiological observation. Short efforts are too noisy.
SUBMAX_MIN_DURATION_S: int = 30 * 60

#: Maximum acceptable HR std (in bpm) over a 30-min portion to call an HR
#: trace "stable" enough for submax_physiological classification.
SUBMAX_HR_STD_THRESHOLD: float = 10.0

#: Maximum absolute slope (as a fraction, not %) considered "flat" for the
#: purpose of extracting ``p_run_wkg``. 2 % matches the V2 calibration
#: service. The streams store ``grade_smooth`` in percent and are converted
#: to a fraction before this comparison.
FLAT_GRADE_FRACTION_THRESHOLD: float = 0.02

#: Minimum plausible running speed (m/s) for a sample to be kept when
#: extracting ``p_run_wkg``. Below this the athlete is most likely walking
#: or stopped.
MIN_RUN_SPEED_MPS: float = 1.0

#: Maximum plausible running speed (m/s) used as an upper bound for
#: ``p_run_wkg`` flat-speed samples. 6.5 m/s ~ 2:34/km.
MAX_RUN_SPEED_MPS: float = 6.5

#: Minimum sample count required on flat terrain before we trust the median
#: flat-speed extraction for a single activity.
MIN_FLAT_SAMPLE_COUNT: int = 30

#: Categories from :class:`RaceValidationReference` that must never contribute
#: to capacity-like parameters. They are surfaced as ``non_scoring``.
NON_SCORING_VALIDATION_CATEGORIES: frozenset[str] = frozenset(
    {"incident_non_scoring", "execution_degraded_non_scoring"}
)

#: Validation categories that authorise the ``performance_anchor`` /
#: ``trail_anchor`` routes (depending on D+/km).
# ``official_normalized`` is valid for prediction-error scoring only: its raw
# streams still contain the documented execution incident and must not become
# a physiological capacity anchor.
SCORING_VALIDATION_CATEGORIES: frozenset[str] = frozenset({"official_clean"})

#: Per-category default weight. Modifiers may be applied (stream quality).
_CATEGORY_BASE_WEIGHT: dict[str, float] = {
    "performance_anchor": 1.0,
    "trail_anchor": 0.8,
    "submax_physiological": 0.5,
    "diagnostic": 0.2,
    "non_scoring": 0.0,
}

#: Boost applied when streams are complete (>50% sample coverage).
_STREAM_QUALITY_FULL: float = 1.0
_STREAM_QUALITY_PARTIAL: float = 0.5

#: Weight for a controlled reference test. Higher than activity-derived
#: observations because the protocol is explicitly maximal/standardised.
_REFERENCE_TEST_WEIGHT: float = 1.5

#: Average Minetti cost on flat terrain (J/(kg.m)). Multiplying a flat speed
#: in m/s by this constant yields the corresponding ``p_ref_steady_wkg`` (W/kg).
#: Matches :func:`physics_engine.minetti_run_cost` at slope 0 and the V2
#: calibration formula ``p_run_wkg = 3.6 * flat_speed_mps``.
_MINETTI_COST_FLAT: float = 3.6

#: Standard deviation (W/kg) attached to a p_ref_steady observation by
#: category. The performance anchor is tightest because the effort is maximal
#: and documented. Submax sessions add aerobic noise. Diagnostic sessions are
#: short/irregular and warrant a much wider uncertainty.
_P_REF_STD_BY_CATEGORY: dict[str, float] = {
    "performance_anchor": 0.4,
    "submax_physiological": 0.6,
    "diagnostic": 0.9,
}

#: Principal FC band (xFCmax) used to extract p_ref_steady_wkg. Mirrors R0
#: decision: tempo / Z3-low Z4 effort. Bracketed below by the fallback band.
FC_BAND_PRIMARY: tuple[float, float] = (0.72, 0.78)

#: Fallback FC band when the principal band yields insufficient evidence.
#: Triggers std inflation and ``fc_band_fallback = true`` in debug_trace.
FC_BAND_FALLBACK: tuple[float, float] = (0.68, 0.82)

#: Minimum sample count (across all activities) inside the principal band
#: required to publish the observations without fallback. Below this OR below
#: ``MIN_ACTIVITIES_IN_BAND``, the aggregator switches to the fallback band.
MIN_SAMPLES_IN_BAND: int = 60

#: Minimum number of distinct activities contributing inside the principal
#: band required to publish the observations without fallback.
MIN_ACTIVITIES_IN_BAND: int = 3

#: Multiplier applied to the per-observation std when the fallback band is
#: used (signals lower trust in the reference intensity definition).
FALLBACK_STD_INFLATION: float = 1.5

#: V3 policy: retain a single well-sampled Garmin route observation with
#: widened uncertainty. V2.3.1 continues to use the strict multi-activity
#: evidence rule by default.
SPARSE_EVIDENCE_POLICY: str = "weighted_sparse"
SPARSE_STD_INFLATION: float = 1.5

#: Default historical window when no ``history_start_date`` is provided.
#: 3 years matches the V2.3 implicit default and avoids unbounded queries.
DEFAULT_HISTORY_WINDOW_DAYS: int = 366 * 3

#: Default p_ref_steady_wkg used when the aggregator cannot derive a
#: preliminary estimate from the history (e.g. day-one user with no
#: extractable observation). 9.0 W/kg matches the V2 ``p_run_base`` default
#: (cf. ``physics_engine.predict_segments``) and corresponds to a 5:30
#: min/km flat pace. Documented in V2.3.1 R2; used only when no
#: data-driven estimate is available.
DEFAULT_P_REF_STEADY_WKG: float = 9.0

#: Minimum duration (seconds) for an activity to feed durability_alpha.
#: V2.3.1 (FIX 4) : seuil monte a 2h. Les sorties courtes (30-90 min) ne
#: peuvent pas resoudre la fatigue cumulee post-2h dont la durability_alpha
#: rend compte; les inclure polluait le posterior par du bruit tempo. Seules
#: les sorties >= 2h alimentent ce parametre.
DURABILITY_MIN_DURATION_S: int = 2 * 3600

#: Per-segment window size (seconds) used to compare early vs late
#: iso-effort ratios. 10 minutes matches V2 ``build_fatigue_profile`` early
#: window (0.25-1h ~ 45 minutes total) and late window (>= 2h).
DURABILITY_WINDOW_S: int = 10 * 60

#: Required keys for an observation dict returned to the updater.
_OBSERVATION_KEYS: tuple[str, ...] = (
    "mean",
    "std",
    "weight",
    "source_label",
    "source_id",
    "source_type",
    "performed_at",
    "category",
    "quality_flags",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def aggregate_observations(
    session: Session,
    user_id: UUID,
    *,
    as_of_date: datetime,
    excluded_activity_ids: Iterable[UUID] | None = None,
    history_start_date: datetime | None = None,
    debug_trace: dict[str, Any] | None = None,
    evidence_policy: str = "strict",
) -> dict[str, list[dict[str, Any]]]:
    """Build the per-parameter observation list for one athlete (V2.3.1 contract).

    Parameters
    ----------
    session
        SQLModel session used to read activities, validation references and
        reference tests.
    user_id
        Identifier of the athlete whose history is consumed.
    as_of_date
        Strict upper bound on the temporal window. Activities and reference
        tests strictly *before* this date are kept.
    excluded_activity_ids
        Set of activity ids to skip (used in backtest replay to drop the
        target activity itself). ``None`` or empty means no exclusion.
    history_start_date
        Optional lower bound on the temporal window. Activities and reference
        tests with ``start_date < history_start_date`` are dropped. When
        None, the default 3-year window ending at ``as_of_date`` is applied.
    debug_trace
        Optional mutable dict that, when provided, receives metadata about the
        FC band actually used (``fc_band_used``, ``fc_band_fallback``,
        ``samples_in_band``, ``activities_in_band``,
        ``history_start_date_applied``, ``history_period_days``). The caller
        (orchestrator) is expected to forward this trace to the response.
    evidence_policy
        ``strict`` preserves V2.3.1 behaviour. ``weighted_sparse`` is the
        V3 policy: one well-sampled Garmin route activity can contribute with
        explicitly inflated uncertainty rather than being discarded.

    Returns
    -------
    dict
        ``{
            "p_ref_steady_wkg": [...],     # consumed by engine
            "p_capacity_test_wkg": [...],   # informative only
            "durability_alpha": [...],
            "trail_cost_factor": [...],
            "fc_max_bpm": [...],
            "walk_power_ratio": [...],
        }``

    Each observation is a dict with keys ``mean``, ``std``, ``weight``,
    ``source_label``, ``source_id``, ``source_type``, ``performed_at``,
    ``category`` and ``quality_flags``.
    """
    excluded_set: set[UUID] = set(excluded_activity_ids or [])

    # Resolve the history window. Default = 3-year retrospective window ending
    # at ``as_of_date`` (R1 decision; matches V2.3 implicit behaviour while
    # still applying ``history_start_date`` when the caller supplies one).
    resolved_history_start = history_start_date
    if resolved_history_start is None:
        resolved_history_start = as_of_date - timedelta(days=DEFAULT_HISTORY_WINDOW_DAYS)
    if resolved_history_start > as_of_date:
        # Defensive: an inverted window yields zero observations.
        resolved_history_start = as_of_date
    history_period_days = max(0, (as_of_date - resolved_history_start).days)

    observations: dict[str, list[dict[str, Any]]] = {
        "p_ref_steady_wkg": [],
        "p_capacity_test_wkg": [],
        "durability_alpha": [],
        "trail_cost_factor": [],
        "fc_max_bpm": [],
        "walk_power_ratio": [],
    }

    # --- 1. Activities ------------------------------------------------------
    activities = _fetch_user_activities(
        session,
        user_id,
        as_of_date=as_of_date,
        excluded_ids=excluded_set,
        history_start_date=resolved_history_start,
    )
    validation_by_activity = _fetch_validation_index(
        session, user_id, activity_ids={a.id for a in activities if a.id is not None}
    )

    # Categorise each activity once (used by all extractors).
    categorised: list[tuple[Activity, str]] = []
    for activity in activities:
        validation = validation_by_activity.get(activity.id) if activity.id else None
        category = categorize_activity(activity, validation)
        if category == "non_scoring":
            continue
        categorised.append((activity, category))

    # --- 1a. P_ref_steady extraction with FC band selection (R1) ------------
    fcmax_debug: dict[str, Any] = {}
    fcmax_estimate = _estimate_fcmax_from_history(
        categorised, debug_trace=fcmax_debug
    )
    p_ref_obs, fc_meta = _build_p_ref_steady_observations(
        categorised,
        fcmax_estimate=fcmax_estimate,
        accept_sparse=evidence_policy == SPARSE_EVIDENCE_POLICY,
    )
    observations["p_ref_steady_wkg"].extend(p_ref_obs)

    # --- 1b. Preliminary p_ref_steady estimate for durability (R2) ----------
    # ``extract_durability_alpha_observation`` needs a steady-power reference
    # to normalise the iso-effort ratio. The Bayesian posterior is computed
    # downstream (in the prediction service); we approximate it here with
    # the median of the per-activity observations just extracted. When no
    # observation is available (day-one user) we fall back to a documented
    # default. The approximation is good enough because the posterior is
    # dominated by the same observations.
    preliminary_p_ref_steady = _estimate_preliminary_p_ref_steady(p_ref_obs)

    # --- 1c. Per-activity extractors (durability, trail, fcmax) -------------
    # R5 (V2.3.1 garde-fous): track *why* a candidate trail_anchor was
    # rejected so the diagnostic surfaced in debug_trace makes it obvious.
    trail_factor_excluded_reasons: dict[str, int] = {}
    for activity, category in categorised:
        durability_obs = extract_durability_alpha_observation(
            activity, category, preliminary_p_ref_steady
        )
        if durability_obs is not None:
            observations["durability_alpha"].append(durability_obs)

        # R5: forward the reconstructable-track flag and the preliminary
        # p_ref_steady_wkg explicitly. The function itself enforces the
        # hard-coded exclusion list as defence in depth.
        if category == "trail_anchor":
            track_ok = _has_reconstructable_track(activity)
            trail_obs = extract_trail_cost_factor_observation(
                activity,
                category,
                has_reconstructable_track=track_ok,
                p_ref_steady_wkg=preliminary_p_ref_steady,
            )
            if trail_obs is not None:
                observations["trail_cost_factor"].append(trail_obs)
            elif not track_ok:
                trail_factor_excluded_reasons["no_reconstructable_track"] = (
                    trail_factor_excluded_reasons.get(
                        "no_reconstructable_track", 0
                    )
                    + 1
                )
            else:
                trail_factor_excluded_reasons["insufficient_signal"] = (
                    trail_factor_excluded_reasons.get(
                        "insufficient_signal", 0
                    )
                    + 1
                )
        else:
            # Other categories never reach extract_trail_cost_factor in this
            # code path; the hard-coded exclusion inside the function would
            # still drop them if they did.
            trail_factor_excluded_reasons[f"category={category}"] = (
                trail_factor_excluded_reasons.get(f"category={category}", 0)
                + 1
            )

        fc_obs = extract_fc_max_observation(activity, category)
        if fc_obs is not None:
            observations["fc_max_bpm"].append(fc_obs)

    # --- 2. Reference tests -------------------------------------------------
    tests = _fetch_user_reference_tests(
        session,
        user_id,
        as_of_date=as_of_date,
        history_start_date=resolved_history_start,
    )
    for test in tests:
        test_obs = convert_reference_test_to_observations(
            test, as_of_date=as_of_date
        )
        for param, obs_list in test_obs.items():
            observations.setdefault(param, []).extend(obs_list)

    # --- 2b. Trail factor activation (R5 garde-fous) -------------------------
    # V2.3.1 keeps the personalised trail_cost_factor INACTIVE regardless of
    # the diagnostic evidence count: a proper residual replay is not yet
    # implemented. Downstream fusion therefore only sees the population prior.
    trail_factor_diagnostic = _decide_trail_factor_activation(
        observations.get("trail_cost_factor", [])
    )
    if not trail_factor_diagnostic["activate_fusion"]:
        observations["trail_cost_factor"] = []

    # --- 3. Debug trace -----------------------------------------------------
    if debug_trace is not None:
        debug_trace.setdefault("aggregator", {})
        debug_trace["aggregator"].update(
            {
                "fc_band_used": list(fc_meta["fc_band_used"]),
                "fc_band_fallback": bool(fc_meta["fc_band_fallback"]),
                "samples_in_band": int(fc_meta["samples_in_band"]),
                "activities_in_band": int(fc_meta["activities_in_band"]),
                "evidence_policy": evidence_policy,
                "sparse_evidence_accepted": bool(
                    fc_meta.get("sparse_evidence_accepted", False)
                ),
                "fcmax_estimate_bpm": (
                    float(fcmax_estimate) if fcmax_estimate is not None else None
                ),
                # FIX 5 (V2.3.1): trace la source effectivement retenue pour
                # l'estimation de FCmax (streams_p995 robuste, fallback
                # activity.max_heartrate, ou hard fallback 190 bpm).
                "fcmax_source": fcmax_debug.get("fcmax_source", "none"),
                "history_start_date_applied": resolved_history_start.isoformat(),
                "history_period_days": int(history_period_days),
                "history_start_date_explicit": history_start_date is not None,
                # R2: preliminary p_ref used to Minetti-normalise the
                # durability_alpha extraction. None of the per-activity
                # observations capture this directly, so it's only visible
                # in the trace.
                "durability_p_ref_steady_preliminary_wkg": float(
                    preliminary_p_ref_steady
                ),
                # R5 garde-fous: trail factor diagnostic. The keys match the
                # contract documented in docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md.
                "trail_factor_mode": trail_factor_diagnostic["mode"],
                "trail_factor_evidence_count": trail_factor_diagnostic[
                    "evidence_count"
                ],
                "trail_factor_inconsistent_evidence": trail_factor_diagnostic[
                    "inconsistent_evidence"
                ],
                "trail_factor_excluded_reasons": dict(
                    trail_factor_excluded_reasons
                ),
                # Surface the diagnostic observations (when applicable) so a
                # human can audit which trail race was actually picked up
                # and what residual it would have implied if fusion had
                # been allowed.
                "trail_factor_diagnostic_observations": trail_factor_diagnostic[
                    "diagnostic_observations"
                ],
            }
        )

    return observations


def _decide_trail_factor_activation(
    trail_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Decide whether the trail_cost_factor posterior may fuse with evidence.

    V2.3.1 (R5 garde-fous) - audit V2.3.1 (FIX 2)
    ---------------------------------------------
    La fusion personnalisée du trail_factor est **désactivée en V2.3.1**,
    quel que soit le nombre d'observations ``official_clean`` cohérentes
    disponibles. La raison : l'extracteur ``extract_trail_cost_factor_observation``
    utilise encore une vitesse populationnelle fixe (3.3 m/s) et ignore le
    ``p_ref_steady_posterior`` réel de l'athlète. La "personnalisation" ne
    serait donc qu'une illusion de personnalisation à partir d'un calcul
    résiduel biaisé. La personnalisation sera activée dans un lot futur
    (``prior_only`` deferred) quand le calcul résiduel correct (rejeu GPX
    avec ``p_ref_steady_posterior`` et ``surface_factor=1.0``) sera
    implémenté.

    Le contrat de retour reste le même pour ne pas casser les consommateurs :

    - ``activate_fusion`` (bool) : **toujours False** en V2.3.1.
    - ``mode`` (str) : un parmi ``"prior_only"`` (0 observations),
      ``"prior_only_single_observation"`` (exactement 1 observation,
      diagnostic), ``"inconsistent_evidence_fallback_prior"`` (>= 2
      observations mais résidus incohérents),
      ``"prior_only_pending_proper_residual_calculation"`` (>= 2 observations
      cohérentes - le mode est conservé en prior_only en V2.3.1).
    - ``evidence_count`` (int) : nombre d'observations collectées.
    - ``inconsistent_evidence`` (bool) : True uniquement en mode
      ``inconsistent_evidence_fallback_prior``.
    - ``diagnostic_observations`` (list[dict] or None) : observations
      conservées pour traçabilité. Toujours non-None dès qu'il y a au moins
      une observation (mode informative).

    Le seuil de cohérence reste +/- 0.15 autour de la médiane des résidus
    (utilisé comme diagnostic d'incohérence pour les operators, même si la
    fusion reste désactivée).
    """
    n = len(trail_observations)
    if n == 0:
        return {
            "activate_fusion": False,
            "mode": "prior_only",
            "evidence_count": 0,
            "inconsistent_evidence": False,
            "diagnostic_observations": None,
        }
    if n == 1:
        return {
            "activate_fusion": False,
            "mode": "prior_only_single_observation",
            "evidence_count": 1,
            "inconsistent_evidence": False,
            "diagnostic_observations": list(trail_observations),
        }

    # n >= 2: check cohérence on the residual means.
    values: list[float] = []
    for obs in trail_observations:
        try:
            values.append(float(obs.get("mean")))
        except (TypeError, ValueError):
            continue
    if len(values) < 2:
        # The means were unreadable; defensively fall back to prior.
        return {
            "activate_fusion": False,
            "mode": "inconsistent_evidence_fallback_prior",
            "evidence_count": n,
            "inconsistent_evidence": True,
            "diagnostic_observations": list(trail_observations),
        }

    sorted_vals = sorted(values)
    m = len(sorted_vals)
    if m % 2 == 1:
        median_val = sorted_vals[m // 2]
    else:
        median_val = (sorted_vals[m // 2 - 1] + sorted_vals[m // 2]) / 2.0
    max_deviation = max(abs(v - median_val) for v in values)

    if max_deviation > 0.15:
        return {
            "activate_fusion": False,
            "mode": "inconsistent_evidence_fallback_prior",
            "evidence_count": n,
            "inconsistent_evidence": True,
            "diagnostic_observations": list(trail_observations),
        }

    # FIX 2 (V2.3.1) : observations cohérentes mais on garde prior_only.
    # L'extracteur courant emploie une vitesse populationnelle fixe (3.3 m/s)
    # au lieu de p_ref_steady_posterior. Activer la fusion produirait une
    # personnalisation biaisée. On conserve les observations en diagnostic
    # pour audit, mais l'aggregator vide la liste avant fusion.
    return {
        "activate_fusion": False,
        "mode": "prior_only_pending_proper_residual_calculation",
        "evidence_count": n,
        "inconsistent_evidence": False,
        "diagnostic_observations": list(trail_observations),
    }


def categorize_activity(
    activity: Activity,
    validation_reference: Optional[RaceValidationReference],
) -> str:
    """Classify an activity into one of the V2.3 evidence roles.

    Returns one of: ``performance_anchor``, ``trail_anchor``,
    ``submax_physiological``, ``diagnostic`` or ``non_scoring``.

    Validation references take precedence: an ``official_clean`` race is the
    strongest available evidence, while documented incidents are always
    excluded from capacity updates regardless of stream quality.
    """
    if validation_reference is not None:
        category = (validation_reference.category or "").strip().lower()
        if category in NON_SCORING_VALIDATION_CATEGORIES:
            return "non_scoring"
        if category == "official_normalized":
            # The adjusted target time is meaningful for model scoring, but
            # the raw stream still contains the documented race incident.
            return "non_scoring"
        if category in SCORING_VALIDATION_CATEGORIES:
            if _is_trail_like(activity):
                return "trail_anchor"
            return "performance_anchor"
        # training_control / unclassified fall through to stream-based logic.

    if not _is_running_activity(activity):
        # Non-run activities never contribute to running-specific parameters.
        return "non_scoring"

    streams_ok, _, hr_std, _ = _stream_quality_summary(activity)

    duration_s = activity.moving_time or 0
    if (
        streams_ok
        and duration_s >= SUBMAX_MIN_DURATION_S
        and hr_std is not None
        and hr_std < SUBMAX_HR_STD_THRESHOLD
    ):
        return "submax_physiological"

    if streams_ok and duration_s >= 10 * 60:
        return "diagnostic"

    return "non_scoring"


def extract_p_ref_steady_observation(
    activity: Activity,
    category: str,
    fcmax_estimate: float | None = None,
    *,
    fc_band: tuple[float, float] = FC_BAND_PRIMARY,
    std_multiplier: float = 1.0,
    fallback_used: bool = False,
) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    """Extract a ``p_ref_steady_wkg`` observation from one activity (R1).

    The reference intensity is defined by an FC band ``[low, high] x FCmax``.
    The function counts samples in the band, computes the median flat-road
    speed inside the band, and converts it to power via the Minetti cost
    (``p_ref = 3.6 * median(flat_speed_mps)``). No Daniels VDOT inversion is
    applied; this estimand is *not* the maximal capacity. Only activities
    explicitly classified as route running (``Run`` / ``VirtualRun``) may
    contribute. ``TrailRun`` is rejected even when one of its segments is
    locally flat, because terrain cost is modelled separately.

    Parameters
    ----------
    activity
        The activity to inspect (must be a running effort).
    category
        Pre-computed activity category. Only ``performance_anchor``,
        ``submax_physiological`` and ``diagnostic`` may feed this parameter.
        ``trail_anchor`` and ``non_scoring`` are excluded.
    fcmax_estimate
        Estimated FCmax (bpm) for the user, used to compute the absolute HR
        thresholds. When None, falls back to ``activity.max_heartrate`` or a
        hard-coded 190 bpm. Estimating FCmax at the user level (in the
        aggregator) yields more stable thresholds than per-activity peaks.
    fc_band
        The FC band fraction window (e.g. ``(0.72, 0.78)`` principal or
        ``(0.68, 0.82)`` fallback).
    std_multiplier
        Multiplicative factor applied to the per-category std (e.g. 1.5 when
        the fallback band is used).
    fallback_used
        Whether the caller is in fallback mode (sets the
        ``fc_band_fallback`` flag in quality_flags).

    Returns
    -------
    (observation_or_None, meta)
        ``observation_or_None`` is the standard observation dict or ``None``
        when extraction failed. ``meta`` is always returned and exposes:
        ``samples_in_band`` (int), ``median_speed_mps`` (float or None) and
        the band actually used. The caller uses ``meta`` to decide whether
        the principal band gathered enough evidence or whether to retry in
        fallback mode at the global aggregator level.
    """
    meta: dict[str, Any] = {
        "samples_in_band": 0,
        "median_speed_mps": None,
        "fc_band": tuple(fc_band),
        "fallback_used": bool(fallback_used),
    }

    if category not in ("performance_anchor", "submax_physiological", "diagnostic"):
        return (None, meta)
    if not _is_road_reference_activity(activity):
        return (None, meta)
    if not _has_minimum_run_fields(activity):
        return (None, meta)

    distance_m = float(activity.distance or 0)
    moving_time_s = int(activity.moving_time or 0)
    if distance_m < 1000 or moving_time_s < 5 * 60:
        return (None, meta)

    streams = _normalize_streams(activity.streams_data)
    if streams is None:
        return (None, meta)

    # Compute the absolute HR window from the band and the user-level FCmax.
    resolved_fcmax = _resolve_fcmax_for_activity(activity, fcmax_estimate)
    if resolved_fcmax is None:
        return (None, meta)
    low_hr = fc_band[0] * resolved_fcmax
    high_hr = fc_band[1] * resolved_fcmax

    flat_speeds = _extract_flat_speed_samples_in_band(
        activity, streams, low_hr=low_hr, high_hr=high_hr
    )
    meta["samples_in_band"] = len(flat_speeds)

    if not flat_speeds:
        return (None, meta)

    median_speed = statistics.median(flat_speeds)
    meta["median_speed_mps"] = float(median_speed)
    if not (MIN_RUN_SPEED_MPS <= median_speed <= MAX_RUN_SPEED_MPS):
        return (None, meta)

    p_ref_wkg = _MINETTI_COST_FLAT * median_speed
    # Reject implausibly large values (>= 25 W/kg ~ world-elite vVO2max region).
    if not (3.0 <= p_ref_wkg <= 25.0):
        return (None, meta)

    streams_ok, _, hr_std, has_full_streams = _stream_quality_summary(activity)

    quality_flags: list[str] = ["fc_band_filtered", "road_reference_only"]
    if has_full_streams:
        stream_factor = _STREAM_QUALITY_FULL
        quality_flags.append("streams_complete")
    else:
        stream_factor = _STREAM_QUALITY_PARTIAL
        quality_flags.append("streams_partial")

    if category == "submax_physiological":
        quality_flags.append("submax_effort")

    if fallback_used:
        quality_flags.append("fc_band_fallback")

    # Variance by category (per R0 / R1 decision). Stream-quality penalty and
    # fallback-band inflation are layered on top.
    std = _P_REF_STD_BY_CATEGORY.get(category, _P_REF_STD_BY_CATEGORY["diagnostic"])
    if not has_full_streams:
        std *= 1.3
    std *= std_multiplier

    base_weight = _CATEGORY_BASE_WEIGHT[category]
    weight = base_weight * stream_factor
    if weight <= 0:
        return (None, meta)

    return (
        _build_observation(
            mean=p_ref_wkg,
            std=std,
            weight=weight,
            source_label=_activity_label(activity),
            source_id=activity.id,
            source_type="activity",
            performed_at=activity.start_date,
            category=category,
            quality_flags=quality_flags,
        ),
        meta,
    )


# Backward-compatible alias kept for callers that have not migrated yet.
# It applies the principal band by default; intended for direct invocation
# from tests checking the legacy V2.3 flat-extraction behaviour.
def extract_p_run_observation(
    activity: Activity,
    category: str,
) -> Optional[dict[str, Any]]:
    """Deprecated alias for the V2.3 flat-extraction function (no FC filter).

    Kept so unit tests that exercise the per-activity flat-grade filtering
    behaviour (without injecting an FCmax) still pass. The V2.3.1 production
    pipeline calls :func:`extract_p_ref_steady_observation` via
    :func:`aggregate_observations`, which applies the FC band globally.
    """
    if category not in ("performance_anchor", "submax_physiological", "diagnostic"):
        return None
    if not _is_road_reference_activity(activity):
        return None
    if not _has_minimum_run_fields(activity):
        return None

    distance_m = float(activity.distance or 0)
    moving_time_s = int(activity.moving_time or 0)
    if distance_m < 1000 or moving_time_s < 5 * 60:
        return None

    streams = _normalize_streams(activity.streams_data)

    flat_speeds: list[float] = []
    used_stream_grade = False
    if streams is not None:
        flat_speeds, used_stream_grade = _extract_flat_speed_samples(activity, streams)

    quality_flags: list[str] = []

    if flat_speeds and len(flat_speeds) >= MIN_FLAT_SAMPLE_COUNT:
        flat_speed_mps = statistics.median(flat_speeds)
        if used_stream_grade:
            quality_flags.append("flat_grade_filtered")
        else:
            quality_flags.append("activity_flat_enough")
    else:
        if streams is not None and flat_speeds:
            quality_flags.append("low_flat_sample_count")
        if _activity_elevation_per_km(activity) > 25.0:
            return None
        avg_speed = distance_m / moving_time_s
        if not (MIN_RUN_SPEED_MPS <= avg_speed <= MAX_RUN_SPEED_MPS):
            return None
        flat_speed_mps = avg_speed
        quality_flags.append("activity_average_fallback")

    if not (MIN_RUN_SPEED_MPS <= flat_speed_mps <= MAX_RUN_SPEED_MPS):
        return None

    p_run_wkg = _MINETTI_COST_FLAT * flat_speed_mps
    if not (3.0 <= p_run_wkg <= 25.0):
        return None

    streams_ok, _, hr_std, has_full_streams = _stream_quality_summary(activity)

    if has_full_streams:
        stream_factor = _STREAM_QUALITY_FULL
        quality_flags.append("streams_complete")
    elif streams is not None:
        stream_factor = _STREAM_QUALITY_PARTIAL
        quality_flags.append("streams_partial")
    else:
        stream_factor = _STREAM_QUALITY_PARTIAL
        quality_flags.append("no_streams")

    if category == "submax_physiological":
        quality_flags.append("submax_effort")

    std = _P_REF_STD_BY_CATEGORY.get(category, _P_REF_STD_BY_CATEGORY["diagnostic"])
    if not has_full_streams:
        std *= 1.3
    if "low_flat_sample_count" in quality_flags:
        std *= 1.2
    if "activity_average_fallback" in quality_flags:
        std *= 1.4

    base_weight = _CATEGORY_BASE_WEIGHT[category]
    weight = base_weight * stream_factor
    if weight <= 0:
        return None

    return _build_observation(
        mean=p_run_wkg,
        std=std,
        weight=weight,
        source_label=_activity_label(activity),
        source_id=activity.id,
        source_type="activity",
        performed_at=activity.start_date,
        category=category,
        quality_flags=quality_flags,
    )


def extract_durability_alpha_observation(
    activity: Activity,
    category: str,
    p_ref_steady_wkg: float = DEFAULT_P_REF_STEADY_WKG,
) -> Optional[dict[str, Any]]:
    """Extract a durability_alpha observation from a long activity (R2).

    V2.3.1 (FIX 4): duration gate raised to 2h
    ------------------------------------------
    Seules les sorties >= ``DURABILITY_MIN_DURATION_S`` (= 2h) alimentent ce
    parametre. La fenetre tardive utilisee pour mesurer la fatigue cumulee
    (>= 2h dans :func:`_minetti_normalised_alpha`) doit exister pour produire
    une observation, sinon le ratio iso-effort tardif n'est qu'une fenetre
    de "dernier tiers" trop bruitee pour informer l'alpha. Les sorties
    inferieures retournent None et ne contaminent plus le posterior.

    V2.3.1 (R2) refactor: Minetti-normalised
    ----------------------------------------
    The V2.3 implementation compared the raw speed of the first quartile
    versus the last quartile of the moving stream. That comparison was
    biased by the elevation profile: a run finishing on a long climb
    mechanically slowed Q4 down even at iso-effort, inflating the alpha
    estimate; a run starting with the climb produced the opposite bias.

    V2.3.1 normalises each speed sample by the iso-effort pace predicted
    by Minetti at the same grade, using the supplied ``p_ref_steady_wkg``
    estimate as the steady-power reference. The ratio
    ``expected_speed / actual_speed`` removes the elevation effect and
    isolates the fatigue signal. This mirrors the logic of
    :func:`fatigue_model.build_fatigue_profile` (V2 reference) and the
    two services now agree on the cost polynomial via the shared
    :func:`_minetti_run_cost` helper.

    Parameters
    ----------
    activity
        The activity to inspect. Must have ``velocity_smooth``,
        ``grade_smooth`` and ``time`` streams to feed the iso-effort ratio.
        Without those streams the function returns None (no fallback to a
        raw quartile comparison; V2.3.1 strictly requires the
        normalisation).
    category
        Pre-computed activity category. Only ``performance_anchor``,
        ``trail_anchor`` and ``submax_physiological`` may feed this
        parameter.
    p_ref_steady_wkg
        Steady-power reference used to compute the iso-effort pace at each
        grade. In production this is the preliminary estimate derived from
        ``p_ref_steady_wkg`` observations (see
        :func:`_estimate_preliminary_p_ref_steady` invoked by
        :func:`aggregate_observations`). Defaults to
        ``DEFAULT_P_REF_STEADY_WKG`` (9.0) when no estimate is available
        (e.g. day-one user, standalone unit test).

    Returns
    -------
    Observation dict or None.

    Methodology
    -----------
    1. Decode streams (velocity_smooth, grade_smooth, time).
    2. For each sample, compute ``grade_fraction = grade_smooth / 100``
       (R0 unit fix) and ``expected_speed = p_ref / minetti_cost(g)``.
    3. The instantaneous ratio is ``expected_speed / actual_speed``. A
       value > 1 means the athlete is moving slower than the iso-effort
       reference would predict (proxy for fatigue or extra cost). A value
       < 1 means faster (extra fitness or downhill momentum).
    4. Aggregate ratios in two windows:
       - early window: hours in ``[0.25, 1.0]`` (warm-up excluded, fresh
         athlete).
       - late window: hours ``>= 2.0`` (post-2h regime where durability
         dominates). When no late-window samples exist (activity < 2h)
         fall back to the last third of samples.
    5. Compute the cumulative fatigue level via
       :func:`default_fatigue_level` over the whole activity (V2-aligned).
    6. ``alpha = (late_median_ratio / early_median_ratio - 1) / fatigue_level``.
    7. Clamp to ``[0.04, 0.30]`` to stay in the physically plausible range
       used by V2 / V2.3 downstream consumers.
    """
    if category not in ("performance_anchor", "trail_anchor", "submax_physiological"):
        return None
    duration_s = int(activity.moving_time or 0)
    # R2: short activities cannot resolve a meaningful alpha; the
    # iso-effort ratio noise dominates any genuine fatigue signal.
    if duration_s < DURABILITY_MIN_DURATION_S:
        return None
    # Defensive: p_ref_steady must be in a credible range; otherwise the
    # iso-effort ratio is meaningless.
    if not (3.0 <= float(p_ref_steady_wkg) <= 25.0):
        return None

    alpha_estimate = _minetti_normalised_alpha(
        activity, p_ref_steady_wkg=float(p_ref_steady_wkg)
    )
    if alpha_estimate is None:
        return None
    # Clamp to a physically plausible range; matches V2 fatigue_model
    # ``clamp(alpha, 0.04, 0.22)`` upper bound widened to 0.30 to match
    # the existing V2.3 downstream consumers and keep continuity with the
    # legacy behaviour.
    alpha_estimate = max(0.04, min(0.30, alpha_estimate))

    quality_flags: list[str] = ["minetti_normalised"]
    if category == "performance_anchor":
        std = 0.05
        weight_factor = 1.0
    elif category == "trail_anchor":
        std = 0.06
        weight_factor = 0.9
        quality_flags.append("trail_terrain_noise")
    else:  # submax_physiological
        std = 0.07
        weight_factor = 0.7
        quality_flags.append("submax_effort")

    streams_ok, _, _, has_full_streams = _stream_quality_summary(activity)
    if not has_full_streams:
        std *= 1.4
        weight_factor *= 0.6
        quality_flags.append("streams_partial")

    base_weight = _CATEGORY_BASE_WEIGHT[category]
    weight = base_weight * weight_factor
    if weight <= 0:
        return None

    return _build_observation(
        mean=alpha_estimate,
        std=std,
        weight=weight,
        source_label=_activity_label(activity),
        source_id=activity.id,
        source_type="activity",
        performed_at=activity.start_date,
        category=category,
        quality_flags=quality_flags,
    )


#: Set of categories that are HARD-CODED forbidden as trail_cost_factor
#: evidence (V2.3.1 R5 garde-fous). The aggregator surfaces a normalised
#: ``category`` string per activity but, to defend against future refactors
#: that might rewire the routing, ``extract_trail_cost_factor_observation``
#: re-checks every excluded label explicitly before doing any work.
TRAIL_FACTOR_EXCLUDED_CATEGORIES: frozenset[str] = frozenset(
    {
        # RaceValidationReference categories that must never feed the
        # personalised surface penalty (incidents, degraded executions,
        # plain training control).
        "incident_non_scoring",
        "execution_degraded_non_scoring",
        "training_control",
        # Aggregator-internal categories that the V2.3.1 plan also forbids.
        "submax_physiological",
        "diagnostic",
        "non_scoring",
        "performance_anchor",
        "reference_test",
        "unclassified",
    }
)


def _has_reconstructable_track(activity: Activity) -> bool:
    """Return True when the activity has streams (latlng + altitude) usable
    for a personalised trail prediction replay (V2.3.1 R5).

    R5 requires a reconstructable track to run the reference physics replay
    that derives the per-course residual surface penalty. When the streams
    are missing both lat/lng AND altitude we cannot rebuild the elevation
    profile, so the observation is silently dropped.
    """
    streams = _normalize_streams(activity.streams_data)
    if streams is None:
        return False
    latlng = _stream_array(streams, "latlng")
    altitude = _stream_array(streams, "altitude")
    # Both are required: lat/lng alone tells us where but not the grade;
    # altitude alone tells us up/down but cannot recompute distance.
    if not latlng or not altitude:
        return False
    # At least a handful of usable samples in each stream; below this we
    # cannot replay anything meaningful.
    return len(latlng) >= 10 and len(altitude) >= 10


def extract_trail_cost_factor_observation(
    activity: Activity,
    category: str,
    *,
    has_reconstructable_track: Optional[bool] = None,
    p_ref_steady_wkg: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Extract a trail_cost_factor observation from a qualified trail race.

    V2.3.1 (R5 - garde-fous uniquement)
    -----------------------------------
    This function is the only entry point through which the trail surface
    penalty can be personalised. The V2.3.1 plan still keeps the personalised
    posterior **inactive** (the engine uses the population prior 1.20 +/-
    0.10) until at least two ``official_clean`` trail races with consistent
    residuals have been collected. To make sure no contamination can sneak
    in, R5 enforces two HARD-CODED guardrails *inside this function*:

    1. Any activity whose normalised ``category`` is in
       :data:`TRAIL_FACTOR_EXCLUDED_CATEGORIES` returns ``None`` immediately.
       The check is redundant with the aggregator's routing, but R5 requires
       defence-in-depth so a future refactor cannot accidentally route a
       degraded race through this code path.
    2. The activity must have a reconstructable track (lat/lng + altitude
       streams). When ``has_reconstructable_track`` is not provided, the
       function performs the streams check itself via
       :func:`_has_reconstructable_track`. Activities without that data
       return ``None``.

    The accepted ``category`` is strictly ``trail_anchor`` (i.e. the
    ``official_clean`` route taken by :func:`categorize_activity` when the
    race has D+/km >= 15). Anything else short-circuits.

    Parameters
    ----------
    activity, category
        See R1 contract.
    has_reconstructable_track
        Optional pre-computed flag (R5). When ``None`` the function checks
        the streams itself. Callers that pre-compute this (e.g. when a GPX
        file is available even though streams are missing) may pass
        ``True`` explicitly.
    p_ref_steady_wkg
        Optional preliminary p_ref_steady_wkg used to document the residual
        calibration. V2.3.1 keeps the legacy heuristic (population-typical
        3.3 m/s flat) for the value itself because the full two-pass
        residual calibration is out of scope for R5 garde-fous (no cohort
        of cohérent ``official_clean`` races yet). The parameter is
        accepted so the future R5 ``personalized_from_clean_races`` mode
        can be wired without changing the signature again.

    Returns
    -------
    Observation dict or None. The observation is *informative* in V2.3.1:
    even when one valid observation is returned, the aggregator empties
    the list before fusion (see ``aggregate_observations``).
    """
    # Defence-in-depth: re-check the exclusion list locally before doing any
    # work. This is the R5 garde-fou: even if the aggregator routing is
    # broken, no excluded category can produce a trail_cost_factor observation.
    if category in TRAIL_FACTOR_EXCLUDED_CATEGORIES:
        return None
    if category != "trail_anchor":
        return None
    if not _has_minimum_run_fields(activity):
        return None

    distance_m = float(activity.distance or 0)
    moving_time_s = int(activity.moving_time or 0)
    if distance_m < 5000 or moving_time_s < 30 * 60:
        return None

    elevation_gain = float(activity.total_elevation_gain or 0)
    if elevation_gain <= 0:
        return None

    # R5: require a reconstructable track. When the caller has not pre-
    # computed the flag (production path: aggregator passes it explicitly),
    # check the streams ourselves so this function stays usable in unit
    # tests that exercise the guard directly.
    if has_reconstructable_track is None:
        has_reconstructable_track = _has_reconstructable_track(activity)
    if not has_reconstructable_track:
        return None

    # Assume a population-typical flat capacity (~3.3 m/s, ~5:00 min/km).
    # The trail cost factor will be dominated by the *deviation* from a
    # naive Minetti prediction, not by the absolute capacity. The flat speed
    # estimate cancels out in the ratio to first order.
    flat_speed_mps = 3.3

    # Naive Minetti time: distance / flat_speed plus a slope-driven extra
    # cost. For a quick population-level estimate we use a global heuristic:
    # +6 s per 100 m of elevation gain per km (mid-range Minetti uphill).
    distance_km = distance_m / 1000.0
    avg_grade_pct = (elevation_gain / max(1.0, distance_m)) * 100.0
    # Minetti cost factor at the average grade (smooth approximation):
    # cost_factor(g) ~= 1 + 5.4 * g^2 + 0.4 * g (g in fraction). For typical
    # trail grades (5-10%) this is ~1.4-1.8, matching the literature.
    g_frac = avg_grade_pct / 100.0
    minetti_extra = max(0.0, 5.4 * g_frac**2 + 0.4 * g_frac)
    minetti_predicted_time_s = (distance_m / flat_speed_mps) * (1.0 + minetti_extra)

    if minetti_predicted_time_s <= 0:
        return None

    ratio = moving_time_s / minetti_predicted_time_s
    # ratio > 1 means real time slower than Minetti-only -> trail surface
    # accounts for the excess. ratio of 1.0-1.6 is the realistic window.
    if not (0.8 <= ratio <= 2.5):
        return None
    # Clamp to literature plausibility (1.0-1.4 is the populated band).
    trail_cost_estimate = max(1.0, min(1.6, ratio))

    quality_flags = ["uncertain_extraction", "trail_anchor"]

    streams_ok, _, _, has_full_streams = _stream_quality_summary(activity)
    if has_full_streams:
        std = 0.08
        weight_factor = 1.0
        quality_flags.append("streams_complete")
    else:
        std = 0.12
        weight_factor = 0.7
        quality_flags.append("streams_partial")

    base_weight = _CATEGORY_BASE_WEIGHT["trail_anchor"]
    weight = base_weight * weight_factor
    if weight <= 0:
        return None

    return _build_observation(
        mean=trail_cost_estimate,
        std=std,
        weight=weight,
        source_label=_activity_label(activity),
        source_id=activity.id,
        source_type="activity",
        performed_at=activity.start_date,
        category=category,
        quality_flags=quality_flags,
    )


def extract_fc_max_observation(
    activity: Activity,
    category: str,
) -> Optional[dict[str, Any]]:
    """Extract an FC max observation from an intense activity.

    Uses ``activity.max_heartrate`` when present; relevant only for
    activities executed at near-maximal effort (performance_anchor, or short
    submax sessions during which peak HR is credible).
    """
    if category == "non_scoring":
        return None
    max_hr = activity.max_heartrate
    if max_hr is None:
        return None
    max_hr = float(max_hr)
    if not (110.0 <= max_hr <= 230.0):
        return None

    # Only credible when the activity was intense enough to reach max HR.
    # We restrict to performance_anchor races, or to short activities (<= 90 min)
    # where peak HR is more likely to reflect true max.
    duration_s = int(activity.moving_time or 0)
    if category not in ("performance_anchor", "trail_anchor") and duration_s > 90 * 60:
        return None

    quality_flags: list[str] = []
    if category in ("performance_anchor", "trail_anchor"):
        std = 5.0
        weight = 1.0
        quality_flags.append("race_effort")
    else:
        std = 8.0
        weight = 0.4
        quality_flags.append("submax_effort")

    return _build_observation(
        mean=max_hr,
        std=std,
        weight=weight,
        source_label=_activity_label(activity),
        source_id=activity.id,
        source_type="activity",
        performed_at=activity.start_date,
        category=category,
        quality_flags=quality_flags,
    )


def convert_reference_test_to_observations(
    test: ReferenceTest,
    *,
    as_of_date: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Convert a single ReferenceTest into a dict of observations per parameter.

    V2.3.1 contract (R1 + FIX 6a)
    -----------------------------
    Reference tests no longer feed ``p_ref_steady_wkg``. The maximal effort
    they probe is a *peak* aerobic capacity, which is structurally different
    from the steady reference power the historical aggregator extracts. They
    therefore feed a separate latent parameter:

    - ``p_capacity_test_wkg`` -- peak capacity (W/kg), Daniels VDOT inversion
      applied to convert the duration-specific test speed into a vVO2max
      equivalent. This parameter is exposed to the response with
      ``consumed_by_engine = false`` and does NOT modify the predicted time.

    Invalid tests yield an empty dict. ``questionable`` tests are kept but
    their std is widened to reflect the lower trust. ``long_steady`` entries
    remain recorded in the database but produce no consumed observation until
    they can be linked to streams measuring real speed/heart-rate drift.

    FIX 6a (V2.3.1) - decroissance d'anciennete:
    Apres 24 mois, le poids de l'observation est divise par 2 par tranche
    additionnelle de 12 mois (decroissance exponentielle douce :
    ``0.5 ** ((months - 24) / 12)``). Conserve les tests anciens en
    diagnostic tout en laissant les nouveaux dominer. Un flag
    ``age_weight_<value>`` apparait dans ``quality_flags`` quand le facteur
    differe de 1.0.
    """
    if test.quality_status == ReferenceTestQuality.INVALIDATED:
        return {}

    if test.duration_seconds is None or test.duration_seconds <= 0:
        return {}

    quality_flag = (
        "questionable" if test.quality_status == ReferenceTestQuality.QUESTIONABLE
        else "valid"
    )
    std_inflation = 1.8 if quality_flag == "questionable" else 1.0

    # FIX 6a (V2.3.1) : decroissance d'anciennete au-dela de 24 mois.
    age_weight = 1.0
    age_quality_flag: Optional[str] = None
    if isinstance(test.performed_at, datetime):
        reference_date = as_of_date or datetime.utcnow()
        # Sanity: performed_at peut etre dans le futur (bugs UI). Dans ce
        # cas months_old <= 0 -> age_weight = 1.0.
        months_old = max(0.0, (reference_date - test.performed_at).days / 30.5)
        if months_old > 24.0:
            age_weight = 0.5 ** ((months_old - 24.0) / 12.0)
            age_quality_flag = f"age_weight_{age_weight:.2f}"

    label = f"reference_test:{test.test_type.value if hasattr(test.test_type, 'value') else test.test_type}"

    out: dict[str, list[dict[str, Any]]] = {}

    test_type = test.test_type
    if hasattr(test_type, "value"):
        test_type_value = test_type.value
    else:
        test_type_value = str(test_type)

    # --- 5K / 10K road test -> p_capacity_test_wkg (informative, R1) ------
    if test_type_value in (ReferenceTestType.ROAD_5K.value, ReferenceTestType.ROAD_10K.value):
        distance_m = test.distance_m
        if distance_m is None:
            # Sensible defaults if the test was logged without a distance.
            distance_m = 5000.0 if test_type_value == ReferenceTestType.ROAD_5K.value else 10000.0
        if distance_m <= 0:
            return {}

        duration_s = test.duration_seconds
        speed_mps = distance_m / duration_s
        if not (MIN_RUN_SPEED_MPS <= speed_mps <= 8.0):
            return {}
        duration_min = duration_s / 60.0
        try:
            fraction = sustainable_fraction(duration_min, durability_alpha=0.12)
        except ValueError:
            return {}
        if fraction <= 0:
            return {}

        # vitesse_test * 3.6 = power equivalent at the test duration.
        # Dividing by sustainable_fraction converts the durable test power
        # into the flat-road peak capacity at vVO2max.
        # For the 10K @ 40 min example: 4.17 m/s * 3.6 / 0.95 ~= 15.8 W/kg.
        p_capacity_wkg = (speed_mps * _MINETTI_COST_FLAT) / fraction
        if not (3.0 <= p_capacity_wkg <= 25.0):
            return {}

        # Std per V2.3 plan: tight, 0.4 W/kg. 5K is slightly noisier because
        # the protocol is shorter and pacing variance higher.
        if test_type_value == ReferenceTestType.ROAD_10K.value:
            std = 0.4 * std_inflation
        else:  # 5K
            std = 0.5 * std_inflation

        capacity_quality_flags = [quality_flag, "controlled_protocol", "informative_only"]
        if age_quality_flag is not None:
            capacity_quality_flags.append(age_quality_flag)
        obs = _build_observation(
            mean=p_capacity_wkg,
            std=std,
            weight=_REFERENCE_TEST_WEIGHT * age_weight,
            source_label=label,
            source_id=test.id,
            source_type="reference_test",
            performed_at=test.performed_at,
            category="reference_test",
            quality_flags=capacity_quality_flags,
        )
        out.setdefault("p_capacity_test_wkg", []).append(obs)

    # --- Long steady test -> informative-only until linked streams exist ---
    elif test_type_value == ReferenceTestType.LONG_STEADY.value:
        # A recorded duration does not measure fatigue resistance. Publishing
        # an alpha centred on a default value would change the engine without
        # evidence. A future bridge may associate this test with an activity
        # stream and then extract an iso-effort Minetti drift.
        return {}

    # --- Hill climb / vertical km -> walk_power_ratio (MVP placeholder) ----
    elif test_type_value in (
        ReferenceTestType.HILL_CLIMB.value,
        ReferenceTestType.VERTICAL_KM.value,
    ):
        # The MVP keeps walk_power_ratio as a prior-only parameter. We still
        # record the test as a usable observation for future use; the
        # downstream updater can ignore it until the model is wired.
        if test.elevation_gain_m and test.duration_seconds and test.elevation_gain_m > 0:
            vertical_speed_mps = test.elevation_gain_m / test.duration_seconds
            # Healthy KV finishers: 0.20-0.45 m/s of vertical speed.
            if 0.05 <= vertical_speed_mps <= 0.80:
                std = 0.10 * std_inflation
                vertical_quality_flags = [quality_flag, "vertical_test"]
                if age_quality_flag is not None:
                    vertical_quality_flags.append(age_quality_flag)
                obs = _build_observation(
                    mean=vertical_speed_mps,
                    std=std,
                    weight=_REFERENCE_TEST_WEIGHT * 0.5 * age_weight,
                    source_label=label,
                    source_id=test.id,
                    source_type="reference_test",
                    performed_at=test.performed_at,
                    category="reference_test",
                    quality_flags=vertical_quality_flags,
                )
                out.setdefault("walk_power_ratio", []).append(obs)

    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_user_activities(
    session: Session,
    user_id: UUID,
    *,
    as_of_date: datetime,
    excluded_ids: set[UUID],
    history_start_date: datetime | None = None,
) -> list[Activity]:
    """Read activities for the user STRICTLY before ``as_of_date``.

    When ``history_start_date`` is provided, also drop activities with
    ``start_date < history_start_date``. The two bounds together define the
    historical window R1 applies (see ``aggregate_observations``).
    """
    statement = select(Activity).where(
        Activity.user_id == user_id,
        Activity.source == ActivitySource.GARMIN.value,
        Activity.start_date < as_of_date,
    )
    if history_start_date is not None:
        statement = statement.where(Activity.start_date >= history_start_date)
    if excluded_ids:
        statement = statement.where(Activity.id.notin_(excluded_ids))
    return list(session.exec(statement).all())


def _fetch_validation_index(
    session: Session,
    user_id: UUID,
    activity_ids: set[UUID],
) -> dict[UUID, RaceValidationReference]:
    """Return a mapping ``activity_id -> RaceValidationReference``.

    Empty when no activity has been qualified yet. Used by
    :func:`categorize_activity` to differentiate ``official_clean`` from
    documented incidents.
    """
    if not activity_ids:
        return {}
    statement = select(RaceValidationReference).where(
        RaceValidationReference.user_id == user_id,
        RaceValidationReference.activity_id.in_(activity_ids),
    )
    rows = session.exec(statement).all()
    return {row.activity_id: row for row in rows}


def _fetch_user_reference_tests(
    session: Session,
    user_id: UUID,
    *,
    as_of_date: datetime,
    history_start_date: datetime | None = None,
) -> list[ReferenceTest]:
    """Read reference tests strictly before ``as_of_date``.

    When ``history_start_date`` is provided, also drop tests with
    ``performed_at < history_start_date``. Mirrors the activities window.
    """
    statement = select(ReferenceTest).where(
        ReferenceTest.user_id == user_id,
        ReferenceTest.performed_at < as_of_date,
        ReferenceTest.quality_status != ReferenceTestQuality.INVALIDATED,
    )
    if history_start_date is not None:
        statement = statement.where(ReferenceTest.performed_at >= history_start_date)
    return list(session.exec(statement).all())


def _is_running_activity(activity: Activity) -> bool:
    """Whether the activity is a running effort (Run or TrailRun)."""
    effective_type = activity.activity_type_override or activity.activity_type
    if effective_type is None:
        return False
    value = effective_type.value if hasattr(effective_type, "value") else str(effective_type)
    return value in (ActivityType.RUN.value, ActivityType.TRAIL_RUN.value, ActivityType.VIRTUAL_RUN.value)


def _is_road_reference_activity(activity: Activity) -> bool:
    """Whether an activity may calibrate the route/flat reference power.

    Terrain penalties are applied separately by the physics engine. Explicit
    trail activities therefore cannot feed ``p_ref_steady_wkg`` even when
    local grade samples are flat.
    """
    effective_type = activity.activity_type_override or activity.activity_type
    if effective_type is None:
        return False
    value = effective_type.value if hasattr(effective_type, "value") else str(effective_type)
    return value in (ActivityType.RUN.value, ActivityType.VIRTUAL_RUN.value)


def _is_trail_like(activity: Activity) -> bool:
    """Heuristic: D+/km >= 15 m flags the activity as trail-like."""
    distance_m = float(activity.distance or 0)
    if distance_m <= 0:
        return False
    distance_km = distance_m / 1000.0
    elevation = float(activity.total_elevation_gain or 0)
    # Also treat explicit TrailRun activity type as trail.
    effective_type = activity.activity_type_override or activity.activity_type
    if effective_type is not None:
        value = effective_type.value if hasattr(effective_type, "value") else str(effective_type)
        if value == ActivityType.TRAIL_RUN.value:
            return True
    return (elevation / distance_km) >= TRAIL_ELEVATION_PER_KM_THRESHOLD


def _has_minimum_run_fields(activity: Activity) -> bool:
    """Activity must have a positive distance + moving_time."""
    if not activity.distance or activity.distance <= 0:
        return False
    if not activity.moving_time or activity.moving_time <= 0:
        return False
    return True


def _activity_label(activity: Activity) -> str:
    """Short human label used in source_label fields."""
    name = activity.name or "Activity"
    iso_date = activity.start_date.date().isoformat() if activity.start_date else "?"
    return f"activity:{name}@{iso_date}"


def _activity_elevation_per_km(activity: Activity) -> float:
    """Return the average D+ per km for an activity (m/km)."""
    distance_km = float(activity.distance or 0) / 1000.0
    if distance_km <= 0:
        return 999.0
    return float(activity.total_elevation_gain or 0) / distance_km


def _normalize_streams(raw: Any) -> Optional[dict[str, Any]]:
    """Decode the ``streams_data`` column into a dict, or None if unusable.

    Mirrors the logic of ``calibration_service._normalize_stream`` so the two
    services agree on what counts as "streams available".
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        if raw.strip().lower() == "null":
            return None
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, dict) and raw:
        return raw
    return None


def _stream_array(streams: dict[str, Any], key: str) -> list[Any]:
    """Extract the inner ``data`` list from a Strava stream payload."""
    value = streams.get(key)
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    return value if isinstance(value, list) else []


def _stream_quality_summary(
    activity: Activity,
) -> tuple[bool, float, Optional[float], bool]:
    """Summarise stream quality for an activity.

    Returns ``(streams_ok, sample_coverage, hr_std, has_full_streams)``.

    - ``streams_ok``: streams_data is decodable AND has at least HR + speed.
    - ``sample_coverage``: ratio (samples found / expected samples).
    - ``hr_std``: standard deviation of the central 60% of HR samples
      (estimator of HR stability over the activity), or None if too few HR
      samples are available.
    - ``has_full_streams``: ``streams_ok`` plus coverage >= 0.5 plus HR+speed
      lists both non-empty.
    """
    streams = _normalize_streams(activity.streams_data)
    if streams is None:
        return (False, 0.0, None, False)

    heartrate_raw = _stream_array(streams, "heartrate")
    velocity_raw = _stream_array(streams, "velocity_smooth")

    heartrate = [float(v) for v in heartrate_raw if v is not None]
    velocity = [float(v) for v in velocity_raw if v is not None]
    if not heartrate or not velocity:
        return (False, 0.0, None, False)

    expected_samples = max(1, int(activity.moving_time or 0))
    coverage = min(1.0, min(len(heartrate), len(velocity)) / expected_samples)

    plausible_hr = [hr for hr in heartrate if 60.0 <= hr <= 230.0]
    hr_std: Optional[float] = None
    if len(plausible_hr) >= 60:
        # Use the central 60% to avoid warm-up/cool-down dominating the std.
        plausible_hr.sort()
        n = len(plausible_hr)
        lo = int(n * 0.20)
        hi = int(n * 0.80)
        window = plausible_hr[lo:hi] or plausible_hr
        if len(window) >= 2:
            try:
                hr_std = float(statistics.stdev(window))
            except statistics.StatisticsError:
                hr_std = None

    has_full_streams = coverage >= 0.5
    streams_ok = True
    return (streams_ok, coverage, hr_std, has_full_streams)


def _extract_flat_speed_samples(
    activity: Activity,
    streams: dict[str, Any],
) -> tuple[list[float], bool]:
    """Return the list of flat-road speed samples (m/s) for one activity.

    Mirrors the V2 calibration_service behaviour:

    - HR must be in ``[60, 230]`` bpm.
    - Speed must be in ``[MIN_RUN_SPEED_MPS, MAX_RUN_SPEED_MPS]``.
    - When ``grade_smooth`` is available, samples with
      ``|grade_smooth| > 2 %`` are dropped (grade is stored in percent and
      converted to a fraction before the comparison).
    - When ``grade_smooth`` is unavailable, samples are kept only if the
      activity itself is flat enough (D+/km <= 25 m).

    Returns a ``(samples, used_stream_grade)`` tuple where
    ``used_stream_grade`` indicates whether sample-level grade filtering was
    applied.
    """
    heartrate_raw = _stream_array(streams, "heartrate")
    velocity_raw = _stream_array(streams, "velocity_smooth")
    grade_raw = _stream_array(streams, "grade_smooth")

    heartrate = [float(v) if v is not None else None for v in heartrate_raw]
    velocity = [float(v) if v is not None else None for v in velocity_raw]
    grade_percent = [float(v) if v is not None else None for v in grade_raw]

    has_grade = bool(grade_percent)
    activity_is_flat_enough = _activity_elevation_per_km(activity) <= 25.0

    limit = min(len(heartrate), len(velocity))
    if limit < 60:
        return ([], has_grade)

    samples: list[float] = []
    for index in range(limit):
        hr = heartrate[index]
        speed = velocity[index]
        if hr is None or speed is None:
            continue
        if not (60.0 <= hr <= 230.0):
            continue
        if not (MIN_RUN_SPEED_MPS <= speed <= MAX_RUN_SPEED_MPS):
            continue

        if has_grade and index < len(grade_percent):
            g_pct = grade_percent[index]
            if g_pct is None:
                continue
            # grade_smooth is stored in percent; convert to a fraction before
            # comparing against the flat threshold.
            g_frac = g_pct / 100.0
            if abs(g_frac) > FLAT_GRADE_FRACTION_THRESHOLD:
                continue
        elif not activity_is_flat_enough:
            continue

        samples.append(speed)

    return (samples, has_grade)


def _quartile_speed_decline(activity: Activity) -> Optional[float]:
    """Return the relative speed decline between Q1 and Q4 of the activity.

    Computed from the velocity_smooth stream. Returns ``None`` when the
    stream is unavailable or too short to estimate quartiles.

    V2.3.1 (R2): kept for diagnostic/audit purposes only. The production
    durability extraction now uses :func:`_minetti_normalised_alpha`.
    """
    streams = _normalize_streams(activity.streams_data)
    if streams is None:
        return None
    velocity = [
        float(v)
        for v in _stream_array(streams, "velocity_smooth")
        if v is not None and float(v) > 0.5
    ]
    if len(velocity) < 200:
        # Too few samples to compute reliable quartiles.
        return None
    n = len(velocity)
    q1 = velocity[: n // 4]
    q4 = velocity[3 * n // 4 :]
    if len(q1) < 20 or len(q4) < 20:
        return None
    try:
        q1_speed = statistics.median(q1)
        q4_speed = statistics.median(q4)
    except statistics.StatisticsError:
        return None
    if q1_speed <= 0:
        return None
    decline = (q1_speed - q4_speed) / q1_speed
    # Drop pathologically large speed-ups (negative decline beyond -5% is
    # almost always a course profile effect, not athlete behaviour).
    if decline < -0.05:
        return 0.0
    return max(0.0, decline)


def _minetti_normalised_alpha(
    activity: Activity,
    *,
    p_ref_steady_wkg: float,
) -> Optional[float]:
    """Estimate durability_alpha from Minetti iso-effort ratios (R2).

    Logic ported from :func:`fatigue_model.build_fatigue_profile` (V2
    reference) and adapted for the per-activity aggregator path used by
    V2.3.1. The fundamental signal is:

    - For every sample i, compute the iso-effort pace at the local grade
      using the user's ``p_ref_steady_wkg`` posterior (R1) and the
      Minetti cost polynomial: ``v_expected = p_ref / minetti_cost(g)``.
    - The iso-effort ratio ``r_i = v_expected / v_actual`` is > 1 when
      the athlete moves slower than the reference and < 1 when faster.
    - Compare the median ratio in an "early" window (warmed-up but fresh,
      hours [0.25, 1.0]) against the median in a "late" window (post-2h
      where durability dominates). The relative increase between the two,
      divided by the cumulative fatigue level, yields alpha.

    Returns the raw alpha estimate (before clamping) or ``None`` if the
    streams are insufficient or the windows would be too short to trust
    the medians.
    """
    streams = _normalize_streams(activity.streams_data)
    if streams is None:
        return None
    time_raw = _stream_array(streams, "time")
    velocity_raw = _stream_array(streams, "velocity_smooth")
    grade_raw = _stream_array(streams, "grade_smooth")
    if not time_raw or not velocity_raw or not grade_raw:
        return None

    # Coerce to floats, dropping None entries to keep parallel indexing.
    try:
        time = [float(v) for v in time_raw if v is not None]
        velocity = [float(v) for v in velocity_raw if v is not None]
        grade_percent = [float(v) for v in grade_raw if v is not None]
    except (TypeError, ValueError):
        return None
    # Need at least 10 minutes of stream to compute a meaningful ratio.
    if len(time) < 600 or len(velocity) < 600 or len(grade_percent) < 600:
        return None

    limit = min(len(time), len(velocity), len(grade_percent))
    normalized_ratios: list[tuple[float, float]] = []
    cumulative_gain = 0.0
    cumulative_loss = 0.0
    previous_time = time[0]
    # Initial grade tracker uses the unit-corrected fraction (R0 fix).
    previous_grade = stream_grade_fraction(grade_percent[0])

    for index in range(limit):
        speed = velocity[index]
        current_time = time[index]
        if speed < 1.0 or current_time <= 0:
            continue
        grade_fraction = stream_grade_fraction(grade_percent[index])
        if index > 0:
            elapsed_delta = max(0.0, current_time - previous_time)
            distance_delta = speed * elapsed_delta
            elevation_delta = previous_grade * distance_delta
            if elevation_delta > 0:
                cumulative_gain += elevation_delta
            else:
                cumulative_loss += abs(elevation_delta)
        previous_time = current_time
        previous_grade = grade_fraction

        cost = _minetti_run_cost(grade_fraction)
        if cost <= 0:
            continue
        expected_speed = p_ref_steady_wkg / cost
        if expected_speed <= 0:
            continue
        # ``hours`` is the elapsed time at this sample, used to slice the
        # early / late windows.
        hours = current_time / 3600.0
        ratio = expected_speed / speed
        normalized_ratios.append((hours, ratio))

    if not normalized_ratios:
        return None

    early = [r for h, r in normalized_ratios if 0.25 <= h <= 1.0]
    # Late window: prefer post-2h samples (matches V2). Fallback to the
    # last third of samples when the activity is shorter than 2h (R2 uses
    # a 30-min minimum so this fallback is the only path for short runs).
    late_post_two_h = [r for h, r in normalized_ratios if h >= 2.0]
    if late_post_two_h:
        late = late_post_two_h
    else:
        n = len(normalized_ratios)
        # Last third of samples by index (ordered chronologically).
        late = [r for _, r in normalized_ratios[2 * n // 3 :]]
    if not early:
        # Fallback: first third of samples when warm-up window is empty.
        n = len(normalized_ratios)
        early = [r for _, r in normalized_ratios[: n // 3]]
    # Require enough samples in each window to trust the medians. 60
    # samples ~ 1 minute at 1 Hz; less than that is noise.
    if len(early) < 60 or len(late) < 60:
        return None

    early_median = statistics.median(early)
    late_median = statistics.median(late)
    if early_median <= 0:
        return None

    final_time_min = max(time[:limit]) / 60.0
    fatigue_level = default_fatigue_level(
        final_time_min, cumulative_gain, cumulative_loss
    )
    # Below 5 % fatigue load the alpha is dominated by noise; skip.
    if fatigue_level <= 0.05:
        return None

    relative_increase = (late_median / early_median) - 1.0
    alpha = relative_increase / fatigue_level
    return alpha


def _estimate_preliminary_p_ref_steady(
    p_ref_obs: list[dict[str, Any]],
) -> float:
    """Pick a preliminary ``p_ref_steady_wkg`` for durability extraction (R2).

    Durability extraction needs a steady-power reference *before* the
    Bayesian posterior is computed (the orchestrator only fuses observations
    later, in :func:`v2_3_prediction_service.predict_event_v2_3`). To break
    the chicken-and-egg, we use the median of the per-activity
    ``p_ref_steady_wkg`` observations already extracted in the same pass.
    When no observation is available we fall back to a documented default
    (``DEFAULT_P_REF_STEADY_WKG = 9.0 W/kg``, the V2 ``p_run_base``).

    This is a pragmatic approximation: the durability alpha attached to
    each activity will be slightly off if the preliminary estimate is far
    from the posterior. In practice, the posterior is dominated by the
    same observations used here (plus the prior), so the difference is
    second-order. The full Bayesian feedback loop is out of scope for R2
    and tracked separately.
    """
    if not p_ref_obs:
        return DEFAULT_P_REF_STEADY_WKG
    means: list[float] = []
    for obs in p_ref_obs:
        try:
            mean_val = float(obs.get("mean"))
        except (TypeError, ValueError):
            continue
        if 3.0 <= mean_val <= 25.0:
            means.append(mean_val)
    if not means:
        return DEFAULT_P_REF_STEADY_WKG
    return statistics.median(means)


def _estimate_fcmax_from_history(
    categorised: list[tuple[Activity, str]],
    *,
    debug_trace: dict[str, Any] | None = None,
) -> float | None:
    """Estimate FCmax from the user's history (R1).

    V2.3.1 (FIX 5) : percentile 99.5 robuste face aux pics capteur isoles
    -------------------------------------------------------------------
    L'estimation FCmax doit etre robuste a deux pieges symetriques :

    1. *Pool tempo / steady* (entrainements modere uniquement) : le
       percentile 99.5 est sous la vraie FCmax. ``activity.max_heartrate``
       (atteinte un jour de seance intense) est alors un meilleur estimateur.
    2. *Pic capteur isole* (5 s de saturation a 220 bpm) :
       ``activity.max_heartrate`` retourne la valeur aberrante alors que le
       percentile 99.5 (qui est statistique) absorbe le pic. Le percentile
       reste donc plus fiable.

    Strategie retenue (FIX 5) :

    - Si le pool contient >= 500 echantillons : calculer le percentile 99.5.
      Comparer avec ``max(activity.max_heartrate)`` :

      * Si ``activity.max_heartrate <= percentile + SPIKE_TOLERANCE_BPM``
        (= 25 bpm), les deux estimateurs sont coherents -> retenir
        ``max(percentile, activity.max_heartrate)`` (preserve la couverture
        sur pool tempo).
      * Si ``activity.max_heartrate > percentile + SPIKE_TOLERANCE_BPM``,
        la divergence est suspectee provenir d'un pic capteur isole ->
        retenir le percentile 99.5 SEUL (l'activity.max_heartrate aberrante
        est ignoree).

    - Sinon (pool < 500 echantillons) : fallback controle vers
      ``max(activity.max_heartrate)`` sur la fenetre.
    - Fallback final : 190 bpm (adulte population-typique).
    - Une borne de plausibilite haute (<= 220 bpm) plafonne toutes les
      valeurs.

    La source effectivement retenue est tracee dans
    ``debug_trace["fcmax_source"]`` (valeurs : ``"streams_p995"``,
    ``"streams_p995_with_activity_max"``, ``"activity_max_fallback"``,
    ``"hard_fallback"``, ``"none"``).
    """
    pool: list[float] = []
    fallback_max: float = 0.0
    for activity, _category in categorised:
        streams = _normalize_streams(activity.streams_data)
        if streams is not None:
            for raw in _stream_array(streams, "heartrate"):
                if raw is None:
                    continue
                try:
                    hr = float(raw)
                except (TypeError, ValueError):
                    continue
                if 60.0 <= hr <= 230.0:
                    pool.append(hr)
        if activity.max_heartrate is not None:
            try:
                mx = float(activity.max_heartrate)
                if 60.0 <= mx <= 230.0 and mx > fallback_max:
                    fallback_max = mx
            except (TypeError, ValueError):
                continue

    # FCMAX_STREAM_SAMPLES_THRESHOLD : seuil au-dela duquel le percentile 99.5
    # est statistiquement fiable. 500 echantillons (~ 8 min d'enregistrement
    # 1 Hz) suffit pour stabiliser un quantile haut.
    FCMAX_STREAM_SAMPLES_THRESHOLD = 500
    # A point maximum may complement a moderate stream pool only when it is
    # close enough to the robust percentile. Larger divergence is treated as
    # an isolated sensor peak.
    SPIKE_TOLERANCE_BPM = 25.0
    # Borne sanity de retour : toutes les estimations sont plafonnees a
    # 220 bpm pour rejeter les valeurs aberrantes en sortie.
    FCMAX_SANITY_UPPER_BOUND = 220.0
    HARD_FALLBACK_BPM = 190.0

    def _record_source(source: str) -> None:
        if debug_trace is not None:
            debug_trace["fcmax_source"] = source

    percentile_estimate: float | None = None
    if len(pool) >= FCMAX_STREAM_SAMPLES_THRESHOLD:
        pool.sort()
        k = 0.995 * (len(pool) - 1)
        lo_idx = int(math.floor(k))
        hi_idx = int(math.ceil(k))
        if lo_idx == hi_idx:
            percentile_estimate = float(pool[lo_idx])
        else:
            percentile_estimate = float(
                pool[lo_idx] + (pool[hi_idx] - pool[lo_idx]) * (k - lo_idx)
            )

    # FIX 5 : si le percentile est disponible, le combiner avec
    # ``activity.max_heartrate`` only when the two measurements are coherent.
    if percentile_estimate is not None:
        fallback_clean = (
            fallback_max
            if fallback_max <= percentile_estimate + SPIKE_TOLERANCE_BPM
            else 0.0
        )
        if fallback_clean > 0:
            combined = max(percentile_estimate, fallback_clean)
            bounded = min(combined, FCMAX_SANITY_UPPER_BOUND)
            _record_source("streams_p995_with_activity_max")
            return float(bounded)
        # max_heartrate suspect ou absent : retenir le percentile seul.
        bounded = min(percentile_estimate, FCMAX_SANITY_UPPER_BOUND)
        _record_source("streams_p995")
        return float(bounded)

    # Pool de streams insuffisant : fallback sur activity.max_heartrate.
    if fallback_max > 0:
        _record_source("activity_max_fallback")
        return float(min(fallback_max, FCMAX_SANITY_UPPER_BOUND))

    if pool:
        # Tres peu d'echantillons mais quelques uns : retourner le max plutot
        # qu'un percentile non fiable. Trace comme fallback.
        _record_source("activity_max_fallback")
        return float(min(max(pool), FCMAX_SANITY_UPPER_BOUND))

    # Aucune donnee : prior populationnel.
    _record_source("hard_fallback")
    return HARD_FALLBACK_BPM


def _resolve_fcmax_for_activity(
    activity: Activity,
    fcmax_estimate: float | None,
) -> float | None:
    """Pick the most credible FCmax estimate for one activity.

    Prefer the user-level estimate computed once by
    :func:`_estimate_fcmax_from_history`. When None, fall back to
    ``activity.max_heartrate`` and finally to 190 bpm.
    """
    if fcmax_estimate is not None and 110.0 <= fcmax_estimate <= 230.0:
        return float(fcmax_estimate)
    if activity.max_heartrate is not None:
        try:
            mx = float(activity.max_heartrate)
            if 110.0 <= mx <= 230.0:
                return mx
        except (TypeError, ValueError):
            pass
    return 190.0


def _extract_flat_speed_samples_in_band(
    activity: Activity,
    streams: dict[str, Any],
    *,
    low_hr: float,
    high_hr: float,
) -> list[float]:
    """Return flat-road speed samples whose simultaneous HR lies in [low, high].

    Combines the V2 flat-road filter (grade < 2 % or activity globally flat)
    with the V2.3.1 reference-band filter ([low_hr, high_hr]). Used by
    :func:`extract_p_ref_steady_observation`.
    """
    heartrate_raw = _stream_array(streams, "heartrate")
    velocity_raw = _stream_array(streams, "velocity_smooth")
    grade_raw = _stream_array(streams, "grade_smooth")

    if not heartrate_raw or not velocity_raw:
        return []

    has_grade = bool(grade_raw)
    activity_is_flat_enough = _activity_elevation_per_km(activity) <= 25.0

    limit = min(len(heartrate_raw), len(velocity_raw))
    if limit < 60:
        return []

    samples: list[float] = []
    for index in range(limit):
        hr_raw = heartrate_raw[index]
        speed_raw = velocity_raw[index]
        if hr_raw is None or speed_raw is None:
            continue
        try:
            hr = float(hr_raw)
            speed = float(speed_raw)
        except (TypeError, ValueError):
            continue
        if not (60.0 <= hr <= 230.0):
            continue
        if not (MIN_RUN_SPEED_MPS <= speed <= MAX_RUN_SPEED_MPS):
            continue
        if not (low_hr <= hr <= high_hr):
            continue
        if has_grade and index < len(grade_raw):
            g_raw = grade_raw[index]
            if g_raw is None:
                continue
            try:
                g_pct = float(g_raw)
            except (TypeError, ValueError):
                continue
            if abs(g_pct / 100.0) > FLAT_GRADE_FRACTION_THRESHOLD:
                continue
        elif not activity_is_flat_enough:
            continue
        samples.append(speed)
    return samples


def _build_p_ref_steady_observations(
    categorised: list[tuple[Activity, str]],
    *,
    fcmax_estimate: float | None,
    accept_sparse: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the p_ref_steady_wkg observation list with FC-band selection (R1).

    Decision logic (per R0 livrable 5)
    ----------------------------------
    1. First pass with the principal band ``[0.72, 0.78]``. Each candidate
       activity is sampled to count contributions inside the band.
    2. If total samples >= ``MIN_SAMPLES_IN_BAND`` AND distinct activities
       >= ``MIN_ACTIVITIES_IN_BAND``, accept the principal band. Each
       contributing activity gets its observation with the standard
       per-category std.
    3. Otherwise switch to the fallback band ``[0.68, 0.82]`` and recompute.
       Each contributing activity gets its observation with
       ``std *= 1.5`` and the ``fc_band_fallback`` flag set in
       quality_flags.
    4. If even the fallback band fails to reach the minimums, return an
       empty list and let the prior dominate the posterior.

    Returns (observation_list, meta) where ``meta`` always contains:
    ``fc_band_used`` (tuple), ``fc_band_fallback`` (bool),
    ``samples_in_band`` (int), ``activities_in_band`` (int).
    """
    # First pass: principal band.
    primary_obs, primary_samples, primary_activities = _try_band(
        categorised,
        fcmax_estimate=fcmax_estimate,
        band=FC_BAND_PRIMARY,
        std_multiplier=1.0,
        fallback_used=False,
    )
    if (
        primary_samples >= MIN_SAMPLES_IN_BAND
        and primary_activities >= MIN_ACTIVITIES_IN_BAND
    ):
        return (
            primary_obs,
            {
                "fc_band_used": FC_BAND_PRIMARY,
                "fc_band_fallback": False,
                "samples_in_band": primary_samples,
                "activities_in_band": primary_activities,
                "sparse_evidence_accepted": False,
            },
        )

    # Second pass: fallback band with inflated std.
    fallback_obs, fallback_samples, fallback_activities = _try_band(
        categorised,
        fcmax_estimate=fcmax_estimate,
        band=FC_BAND_FALLBACK,
        std_multiplier=FALLBACK_STD_INFLATION,
        fallback_used=True,
    )
    if (
        fallback_samples >= MIN_SAMPLES_IN_BAND
        and fallback_activities >= MIN_ACTIVITIES_IN_BAND
    ):
        return (
            fallback_obs,
            {
                "fc_band_used": FC_BAND_FALLBACK,
                "fc_band_fallback": True,
                "samples_in_band": fallback_samples,
                "activities_in_band": fallback_activities,
                "sparse_evidence_accepted": False,
            },
        )

    # V3: an isolated but well-sampled Garmin route session is evidence, not
    # an absence of evidence. Recompute with a wider standard deviation so it
    # influences the prior without claiming multi-session certainty.
    if (
        accept_sparse
        and fallback_samples >= MIN_SAMPLES_IN_BAND
        and fallback_activities >= 1
    ):
        sparse_obs, sparse_samples, sparse_activities = _try_band(
            categorised,
            fcmax_estimate=fcmax_estimate,
            band=FC_BAND_FALLBACK,
            std_multiplier=FALLBACK_STD_INFLATION * SPARSE_STD_INFLATION,
            fallback_used=True,
        )
        for observation in sparse_obs:
            observation.setdefault("quality_flags", []).append("sparse_evidence")
        return (
            sparse_obs,
            {
                "fc_band_used": FC_BAND_FALLBACK,
                "fc_band_fallback": True,
                "samples_in_band": sparse_samples,
                "activities_in_band": sparse_activities,
                "sparse_evidence_accepted": True,
            },
        )

    # Even the fallback band failed: let the prior dominate.
    return (
        [],
        {
            "fc_band_used": FC_BAND_FALLBACK,
            "fc_band_fallback": True,
            "samples_in_band": fallback_samples,
            "activities_in_band": fallback_activities,
            "sparse_evidence_accepted": False,
        },
    )


def _try_band(
    categorised: list[tuple[Activity, str]],
    *,
    fcmax_estimate: float | None,
    band: tuple[float, float],
    std_multiplier: float,
    fallback_used: bool,
) -> tuple[list[dict[str, Any]], int, int]:
    """Run :func:`extract_p_ref_steady_observation` over the categorised pool.

    Returns ``(observations, total_samples, activities_contributing)``.
    """
    obs_list: list[dict[str, Any]] = []
    total_samples = 0
    activities_contributing = 0
    for activity, category in categorised:
        obs, meta = extract_p_ref_steady_observation(
            activity,
            category,
            fcmax_estimate=fcmax_estimate,
            fc_band=band,
            std_multiplier=std_multiplier,
            fallback_used=fallback_used,
        )
        # Count samples / activities even when the obs is rejected (e.g.
        # implausible median), so the decision picks the band that yields the
        # richest evidence pool. This matches the audit-script logic and
        # avoids hiding a usable principal band behind a single outlier.
        if meta.get("samples_in_band"):
            total_samples += int(meta["samples_in_band"])
            activities_contributing += 1
        if obs is not None:
            obs_list.append(obs)
    return (obs_list, total_samples, activities_contributing)


def _build_observation(
    *,
    mean: float,
    std: float,
    weight: float,
    source_label: str,
    source_id: Optional[UUID],
    source_type: str,
    performed_at: Optional[datetime],
    category: str,
    quality_flags: list[str],
) -> dict[str, Any]:
    """Build a fully-shaped observation dict.

    Centralised so every observation in this module has the same key set.
    See :data:`_OBSERVATION_KEYS` for the canonical contract.
    """
    return {
        "mean": float(mean),
        "std": float(std),
        "weight": float(weight),
        "source_label": str(source_label),
        "source_id": str(source_id) if source_id is not None else None,
        "source_type": str(source_type),
        "performed_at": performed_at.isoformat() if isinstance(performed_at, datetime) else None,
        "category": str(category),
        "quality_flags": list(quality_flags),
    }


__all__ = [
    "aggregate_observations",
    "categorize_activity",
    "extract_p_ref_steady_observation",
    "extract_p_run_observation",
    "extract_durability_alpha_observation",
    "extract_trail_cost_factor_observation",
    "extract_fc_max_observation",
    "convert_reference_test_to_observations",
    "TRAIL_ELEVATION_PER_KM_THRESHOLD",
    "SUBMAX_MIN_DURATION_S",
    "SUBMAX_HR_STD_THRESHOLD",
    "FLAT_GRADE_FRACTION_THRESHOLD",
    "MIN_RUN_SPEED_MPS",
    "MAX_RUN_SPEED_MPS",
    "NON_SCORING_VALIDATION_CATEGORIES",
    "SCORING_VALIDATION_CATEGORIES",
    "TRAIL_FACTOR_EXCLUDED_CATEGORIES",
    "FC_BAND_PRIMARY",
    "FC_BAND_FALLBACK",
    "MIN_SAMPLES_IN_BAND",
    "MIN_ACTIVITIES_IN_BAND",
    "FALLBACK_STD_INFLATION",
    "SPARSE_EVIDENCE_POLICY",
    "SPARSE_STD_INFLATION",
    "DEFAULT_HISTORY_WINDOW_DAYS",
    "DEFAULT_P_REF_STEADY_WKG",
    "DURABILITY_MIN_DURATION_S",
    "DURABILITY_WINDOW_S",
]
