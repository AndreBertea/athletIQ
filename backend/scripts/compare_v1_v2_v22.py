"""Compare V1 RandomForest vs V2 physique vs V2.2 bayesien vs réel sur le golden set.

Backtest chronologique strict : pour chaque cas, as_of_date = race_datetime
et l'activité cible est exclue de l'historique utilisé.
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
    custom_ravitos_json = None  # auto
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
        custom_ravitos=custom_ravitos_json,
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
        "total_distance_km": float(result.get("total_distance_km") or 0),
        "elevation_gain_m": float(result.get("total_elevation_gain_m") or 0),
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
                print(f"⚠️  {case.label}: GPX load failed ({exc})")
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
            v1 = run_v1(
                gpx_text, session,
                case=case,
                history_start_date=history_start_date,
                excluded_activity_ids=excluded_ids,
            )
            v2 = run_v2(
                gpx_text, session,
                case=case,
                calibration=calibration,
                fatigue=fatigue,
                trail_surface_factor=1.20,
            )

            # V2.2 avec backtest chrono strict, sans profil athlétique
            print(f"  → Lancement V2.2 pour {case.label}...", flush=True)
            try:
                v22 = run_v22(
                    gpx_text, session,
                    case=case,
                    as_of_date=case.race_datetime,
                    excluded_activity_ids=excluded_ids,
                )
            except Exception as exc:
                import traceback
                traceback.print_exc()
                print(f"⚠️  V2.2 failed for {case.label}: {exc}")
                v22 = None

            real_moving_min = case.real_moving_s / 60
            real_distance_km = case.real_distance_m / 1000
            real_pace = real_moving_min / real_distance_km if real_distance_km else 0

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
                "v1": v1,
                "v2": v2,
                "v22": v22,
                "d_v1": v1["moving_time_min"] - real_moving_min,
                "d_v2": v2["moving_time_min"] - real_moving_min,
                "d_v22": (v22["moving_time_min"] - real_moving_min) if v22 else None,
                "calibration": calibration,
            })

    # --- AFFICHAGE ---
    print()
    print("=" * 120)
    print("GOLDEN SET — Comparaison V1 / V2 (SF=1.20) / V2.2 (sans profil) / Réel")
    print("=" * 120)
    print("Backtest chronologique strict : as_of_date = race_datetime, activité cible exclue.")
    print()

    for r in results:
        real = r["real"]
        v1 = r["v1"]
        v2 = r["v2"]
        v22 = r["v22"]
        d_v1_pct = r["d_v1"] / real["moving_min"] * 100
        d_v2_pct = r["d_v2"] / real["moving_min"] * 100
        d_v22_pct = (r["d_v22"] / real["moving_min"] * 100) if r["d_v22"] is not None else None

        print(f"━━━ {r['label']} ({r['category']}) ━━━")
        print(f"  Notes  : {r['notes']}")
        print(f"  Réel   : dist {real['distance_km']:.2f} km · D+ {real['dplus']:.0f} m · moving {fmt_min(real['moving_min'])} ({fmt_pace(real['pace'])})")
        if r["potential_gain"]:
            low, high = r["potential_gain"]
            pot_low = real["moving_min"] - high
            pot_high = real["moving_min"] - low
            print(f"  Potent.: sans incident final estimé {fmt_min(pot_low)} - {fmt_min(pot_high)}")
        print(f"  V1     : moving {fmt_min(v1['moving_time_min'])}                                          écart {r['d_v1']:+7.1f} min ({d_v1_pct:+5.1f}%)")
        print(f"  V2 1.20: moving {fmt_min(v2['moving_time_min'])}  · P10/P50/P90 {fmt_min(v2['uncertainty_p10_total'])}/{fmt_min(v2['uncertainty_p50_total'])}/{fmt_min(v2['uncertainty_p90_total'])}  écart {r['d_v2']:+7.1f} min ({d_v2_pct:+5.1f}%)")
        if v22:
            print(f"  V2.2   : moving {fmt_min(v22['moving_time_min'])}  · P10/P50/P90 mov {fmt_min(v22['uncertainty_p10_moving'])}/{fmt_min(v22['uncertainty_p50_moving'])}/{fmt_min(v22['uncertainty_p90_moving'])}  écart {r['d_v22']:+7.1f} min ({d_v22_pct:+5.1f}%)")
            print(f"           Posterior : P_capacity={v22['p_capacity_wkg']:.2f} W/kg, P_event={v22['p_event_wkg']:.2f} W/kg, fraction={v22['sustainable_fraction']:.3f}")
            print(f"           Trail factor={v22['trail_cost_factor_mean']:.3f}, durabilité α={v22['durability_alpha_mean']:.3f}, flat_capacity={v22['flat_capacity_mean']:.2f}±{v22['flat_capacity_std']:.2f} m/s")
            print(f"           Profile present: {v22['profile_present']} · {v22['evidence_count']} obs, {v22['outliers_count']} outliers · iter={v22['iterations']} converged={v22['converged']}")
        else:
            print(f"  V2.2   : ÉCHEC")
        print()

    print("=" * 120)
    print("RÉSUMÉ TABLEAU")
    print("=" * 120)
    print(f"{'Course':<36} {'Catégorie':<25} {'Réel':>10} {'V1':>10} {'ΔV1':>7} {'V2':>10} {'ΔV2':>7} {'V2.2':>10} {'ΔV2.2':>8}")
    print("-" * 120)
    for r in results:
        real = r["real"]
        v1 = r["v1"]
        v2 = r["v2"]
        v22 = r["v22"]
        d_v1_pct = r["d_v1"] / real["moving_min"] * 100
        d_v2_pct = r["d_v2"] / real["moving_min"] * 100
        if v22:
            v22_str = fmt_min(v22["moving_time_min"])
            d_v22_pct = r["d_v22"] / real["moving_min"] * 100
            d_v22_str = f"{d_v22_pct:+6.1f}%"
        else:
            v22_str = "FAIL"
            d_v22_str = "  -"
        print(f"{r['label']:<36} {r['category']:<25} {fmt_min(real['moving_min']):>10} {fmt_min(v1['moving_time_min']):>10} {d_v1_pct:>+6.1f}% {fmt_min(v2['moving_time_min']):>10} {d_v2_pct:>+6.1f}% {v22_str:>10} {d_v22_str:>8}")

    # MAPE par catégorie
    print()
    print("MAPE PAR CATÉGORIE")
    print("-" * 60)
    for category in ["official_clean", "training_control", "execution_degraded_non_scoring", "incident_non_scoring"]:
        selected = [r for r in results if r["category"] == category]
        if not selected:
            continue
        mape_v1 = sum(abs(r["d_v1"] / r["real"]["moving_min"]) for r in selected) * 100 / len(selected)
        mape_v2 = sum(abs(r["d_v2"] / r["real"]["moving_min"]) for r in selected) * 100 / len(selected)
        valid_v22 = [r for r in selected if r["d_v22"] is not None]
        mape_v22 = (sum(abs(r["d_v22"] / r["real"]["moving_min"]) for r in valid_v22) * 100 / len(valid_v22)) if valid_v22 else None
        print(f"  {category} ({len(selected)} cas):")
        print(f"    V1 MAPE   = {mape_v1:.1f}%")
        print(f"    V2 MAPE   = {mape_v2:.1f}%")
        if mape_v22 is not None:
            print(f"    V2.2 MAPE = {mape_v22:.1f}%")
        print()

    # Dump JSON
    Path("/tmp/golden_set_v1_v2_v22.json").write_text(json.dumps(results, default=str, indent=2))
    print("Dump JSON: /tmp/golden_set_v1_v2_v22.json")


if __name__ == "__main__":
    main()
