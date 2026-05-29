"""
Tests pour weather_service — Tache 2.5.1
Mock HTTP response Open-Meteo pour tester l'enrichissement meteo des activites.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import httpx
from sqlalchemy.exc import IntegrityError

from app.domain.entities.activity_weather import ActivityWeather
from app.domain.services.weather_service import (
    _parse_streams,
    _extract_first_gps,
    _extract_activity_gps,
    _find_closest_hour_index,
    _build_weather_from_response,
    _build_open_meteo_request,
    _call_open_meteo,
    fetch_weather_for_activity,
    enrich_all_weather,
    is_weather_fetched,
    HISTORICAL_BASE_URL,
    FORECAST_BASE_URL,
    FORECAST_LOOKBACK_DAYS,
    HOURLY_VARIABLES,
)


def _make_activity(
    streams_data,
    start_date=None,
    activity_id=None,
    user_id=None,
    start_latlng=None,
    end_latlng=None,
    moving_time=None,
    elapsed_time=None,
):
    """Cree un mock Activity pour les tests meteo."""
    activity = MagicMock()
    activity.id = activity_id or uuid4()
    activity.user_id = user_id or uuid4()
    activity.streams_data = streams_data
    activity.start_date = start_date or datetime(2025, 6, 15, 9, 30, 0)
    activity.start_latlng = start_latlng
    activity.end_latlng = end_latlng
    if moving_time is not None:
        activity.moving_time = moving_time
    if elapsed_time is not None:
        activity.elapsed_time = elapsed_time
    return activity


def _make_mock_session(weather_exists=False):
    """Cree un mock Session SQLModel."""
    session = MagicMock()
    if weather_exists:
        session.exec.return_value.first.return_value = MagicMock(spec=ActivityWeather)
    else:
        session.exec.return_value.first.return_value = None
    return session


# --- Reponse Open-Meteo mock ---
MOCK_OPEN_METEO_RESPONSE = {
    "latitude": 48.8566,
    "longitude": 2.3522,
    "elevation": 42.0,
    "hourly_units": {
        "temperature_2m": "°C",
        "apparent_temperature": "°C",
        "wind_gusts_10m": "km/h",
    },
    "hourly": {
        "time": [
            "2025-06-15T08:00", "2025-06-15T09:00", "2025-06-15T10:00",
            "2025-06-15T11:00", "2025-06-15T12:00",
        ],
        "temperature_2m": [18.5, 20.1, 22.3, 24.0, 25.2],
        "apparent_temperature": [17.8, 19.4, 21.8, 23.7, 24.9],
        "dew_point_2m": [13.2, 13.3, 13.4, 13.5, 13.6],
        "relative_humidity_2m": [72.0, 65.0, 58.0, 52.0, 48.0],
        "wind_speed_10m": [8.5, 10.2, 12.0, 11.5, 10.8],
        "wind_direction_10m": [180.0, 185.0, 190.0, 195.0, 200.0],
        "wind_gusts_10m": [14.0, 16.0, 19.0, 18.0, 17.0],
        "surface_pressure": [1013.2, 1013.0, 1012.8, 1012.5, 1012.3],
        "precipitation": [0.0, 0.0, 0.1, 0.0, 0.0],
        "rain": [0.0, 0.0, 0.1, 0.0, 0.0],
        "cloud_cover": [25.0, 30.0, 45.0, 60.0, 55.0],
        "weather_code": [1, 2, 3, 2, 1],
    }
}

# Streams avec GPS valide
STREAMS_WITH_GPS = {
    "latlng": {"data": [[48.8566, 2.3522], [48.8570, 2.3530]]},
    "distance": {"data": [0, 100]},
    "time": {"data": [0, 30]},
}

# Streams sans GPS
STREAMS_NO_GPS = {
    "distance": {"data": [0, 100, 200]},
    "time": {"data": [0, 30, 60]},
}


# =============================================================================
# Tests _extract_first_gps
# =============================================================================
class TestExtractFirstGps:

    def test_extract_from_dict_format(self):
        streams = {"latlng": {"data": [[48.8566, 2.3522], [48.857, 2.353]]}}
        result = _extract_first_gps(streams)
        assert result == (48.8566, 2.3522)

    def test_extract_from_list_format(self):
        streams = {"latlng": [[45.0, 3.0], [45.1, 3.1]]}
        result = _extract_first_gps(streams)
        assert result == (45.0, 3.0)

    def test_no_latlng_key(self):
        streams = {"distance": {"data": [0, 100]}}
        assert _extract_first_gps(streams) is None

    def test_empty_latlng_data(self):
        streams = {"latlng": {"data": []}}
        assert _extract_first_gps(streams) is None

    def test_latlng_none(self):
        streams = {"latlng": None}
        assert _extract_first_gps(streams) is None

    def test_invalid_point_skipped(self):
        """Points invalides sont ignores, le premier valide est retourne."""
        streams = {"latlng": {"data": [[None, None], [48.85, 2.35]]}}
        result = _extract_first_gps(streams)
        assert result == (48.85, 2.35)

    def test_single_value_point_skipped(self):
        streams = {"latlng": {"data": [[48.85]]}}
        assert _extract_first_gps(streams) is None


# =============================================================================
# Tests _extract_activity_gps
# =============================================================================
class TestExtractActivityGps:

    def test_prefers_streams_latlng(self):
        activity = _make_activity(STREAMS_WITH_GPS, start_latlng=[45.0, 3.0])
        assert _extract_activity_gps(activity) == (48.8566, 2.3522)

    def test_falls_back_to_start_latlng(self):
        activity = _make_activity(STREAMS_NO_GPS, start_latlng=[45.0, 3.0])
        assert _extract_activity_gps(activity) == (45.0, 3.0)

    def test_falls_back_to_start_latlng_json_string(self):
        activity = _make_activity(None, start_latlng="[45.0, 3.0]")
        assert _extract_activity_gps(activity) == (45.0, 3.0)

    def test_falls_back_to_end_latlng(self):
        activity = _make_activity(None, start_latlng=None, end_latlng=[46.0, 4.0])
        assert _extract_activity_gps(activity) == (46.0, 4.0)

    def test_invalid_activity_coordinates_return_none(self):
        activity = _make_activity(None, start_latlng=[999, 3.0], end_latlng="invalid")
        assert _extract_activity_gps(activity) is None


# =============================================================================
# Tests _find_closest_hour_index
# =============================================================================
class TestFindClosestHourIndex:

    def test_exact_match(self):
        hours = ["2025-06-15T09:00", "2025-06-15T10:00", "2025-06-15T11:00"]
        target = datetime(2025, 6, 15, 10, 0, 0)
        assert _find_closest_hour_index(hours, target) == 1

    def test_closest_match(self):
        """09:30 est plus proche de 10:00 que de 09:00 (30 min vs 30 min, mais 09:00 gagne car premier)."""
        hours = ["2025-06-15T09:00", "2025-06-15T10:00", "2025-06-15T11:00"]
        target = datetime(2025, 6, 15, 9, 30, 0)
        idx = _find_closest_hour_index(hours, target)
        # 09:30 est a 30min de 09:00 et 30min de 10:00, le premier gagne (best_diff egal, pas de remplacement)
        assert idx == 0

    def test_closer_to_later_hour(self):
        """09:45 est plus proche de 10:00 (15min) que de 09:00 (45min)."""
        hours = ["2025-06-15T09:00", "2025-06-15T10:00", "2025-06-15T11:00"]
        target = datetime(2025, 6, 15, 9, 45, 0)
        assert _find_closest_hour_index(hours, target) == 1

    def test_single_hour(self):
        hours = ["2025-06-15T12:00"]
        target = datetime(2025, 6, 15, 8, 0, 0)
        assert _find_closest_hour_index(hours, target) == 0

    def test_empty_hours_returns_zero(self):
        assert _find_closest_hour_index([], datetime(2025, 6, 15, 9, 0, 0)) == 0


# =============================================================================
# Tests _build_weather_from_response
# =============================================================================
class TestBuildWeatherFromResponse:

    def test_builds_correct_weather(self):
        """Verifie que la reponse Open-Meteo est correctement mappee."""
        activity = _make_activity(
            STREAMS_WITH_GPS,
            start_date=datetime(2025, 6, 15, 9, 30, 0),
            elapsed_time=1800,
        )
        weather = _build_weather_from_response(MOCK_OPEN_METEO_RESPONSE, activity)

        assert weather is not None
        assert weather.activity_id == activity.id
        # 09:30 → index 1 (09:00) ou 2 (10:00). 09:30 est a 30min des deux, index 1 gagne
        assert weather.temperature_c == 20.1
        assert weather.humidity_pct == 65.0
        assert weather.wind_speed_kmh == 10.2
        assert weather.wind_direction_deg == 185.0
        assert weather.pressure_hpa == 1013.0
        assert weather.precipitation_mm == 0.0
        assert weather.cloud_cover_pct == 30.0
        assert weather.weather_code == 2
        assert weather.sampled_at == datetime(2025, 6, 15, 9, 0, 0)
        assert weather.latitude == 48.8566
        assert weather.longitude == 2.3522
        assert weather.elevation_m == 42.0
        assert weather.hourly_units == MOCK_OPEN_METEO_RESPONSE["hourly_units"]
        assert weather.hourly_snapshot["time"] == "2025-06-15T09:00"
        assert weather.hourly_snapshot["apparent_temperature"] == 19.4
        assert weather.hourly_snapshot["dew_point_2m"] == 13.3
        assert weather.hourly_snapshot["wind_gusts_10m"] == 16.0
        assert weather.hourly_snapshot["timeline_interval_min"] == 10
        assert weather.hourly_snapshot["timeline_duration_min"] == 30.0
        timeline = weather.hourly_snapshot["timeline_10min"]
        assert [point["elapsed_min"] for point in timeline] == [0, 10, 20, 30]
        assert timeline[0]["timestamp"] == "2025-06-15T09:30:00"
        assert timeline[0]["temperature_c"] == 21.2
        assert timeline[-1]["timestamp"] == "2025-06-15T10:00:00"
        assert timeline[-1]["temperature_c"] == 22.3

    def test_no_hourly_data(self):
        data = {"latitude": 48.85, "longitude": 2.35}
        activity = _make_activity(STREAMS_WITH_GPS)
        assert _build_weather_from_response(data, activity) is None

    def test_empty_time_array(self):
        data = {"hourly": {"time": []}}
        activity = _make_activity(STREAMS_WITH_GPS)
        assert _build_weather_from_response(data, activity) is None

    def test_weather_code_is_int(self):
        activity = _make_activity(STREAMS_WITH_GPS, start_date=datetime(2025, 6, 15, 9, 0, 0))
        weather = _build_weather_from_response(MOCK_OPEN_METEO_RESPONSE, activity)
        assert isinstance(weather.weather_code, int)

    def test_request_metadata_is_persisted(self):
        activity = _make_activity(STREAMS_WITH_GPS, start_date=datetime(2025, 6, 15, 9, 0, 0))
        data = {
            **MOCK_OPEN_METEO_RESPONSE,
            "_athletiq_request": {
                "template": "historical_archive",
                "base_url": HISTORICAL_BASE_URL,
                "params": {"hourly": ",".join(HOURLY_VARIABLES)},
            },
        }

        weather = _build_weather_from_response(data, activity)

        assert weather.source_endpoint == "historical_archive"
        assert weather.source_url == HISTORICAL_BASE_URL
        assert weather.request_params == {"hourly": ",".join(HOURLY_VARIABLES)}


# =============================================================================
# Tests _call_open_meteo (mock HTTP)
# =============================================================================
class TestCallOpenMeteo:

    def test_build_open_meteo_request_uses_shared_template(self):
        """Le template doit centraliser les variables demandees aux deux endpoints."""
        old_date = datetime.now(timezone.utc) - timedelta(days=FORECAST_LOOKBACK_DAYS + 10)

        base_url, params, template_name = _build_open_meteo_request(48.85, 2.35, old_date)

        assert base_url == HISTORICAL_BASE_URL
        assert template_name == "historical_archive"
        assert params["hourly"] == ",".join(HOURLY_VARIABLES)
        assert "apparent_temperature" in params["hourly"]
        assert "wind_gusts_10m" in params["hourly"]
        assert params["start_date"] == old_date.strftime("%Y-%m-%d")
        assert params["end_date"] == old_date.strftime("%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_forecast_api_for_recent_past_activity(self):
        """Activite recente passee → utilise forecast avec past_days."""
        old_date = datetime.now(timezone.utc) - timedelta(days=30)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await _call_open_meteo(48.85, 2.35, old_date, client)

        assert result["hourly"] == MOCK_OPEN_METEO_RESPONSE["hourly"]
        assert result["_athletiq_request"]["template"] == "forecast_recent"
        call_args = client.get.call_args
        assert call_args[0][0] == FORECAST_BASE_URL
        params = call_args[1]["params"]
        assert params["past_days"] == 30
        assert params["forecast_days"] == 1
        assert "apparent_temperature" in params["hourly"]
        assert "wind_gusts_10m" in params["hourly"]

    @pytest.mark.asyncio
    async def test_forecast_past_days_uses_calendar_date(self):
        """past_days doit inclure le jour cible meme si l'heure n'a pas encore ete atteinte."""
        now = datetime.now(timezone.utc)
        target = (now - timedelta(days=9)).replace(hour=23, minute=59, second=0, microsecond=0)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        await _call_open_meteo(48.85, 2.35, target, client)

        params = client.get.call_args[1]["params"]
        assert params["past_days"] == 9

    @pytest.mark.asyncio
    async def test_historical_api_for_old_activity(self):
        """Activite trop ancienne pour forecast/past_days → utilise archive-api."""
        old_date = datetime.now(timezone.utc) - timedelta(days=FORECAST_LOOKBACK_DAYS + 10)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await _call_open_meteo(48.85, 2.35, old_date, client)

        assert result["hourly"] == MOCK_OPEN_METEO_RESPONSE["hourly"]
        assert result["_athletiq_request"]["template"] == "historical_archive"
        call_args = client.get.call_args
        assert call_args[0][0] == HISTORICAL_BASE_URL

    @pytest.mark.asyncio
    async def test_forecast_api_for_recent_activity(self):
        """Activite <= 93 jours → utilise api.open-meteo.com."""
        recent_date = datetime.now(timezone.utc) - timedelta(days=1)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await _call_open_meteo(48.85, 2.35, recent_date, client)

        assert result["hourly"] == MOCK_OPEN_METEO_RESPONSE["hourly"]
        assert result["_athletiq_request"]["template"] == "forecast_recent"
        call_args = client.get.call_args
        assert call_args[0][0] == FORECAST_BASE_URL

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        """Erreur HTTP → retourne None."""
        client = AsyncMock(spec=httpx.AsyncClient)
        response = MagicMock()
        response.status_code = 429
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Too Many Requests", request=MagicMock(), response=response
        )
        client.get = AsyncMock(return_value=response)

        result = await _call_open_meteo(48.85, 2.35, datetime.now(timezone.utc), client)
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        """Erreur reseau → retourne None."""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused", request=MagicMock()))

        result = await _call_open_meteo(48.85, 2.35, datetime.now(timezone.utc), client)
        assert result is None

    @pytest.mark.asyncio
    async def test_correct_params_sent(self):
        """Verifie les parametres envoyes a Open-Meteo."""
        date = datetime(2025, 1, 10, 14, 0, 0, tzinfo=timezone.utc)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        await _call_open_meteo(45.0, 3.0, date, client)

        call_kwargs = client.get.call_args[1]
        params = call_kwargs["params"]
        assert params["latitude"] == 45.0
        assert params["longitude"] == 3.0
        assert params["start_date"] == "2025-01-10"
        assert params["end_date"] == "2025-01-10"
        assert params["timezone"] == "UTC"


# =============================================================================
# Tests fetch_weather_for_activity (integration avec mocks)
# =============================================================================
class TestFetchWeatherForActivity:

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Fetch reussi → ActivityWeather stocke en base."""
        activity = _make_activity(
            STREAMS_WITH_GPS,
            start_date=datetime(2025, 6, 15, 9, 30, 0),
        )
        session = _make_mock_session(weather_exists=False)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await fetch_weather_for_activity(session, activity, client)

        assert result is True
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, ActivityWeather)
        assert added.activity_id == activity.id
        assert added.temperature_c is not None
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_fetched_skips(self):
        """Si meteo deja en base → retourne True sans appel API."""
        activity = _make_activity(STREAMS_WITH_GPS)
        session = _make_mock_session(weather_exists=True)

        client = AsyncMock(spec=httpx.AsyncClient)

        result = await fetch_weather_for_activity(session, activity, client)

        assert result is True
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_streams_returns_false(self):
        """Pas de streams_data et pas de coordonnees d'activite → retourne False."""
        activity = _make_activity(streams_data=None)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False

    @pytest.mark.asyncio
    async def test_no_streams_with_start_latlng_fetches_weather(self):
        """Pas de streams_data mais start_latlng disponible → fetch meteo."""
        activity = _make_activity(
            streams_data=None,
            start_date=datetime(2025, 6, 15, 9, 30, 0),
            start_latlng=[48.8566, 2.3522],
        )
        session = _make_mock_session(weather_exists=False)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await fetch_weather_for_activity(session, activity, client)

        assert result is True
        params = client.get.call_args[1]["params"]
        assert params["latitude"] == 48.8566
        assert params["longitude"] == 2.3522
        session.add.assert_called_once()
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_gps_returns_false(self):
        """Streams sans GPS et pas de coordonnees d'activite → retourne False."""
        activity = _make_activity(STREAMS_NO_GPS)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False

    @pytest.mark.asyncio
    async def test_null_string_streams_returns_false(self):
        """streams_data = 'null' → retourne False."""
        activity = _make_activity(streams_data="null")
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False

    @pytest.mark.asyncio
    async def test_api_failure_returns_false(self):
        """Erreur API Open-Meteo → retourne False, rien stocke."""
        activity = _make_activity(STREAMS_WITH_GPS)
        session = _make_mock_session()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.RequestError("timeout", request=MagicMock()))

        result = await fetch_weather_for_activity(session, activity, client)

        assert result is False
        session.add.assert_not_called()


# =============================================================================
# Tests is_weather_fetched
# =============================================================================
class TestIsWeatherFetched:

    def test_not_fetched(self):
        session = _make_mock_session(weather_exists=False)
        assert is_weather_fetched(session, uuid4()) is False

    def test_already_fetched(self):
        session = _make_mock_session(weather_exists=True)
        assert is_weather_fetched(session, uuid4()) is True


# =============================================================================
# Tests fallback si pas de GPS — Tache 2.5.2
# =============================================================================
class TestFallbackNoGps:
    """Verifie que le service meteo skip correctement les activites sans coordonnees GPS."""

    @pytest.mark.asyncio
    async def test_streams_with_empty_latlng_data(self):
        """latlng present mais data vide → fallback, retourne False."""
        streams = {"latlng": {"data": []}, "distance": {"data": [0, 100]}}
        activity = _make_activity(streams)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False
        session.add.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_streams_with_only_invalid_gps_points(self):
        """Tous les points GPS sont invalides (None) → fallback."""
        streams = {"latlng": {"data": [[None, None], [None, None]]}}
        activity = _make_activity(streams)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_streams_with_single_element_points(self):
        """Points GPS avec un seul element (pas lat+lon) → fallback."""
        streams = {"latlng": {"data": [[48.85], [2.35]]}}
        activity = _make_activity(streams)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_streams_json_string_without_gps(self):
        """streams_data est un JSON string valide sans latlng → fallback."""
        streams_json = json.dumps({"distance": {"data": [0, 100, 200]}, "time": {"data": [0, 30, 60]}})
        activity = _make_activity(streams_json)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_streams_latlng_none_value(self):
        """latlng est explicitement None dans le dict → fallback."""
        streams = {"latlng": None, "distance": {"data": [0, 50]}}
        activity = _make_activity(streams)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_streams_latlng_not_a_list_or_dict(self):
        """latlng est un type inattendu (string) → fallback."""
        streams = {"latlng": "invalid"}
        activity = _make_activity(streams)
        session = _make_mock_session()

        result = await fetch_weather_for_activity(session, activity)

        assert result is False
        session.add.assert_not_called()


# =============================================================================
# Tests interpolation horaire — Tache 2.5.3
# =============================================================================
class TestHourlyInterpolation:
    """Verifie que l'interpolation horaire selectionne la bonne heure
    et retourne les donnees meteo correspondantes."""

    def test_activity_before_all_hours(self):
        """Activite a 06:00, heures commencent a 08:00 → selectionne la premiere heure."""
        hours = ["2025-06-15T08:00", "2025-06-15T09:00", "2025-06-15T10:00"]
        target = datetime(2025, 6, 15, 6, 0, 0)
        assert _find_closest_hour_index(hours, target) == 0

    def test_activity_after_all_hours(self):
        """Activite a 23:00, heures s'arretent a 12:00 → selectionne la derniere heure."""
        hours = ["2025-06-15T08:00", "2025-06-15T09:00", "2025-06-15T12:00"]
        target = datetime(2025, 6, 15, 23, 0, 0)
        assert _find_closest_hour_index(hours, target) == 2

    def test_asymmetric_gap_closer_to_earlier(self):
        """09:10 est a 10min de 09:00 et 50min de 10:00 → selectionne 09:00."""
        hours = ["2025-06-15T09:00", "2025-06-15T10:00"]
        target = datetime(2025, 6, 15, 9, 10, 0)
        assert _find_closest_hour_index(hours, target) == 0

    def test_asymmetric_gap_closer_to_later(self):
        """09:50 est a 50min de 09:00 et 10min de 10:00 → selectionne 10:00."""
        hours = ["2025-06-15T09:00", "2025-06-15T10:00"]
        target = datetime(2025, 6, 15, 9, 50, 0)
        assert _find_closest_hour_index(hours, target) == 1

    def test_timezone_aware_target(self):
        """Un start_date avec tzinfo doit fonctionner (replace(tzinfo=None) dans le code)."""
        hours = ["2025-06-15T09:00", "2025-06-15T10:00", "2025-06-15T11:00"]
        target = datetime(2025, 6, 15, 10, 15, 0, tzinfo=timezone.utc)
        assert _find_closest_hour_index(hours, target) == 1

    def test_24_hours_midday_activity(self):
        """Journee complete (24h), activite a 14:30 → selectionne 14:00 ou 15:00."""
        hours = [f"2025-06-15T{h:02d}:00" for h in range(24)]
        target = datetime(2025, 6, 15, 14, 30, 0)
        idx = _find_closest_hour_index(hours, target)
        # 14:30 equidistant de 14:00 et 15:00, premiere rencontree gagne
        assert idx == 14

    def test_24_hours_activity_at_14_45(self):
        """Journee complete (24h), activite a 14:45 → 15:00 est plus proche."""
        hours = [f"2025-06-15T{h:02d}:00" for h in range(24)]
        target = datetime(2025, 6, 15, 14, 45, 0)
        assert _find_closest_hour_index(hours, target) == 15

    def test_build_weather_uses_correct_hour_data(self):
        """Verifie que _build_weather_from_response retourne les donnees de l'heure interpolee."""
        response = {
            "hourly": {
                "time": [
                    "2025-06-15T06:00", "2025-06-15T07:00", "2025-06-15T08:00",
                    "2025-06-15T09:00", "2025-06-15T10:00",
                ],
                "temperature_2m": [10.0, 12.0, 15.0, 18.0, 21.0],
                "relative_humidity_2m": [90.0, 85.0, 75.0, 65.0, 55.0],
                "wind_speed_10m": [5.0, 6.0, 7.0, 8.0, 9.0],
                "wind_direction_10m": [100.0, 110.0, 120.0, 130.0, 140.0],
                "surface_pressure": [1015.0, 1014.5, 1014.0, 1013.5, 1013.0],
                "precipitation": [0.5, 0.3, 0.1, 0.0, 0.0],
                "cloud_cover": [80.0, 70.0, 50.0, 30.0, 20.0],
                "weather_code": [61, 3, 2, 1, 0],
            }
        }
        # Activite a 08:20 → plus proche de 08:00 (index 2) que de 09:00 (index 3)
        activity = _make_activity(STREAMS_WITH_GPS, start_date=datetime(2025, 6, 15, 8, 20, 0))
        weather = _build_weather_from_response(response, activity)

        assert weather is not None
        assert weather.temperature_c == 15.0  # index 2
        assert weather.humidity_pct == 75.0
        assert weather.wind_speed_kmh == 7.0
        assert weather.precipitation_mm == 0.1
        assert weather.weather_code == 2

    def test_build_weather_late_activity(self):
        """Activite a 09:50 → plus proche de 10:00 (index 4)."""
        response = {
            "hourly": {
                "time": [
                    "2025-06-15T06:00", "2025-06-15T07:00", "2025-06-15T08:00",
                    "2025-06-15T09:00", "2025-06-15T10:00",
                ],
                "temperature_2m": [10.0, 12.0, 15.0, 18.0, 21.0],
                "relative_humidity_2m": [90.0, 85.0, 75.0, 65.0, 55.0],
                "wind_speed_10m": [5.0, 6.0, 7.0, 8.0, 9.0],
                "wind_direction_10m": [100.0, 110.0, 120.0, 130.0, 140.0],
                "surface_pressure": [1015.0, 1014.5, 1014.0, 1013.5, 1013.0],
                "precipitation": [0.5, 0.3, 0.1, 0.0, 0.0],
                "cloud_cover": [80.0, 70.0, 50.0, 30.0, 20.0],
                "weather_code": [61, 3, 2, 1, 0],
            }
        }
        activity = _make_activity(STREAMS_WITH_GPS, start_date=datetime(2025, 6, 15, 9, 50, 0))
        weather = _build_weather_from_response(response, activity)

        assert weather is not None
        assert weather.temperature_c == 21.0  # index 4
        assert weather.humidity_pct == 55.0
        assert weather.wind_speed_kmh == 9.0
        assert weather.weather_code == 0

    @pytest.mark.asyncio
    async def test_end_to_end_interpolation(self):
        """Test bout-en-bout : fetch_weather_for_activity utilise l'interpolation correcte."""
        activity = _make_activity(
            STREAMS_WITH_GPS,
            start_date=datetime(2025, 6, 15, 10, 15, 0),
        )
        session = _make_mock_session(weather_exists=False)

        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_OPEN_METEO_RESPONSE
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await fetch_weather_for_activity(session, activity, client)

        assert result is True
        added = session.add.call_args[0][0]
        # 10:15 → plus proche de 10:00 (index 2) que de 11:00 (index 3)
        assert added.temperature_c == 22.3  # index 2 dans MOCK_OPEN_METEO_RESPONSE
        assert added.humidity_pct == 58.0
        assert added.wind_speed_kmh == 12.0


    @pytest.mark.asyncio
    async def test_enrich_all_skips_no_gps_activities(self):
        """enrich_all_weather skip les activites sans GPS sans erreur."""
        activity_no_gps = _make_activity(STREAMS_NO_GPS)
        activity_no_gps.streams_data = STREAMS_NO_GPS

        session = MagicMock()
        # exec pour la requete select(Activity) retourne l'activite sans GPS
        session.exec.return_value.all.return_value = [activity_no_gps]
        # exec pour is_weather_fetched retourne None (pas encore fetched)
        session.exec.return_value.first.return_value = None

        result = await enrich_all_weather(session, user_id=activity_no_gps.user_id)

        assert result["processed"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == 0
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_archive_mode_only_processes_historical_activities(self):
        """Le mode archive ne doit pas consommer le lot sur des activites recentes."""
        user_id = uuid4()
        recent_activity = _make_activity(
            STREAMS_WITH_GPS,
            start_date=datetime.now(timezone.utc) - timedelta(days=10),
            user_id=user_id,
        )
        old_activity = _make_activity(
            STREAMS_WITH_GPS,
            start_date=datetime.now(timezone.utc) - timedelta(days=FORECAST_LOOKBACK_DAYS + 10),
            user_id=user_id,
        )

        session = MagicMock()
        session.exec.return_value.all.return_value = [recent_activity, old_activity]
        session.exec.return_value.first.return_value = None

        with patch(
            "app.domain.services.weather_service._call_open_meteo",
            new=AsyncMock(return_value=MOCK_OPEN_METEO_RESPONSE),
        ) as mocked_call:
            result = await enrich_all_weather(
                session,
                user_id=user_id,
                max_activities=1,
                concurrency=1,
                include_historical_archive=True,
            )

        assert result["processed"] == 1
        assert mocked_call.await_count == 1
        called_date = mocked_call.await_args.args[2]
        assert called_date == old_activity.start_date

    @pytest.mark.asyncio
    async def test_enrich_recovers_from_concurrent_weather_insert(self):
        """Deux enrichissements simultanes ne doivent pas planter sur l'unicite activity_id."""
        user_id = uuid4()
        activity = _make_activity(
            STREAMS_WITH_GPS,
            start_date=datetime(2025, 6, 15, 9, 30, 0),
            user_id=user_id,
        )
        concurrent_weather = ActivityWeather(activity_id=activity.id, temperature_c=1.0)

        exec_result = MagicMock()
        exec_result.all.return_value = [activity]
        exec_result.first.side_effect = [
            None,                # selection des candidats
            None,                # relecture juste avant insert
            concurrent_weather,  # relecture apres IntegrityError
        ]

        session = MagicMock()
        session.exec.return_value = exec_result
        session.commit.side_effect = [
            IntegrityError("insert", {}, Exception("duplicate")),
            None,
        ]

        with patch(
            "app.domain.services.weather_service._call_open_meteo",
            new=AsyncMock(return_value=MOCK_OPEN_METEO_RESPONSE),
        ):
            result = await enrich_all_weather(
                session,
                user_id=user_id,
                max_activities=1,
                concurrency=1,
                include_historical_archive=True,
            )

        assert result["processed"] == 1
        assert result["errors"] == 0
        assert session.rollback.call_count == 1
        assert session.commit.call_count == 2
        updated_weather = session.add.call_args_list[-1].args[0]
        assert updated_weather is concurrent_weather
        assert updated_weather.temperature_c == 20.1
