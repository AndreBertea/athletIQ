"""Compare V1 RandomForest vs V2 physique vs V2.2 vs V2.3.1 vs V3 vs réel.

Backtest chronologique strict : pour chaque cas, as_of_date = race_datetime
et l'activité cible est exclue de l'historique utilisé.

V2.3.1 = moteur physique + reference route/plate bayesienne
       (intervalle P10/P90 honnête, priors populationnels) SANS le bug d'inversion
       Daniels-VDOT qui sur-estimait V2.2.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "sqlite:///./stridedelta.db")
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session

from app.core.database import engine as db_engine
from app.domain.services.race_predictor.v2_2_prediction_service import predict_v2_2
from app.domain.services.race_predictor.v2_3_prediction_service import predict_v2_3
from app.domain.services.race_predictor.v3_prediction_service import predict_v3

# Réutilise la définition des cases + run_v1 + run_v2 + helpers du script existant
from compare_golden_set import (  # type: ignore
    CASES,
    USER_ID,
    MAX_HISTORY_DAYS,
    reconstruct_gpx_from_streams,
    run_v1,
    run_v2,
    fmt_min,
    fmt_pace,
)
from app.domain.services.race_predictor.calibration_service import build_calibration
from app.domain.services.race_predictor.fatigue_model import build_fatigue_profile


def run_v22(
    gpx_text: str,
    session: Session,
    *,
    case,
    as_of_date: datetime,
    excluded_activity_ids: set[UUID],
) -> dict:
    """Appel V2.2 avec backtest chronologique strict."""
    result = predict_v2_2(
        session=session,
        user_id=USER_ID,
        gpx_text=gpx_text,
        race_datetime=case.race_datetime,
        effort_mode=case.effort_mode,
        analysis_mode=case.analysis_mode,
        target_heartrate=None,
        weather_mode="auto",
        manual_temperature_c=None,
        ravito_mode="auto",
        custom_ravitos=None,
        as_of_date=as_of_date,
        excluded_activity_ids=excluded_activity_ids,
    )

    summary = result.get("summary", {})
    uncertainty = result.get("uncertainty", {})
    athlete_model = result.get("athlete_model", {})
    posterior = athlete_model.get("posterior", {})
    evidence_summary = athlete_model.get("evidence_summary", {})
    event_intensity = result.get("event_intensity", {})

    return {
        "moving_time_min": float(summary.get("moving_time_min") or result.get("moving_time_min") or 0),
        "total_pause_min": float(summary.get("total_pause_min") or result.get("total_pause_min") or 0),
        "total_time_min": float(summary.get("total_time_min") or result.get("total_time_min") or 0),
        "uncertainty_p10_total": uncertainty.get("total_time", {}).get("p10"),
        "uncertainty_p50_total": uncertainty.get("total_time", {}).get("p50"),
        "uncertainty_p90_total": uncertainty.get("total_time", {}).get("p90"),
        "uncertainty_p10_moving": uncertainty.get("moving_time", {}).get("p10"),
        "uncertainty_p50_moving": uncertainty.get("moving_time", {}).get("p50"),
        "uncertainty_p90_moving": uncertainty.get("moving_time", {}).get("p90"),
        "p_capacity_wkg": event_intensity.get("capacity_wkg"),
        "p_event_wkg": event_intensity.get("target_power_wkg"),
        "sustainable_fraction": event_intensity.get("sustainable_fraction"),
        "iterations": len(event_intensity.get("iterations", [])),
        "converged": event_intensity.get("converged"),
        "flat_capacity_mean": (posterior.get("flat_capacity_mps") or {}).get("mean"),
        "flat_capacity_std": (posterior.get("flat_capacity_mps") or {}).get("std"),
        "trail_cost_factor_mean": (posterior.get("trail_cost_factor") or {}).get("mean"),
        "durability_alpha_mean": (posterior.get("durability_alpha") or {}).get("mean"),
        "evidence_count": evidence_summary.get("total_observations_count"),
        "outliers_count": evidence_summary.get("outliers_detected"),
        "profile_present": athlete_model.get("profile_present", False),
    }


def run_v23(
    gpx_text: str,
    session: Session,
    *,
    case,
    as_of_date: datetime,
    excluded_activity_ids: set[UUID],
) -> dict:
    """Appel V2.3.1 avec backtest chronologique strict."""
    result = predict_v2_3(
        session=session,
        user_id=USER_ID,
        gpx_text=gpx_text,
        race_datetime=case.race_datetime,
        effort_mode=case.effort_mode,
        analysis_mode=case.analysis_mode,
        target_heartrate=None,
        weather_mode="auto",
        manual_temperature_c=None,
        ravito_mode="auto",
        custom_ravitos=None,
        as_of_date=as_of_date,
        excluded_activity_ids=excluded_activity_ids,
    )

    summary = result.get("summary", {})
    uncertainty = result.get("uncertainty", {})
    athlete_model = result.get("athlete_model", {})
    posterior = athlete_model.get("posterior", {})
    evidence_summary = athlete_model.get("evidence_summary", {})
    physics_inputs = result.get("physics_inputs", {})

    p_run = posterior.get("p_run_wkg") or {}
    durability = posterior.get("durability_alpha") or {}
    trail = posterior.get("trail_cost_factor") or {}
    fcmax = posterior.get("fc_max_bpm") or {}

    return {
        "moving_time_min": float(summary.get("moving_time_min") or result.get("moving_time_min") or 0),
        "total_pause_min": float(summary.get("total_pause_min") or result.get("total_pause_min") or 0),
        "total_time_min": float(summary.get("total_time_min") or result.get("total_time_min") or 0),
        "uncertainty_p10_total": uncertainty.get("total_time", {}).get("p10"),
        "uncertainty_p50_total": uncertainty.get("total_time", {}).get("p50"),
        "uncertainty_p90_total": uncertainty.get("total_time", {}).get("p90"),
        "uncertainty_p10_moving": uncertainty.get("moving_time", {}).get("p10"),
        "uncertainty_p50_moving": uncertainty.get("moving_time", {}).get("p50"),
        "uncertainty_p90_moving": uncertainty.get("moving_time", {}).get("p90"),
        "p_run_wkg_mean": p_run.get("mean"),
        "p_run_wkg_std": p_run.get("std"),
        "p_run_evidence_count": p_run.get("evidence_count"),
        "durability_alpha_mean": durability.get("mean"),
        "trail_cost_factor_mean": trail.get("mean"),
        "fc_max_mean": fcmax.get("mean"),
        "evidence_count": evidence_summary.get("total_observations_count"),
        "outliers_count": evidence_summary.get("outliers_detected"),
        "profile_present": athlete_model.get("profile_present", False),
        "p_run_wkg_used": physics_inputs.get("p_run_wkg_used"),
        "trail_factor_used": physics_inputs.get("trail_factor_used"),
        "fatigue_alpha_used": physics_inputs.get("fatigue_alpha_used"),
        "using_legacy_aggregator": (result.get("debug_trace") or {}).get(
            "using_legacy_observation_aggregator", False
        ),
        "prior_only_no_p_ref_evidence": (result.get("debug_trace") or {}).get(
            "prior_only_no_p_ref_evidence", False
        ),
        "p_ref_steady_source": (result.get("debug_trace") or {}).get(
            "p_ref_steady_source"
        ),
        "aggregator": (result.get("debug_trace") or {}).get("aggregator", {}),
    }


def run_v3(
    gpx_text: str,
    session: Session,
    *,
    case,
    as_of_date: datetime,
    excluded_activity_ids: set[UUID],
) -> dict:
    """Appel V3 avec evidence Garmin sparse ponderee et RF encore gate."""
    result = predict_v3(
        session=session,
        user_id=USER_ID,
        gpx_text=gpx_text,
        race_datetime=case.race_datetime,
        effort_mode=case.effort_mode,
        analysis_mode=case.analysis_mode,
        target_heartrate=None,
        weather_mode="auto",
        manual_temperature_c=None,
        ravito_mode="auto",
        custom_ravitos=None,
        as_of_date=as_of_date,
        excluded_activity_ids=excluded_activity_ids,
    )
    summary = result.get("summary", {})
    uncertainty = result.get("uncertainty", {})
    posterior = result.get("athlete_model", {}).get("posterior", {})
    physics_inputs = result.get("physics_inputs", {})
    p_run = posterior.get("p_run_wkg") or {}
    return {
        "moving_time_min": float(summary.get("moving_time_min") or 0),
        "total_time_min": float(summary.get("total_time_min") or 0),
        "uncertainty_p10_moving": uncertainty.get("moving_time", {}).get("p10"),
        "uncertainty_p90_moving": uncertainty.get("moving_time", {}).get("p90"),
        "p_run_wkg_mean": p_run.get("mean"),
        "p_run_wkg_std": p_run.get("std"),
        "p_run_evidence_count": p_run.get("evidence_count"),
        "p_run_wkg_used": physics_inputs.get("p_run_wkg_used"),
        "aggregator": (result.get("debug_trace") or {}).get("aggregator", {}),
        "residual": result.get("hybrid_model", {}).get("residual_correction", {}),
    }


def _safe_fmt(value):
    if value is None:
        return "-"
    return fmt_min(float(value))


def main() -> None:
    results = []
    with Session(db_engine) as session:
        for case in CASES:
            history_start_date = case.race_datetime - timedelta(days=MAX_HISTORY_DAYS)
            excluded_ids = {UUID(case.activity_id_hex)} if case.activity_id_hex else set()

            # GPX loading
            try:
                if case.gpx_path:
                    gpx_text = case.gpx_path.read_text(encoding="utf-8")
                else:
                    gpx_text = reconstruct_gpx_from_streams(session, case.activity_id_hex)
            except Exception as exc:
                print(f"GPX load FAILED for {case.label}: {exc}", flush=True)
                continue

            # V1 + V2 (SF=1.20 production prior) avec backtest chrono
            calibration = build_calibration(
                session,
                USER_ID,
                history_start_date=history_start_date,
                history_end_date=case.race_datetime,
                excluded_activity_ids=excluded_ids,
                target_heartrate=None,
            )
            fatigue = build_fatigue_profile(
                session,
                USER_ID,
                history_start_date=history_start_date,
                history_end_date=case.race_datetime,
                excluded_activity_ids=excluded_ids,
                p_run_wkg=float(calibration.get("p_run_wkg") or 9.5),
            )
            print(f"  -> V1 {case.label}", flush=True)
            v1 = run_v1(
                gpx_text, session,
                case=case,
                history_start_date=history_start_date,
                excluded_activity_ids=excluded_ids,
            )
            print(f"  -> V2 SF=1.20 {case.label}", flush=True)
            v2 = run_v2(
                gpx_text, session,
                case=case,
                calibration=calibration,
                fatigue=fatigue,
                trail_surface_factor=1.20,
            )

            # V2.2 avec backtest chrono strict, sans profil athlétique
            print(f"  -> V2.2 {case.label}", flush=True)
            v22 = None
            v22_error = None
            try:
                v22 = run_v22(
                    gpx_text, session,
                    case=case,
                    as_of_date=case.race_datetime,
                    excluded_activity_ids=excluded_ids,
                )
            except Exception as exc:
                v22_error = f"{type(exc).__name__}: {exc}"
                print(f"  V2.2 FAIL: {v22_error}", flush=True)

            # V2.3.1 avec backtest chrono strict, sans profil athletique
            print(f"  -> V2.3.1 {case.label}", flush=True)
            v23 = None
            v23_error = None
            try:
                v23 = run_v23(
                    gpx_text, session,
                    case=case,
                    as_of_date=case.race_datetime,
                    excluded_activity_ids=excluded_ids,
                )
            except Exception as exc:
                import traceback
                traceback.print_exc()
                v23_error = f"{type(exc).__name__}: {exc}"
                print(f"  V2.3.1 FAIL: {v23_error}", flush=True)

            print(f"  -> V3 {case.label}", flush=True)
            v3 = None
            v3_error = None
            try:
                v3 = run_v3(
                    gpx_text, session,
                    case=case,
                    as_of_date=case.race_datetime,
                    excluded_activity_ids=excluded_ids,
                )
            except Exception as exc:
                v3_error = f"{type(exc).__name__}: {exc}"
                print(f"  V3 FAIL: {v3_error}", flush=True)

            real_moving_min = case.real_moving_s / 60
            real_distance_km = case.real_distance_m / 1000
            real_pace = real_moving_min / real_distance_km if real_distance_km else 0
            scored_moving_min = real_moving_min
            if case.category == "official_normalized" and case.potential_gain_min_range:
                low_gain, high_gain = case.potential_gain_min_range
                scored_moving_min -= (low_gain + high_gain) / 2.0

            results.append({
                "label": case.label,
                "category": case.category,
                "notes": case.notes,
                "potential_gain": case.potential_gain_min_range,
                "real": {
                    "moving_min": real_moving_min,
                    "distance_km": real_distance_km,
                    "pace": real_pace,
                    "dplus": case.real_elevation_gain_m,
                },
                "scored_moving_min": scored_moving_min,
                "v1": v1,
                "v2": v2,
                "v22": v22,
                "v22_error": v22_error,
                "v23": v23,
                "v23_error": v23_error,
                "v3": v3,
                "v3_error": v3_error,
                "d_v1": v1["moving_time_min"] - real_moving_min,
                "d_v2": v2["moving_time_min"] - real_moving_min,
                "d_v22": (v22["moving_time_min"] - real_moving_min) if v22 else None,
                "d_v23": (v23["moving_time_min"] - real_moving_min) if v23 else None,
                "d_v3": (v3["moving_time_min"] - real_moving_min) if v3 else None,
                "scored_d_v1": v1["moving_time_min"] - scored_moving_min,
                "scored_d_v2": v2["moving_time_min"] - scored_moving_min,
                "scored_d_v22": (v22["moving_time_min"] - scored_moving_min) if v22 else None,
                "scored_d_v23": (v23["moving_time_min"] - scored_moving_min) if v23 else None,
                "scored_d_v3": (v3["moving_time_min"] - scored_moving_min) if v3 else None,
                "calibration": calibration,
            })

    # --- AFFICHAGE -----------------------------------------------------------
    print()
    print("=" * 120)
    print("GOLDEN SET -- Comparaison complete V1 / V2 (SF=1.20) / V2.2 / V2.3.1 / V3 / Reel")
    print("=" * 120)
    print("Backtest chronologique strict : as_of_date = race_datetime, activite cible exclue.")
    print()

    for r in results:
        real = r["real"]
        v1 = r["v1"]
        v2 = r["v2"]
        v22 = r["v22"]
        v23 = r["v23"]
        v3 = r["v3"]
        d_v1_pct = r["d_v1"] / real["moving_min"] * 100
        d_v2_pct = r["d_v2"] / real["moving_min"] * 100
        d_v22_pct = (r["d_v22"] / real["moving_min"] * 100) if r["d_v22"] is not None else None
        d_v23_pct = (r["d_v23"] / real["moving_min"] * 100) if r["d_v23"] is not None else None
        d_v3_pct = (r["d_v3"] / real["moving_min"] * 100) if r["d_v3"] is not None else None

        print(f"--- {r['label']} ({r['category']}) ---")
        print(f"  Notes  : {r['notes']}")
        print(f"  Reel   : dist {real['distance_km']:.2f} km  D+ {real['dplus']:.0f} m  moving {fmt_min(real['moving_min'])} ({fmt_pace(real['pace'])})")
        if r["potential_gain"]:
            low, high = r["potential_gain"]
            pot_low = real["moving_min"] - high
            pot_high = real["moving_min"] - low
            print(f"  Potent.: sans incident final estime {fmt_min(pot_low)} - {fmt_min(pot_high)}")
            print(f"  Score  : reference normalisee centrale {fmt_min(r['scored_moving_min'])}")
        print(f"  V1     : moving {fmt_min(v1['moving_time_min']):<10}                                       ecart {r['d_v1']:+7.1f} min ({d_v1_pct:+5.1f}%)")
        print(f"  V2 1.20: moving {fmt_min(v2['moving_time_min']):<10}                                       ecart {r['d_v2']:+7.1f} min ({d_v2_pct:+5.1f}%)")
        if v22:
            interval_v22 = f"P10/P50/P90 mov {_safe_fmt(v22['uncertainty_p10_moving'])}/{_safe_fmt(v22['uncertainty_p50_moving'])}/{_safe_fmt(v22['uncertainty_p90_moving'])}"
            print(f"  V2.2   : moving {fmt_min(v22['moving_time_min']):<10}  {interval_v22}  ecart {r['d_v22']:+7.1f} min ({d_v22_pct:+5.1f}%)")
            if v22['p_capacity_wkg'] is not None and v22['p_event_wkg'] is not None:
                print(f"           P_capacity={v22['p_capacity_wkg']:.2f} W/kg  P_event={v22['p_event_wkg']:.2f} W/kg  fraction={v22['sustainable_fraction']:.3f}  flat_cap={v22['flat_capacity_mean']:.2f} m/s")
            print(f"           Trail factor={v22['trail_cost_factor_mean']:.3f}  durabilite alpha={v22['durability_alpha_mean']:.3f}  obs={v22['evidence_count']}  outliers={v22['outliers_count']}")
        else:
            print(f"  V2.2   : FAIL ({r['v22_error']})")
        if v23:
            interval_v23 = f"P10/P50/P90 mov {_safe_fmt(v23['uncertainty_p10_moving'])}/{_safe_fmt(v23['uncertainty_p50_moving'])}/{_safe_fmt(v23['uncertainty_p90_moving'])}"
            print(f"  V2.3.1 : moving {fmt_min(v23['moving_time_min']):<10}  {interval_v23}  ecart {r['d_v23']:+7.1f} min ({d_v23_pct:+5.1f}%)")
            print(f"           P_run posterior={v23['p_run_wkg_mean']:.2f} +/- {v23['p_run_wkg_std']:.2f} W/kg  (used={v23['p_run_wkg_used']:.2f})  evid={v23['p_run_evidence_count']}")
            print(f"           Trail factor={v23['trail_cost_factor_mean']:.3f}  durabilite alpha={v23['durability_alpha_mean']:.4f}  obs={v23['evidence_count']}  outliers={v23['outliers_count']}")
            # Couverture P10-P90 sur moving_time
            p10 = v23["uncertainty_p10_moving"]
            p90 = v23["uncertainty_p90_moving"]
            if p10 is not None and p90 is not None:
                inside = p10 <= real["moving_min"] <= p90
                print(f"           Couverture P10-P90 moving : reel {fmt_min(real['moving_min'])} dans [{fmt_min(p10)}, {fmt_min(p90)}] ? {'OUI' if inside else 'NON'}")
            if v23.get("using_legacy_aggregator"):
                print(f"           [WARN] using_legacy_observation_aggregator=True (Lot 1 V2.3 pas encore livre)")
            elif v23.get("prior_only_no_p_ref_evidence"):
                print("           [INFO] prior_only_no_p_ref_evidence=True (pipeline V2.3.1 actif, historique route insuffisant)")
            aggregator = v23.get("aggregator") or {}
            print(
                "           P_ref source={} band={} FCmax={} ({}) alpha={}".format(
                    v23.get("p_ref_steady_source"),
                    aggregator.get("fc_band_used"),
                    aggregator.get("fcmax_estimate_bpm"),
                    aggregator.get("fcmax_source"),
                    v23.get("fatigue_alpha_used"),
                )
            )
        else:
            print(f"  V2.3.1 : FAIL ({r['v23_error']})")
        if v3:
            interval_v3 = f"P10/P90 mov {_safe_fmt(v3['uncertainty_p10_moving'])}/{_safe_fmt(v3['uncertainty_p90_moving'])}"
            print(f"  V3     : moving {fmt_min(v3['moving_time_min']):<10}  {interval_v3}  ecart {r['d_v3']:+7.1f} min ({d_v3_pct:+5.1f}%)")
            print(f"           P_run={v3['p_run_wkg_used']:.2f} W/kg  evid={v3['p_run_evidence_count']} sparse={v3['aggregator'].get('sparse_evidence_accepted')} RF={v3['residual'].get('status')}")
        else:
            print(f"  V3     : FAIL ({r['v3_error']})")
        print()

    # --- RESUME TABLEAU ------------------------------------------------------
    print("=" * 130)
    print("TABLEAU RESUME")
    print("=" * 130)
    print(f"{'Course':<33} {'Categorie':<32} {'Reel':>9} {'V1':>9} {'dV1':>7} {'V2':>9} {'dV2':>7} {'V2.2':>9} {'dV2.2':>7} {'V2.3.1':>9} {'dV2.3.1':>7} {'V3':>9} {'dV3':>7}")
    print("-" * 130)
    for r in results:
        real = r["real"]
        v1 = r["v1"]
        v2 = r["v2"]
        v22 = r["v22"]
        v23 = r["v23"]
        v3 = r["v3"]
        d_v1_pct = r["d_v1"] / real["moving_min"] * 100
        d_v2_pct = r["d_v2"] / real["moving_min"] * 100
        if v22:
            v22_str = fmt_min(v22["moving_time_min"])
            d_v22_pct = r["d_v22"] / real["moving_min"] * 100
            d_v22_str = f"{d_v22_pct:+6.1f}%"
        else:
            v22_str = "FAIL"
            d_v22_str = "  -"
        if v23:
            v23_str = fmt_min(v23["moving_time_min"])
            d_v23_pct = r["d_v23"] / real["moving_min"] * 100
            d_v23_str = f"{d_v23_pct:+6.1f}%"
        else:
            v23_str = "FAIL"
            d_v23_str = "  -"
        if v3:
            v3_str = fmt_min(v3["moving_time_min"])
            d_v3_pct = r["d_v3"] / real["moving_min"] * 100
            d_v3_str = f"{d_v3_pct:+6.1f}%"
        else:
            v3_str = "FAIL"
            d_v3_str = "  -"
        print(
            f"{r['label']:<33} {r['category']:<32} "
            f"{fmt_min(real['moving_min']):>9} "
            f"{fmt_min(v1['moving_time_min']):>9} {d_v1_pct:>+6.1f}% "
            f"{fmt_min(v2['moving_time_min']):>9} {d_v2_pct:>+6.1f}% "
            f"{v22_str:>9} {d_v22_str:>7} "
            f"{v23_str:>9} {d_v23_str:>7} "
            f"{v3_str:>9} {d_v3_str:>7}"
        )

    # --- MAPE PAR CATEGORIE ---------------------------------------------------
    print()
    print("MAPE PAR CATEGORIE")
    print("-" * 80)
    categories_seen = []
    for r in results:
        if r["category"] not in categories_seen:
            categories_seen.append(r["category"])
    category_order = [
        c for c in ["official_clean", "official_normalized", "training_control", "execution_degraded_non_scoring", "incident_non_scoring"]
        if c in categories_seen
    ]
    for category in category_order:
        selected = [r for r in results if r["category"] == category]
        if not selected:
            continue
        mape_v1 = sum(abs(r["scored_d_v1"] / r["scored_moving_min"]) for r in selected) * 100 / len(selected)
        mape_v2 = sum(abs(r["scored_d_v2"] / r["scored_moving_min"]) for r in selected) * 100 / len(selected)
        valid_v22 = [r for r in selected if r["d_v22"] is not None]
        valid_v23 = [r for r in selected if r["d_v23"] is not None]
        valid_v3 = [r for r in selected if r["d_v3"] is not None]
        mape_v22 = (
            sum(abs(r["scored_d_v22"] / r["scored_moving_min"]) for r in valid_v22) * 100 / len(valid_v22)
        ) if valid_v22 else None
        mape_v23 = (
            sum(abs(r["scored_d_v23"] / r["scored_moving_min"]) for r in valid_v23) * 100 / len(valid_v23)
        ) if valid_v23 else None
        mape_v3 = (
            sum(abs(r["scored_d_v3"] / r["scored_moving_min"]) for r in valid_v3) * 100 / len(valid_v3)
        ) if valid_v3 else None
        print(f"  {category} ({len(selected)} cas):")
        print(f"    V1  MAPE = {mape_v1:.1f}%")
        print(f"    V2  MAPE = {mape_v2:.1f}%")
        if mape_v22 is not None:
            print(f"    V2.2 MAPE = {mape_v22:.1f}% ({len(valid_v22)}/{len(selected)} cas valides)")
        else:
            print(f"    V2.2 MAPE = FAIL (0/{len(selected)} cas valides)")
        if mape_v23 is not None:
            print(f"    V2.3.1 MAPE = {mape_v23:.1f}% ({len(valid_v23)}/{len(selected)} cas valides)")
        else:
            print(f"    V2.3.1 MAPE = FAIL (0/{len(selected)} cas valides)")
        if mape_v3 is not None:
            print(f"    V3 MAPE = {mape_v3:.1f}% ({len(valid_v3)}/{len(selected)} cas valides)")
        else:
            print(f"    V3 MAPE = FAIL (0/{len(selected)} cas valides)")
        print()

    # --- ANALYSE V2.3.1 vs V2.2 -----------------------------------------------
    print("ANALYSE V2.3.1 vs V2.2")
    print("-" * 80)
    pairs = [r for r in results if r["d_v22"] is not None and r["d_v23"] is not None]
    if pairs:
        # Positif si V2.3.1 est plus proche du reel.
        improvements = [abs(r["d_v22"]) - abs(r["d_v23"]) for r in pairs]
        mean_improvement = sum(improvements) / len(improvements)
        print(f"  Cas avec V2.2 et V2.3.1 valides : {len(pairs)}/{len(results)}")
        print(f"  Amelioration moyenne |ecart V2.2| - |ecart V2.3.1| = {mean_improvement:+.1f} min ({len([i for i in improvements if i > 0])}/{len(pairs)} cas ameliores)")
    else:
        print(f"  Aucun cas avec V2.2 ET V2.3.1 valides")

    pairs_v2_v23 = [r for r in results if r["d_v23"] is not None]
    if pairs_v2_v23:
        diffs = [r["v23"]["moving_time_min"] - r["v2"]["moving_time_min"] for r in pairs_v2_v23]
        mean_diff = sum(diffs) / len(diffs)
        print(f"  Difference moyenne V2.3.1 - V2 = {mean_diff:+.1f} min")

    # Coverage V2.3.1 sur moving_time
    coverage_pairs = [
        r for r in results
        if r["v23"]
        and r["v23"]["uncertainty_p10_moving"] is not None
        and r["v23"]["uncertainty_p90_moving"] is not None
    ]
    if coverage_pairs:
        in_band = sum(
            1
            for r in coverage_pairs
            if r["v23"]["uncertainty_p10_moving"] <= r["real"]["moving_min"] <= r["v23"]["uncertainty_p90_moving"]
        )
        print(f"  Coverage V2.3.1 (reel dans [P10, P90] moving) : {in_band}/{len(coverage_pairs)} cas")
    coverage_v3_pairs = [
        r for r in results
        if r["v3"]
        and r["v3"]["uncertainty_p10_moving"] is not None
        and r["v3"]["uncertainty_p90_moving"] is not None
    ]
    if coverage_v3_pairs:
        in_band_v3 = sum(
            1
            for r in coverage_v3_pairs
            if r["v3"]["uncertainty_p10_moving"] <= r["real"]["moving_min"] <= r["v3"]["uncertainty_p90_moving"]
        )
        print(f"  Coverage V3 (reel brut dans [P10, P90] moving) : {in_band_v3}/{len(coverage_v3_pairs)} cas")

    # --- CONCLUSION -----------------------------------------------------------
    print()
    print("CONCLUSION")
    print("-" * 80)
    v22_ok = [r for r in results if r["d_v22"] is not None]
    v23_ok = [r for r in results if r["d_v23"] is not None]
    v3_ok = [r for r in results if r["d_v3"] is not None]
    if not v22_ok:
        print("  - V2.2 a echoue sur tous les cas (probablement bug refactor observation_aggregator).")
    elif len(v22_ok) < len(results):
        print(f"  - V2.2 a echoue sur {len(results) - len(v22_ok)}/{len(results)} cas.")

    if not v23_ok:
        print("  - V2.3.1 a echoue sur tous les cas.")
    else:
        # MAPE training_control
        train_v23 = [r for r in v23_ok if r["category"] == "training_control"]
        if train_v23:
            mape_train_v23 = sum(abs(r["d_v23"] / r["real"]["moving_min"]) for r in train_v23) * 100 / len(train_v23)
            train_v22 = [r for r in v22_ok if r["category"] == "training_control"]
            mape_train_v22 = (
                sum(abs(r["d_v22"] / r["real"]["moving_min"]) for r in train_v22) * 100 / len(train_v22)
            ) if train_v22 else None
            if mape_train_v22 is not None:
                delta_mape = mape_train_v22 - mape_train_v23
                if delta_mape > 0:
                    print(f"  - V2.3.1 reduit la MAPE training_control de {mape_train_v22:.1f}% (V2.2) a {mape_train_v23:.1f}% = -{delta_mape:.1f} pt")
                else:
                    print(f"  - V2.3.1 NE reduit PAS la MAPE training_control (V2.2={mape_train_v22:.1f}% vs V2.3.1={mape_train_v23:.1f}%)")

        # UTMJ verification
        utmj = next((r for r in v23_ok if "UTMJ" in r["label"]), None)
        if utmj:
            v23_moving = utmj["v23"]["moving_time_min"]
            in_range = 195 <= v23_moving <= 245
            print(f"  - UTMJ V2.3.1 moving = {fmt_min(v23_moving)} {'(dans plage attendue)' if in_range else '(hors plage historique)'}")

        # Reproduction V2
        diffs_v2 = [
            abs(r["v23"]["moving_time_min"] - r["v2"]["moving_time_min"])
            for r in v23_ok
        ]
        if diffs_v2:
            mean_abs_diff = sum(diffs_v2) / len(diffs_v2)
            print(f"  - Difference absolue moyenne V2.3.1 / V2 : {mean_abs_diff:.1f} min")

        # Check using_legacy
        legacy_warnings = [r for r in v23_ok if r["v23"].get("using_legacy_aggregator")]
        if legacy_warnings:
            print(f"  - [WARN] V2.3.1 utilise encore un aggregator legacy sur {len(legacy_warnings)}/{len(v23_ok)} cas")
    if v3_ok:
        train_v3 = [r for r in v3_ok if r["category"] == "training_control"]
        if train_v3:
            mape_train_v3 = sum(
                abs(r["scored_d_v3"] / r["scored_moving_min"]) for r in train_v3
            ) * 100 / len(train_v3)
            print(f"  - V3 MAPE training_control = {mape_train_v3:.1f}% ; RF residuel inactif tant que les references qualifiees sont insuffisantes.")
        utmj_v3 = next((r for r in v3_ok if "UTMJ" in r["label"]), None)
        if utmj_v3:
            normalized_delta = utmj_v3["scored_d_v3"]
            normalized_pct = normalized_delta / utmj_v3["scored_moving_min"] * 100
            print(f"  - UTMJ normalisee V3 = {fmt_min(utmj_v3['v3']['moving_time_min'])}, ecart centre corrige {normalized_delta:+.1f} min ({normalized_pct:+.1f}%).")

    # Dump JSON
    Path("/tmp/golden_set_all_versions.json").write_text(
        json.dumps(results, default=str, indent=2)
    )
    print()
    print("Dump JSON: /tmp/golden_set_all_versions.json")


if __name__ == "__main__":
    main()
