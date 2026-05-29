"""Environment inputs for Race Predictor V2."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


OPTIMAL_TEMPERATURE_C = 11.0
DEFAULT_TIMELINE_HOURS = 72


def temperature_factor(temperature_c: float, *, p_run_wkg: float = 9.5) -> float:
    """Progressive heat penalty above the 10-12 C optimum."""
    heat_delta = max(0.0, temperature_c - OPTIMAL_TEMPERATURE_C)
    level_adjustment = max(0.65, min(1.35, 9.5 / max(6.0, p_run_wkg)))
    return 1.0 + heat_delta * 0.0045 * level_adjustment


def _fetch_open_meteo_timeline(
    latitude: float,
    longitude: float,
    race_datetime: datetime,
    *,
    duration_hours: int = DEFAULT_TIMELINE_HOURS,
) -> tuple[list[dict[str, Any]], str]:
    now = datetime.utcnow()
    is_archive = race_datetime < now - timedelta(days=5)
    base_url = "https://archive-api.open-meteo.com/v1/archive" if is_archive else "https://api.open-meteo.com/v1/forecast"
    end_datetime = race_datetime + timedelta(hours=max(1, duration_hours))
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "timezone": "UTC",
        "start_date": race_datetime.date().isoformat(),
        "end_date": end_datetime.date().isoformat(),
    }
    url = f"{base_url}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return [], "auto_failed"

    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    temperatures = hourly.get("temperature_2m") or []
    if not times or not temperatures:
        return [], "auto_failed"

    humidity = hourly.get("relative_humidity_2m") or []
    wind = hourly.get("wind_speed_10m") or []
    precipitation = hourly.get("precipitation") or []
    timeline: list[dict[str, Any]] = []
    for index, time_value in enumerate(times):
        try:
            timestamp = datetime.fromisoformat(str(time_value))
            temperature_c = float(temperatures[index])
        except (TypeError, ValueError, IndexError):
            continue
        elapsed_min = (timestamp - race_datetime).total_seconds() / 60
        if elapsed_min < -60 or elapsed_min > duration_hours * 60 + 60:
            continue
        timeline.append({
            "timestamp": timestamp.isoformat(),
            "elapsed_min": round(elapsed_min, 1),
            "temperature_c": temperature_c,
            "humidity_pct": humidity[index] if index < len(humidity) else None,
            "wind_speed_kmh": wind[index] if index < len(wind) else None,
            "precipitation_mm": precipitation[index] if index < len(precipitation) else None,
        })
    return timeline, "open_meteo_archive" if is_archive else "open_meteo_forecast"


def _interpolate_temperature(timeline: list[dict[str, Any]], elapsed_min: float) -> float | None:
    points = [point for point in timeline if point.get("temperature_c") is not None]
    if not points:
        return None
    ordered = sorted(points, key=lambda point: float(point.get("elapsed_min") or 0))
    if elapsed_min <= float(ordered[0]["elapsed_min"]):
        return float(ordered[0]["temperature_c"])
    if elapsed_min >= float(ordered[-1]["elapsed_min"]):
        return float(ordered[-1]["temperature_c"])
    for previous, current in zip(ordered, ordered[1:]):
        start = float(previous["elapsed_min"])
        end = float(current["elapsed_min"])
        if start <= elapsed_min <= end:
            if end == start:
                return float(current["temperature_c"])
            weight = (elapsed_min - start) / (end - start)
            return float(previous["temperature_c"]) + weight * (
                float(current["temperature_c"]) - float(previous["temperature_c"])
            )
    return float(ordered[-1]["temperature_c"])


def weather_at_elapsed(environment: dict[str, Any], elapsed_min: float) -> dict[str, float]:
    """Return segment heat exposure, interpolated from one fetched timeline."""
    p_run_wkg = float(environment.get("p_run_wkg") or 9.5)
    temperature_c = (
        _interpolate_temperature(environment.get("weather_timeline") or [], elapsed_min)
        if environment.get("weather_timeline_enabled", True)
        else None
    )
    if temperature_c is None:
        temperature_c = float(environment.get("temperature_c") or OPTIMAL_TEMPERATURE_C)
    factor = temperature_factor(temperature_c, p_run_wkg=p_run_wkg)
    return {
        "temperature_c": round(temperature_c, 1),
        "weather_factor": round(factor, 4),
        "heat_penalty_percent": round((factor - 1.0) * 100, 2),
    }


def summarize_weather_exposure(environment: dict[str, Any], duration_min: float) -> dict[str, Any]:
    """Build the user-facing 30-minute exposure summary for the predicted duration."""
    samples = []
    elapsed_min = 0.0
    while elapsed_min < max(0.0, duration_min):
        samples.append({"elapsed_min": round(elapsed_min, 1), **weather_at_elapsed(environment, elapsed_min)})
        elapsed_min += 30
    samples.append({"elapsed_min": round(max(0.0, duration_min), 1), **weather_at_elapsed(environment, duration_min)})
    temperatures = [float(sample["temperature_c"]) for sample in samples]
    heat_penalties = [float(sample["heat_penalty_percent"]) for sample in samples]
    return {
        **environment,
        "predicted_exposure_duration_min": round(duration_min, 1),
        "exposure_interval_min": 30,
        "exposure_timeline": samples,
        "temperature_min_c": round(min(temperatures), 1),
        "temperature_max_c": round(max(temperatures), 1),
        "peak_heat_penalty_percent": round(max(heat_penalties), 2),
    }


def build_environment(
    global_stats: dict[str, Any],
    *,
    race_datetime: datetime | None,
    weather_mode: str,
    manual_temperature_c: float | None,
    p_run_wkg: float,
) -> dict[str, Any]:
    temperature_c: float | None = None
    source = "default"
    normalized_mode = (weather_mode or "auto").strip().lower()
    timeline: list[dict[str, Any]] = []

    if normalized_mode == "auto" and race_datetime:
        timeline, source = _fetch_open_meteo_timeline(
            float(global_stats.get("start_lat") or 0),
            float(global_stats.get("start_lon") or 0),
            race_datetime,
        )
        temperature_c = _interpolate_temperature(timeline, 0)

    if temperature_c is None and manual_temperature_c is not None:
        temperature_c = float(manual_temperature_c)
        source = "manual"

    if temperature_c is None:
        temperature_c = OPTIMAL_TEMPERATURE_C
        source = "default"

    factor = temperature_factor(temperature_c, p_run_wkg=p_run_wkg)
    temperatures = [float(point["temperature_c"]) for point in timeline if point.get("temperature_c") is not None]
    return {
        "weather_mode": normalized_mode,
        "weather_source": source,
        "temperature_c": round(temperature_c, 1),
        "temperature_min_c": round(min(temperatures), 1) if temperatures else round(temperature_c, 1),
        "temperature_max_c": round(max(temperatures), 1) if temperatures else round(temperature_c, 1),
        "optimal_temperature_c": OPTIMAL_TEMPERATURE_C,
        "weather_factor": round(factor, 4),
        "heat_penalty_percent": round((factor - 1.0) * 100, 2),
        "weather_timeline": timeline,
        "weather_timeline_enabled": bool(timeline),
        "p_run_wkg": p_run_wkg,
    }
