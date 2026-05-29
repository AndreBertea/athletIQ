"""Compare V1 RandomForest vs V2 physique vs réel sur golden set étendu.

Supporte 2 sources GPX :
- Fichier .gpx sur disque (courses)
- Reconstruction depuis les streams d'une activité (entraînements)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "sqlite:///./stridedelta.db")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import joblib
import numpy as np
from sqlalchemy import and_, or_, select
from sqlmodel import Session

from app.core.database import engine as db_engine
from app.domain.entities.activity import Activity, ActivityType
from app.domain.services.race_predictor.calibration_service import build_calibration
from app.domain.services.race_predictor.environment_service import build_environment, summarize_weather_exposure
from app.domain.services.race_predictor.fatigue_model import build_fatigue_profile
from app.domain.services.race_predictor.gpx_analyzer import analyze_gpx
from app.domain.services.race_predictor.physics_engine import predict_segments
from app.domain.services.race_predictor.ravito_service import auto_ravitos
from app.domain.services.race_predictor.uncertainty_service import monte_carlo_uncertainty
from gpx_parser import calculate_global_stats, parse_gpx_file


USER_ID = UUID("b5727f6086db41ab86e2bc803460b868")
MAX_HISTORY_DAYS = 366 * 3
MODEL_PATH = BACKEND_DIR.parent / "models" / "pace_predictor_model.joblib"


@dataclass
class GoldenCase:
    label: str
    real_moving_s: float
    real_elapsed_s: float
    real_distance_m: float
    real_elevation_gain_m: float
    race_datetime: datetime
    category: str
    analysis_mode: str = "trail"
    effort_mode: str = "steady"
    gpx_path: Optional[Path] = None
    activity_id_hex: Optional[str] = None  # reconstruct GPX from streams
    notes: str = ""
    potential_gain_min_range: tuple[float, float] | None = None


def reconstruct_gpx_from_streams(session: Session, activity_id_hex: str) -> str:
    activity = session.get(Activity, UUID(activity_id_hex))
    if activity is None:
        raise RuntimeError(f"Activity {activity_id_hex} not found")
    streams_raw = activity.streams_data
    if isinstance(streams_raw, str):
        if streams_raw.strip().lower() == "null":
            raise RuntimeError(f"Activity {activity_id_hex} streams_data is null string")
        streams = json.loads(streams_raw)
    else:
        streams = streams_raw
    if not streams:
        raise RuntimeError(f"Activity {activity_id_hex} has no streams")

    def _array(key: str):
        v = streams.get(key)
        if isinstance(v, dict) and "data" in v:
            v = v["data"]
        return v if isinstance(v, list) else []

    latlng = _array("latlng")
    altitude = _array("altitude")
    time_arr = _array("time")
    if not latlng or not altitude:
        raise RuntimeError(f"Activity {activity_id_hex} missing latlng/altitude streams")
    n = min(len(latlng), len(altitude))

    start_dt = activity.start_date or datetime.utcnow()
    trkpts = []
    skipped = 0
    for i in range(n):
        coord = latlng[i]
        ele = altitude[i]
        if coord is None or not isinstance(coord, (list, tuple)) or len(coord) < 2 or coord[0] is None or coord[1] is None or ele is None:
            skipped += 1
            continue
        lat, lon = float(coord[0]), float(coord[1])
        t_offset = int(time_arr[i]) if i < len(time_arr) else i
        ts = (start_dt + timedelta(seconds=t_offset)).isoformat()
        trkpts.append(
            f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"><ele>{float(ele):.1f}</ele><time>{ts}Z</time></trkpt>'
        )
    if len(trkpts) < 2:
        raise RuntimeError(f"Activity {activity_id_hex}: only {len(trkpts)} valid GPS points (skipped {skipped})")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="reconstructed-from-streams">
  <trk><name>{activity.name or "reconstructed"}</name><trkseg>{"".join(trkpts)}</trkseg></trk>
</gpx>"""


CASES = [
    # Courses connues
    GoldenCase(
        label="Trail des tranchées (course)",
        gpx_path=Path("/Users/andrebertea/Downloads/trail-des-tranchees-2026-circuit-poilu (2).gpx"),
        activity_id_hex="f2232f1079f647f2804f592e024132cf",
        real_moving_s=18111, real_elapsed_s=19974,
        real_distance_m=33076.6, real_elevation_gain_m=802.0,
        race_datetime=datetime(2026, 3, 29, 7, 0),
        category="incident_non_scoring",
        notes="Course CASSÉE : nuit blanche + retour blessure + bouchon km8 + crampes fin de course",
    ),
    GoldenCase(
        label="UTMJ relai 5 (course)",
        gpx_path=Path("/Users/andrebertea/Downloads/utmj-24-relais-5-mouthe-jougne.gpx"),
        activity_id_hex="1c3d688792d945ebb004edf388472fe5",
        real_moving_s=12562, real_elapsed_s=13637,
        real_distance_m=22727.5, real_elevation_gain_m=1012.0,
        race_datetime=datetime(2025, 10, 4, 6, 30),
        category="official_normalized",
        notes="Reference normalisee : perte de jambes sur les 2 derniers km apres descente trop engagee; comparer aussi au potentiel corrige de 5-10 min.",
        potential_gain_min_range=(5.0, 10.0),
    ),
    # Entraînements (GPX reconstruit depuis streams)
    GoldenCase(
        label="Morning Trail Run 11/01/26",
        activity_id_hex="d187b357458c40fdbc53819f09d0455c",
        real_moving_s=5763, real_elapsed_s=6381,
        real_distance_m=13010.2, real_elevation_gain_m=304.0,
        race_datetime=datetime(2026, 1, 11, 8, 35),
        category="training_control",
        notes="Entraînement, pas à fond, légère pause visible dans streams",
    ),
    GoldenCase(
        label="Morning Trail Run 04/01/26",
        activity_id_hex="f7b7218b4b5243809165b0376e163f2b",
        real_moving_s=7820, real_elapsed_s=7821,
        real_distance_m=15521.8, real_elevation_gain_m=395.0,
        race_datetime=datetime(2026, 1, 4, 8, 38),
        category="training_control",
        notes="Entraînement, pas à fond",
    ),
    GoldenCase(
        label="Afternoon Trail Run 30/07/25",
        activity_id_hex="d9305835a991498d9241f664bcdd784c",
        real_moving_s=7107, real_elapsed_s=7266,
        real_distance_m=14983.5, real_elevation_gain_m=295.0,
        race_datetime=datetime(2025, 7, 30, 14, 0),
        category="training_control",
        notes="Entraînement, pas à fond",
    ),
]


def _historical_heart_rate(
    session: Session,
    *,
    is_trail: bool,
    history_start_date: datetime,
    history_end_date: datetime,
    excluded_activity_ids: set[UUID],
) -> int:
    activity_type = ActivityType.TRAIL_RUN if is_trail else ActivityType.RUN
    effective_type_clause = or_(
        Activity.activity_type_override == activity_type,
        and_(Activity.activity_type_override.is_(None), Activity.activity_type == activity_type),
    )
    statement = select(Activity.average_heartrate).where(
        Activity.user_id == USER_ID,
        effective_type_clause,
        Activity.average_heartrate.is_not(None),
        Activity.average_heartrate > 0,
        Activity.start_date >= history_start_date,
        Activity.start_date < history_end_date,
    )
    if excluded_activity_ids:
        statement = statement.where(Activity.id.notin_(excluded_activity_ids))
    heart_rates = list(session.execute(statement).scalars().all())
    if heart_rates:
        return int(sum(heart_rates) / len(heart_rates))
    return 150 if is_trail else 140


def run_v1(
    gpx_text: str,
    session: Session,
    *,
    case: GoldenCase,
    history_start_date: datetime,
    excluded_activity_ids: set[UUID],
) -> dict:
    segments, _ = parse_gpx_file(gpx_text)
    global_stats = calculate_global_stats(segments)
    is_trail = case.analysis_mode == "trail"
    historical_hr = _historical_heart_rate(
        session,
        is_trail=is_trail,
        history_start_date=history_start_date,
        history_end_date=case.race_datetime,
        excluded_activity_ids=excluded_activity_ids,
    )
    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    scaler = model_data["scaler"]

    moving_time_min = 0.0
    for segment in segments:
        segment["is_trail"] = 1 if is_trail else 0
        segment["avg_heartrate"] = historical_hr
        features = np.array([
            segment["distance_km"],
            segment["elevation_gain_m"],
            segment["elevation_loss_m"],
            segment["elevation_gain_m"] - segment["elevation_loss_m"],
            (segment["elevation_gain_m"] - segment["elevation_loss_m"]) / segment["distance_km"]
                if segment["distance_km"] else 0,
            segment["avg_grade_percent"],
            segment["is_trail"],
            segment["avg_heartrate"],
        ]).reshape(1, -1)
        predicted_pace = float(model.predict(scaler.transform(features))[0])
        moving_time_min += predicted_pace * segment["distance_km"]

    return {
        "moving_time_min": moving_time_min,
        "total_distance_km": global_stats["total_distance_km"],
        "elevation_gain_m": global_stats["total_elevation_gain_m"],
        "elevation_loss_m": global_stats["total_elevation_loss_m"],
        "historical_hr": historical_hr,
        "segments_count": len(segments),
        "note": "Le modele RF est fige; seule la FC injectee est bornee chronologiquement.",
    }


def run_v2(
    gpx_text: str,
    session: Session,
    *,
    case: GoldenCase,
    calibration: dict,
    fatigue: dict,
    trail_surface_factor: float | None = None,
) -> dict:
    analysis = analyze_gpx(gpx_text)
    global_stats = analysis["global_stats"]

    environment = build_environment(
        global_stats,
        race_datetime=case.race_datetime,
        weather_mode="auto",
        manual_temperature_c=None,
        p_run_wkg=float(calibration.get("p_run_wkg") or 9.5),
    )
    physics = predict_segments(
        analysis["segments"],
        calibration=calibration,
        environment=environment,
        fatigue_profile=fatigue,
        trail_surface_factor=trail_surface_factor,
        analysis_mode=case.analysis_mode,
        effort_mode=case.effort_mode,
    )
    segments_predicted = physics["segments"]
    moving_time_min = float(physics["moving_time_min"])
    environment = summarize_weather_exposure(environment, moving_time_min)

    ravitos = auto_ravitos(
        segments_predicted, global_stats, moving_time_min,
        analysis_mode=case.analysis_mode,
        temperature_c=float(environment.get("temperature_max_c") or environment.get("temperature_c") or 11.0),
    )
    total_pause = sum(float(r.get("pause_min") or 0) for r in ravitos)
    total_time = moving_time_min + total_pause

    uncertainty = monte_carlo_uncertainty(
        segments=segments_predicted, moving_time_min=moving_time_min,
        total_pause_min=total_pause, calibration=calibration, environment=environment,
        simulations=300,
    )

    walk_km = sum(float(s.get("distance_km") or 0) for s in segments_predicted if s.get("locomotion") == "walk")

    return {
        "moving_time_min": moving_time_min,
        "total_pause_min": total_pause,
        "total_time_min": total_time,
        "total_distance_km": global_stats["total_distance_km"],
        "elevation_gain_m": global_stats["total_elevation_gain_m"],
        "elevation_loss_m": global_stats["total_elevation_loss_m"],
        "temperature_c": environment.get("temperature_c"),
        "temperature_min_c": environment.get("temperature_min_c"),
        "temperature_max_c": environment.get("temperature_max_c"),
        "peak_heat_penalty_percent": environment.get("peak_heat_penalty_percent"),
        "weather_source": environment.get("weather_source"),
        "uncertainty_p10_total": uncertainty["total_time"]["p10"],
        "uncertainty_p50_total": uncertainty["total_time"]["p50"],
        "uncertainty_p90_total": uncertainty["total_time"]["p90"],
        "ravitos_count": len(ravitos),
        "walk_distance_km": walk_km,
        "segments_count": len(segments_predicted),
        "surface_factor": physics["physics"]["surface_factor"],
        "surface_factor_source": physics["physics"]["surface_factor_source"],
    }


def fmt_min(minutes: float) -> str:
    if minutes is None:
        return "-"
    total = int(round(minutes * 60))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h}h{m:02d}:{s:02d}" if h else f"{m}min{s:02d}"


def fmt_pace(pace: float) -> str:
    if not pace:
        return "-"
    mn = int(pace)
    sc = int(round((pace - mn) * 60))
    return f"{mn}:{sc:02d}/km"


def main() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modèle V1 introuvable: {MODEL_PATH}")

    results = []
    with Session(db_engine) as session:
        for case in CASES:
            history_start_date = case.race_datetime - timedelta(days=MAX_HISTORY_DAYS)
            excluded_activity_ids = {UUID(case.activity_id_hex)} if case.activity_id_hex else set()
            calibration = build_calibration(
                session,
                USER_ID,
                history_start_date=history_start_date,
                history_end_date=case.race_datetime,
                excluded_activity_ids=excluded_activity_ids,
                target_heartrate=None,
            )
            fatigue = build_fatigue_profile(
                session,
                USER_ID,
                history_start_date=history_start_date,
                history_end_date=case.race_datetime,
                excluded_activity_ids=excluded_activity_ids,
                p_run_wkg=float(calibration.get("p_run_wkg") or 9.5),
            )
            try:
                if case.gpx_path:
                    gpx_text = case.gpx_path.read_text(encoding="utf-8")
                    source = f"fichier {case.gpx_path.name}"
                else:
                    gpx_text = reconstruct_gpx_from_streams(session, case.activity_id_hex)
                    source = f"streams activity {case.activity_id_hex[:8]}"
            except Exception as exc:
                print(f"⚠️  {case.label}: impossible de charger GPX ({exc})")
                continue

            real_moving_min = case.real_moving_s / 60
            real_distance_km = case.real_distance_m / 1000
            real_pace = real_moving_min / real_distance_km if real_distance_km else 0
            v1 = run_v1(
                gpx_text,
                session,
                case=case,
                history_start_date=history_start_date,
                excluded_activity_ids=excluded_activity_ids,
            )
            v2 = run_v2(
                gpx_text,
                session,
                case=case,
                calibration=calibration,
                fatigue=fatigue,
                trail_surface_factor=1.20,
            )
            v2_mid = run_v2(
                gpx_text,
                session,
                case=case,
                calibration=calibration,
                fatigue=fatigue,
                trail_surface_factor=1.10,
            )
            v2_neutral = run_v2(
                gpx_text,
                session,
                case=case,
                calibration=calibration,
                fatigue=fatigue,
                trail_surface_factor=1.00,
            )

            results.append({
                "label": case.label, "category": case.category, "notes": case.notes, "source": source,
                "real": {"moving_min": real_moving_min, "distance_km": real_distance_km, "pace": real_pace, "dplus": case.real_elevation_gain_m},
                "v1": v1, "v2": v2, "v2_mid": v2_mid, "v2_neutral": v2_neutral,
                "calibration": calibration,
                "fatigue": fatigue,
                "validation": {
                    "history_start_date": history_start_date.isoformat(),
                    "history_end_date": case.race_datetime.isoformat(),
                    "excluded_activity_ids": [str(item) for item in excluded_activity_ids],
                },
                "d_v1": v1["moving_time_min"] - real_moving_min,
                "d_v2": v2["moving_time_min"] - real_moving_min,
                "d_v2_mid": v2_mid["moving_time_min"] - real_moving_min,
                "d_v2_neutral": v2_neutral["moving_time_min"] - real_moving_min,
                "potential_gain_min_range": case.potential_gain_min_range,
            })

    print("=" * 110)
    print("GOLDEN SET — Comparaison V1 / V2 / Réel")
    print("=" * 110)
    for r in results:
        real, v1, v2, v2_mid, v2_neutral = r["real"], r["v1"], r["v2"], r["v2_mid"], r["v2_neutral"]
        d_v1 = r["d_v1"]
        d_v2 = r["d_v2"]
        d_v2_mid = r["d_v2_mid"]
        d_v2_neutral = r["d_v2_neutral"]
        d_v1_pct = d_v1 / real["moving_min"] * 100
        d_v2_pct = d_v2 / real["moving_min"] * 100
        d_v2_mid_pct = d_v2_mid / real["moving_min"] * 100
        d_v2_neutral_pct = d_v2_neutral / real["moving_min"] * 100

        print()
        print(f"━━━ {r['label']} ━━━")
        print(f"  Classe : {r['category']}")
        print(f"  Notes  : {r['notes']}")
        print(f"  Source : {r['source']}")
        print(f"  Train  : données < {r['validation']['history_end_date'][:10]} · exclusion référence = {bool(r['validation']['excluded_activity_ids'])}")
        print(f"  Réel   : dist {real['distance_km']:.2f} km · D+ {real['dplus']:.0f} m · moving {fmt_min(real['moving_min'])} ({fmt_pace(real['pace'])})")
        if r["potential_gain_min_range"]:
            low_gain, high_gain = r["potential_gain_min_range"]
            potential_low = real["moving_min"] - high_gain
            potential_high = real["moving_min"] - low_gain
            print(f"  Potent.: contexte utilisateur, sans incident final = {fmt_min(potential_low)} à {fmt_min(potential_high)} (non scoré)")
        print(f"  V1     : dist {v1['total_distance_km']:.2f} km · D+ {v1['elevation_gain_m']:.0f} m · moving {fmt_min(v1['moving_time_min'])}  · écart {d_v1:+.1f} min ({d_v1_pct:+.1f}%)")
        print(f"  V2 1.20: dist {v2['total_distance_km']:.2f} km · D+ {v2['elevation_gain_m']:.0f} m · moving {fmt_min(v2['moving_time_min'])}  · écart {d_v2:+.1f} min ({d_v2_pct:+.1f}%)")
        print(f"  V2 1.10: dist {v2_mid['total_distance_km']:.2f} km · D+ {v2_mid['elevation_gain_m']:.0f} m · moving {fmt_min(v2_mid['moving_time_min'])}  · écart {d_v2_mid:+.1f} min ({d_v2_mid_pct:+.1f}%)")
        print(f"  V2 1.00: dist {v2_neutral['total_distance_km']:.2f} km · D+ {v2_neutral['elevation_gain_m']:.0f} m · moving {fmt_min(v2_neutral['moving_time_min'])}  · écart {d_v2_neutral:+.1f} min ({d_v2_neutral_pct:+.1f}%)")
        print(f"  V2 P10/P50/P90 (total): {fmt_min(v2['uncertainty_p10_total'])} / {fmt_min(v2['uncertainty_p50_total'])} / {fmt_min(v2['uncertainty_p90_total'])}  · météo {v2['temperature_min_c']}-{v2['temperature_max_c']}°C, pic +{v2['peak_heat_penalty_percent']}% ({v2['weather_source']})")
        calibration = r["calibration"]
        fatigue = r["fatigue"]
        print(f"  Params : P_run {calibration['p_run_wkg']} W/kg · {calibration['calibration_quality']} · {calibration['activity_count']} activités/{calibration['sample_count']} points · fatigue α={fatigue['alpha']} ({fatigue['model']})")

    print("\n" + "=" * 110)
    print("RÉSUMÉ")
    print("=" * 110)
    print(f"{'Course':<36} {'Réel':>10} {'V1':>10} {'ΔV1':>8} {'V2 1.20':>10} {'Δ':>8} {'V2 1.10':>10} {'Δ':>8} {'V2 1.00':>10} {'Δ':>8}")
    print("-" * 110)
    for r in results:
        real, v1, v2, v2_mid, v2_neutral = r["real"], r["v1"], r["v2"], r["v2_mid"], r["v2_neutral"]
        d_v1_pct = r["d_v1"] / real["moving_min"] * 100
        d_v2_pct = r["d_v2"] / real["moving_min"] * 100
        d_v2_mid_pct = r["d_v2_mid"] / real["moving_min"] * 100
        d_v2_neutral_pct = r["d_v2_neutral"] / real["moving_min"] * 100
        print(f"{r['label']:<36} {fmt_min(real['moving_min']):>10} {fmt_min(v1['moving_time_min']):>10} {d_v1_pct:>+7.1f}% {fmt_min(v2['moving_time_min']):>10} {d_v2_pct:>+7.1f}% {fmt_min(v2_mid['moving_time_min']):>10} {d_v2_mid_pct:>+7.1f}% {fmt_min(v2_neutral['moving_time_min']):>10} {d_v2_neutral_pct:>+7.1f}%")

    category_labels = {
        "official_clean": "Course officielle propre (score performance)",
        "training_control": "Entrainements controle (diagnostic uniquement)",
        "execution_degraded_non_scoring": "Course degradee par execution / non scoring",
        "incident_non_scoring": "Incident / non scoring",
    }
    for category, label in category_labels.items():
        selected = [result for result in results if result["category"] == category]
        if not selected:
            continue
        mae_v1 = sum(abs(result["d_v1"]) for result in selected) / len(selected)
        mae_v2 = sum(abs(result["d_v2"]) for result in selected) / len(selected)
        mae_v2_mid = sum(abs(result["d_v2_mid"]) for result in selected) / len(selected)
        mae_v2_neutral = sum(abs(result["d_v2_neutral"]) for result in selected) / len(selected)
        mape_v1 = sum(abs(result["d_v1"] / result["real"]["moving_min"] * 100) for result in selected) / len(selected)
        mape_v2 = sum(abs(result["d_v2"] / result["real"]["moving_min"] * 100) for result in selected) / len(selected)
        mape_v2_mid = sum(abs(result["d_v2_mid"] / result["real"]["moving_min"] * 100) for result in selected) / len(selected)
        mape_v2_neutral = sum(abs(result["d_v2_neutral"] / result["real"]["moving_min"] * 100) for result in selected) / len(selected)
        print()
        print(f"{label} - {len(selected)} cas :")
        print(f"  V1 : MAE = {mae_v1:.1f} min · MAPE = {mape_v1:.1f}%")
        print(f"  V2 SF=1.20 : MAE = {mae_v2:.1f} min · MAPE = {mape_v2:.1f}%")
        print(f"  V2 SF=1.10 : MAE = {mae_v2_mid:.1f} min · MAPE = {mape_v2_mid:.1f}%")
        print(f"  V2 SF=1.00 : MAE = {mae_v2_neutral:.1f} min · MAPE = {mape_v2_neutral:.1f}%")

    Path("/tmp/golden_set_output.json").write_text(json.dumps([
        {**r, "real": r["real"]} for r in results
    ], default=str, indent=2))
    print()
    print("Dump JSON brut → /tmp/golden_set_output.json")


if __name__ == "__main__":
    main()
