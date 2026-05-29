"""GPX cleaning and adaptive segmentation for Race Predictor V2."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import gpxpy


EARTH_RADIUS_M = 6_371_000
ELEVATION_NOISE_THRESHOLD_M = 0.0
MIN_SEGMENT_M = 200
MAX_SEGMENT_M = 1000
GRADE_CHANGE_CUT = 0.04


@dataclass
class TrackPoint:
    lat: float
    lon: float
    elevation_m: float
    smoothed_elevation_m: float
    distance_m: float
    time: Any = None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _smooth(values: list[float], window: int = 3) -> list[float]:
    if not values:
        return []
    if len(values) < 3:
        return values[:]

    half = max(1, window // 2)
    smoothed: list[float] = []
    for index in range(len(values)):
        start = max(0, index - half)
        end = min(len(values), index + half + 1)
        smoothed.append(sum(values[start:end]) / (end - start))
    return smoothed


def _segment_elevation_stats(points: list[TrackPoint], start_index: int, end_index: int) -> dict[str, float]:
    gain = 0.0
    loss = 0.0
    grades: list[float] = []

    for index in range(start_index + 1, end_index + 1):
        previous = points[index - 1]
        current = points[index]
        distance_delta = max(0.0, current.distance_m - previous.distance_m)
        elevation_delta = current.smoothed_elevation_m - previous.smoothed_elevation_m
        if abs(elevation_delta) >= ELEVATION_NOISE_THRESHOLD_M:
            if elevation_delta > 0:
                gain += elevation_delta
            else:
                loss += abs(elevation_delta)
        if distance_delta > 0:
            grades.append(elevation_delta / distance_delta)

    net = points[end_index].smoothed_elevation_m - points[start_index].smoothed_elevation_m
    max_grade = max((abs(item) for item in grades), default=0.0)
    avg_altitude = sum(point.smoothed_elevation_m for point in points[start_index:end_index + 1]) / (end_index - start_index + 1)
    variability = 0.0
    if len(grades) > 1:
        mean = sum(grades) / len(grades)
        variability = math.sqrt(sum((grade - mean) ** 2 for grade in grades) / len(grades))

    return {
        "elevation_gain_m": gain,
        "elevation_loss_m": loss,
        "net_elevation_m": net,
        "max_grade_percent": max_grade * 100,
        "altitude_m": avg_altitude,
        "grade_variability": variability,
    }


def _manual_ravito_distances(custom_ravitos: list[dict[str, Any]] | None) -> list[float]:
    distances = []
    for ravito in custom_ravitos or []:
        try:
            km = float(ravito.get("km", ravito.get("distance_km", 0)))
        except (TypeError, ValueError):
            continue
        if km > 0:
            distances.append(km * 1000)
    return sorted(set(round(distance, 1) for distance in distances))


def _build_segment(
    points: list[TrackPoint],
    *,
    segment_id: int,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    start_point = points[start_index]
    end_point = points[end_index]
    distance_m = max(1.0, end_point.distance_m - start_point.distance_m)
    elevation_stats = _segment_elevation_stats(points, start_index, end_index)
    avg_grade = elevation_stats["net_elevation_m"] / distance_m

    return {
        "segment_id": segment_id,
        "from_km": round(start_point.distance_m / 1000, 3),
        "to_km": round(end_point.distance_m / 1000, 3),
        "distance_km": round(distance_m / 1000, 3),
        "distance_m": round(distance_m, 1),
        "elevation_gain_m": round(elevation_stats["elevation_gain_m"], 1),
        "elevation_loss_m": round(elevation_stats["elevation_loss_m"], 1),
        "net_elevation_m": round(elevation_stats["net_elevation_m"], 1),
        "avg_grade_percent": round(avg_grade * 100, 2),
        "max_grade_percent": round(elevation_stats["max_grade_percent"], 2),
        "altitude_m": round(elevation_stats["altitude_m"], 1),
        "grade_variability": round(elevation_stats["grade_variability"], 5),
        "start_lat": start_point.lat,
        "start_lon": start_point.lon,
        "end_lat": end_point.lat,
        "end_lon": end_point.lon,
        "terrain_type": "unknown",
    }


def analyze_gpx(
    gpx_text: str,
    *,
    custom_ravitos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a GPX file, smooth elevation and create adaptive segments."""
    gpx = gpxpy.parse(gpx_text)
    raw_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if point.elevation is None:
                    continue
                raw_points.append(point)

    if len(raw_points) < 2:
        raise ValueError("Fichier GPX sans trace exploitable")

    elevations = [float(point.elevation or 0) for point in raw_points]
    smoothed_elevations = _smooth(elevations)
    points: list[TrackPoint] = []
    cumulative_distance = 0.0

    for index, point in enumerate(raw_points):
        if index > 0:
            previous = raw_points[index - 1]
            cumulative_distance += _haversine_m(previous.latitude, previous.longitude, point.latitude, point.longitude)
        points.append(
            TrackPoint(
                lat=float(point.latitude),
                lon=float(point.longitude),
                elevation_m=elevations[index],
                smoothed_elevation_m=smoothed_elevations[index],
                distance_m=cumulative_distance,
                time=point.time,
            )
        )

    ravito_distances = _manual_ravito_distances(custom_ravitos)
    ravito_index = 0
    segments: list[dict[str, Any]] = []
    start_index = 0
    segment_id = 1

    for index in range(1, len(points)):
        distance_from_start = points[index].distance_m - points[start_index].distance_m
        if distance_from_start <= 0:
            continue

        start_elevation = points[start_index].smoothed_elevation_m
        current_grade = (points[index].smoothed_elevation_m - points[index - 1].smoothed_elevation_m) / max(
            1.0,
            points[index].distance_m - points[index - 1].distance_m,
        )
        segment_grade = (points[index].smoothed_elevation_m - start_elevation) / max(1.0, distance_from_start)
        next_ravito_distance = ravito_distances[ravito_index] if ravito_index < len(ravito_distances) else None
        crossed_ravito = (
            next_ravito_distance is not None
            and points[start_index].distance_m < next_ravito_distance <= points[index].distance_m
            and distance_from_start >= MIN_SEGMENT_M
        )

        should_cut = (
            distance_from_start >= MAX_SEGMENT_M
            or (distance_from_start >= MIN_SEGMENT_M and abs(current_grade - segment_grade) >= GRADE_CHANGE_CUT)
            or crossed_ravito
        )

        if should_cut:
            end_index = index
            previous_distance = points[index - 1].distance_m - points[start_index].distance_m
            if distance_from_start > MAX_SEGMENT_M and previous_distance >= MIN_SEGMENT_M:
                end_index = index - 1
            segments.append(_build_segment(points, segment_id=segment_id, start_index=start_index, end_index=end_index))
            segment_id += 1
            start_index = end_index
            if crossed_ravito:
                ravito_index += 1

    if start_index < len(points) - 1:
        remaining_distance = points[-1].distance_m - points[start_index].distance_m
        if segments and remaining_distance < MIN_SEGMENT_M * 0.5:
            previous_from_km = segments[-1]["from_km"]
            previous_start_index = min(
                range(len(points)),
                key=lambda point_index: abs(points[point_index].distance_m / 1000 - previous_from_km),
            )
            segments[-1] = _build_segment(points, segment_id=segments[-1]["segment_id"], start_index=previous_start_index, end_index=len(points) - 1)
        else:
            segments.append(_build_segment(points, segment_id=segment_id, start_index=start_index, end_index=len(points) - 1))

    total_gain = sum(float(segment["elevation_gain_m"]) for segment in segments)
    total_loss = sum(float(segment["elevation_loss_m"]) for segment in segments)
    total_distance_km = cumulative_distance / 1000
    net_elevation = points[-1].smoothed_elevation_m - points[0].smoothed_elevation_m

    elevation_points = [
        {
            "distance_km": round(point.distance_m / 1000, 3),
            "elevation_m": round(point.smoothed_elevation_m, 1),
            "raw_elevation_m": round(point.elevation_m, 1),
        }
        for index, point in enumerate(points)
        if index == 0 or index == len(points) - 1 or index % max(1, len(points) // 500) == 0
    ]

    global_stats = {
        "total_distance_km": round(total_distance_km, 2),
        "total_elevation_gain_m": round(total_gain, 1),
        "total_elevation_loss_m": round(total_loss, 1),
        "net_elevation_m": round(net_elevation, 1),
        "avg_grade_percent": round((net_elevation / cumulative_distance) * 100, 2) if cumulative_distance > 0 else 0,
        "elevation_per_km": round(total_gain / total_distance_km, 1) if total_distance_km > 0 else 0,
        "start_lat": points[0].lat,
        "start_lon": points[0].lon,
        "end_lat": points[-1].lat,
        "end_lon": points[-1].lon,
        "segment_count": len(segments),
    }

    return {
        "points": points,
        "segments": segments,
        "elevation_points": elevation_points,
        "global_stats": global_stats,
    }
