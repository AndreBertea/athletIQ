"""Physics based pace engine for Race Predictor V2."""
from __future__ import annotations

from typing import Any

from .environment_service import weather_at_elapsed
from .fatigue_model import clamp, default_fatigue_level, fatigue_factor


def minetti_run_cost(grade_fraction: float) -> float:
    """Running cost in J/kg/m from Minetti 2002."""
    grade = clamp(grade_fraction, -0.45, 0.45)
    return max(
        1.8,
        155.4 * grade**5
        - 30.4 * grade**4
        - 43.3 * grade**3
        + 46.3 * grade**2
        + 19.5 * grade
        + 3.6,
    )


def minetti_walk_cost(grade_fraction: float) -> float:
    """Walking cost in J/kg/m using Minetti walking polynomial."""
    grade = clamp(grade_fraction, -0.45, 0.45)
    return max(
        1.8,
        280.5 * grade**5
        - 58.7 * grade**4
        - 76.8 * grade**3
        + 51.9 * grade**2
        + 19.6 * grade
        + 2.5,
    )


def altitude_factor(altitude_m: float) -> float:
    return 1.0 + 0.06 * max(0.0, (altitude_m - 1500.0) / 1000.0)


def walk_threshold(p_run_wkg: float, fatigue_level: float) -> float:
    level_delta = clamp((p_run_wkg - 9.5) * 0.015, -0.04, 0.05)
    fatigue_delta = fatigue_level * 0.08
    return clamp(0.22 + level_delta - fatigue_delta, 0.15, 0.30)


def effort_multiplier(effort_mode: str) -> float:
    normalized = (effort_mode or "steady").strip().lower()
    if normalized in {"endurance", "easy"}:
        return 0.90
    if normalized in {"aggressive", "objectif_agressif", "objectif agressif"}:
        return 1.08
    if normalized in {"hr_target", "fc_cible", "fc cible"}:
        return 1.0
    return 1.0


def predict_segments(
    segments: list[dict[str, Any]],
    *,
    calibration: dict[str, Any],
    environment: dict[str, Any],
    fatigue_profile: dict[str, Any] | None = None,
    trail_surface_factor: float | None = None,
    analysis_mode: str,
    effort_mode: str,
) -> dict[str, Any]:
    p_run_base = float(calibration.get("p_run_wkg") or 9.5)
    p_run = max(5.0, p_run_base * effort_multiplier(effort_mode))
    p_walk_ratio = float(calibration.get("p_walk_ratio") or 0.75)
    p_walk = p_run * p_walk_ratio
    fatigue_alpha = float((fatigue_profile or {}).get("alpha") or 0.12)

    moving_time = 0.0
    cumulative_gain = 0.0
    cumulative_loss = 0.0
    predicted: list[dict[str, Any]] = []
    mode = analysis_mode if analysis_mode in {"route", "trail"} else "trail"
    surface_factor = (
        float(trail_surface_factor if trail_surface_factor is not None else 1.20)
        if mode == "trail"
        else 1.0
    )

    for segment in segments:
        grade_fraction = float(segment.get("avg_grade_percent") or 0) / 100
        distance_m = float(segment.get("distance_m") or float(segment.get("distance_km") or 0) * 1000)
        distance_km = distance_m / 1000
        cumulative_gain += float(segment.get("elevation_gain_m") or 0)
        cumulative_loss += float(segment.get("elevation_loss_m") or 0)

        fatigue_level = default_fatigue_level(moving_time, cumulative_gain, cumulative_loss)
        threshold = walk_threshold(p_run, fatigue_level)
        should_walk = mode == "trail" and grade_fraction >= threshold
        cost = minetti_walk_cost(grade_fraction) if should_walk else minetti_run_cost(grade_fraction)
        power = p_walk if should_walk else p_run
        segment_altitude_factor = altitude_factor(float(segment.get("altitude_m") or 0))
        segment_fatigue_factor = fatigue_factor(moving_time, cumulative_gain, cumulative_loss, alpha=fatigue_alpha)
        segment_weather = weather_at_elapsed(environment, moving_time)
        weather_factor = float(segment_weather["weather_factor"])
        combined_factor = segment_altitude_factor * segment_fatigue_factor * weather_factor * surface_factor
        speed_mps = max(0.35, power / (cost * combined_factor))
        segment_time_min = (distance_m / speed_mps) / 60
        moving_time += segment_time_min

        predicted_segment = {
            **segment,
            "locomotion": "walk" if should_walk else "run",
            "minetti_cost": round(cost, 3),
            "p_target_wkg": round(power, 2),
            "walk_threshold_percent": round(threshold * 100, 1),
            "fatigue_level": round(fatigue_level, 3),
            "fatigue_factor": round(segment_fatigue_factor, 4),
            "weather_factor": round(weather_factor, 4),
            "temperature_c": segment_weather["temperature_c"],
            "heat_penalty_percent": segment_weather["heat_penalty_percent"],
            "altitude_factor": round(segment_altitude_factor, 4),
            "surface_factor": round(surface_factor, 4),
            "speed_mps": round(speed_mps, 3),
            "predicted_pace": round(segment_time_min / distance_km, 2) if distance_km > 0 else 0,
            "predicted_time_min": round(segment_time_min, 2),
            "cumulative_moving_time_min": round(moving_time, 2),
            "cumulative_time_min": round(moving_time, 2),
        }
        predicted.append(predicted_segment)

    return {
        "segments": predicted,
        "moving_time_min": moving_time,
        "physics": {
            "model": "minetti_run_walk",
            "p_run_wkg": round(p_run, 2),
            "p_walk_wkg": round(p_walk, 2),
            "p_walk_ratio": round(p_walk_ratio, 2),
            "weather_factor": environment.get("weather_factor"),
            "dynamic_weather": bool(environment.get("weather_timeline_enabled")),
            "surface_factor": surface_factor,
            "surface_factor_source": (
                "explicit_override" if trail_surface_factor is not None else "empirical_trail_prior"
            ) if mode == "trail" else "route",
            "fatigue_alpha": round(fatigue_alpha, 3),
        },
    }
