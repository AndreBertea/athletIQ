"""
Tests pour parse_fit_file_streams : conversion FIT records → streams_data.
Couvre : conversion semicircles→degrees, format compatible segmentation, indoor (pas de GPS).
"""
import sys
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from io import BytesIO

from app.domain.services.garmin_sync_service import (
    parse_fit_file_streams,
    SEMICIRCLE_TO_DEG,
)


# ============================================================
# Mock fitparse
# ============================================================

class MockFitRecord:
    """Simule un record FIT."""
    def __init__(self, values: dict):
        self._values = values

    def get_value(self, key):
        return self._values.get(key)


class MockFitFile:
    """Simule un FitFile avec des records."""
    def __init__(self, records=None, sessions=None):
        self._records = records or []
        self._sessions = sessions or []

    def get_messages(self, msg_type):
        if msg_type == "record":
            return self._records
        if msg_type == "session":
            return self._sessions
        return []


def _make_fitparse_module(fit_file):
    """Cree un mock module fitparse qui retourne le fit_file donne."""
    mock_module = MagicMock()
    mock_module.FitFile.return_value = fit_file
    return mock_module


# ============================================================
# Tests parse_fit_file_streams
# ============================================================

class TestParseFitFileStreams:
    """Tests de base pour la conversion FIT → streams_data."""

    def test_complete_records(self):
        """Records complets avec GPS, HR, cadence, altitude, distance."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        records = [
            MockFitRecord({
                "timestamp": start,
                "distance": 0.0,
                "enhanced_altitude": 100.0,
                "heart_rate": 120,
                "cadence": 85,
                "position_lat": int(48.8566 / SEMICIRCLE_TO_DEG),
                "position_long": int(2.3522 / SEMICIRCLE_TO_DEG),
                "grade": 0.0,
            }),
            MockFitRecord({
                "timestamp": start + timedelta(seconds=5),
                "distance": 25.0,
                "enhanced_altitude": 101.0,
                "heart_rate": 125,
                "cadence": 86,
                "position_lat": int(48.8567 / SEMICIRCLE_TO_DEG),
                "position_long": int(2.3523 / SEMICIRCLE_TO_DEG),
                "grade": 2.0,
            }),
            MockFitRecord({
                "timestamp": start + timedelta(seconds=10),
                "distance": 50.0,
                "enhanced_altitude": 102.0,
                "heart_rate": 130,
                "cadence": 87,
                "position_lat": int(48.8568 / SEMICIRCLE_TO_DEG),
                "position_long": int(2.3524 / SEMICIRCLE_TO_DEG),
                "grade": 1.5,
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake_fit_data")

        assert "time" in streams
        assert "distance" in streams
        assert "altitude" in streams
        assert "heartrate" in streams
        assert "cadence" in streams
        assert "latlng" in streams
        assert "grade_smooth" in streams

        # Verify time is relative
        assert streams["time"]["data"][0] == 0.0
        assert streams["time"]["data"][1] == 5.0
        assert streams["time"]["data"][2] == 10.0

        # Verify distance
        assert streams["distance"]["data"] == [0.0, 25.0, 50.0]

        # Verify altitude
        assert streams["altitude"]["data"] == [100.0, 101.0, 102.0]

        # Verify HR
        assert streams["heartrate"]["data"] == [120, 125, 130]

        # Verify cadence
        assert streams["cadence"]["data"] == [85, 86, 87]

        # Verify grade
        assert streams["grade_smooth"]["data"] == [0.0, 2.0, 1.5]

    def test_semicircle_conversion(self):
        """Verifie la conversion semicircles → degrees pour GPS."""
        lat_deg = 48.8566
        lng_deg = 2.3522
        lat_semi = int(lat_deg / SEMICIRCLE_TO_DEG)
        lng_semi = int(lng_deg / SEMICIRCLE_TO_DEG)

        records = [
            MockFitRecord({
                "timestamp": datetime(2026, 2, 7, 7, 0, 0),
                "position_lat": lat_semi,
                "position_long": lng_semi,
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        assert "latlng" in streams
        lat_result, lng_result = streams["latlng"]["data"][0]
        # Conversion back should be close to original
        assert abs(lat_result - lat_deg) < 0.001
        assert abs(lng_result - lng_deg) < 0.001

    def test_indoor_no_gps(self):
        """Activite en interieur : pas de GPS, les autres streams sont presents."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        records = [
            MockFitRecord({
                "timestamp": start,
                "distance": 0.0,
                "heart_rate": 130,
                "cadence": 90,
                "position_lat": None,
                "position_long": None,
                "grade": None,
                "enhanced_altitude": None,
            }),
            MockFitRecord({
                "timestamp": start + timedelta(seconds=5),
                "distance": 20.0,
                "heart_rate": 135,
                "cadence": 91,
                "position_lat": None,
                "position_long": None,
                "grade": None,
                "enhanced_altitude": None,
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        assert "time" in streams
        assert "distance" in streams
        assert "heartrate" in streams
        assert "cadence" in streams
        # GPS + altitude + grade absents pour indoor
        assert "latlng" not in streams
        assert "altitude" not in streams
        assert "grade_smooth" not in streams

    def test_empty_records(self):
        """FIT file sans records retourne un dict vide."""
        fit_file = MockFitFile(records=[])

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        assert streams == {}

    def test_mixed_none_values(self):
        """Certains records ont des champs None (intermittent)."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        records = [
            MockFitRecord({
                "timestamp": start,
                "distance": 0.0,
                "heart_rate": 120,
                "cadence": None,
                "position_lat": None,
                "position_long": None,
            }),
            MockFitRecord({
                "timestamp": start + timedelta(seconds=5),
                "distance": 25.0,
                "heart_rate": None,
                "cadence": 85,
                "position_lat": int(48.8 / SEMICIRCLE_TO_DEG),
                "position_long": int(2.3 / SEMICIRCLE_TO_DEG),
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        # time et distance toujours presents
        assert "time" in streams
        assert "distance" in streams
        # HR avec un None
        assert streams["heartrate"]["data"] == [120, None]
        # Cadence avec un None
        assert streams["cadence"]["data"] == [None, 85]
        # latlng : premier None, deuxieme avec coords
        assert streams["latlng"]["data"][0] is None
        assert streams["latlng"]["data"][1] is not None

    def test_altitude_fallback(self):
        """Utilise 'altitude' si 'enhanced_altitude' absent."""
        records = [
            MockFitRecord({
                "timestamp": datetime(2026, 2, 7, 7, 0, 0),
                "enhanced_altitude": None,
                "altitude": 250.0,
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        assert streams["altitude"]["data"] == [250.0]


class TestStreamsCompatibleSegmentation:
    """Verifie que le format de sortie est compatible avec le pipeline de segmentation."""

    def test_streams_format_dict_with_data_key(self):
        """Chaque stream est un dict avec une cle 'data'."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        records = [
            MockFitRecord({
                "timestamp": start, "distance": 0.0,
                "heart_rate": 120, "enhanced_altitude": 100.0,
            }),
            MockFitRecord({
                "timestamp": start + timedelta(seconds=5), "distance": 50.0,
                "heart_rate": 125, "enhanced_altitude": 101.0,
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        for key in ["time", "distance", "heartrate", "altitude"]:
            assert key in streams
            assert "data" in streams[key]
            assert isinstance(streams[key]["data"], list)

    def test_distance_data_is_cumulative(self):
        """distance.data doit etre cumulatif (requis par segmentation)."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        records = [
            MockFitRecord({"timestamp": start, "distance": 0.0}),
            MockFitRecord({"timestamp": start + timedelta(seconds=5), "distance": 100.0}),
            MockFitRecord({"timestamp": start + timedelta(seconds=10), "distance": 200.0}),
            MockFitRecord({"timestamp": start + timedelta(seconds=15), "distance": 300.0}),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        dist = streams["distance"]["data"]
        # Verify cumulative
        for i in range(1, len(dist)):
            if dist[i] is not None and dist[i - 1] is not None:
                assert dist[i] >= dist[i - 1]

    def test_latlng_format_list_of_pairs(self):
        """latlng.data doit etre une liste de [lat, lng] pairs."""
        records = [
            MockFitRecord({
                "timestamp": datetime(2026, 2, 7, 7, 0, 0),
                "position_lat": int(48.8 / SEMICIRCLE_TO_DEG),
                "position_long": int(2.3 / SEMICIRCLE_TO_DEG),
            }),
            MockFitRecord({
                "timestamp": datetime(2026, 2, 7, 7, 0, 5),
                "position_lat": int(48.9 / SEMICIRCLE_TO_DEG),
                "position_long": int(2.4 / SEMICIRCLE_TO_DEG),
            }),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        latlng = streams["latlng"]["data"]
        for pair in latlng:
            if pair is not None:
                assert isinstance(pair, list)
                assert len(pair) == 2

    def test_time_starts_at_zero(self):
        """time.data commence toujours a 0."""
        start = datetime(2026, 2, 7, 7, 30, 0)
        records = [
            MockFitRecord({"timestamp": start}),
            MockFitRecord({"timestamp": start + timedelta(seconds=10)}),
        ]
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        assert streams["time"]["data"][0] == 0.0


class TestSemicircleConversion:
    """Tests specifiques pour la conversion semicircles → degrees."""

    def test_known_paris_coords(self):
        lat_deg = 48.8566
        lng_deg = 2.3522
        lat_semi = lat_deg / SEMICIRCLE_TO_DEG
        lng_semi = lng_deg / SEMICIRCLE_TO_DEG

        # Reconversion
        lat_back = lat_semi * SEMICIRCLE_TO_DEG
        lng_back = lng_semi * SEMICIRCLE_TO_DEG

        assert abs(lat_back - lat_deg) < 1e-10
        assert abs(lng_back - lng_deg) < 1e-10

    def test_negative_coords(self):
        """Coordonnees negatives (hemisphere sud, ouest)."""
        lat_deg = -33.8688  # Sydney
        lng_deg = 151.2093

        lat_semi = int(lat_deg / SEMICIRCLE_TO_DEG)
        lng_semi = int(lng_deg / SEMICIRCLE_TO_DEG)

        lat_back = lat_semi * SEMICIRCLE_TO_DEG
        lng_back = lng_semi * SEMICIRCLE_TO_DEG

        assert abs(lat_back - lat_deg) < 0.001
        assert abs(lng_back - lng_deg) < 0.001

    def test_zero_coords(self):
        assert 0 * SEMICIRCLE_TO_DEG == 0.0

    def test_max_semicircle(self):
        """Max semicircle (2^31 - 1) ≈ 180 degrees."""
        max_semi = 2**31 - 1
        deg = max_semi * SEMICIRCLE_TO_DEG
        assert abs(deg - 180.0) < 0.001


class TestFitStreamsManyRecords:
    """Test avec un grand nombre de records (simulation course longue)."""

    def test_long_run_20_records(self):
        start = datetime(2026, 2, 7, 7, 0, 0)
        records = []
        for i in range(20):
            records.append(MockFitRecord({
                "timestamp": start + timedelta(seconds=i * 30),
                "distance": float(i * 150),
                "enhanced_altitude": 100.0 + i * 0.5,
                "heart_rate": 130 + i,
                "cadence": 85 + (i % 5),
                "position_lat": int((48.8566 + i * 0.0001) / SEMICIRCLE_TO_DEG),
                "position_long": int((2.3522 + i * 0.0001) / SEMICIRCLE_TO_DEG),
                "grade": 1.0 + (i % 3),
            }))
        fit_file = MockFitFile(records=records)

        with patch.dict(sys.modules, {"fitparse": _make_fitparse_module(fit_file)}):
            streams = parse_fit_file_streams(b"fake")

        assert len(streams["time"]["data"]) == 20
        assert len(streams["distance"]["data"]) == 20
        assert len(streams["heartrate"]["data"]) == 20
        assert len(streams["latlng"]["data"]) == 20
        assert streams["time"]["data"][-1] == 570.0  # 19 * 30
        assert streams["distance"]["data"][-1] == 2850.0  # 19 * 150
