"""Aid-station planning for Race Predictor V2."""
from __future__ import annotations

from typing import Any


def _format_minutes(minutes: float) -> str:
    return f"{int(minutes // 60)}h{int(minutes % 60):02d}"


def _format_pause(minutes: float) -> str:
    if minutes <= 0:
        return "0min"
    if float(minutes).is_integer():
        return f"{int(minutes)}min"
    return f"{minutes:.1f}min"


def _moving_time_at_distance(segments: list[dict[str, Any]], target_km: float) -> float:
    previous_distance = 0.0
    previous_time = 0.0
    for segment in segments:
        segment_distance = float(segment.get("distance_km") or 0)
        segment_time = float(segment.get("predicted_time_min") or 0)
        next_distance = previous_distance + segment_distance
        if target_km <= next_distance:
            ratio = (target_km - previous_distance) / segment_distance if segment_distance > 0 else 0
            return previous_time + segment_time * max(0.0, min(1.0, ratio))
        previous_distance = next_distance
        previous_time += segment_time
    return previous_time


def _ravito_point(
    segments: list[dict[str, Any]],
    *,
    distance_km: float,
    name: str,
    pause_min: float,
    cumulative_pause_before: float,
    source: str,
) -> dict[str, Any]:
    moving_time = _moving_time_at_distance(segments, distance_km)
    arrival = moving_time + cumulative_pause_before
    departure = arrival + pause_min
    return {
        "distance_km": round(distance_km, 2),
        "name": name,
        "pause_min": round(pause_min, 1),
        "pause_formatted": _format_pause(round(pause_min, 1)),
        "moving_time_min": round(moving_time, 1),
        "arrival_time_min": round(arrival, 1),
        "departure_time_min": round(departure, 1),
        "time_min": round(arrival, 1),
        "time_formatted": _format_minutes(arrival),
        "arrival_time_formatted": _format_minutes(arrival),
        "departure_time_formatted": _format_minutes(departure),
        "source": source,
    }


def manual_ravitos(
    segments: list[dict[str, Any]],
    custom_ravitos: list[dict[str, Any]] | None,
    total_distance_km: float,
    *,
    source: str = "manual",
) -> list[dict[str, Any]]:
    normalized = []
    for index, ravito in enumerate(custom_ravitos or []):
        try:
            distance_km = float(ravito.get("km", ravito.get("distance_km", 0)))
            pause_min = max(0.0, float(ravito.get("pause_min", ravito.get("pause", 0)) or 0))
        except (TypeError, ValueError):
            continue
        if 0 < distance_km < total_distance_km:
            normalized.append({
                "distance_km": distance_km,
                "pause_min": pause_min,
                "name": str(ravito.get("name") or f"Ravito {index + 1}"),
            })

    unique_by_distance = {round(item["distance_km"], 2): item for item in normalized}
    cumulative_pause = 0.0
    points = []
    for item in sorted(unique_by_distance.values(), key=lambda value: value["distance_km"]):
        point = _ravito_point(
            segments,
            distance_km=item["distance_km"],
            name=item["name"],
            pause_min=item["pause_min"],
            cumulative_pause_before=cumulative_pause,
            source=source,
        )
        points.append(point)
        cumulative_pause += item["pause_min"]
    return points


def auto_ravitos(
    segments: list[dict[str, Any]],
    global_stats: dict[str, Any],
    moving_time_min: float,
    *,
    analysis_mode: str,
    temperature_c: float,
) -> list[dict[str, Any]]:
    total_distance = float(global_stats.get("total_distance_km") or 0)
    if total_distance < 8:
        return []

    elevation_gain = float(global_stats.get("total_elevation_gain_m") or 0)
    elevation_per_km = elevation_gain / total_distance if total_distance else 0
    moving_hours = moving_time_min / 60
    is_trail = analysis_mode == "trail"
    heat_load = max(0.0, temperature_c - 18.0) / 12.0

    if is_trail:
        interval = 5.5 if elevation_per_km >= 70 or moving_hours >= 5 else 7.5
        base_pause = 3.0
        min_pause = 2.0
        max_pause = 12.0
    else:
        interval = 7.5 if moving_hours >= 3 else 10.0
        base_pause = 1.2
        min_pause = 0.5
        max_pause = 6.0

    distances = []
    next_distance = interval
    finish_buffer = max(2.0, interval * 0.35)
    while next_distance < total_distance - finish_buffer:
        distances.append(round(next_distance, 1))
        next_distance += interval

    points = []
    cumulative_pause = 0.0
    for index, distance_km in enumerate(distances):
        progress = distance_km / total_distance
        pause = base_pause
        pause += progress * (3.0 if is_trail else 1.0)
        pause += min(elevation_per_km / (40 if is_trail else 90), 2.5)
        pause += heat_load * (2.0 if is_trail else 1.0)
        pause += max(0.0, moving_hours - (3.0 if is_trail else 2.5)) * (0.50 if is_trail else 0.20)
        pause = round(max(min_pause, min(max_pause, pause)) * 2) / 2
        point = _ravito_point(
            segments,
            distance_km=distance_km,
            name=f"Ravito auto {index + 1}",
            pause_min=pause,
            cumulative_pause_before=cumulative_pause,
            source="auto",
        )
        points.append(point)
        cumulative_pause += pause
    return points


def apply_pauses_to_segments(segments: list[dict[str, Any]], ravito_points: list[dict[str, Any]]) -> None:
    cumulative_distance = 0.0
    for segment in segments:
        cumulative_distance += float(segment.get("distance_km") or 0)
        pause_before_end = sum(
            float(ravito.get("pause_min") or 0)
            for ravito in ravito_points
            if float(ravito.get("distance_km") or 0) <= cumulative_distance
        )
        segment["cumulative_time_min"] = round(float(segment.get("cumulative_moving_time_min") or 0) + pause_before_end, 2)


def ravito_config_from_points(ravito_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "km": round(float(ravito.get("distance_km") or 0), 2),
            "name": ravito.get("name") or "Ravito",
            "pause_min": round(float(ravito.get("pause_min") or 0), 1),
        }
        for ravito in ravito_points
        if float(ravito.get("distance_km") or 0) > 0
    ]
