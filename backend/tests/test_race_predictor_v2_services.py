from datetime import datetime
from uuid import UUID

from app.api.routers.prediction_router import _parse_optional_datetime, _resolve_history_start_date
from app.domain.entities.activity import Activity, ActivityType
from app.domain.services.race_predictor.calibration_service import build_calibration
from app.domain.services.race_predictor.environment_service import summarize_weather_exposure, weather_at_elapsed
from app.domain.services.race_predictor.fatigue_model import stream_grade_fraction
from app.domain.services.race_predictor.gpx_analyzer import analyze_gpx
from app.domain.services.race_predictor.physics_engine import (
    altitude_factor,
    minetti_run_cost,
    minetti_walk_cost,
    predict_segments,
    walk_threshold,
)
from app.domain.services.race_predictor.uncertainty_service import monte_carlo_uncertainty


def _sample_gpx() -> str:
    points = []
    lat = 45.0
    lon = 6.0
    elevation = 100.0
    for index in range(26):
        noisy = 0.9 if index % 2 == 0 else -0.9
        if index > 12:
            elevation += 2.0
        points.append(
            f'<trkpt lat="{lat + index * 0.001}" lon="{lon}"><ele>{elevation + noisy:.1f}</ele></trkpt>'
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test">
  <trk><name>Test</name><trkseg>{''.join(points)}</trkseg></trk>
</gpx>"""


def test_gpx_analyzer_smooths_altitude_noise_and_segments_adaptively():
    result = analyze_gpx(_sample_gpx())
    segments = result["segments"]

    assert segments
    assert result["global_stats"]["total_elevation_gain_m"] < 40
    assert all(segment["distance_m"] <= 1000.1 for segment in segments[:-1])
    assert all(segment["distance_m"] >= 180 for segment in segments[:-1])


def test_minetti_costs_and_walk_threshold_behaviour():
    assert 3.4 <= minetti_run_cost(0.0) <= 3.8
    assert 2.3 <= minetti_walk_cost(0.0) <= 2.7
    assert walk_threshold(12.0, 0.0) > walk_threshold(8.0, 0.0)
    assert walk_threshold(9.5, 0.8) < walk_threshold(9.5, 0.0)


def test_altitude_factor_and_uncertainty_ordering():
    assert altitude_factor(1200) == 1.0
    assert altitude_factor(2500) > 1.0

    uncertainty = monte_carlo_uncertainty(
        segments=[{"segment_id": 1, "predicted_time_min": 10.0}],
        moving_time_min=10.0,
        total_pause_min=2.0,
        calibration={"confidence": 0.7},
        environment={"weather_factor": 1.02, "weather_source": "manual"},
        simulations=300,
    )
    total_time = uncertainty["total_time"]
    assert total_time["p10"] <= total_time["p50"] <= total_time["p90"]
    assert uncertainty["segments"][0]["p10"] <= uncertainty["segments"][0]["p50"] <= uncertainty["segments"][0]["p90"]


def test_uncertainty_does_not_apply_weather_factor_twice():
    uncertainty = monte_carlo_uncertainty(
        segments=[{"segment_id": 1, "predicted_time_min": 100.0}],
        moving_time_min=100.0,
        total_pause_min=5.0,
        calibration={"confidence": 1.0},
        environment={"weather_factor": 1.20, "weather_source": "manual"},
        simulations=10,
        variation_stds={"p_run": 0.0, "fatigue": 0.0, "weather": 0.0, "surface": 0.0},
    )

    assert uncertainty["moving_time"]["p50"] == 100.0
    assert uncertainty["total_time"]["p50"] == 105.0


def test_weather_timeline_interpolates_heat_at_predicted_segment_passage():
    dynamic_environment = {
        "temperature_c": 11.0,
        "weather_factor": 1.0,
        "weather_source": "open_meteo_forecast",
        "weather_timeline_enabled": True,
        "weather_timeline": [
            {"elapsed_min": 0.0, "temperature_c": 11.0},
            {"elapsed_min": 60.0, "temperature_c": 31.0},
        ],
        "p_run_wkg": 9.5,
    }
    midpoint = weather_at_elapsed(dynamic_environment, 30.0)
    assert midpoint["temperature_c"] == 21.0
    assert midpoint["weather_factor"] > 1.0

    segments = [
        {"distance_m": 10000.0, "distance_km": 10.0, "avg_grade_percent": 0.0},
        {"distance_m": 10000.0, "distance_km": 10.0, "avg_grade_percent": 0.0},
    ]
    inputs = {
        "calibration": {"p_run_wkg": 9.5, "p_walk_ratio": 0.75},
        "fatigue_profile": {"alpha": 0.12},
        "analysis_mode": "route",
        "effort_mode": "steady",
    }
    static = predict_segments(
        segments,
        environment={**dynamic_environment, "weather_timeline_enabled": False},
        **inputs,
    )
    dynamic = predict_segments(segments, environment=dynamic_environment, **inputs)

    assert dynamic["segments"][0]["temperature_c"] == 11.0
    assert dynamic["segments"][1]["temperature_c"] > dynamic["segments"][0]["temperature_c"]
    assert dynamic["moving_time_min"] > static["moving_time_min"]
    exposure = summarize_weather_exposure(dynamic_environment, dynamic["moving_time_min"])
    assert exposure["temperature_max_c"] > exposure["temperature_min_c"]
    assert exposure["peak_heat_penalty_percent"] > 0


def test_historical_prediction_history_is_bounded_from_race_date():
    race_date = _parse_optional_datetime("2025-10-04T06:30:00+02:00")

    assert race_date == datetime(2025, 10, 4, 4, 30)
    assert _resolve_history_start_date(None, reference_date=race_date) == datetime(2022, 10, 2, 4, 30)
    assert _resolve_history_start_date("2026-01-01", reference_date=race_date) == datetime(2025, 7, 4, 4, 30)


def test_stream_grade_percent_is_converted_and_used_in_flat_calibration():
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    sample_count = 150
    activity = Activity(
        source="garmin",
        name="Flat route stream",
        activity_type=ActivityType.RUN,
        start_date=datetime(2025, 1, 10),
        distance=3000,
        moving_time=sample_count,
        elapsed_time=sample_count,
        total_elevation_gain=5,
        user_id=user_id,
        streams_data={
            "heartrate": {"data": [140] * sample_count},
            "velocity_smooth": {"data": [3.0] * sample_count},
            "grade_smooth": {"data": [1.5] * sample_count},
            "distance": {"data": [float(index * 3) for index in range(sample_count)]},
            "time": {"data": [float(index) for index in range(sample_count)]},
        },
    )

    class Rows:
        def all(self):
            return [activity]

    class SessionStub:
        def exec(self, _statement):
            return Rows()

    calibration = build_calibration(
        SessionStub(),
        user_id,
        history_start_date=datetime(2024, 1, 1),
    )

    assert stream_grade_fraction(9.6) == 0.096
    assert calibration["source"] == "streams_flat_road"
    assert calibration["sample_count"] == sample_count
    assert calibration["p_run_wkg"] == 10.8


def test_trail_surface_factor_can_be_measured_against_neutral_baseline():
    segments = [{"distance_m": 1000.0, "distance_km": 1.0, "avg_grade_percent": 0.0}]
    inputs = {
        "calibration": {"p_run_wkg": 9.5, "p_walk_ratio": 0.75},
        "environment": {"weather_factor": 1.0},
        "fatigue_profile": {"alpha": 0.12},
        "analysis_mode": "trail",
        "effort_mode": "steady",
    }

    neutral = predict_segments(segments, trail_surface_factor=1.0, **inputs)
    empirical_prior = predict_segments(segments, trail_surface_factor=1.2, **inputs)

    assert neutral["physics"]["surface_factor"] == 1.0
    assert empirical_prior["physics"]["surface_factor"] == 1.2
    assert empirical_prior["moving_time_min"] > neutral["moving_time_min"]
