"""
Tests pour le calcul Edwards TRIMP.
"""
import pytest
from unittest.mock import MagicMock
import json

from app.domain.services.derived_features_service import (
    compute_edwards_trimp,
    _get_edwards_zone_coeff,
)


def _make_activity(max_hr, streams_data):
    """Cree un mock d'Activity avec max_heartrate et streams_data."""
    act = MagicMock()
    act.max_heartrate = max_hr
    act.streams_data = streams_data
    return act


class TestGetEdwardsZoneCoeff:
    """Tests pour _get_edwards_zone_coeff."""

    def test_below_50_pct(self):
        assert _get_edwards_zone_coeff(0.40) == 0
        assert _get_edwards_zone_coeff(0.49) == 0

    def test_zone_1(self):
        assert _get_edwards_zone_coeff(0.50) == 1
        assert _get_edwards_zone_coeff(0.59) == 1

    def test_zone_2(self):
        assert _get_edwards_zone_coeff(0.60) == 2
        assert _get_edwards_zone_coeff(0.69) == 2

    def test_zone_3(self):
        assert _get_edwards_zone_coeff(0.70) == 3
        assert _get_edwards_zone_coeff(0.79) == 3

    def test_zone_4(self):
        assert _get_edwards_zone_coeff(0.80) == 4
        assert _get_edwards_zone_coeff(0.89) == 4

    def test_zone_5(self):
        assert _get_edwards_zone_coeff(0.90) == 5
        assert _get_edwards_zone_coeff(1.00) == 5


class TestComputeEdwardsTrimp:
    """Tests pour compute_edwards_trimp."""

    def test_no_max_hr_anywhere(self):
        """Retourne None si pas de max_heartrate ni user_max_hr."""
        act = _make_activity(None, json.dumps({
            "heartrate": {"data": [120, 130]},
            "time": {"data": [0, 60]},
        }))
        assert compute_edwards_trimp(act, user_max_hr=None) is None

    def test_no_streams(self):
        """Retourne None si pas de streams_data."""
        act = _make_activity(200, None)
        assert compute_edwards_trimp(act, user_max_hr=200) is None

    def test_null_string_streams(self):
        """Retourne None si streams_data est la string 'null'."""
        act = _make_activity(200, "null")
        assert compute_edwards_trimp(act, user_max_hr=200) is None

    def test_no_hr_data(self):
        """Retourne None si pas de heartrate dans les streams."""
        act = _make_activity(200, json.dumps({
            "time": {"data": [0, 60]},
        }))
        assert compute_edwards_trimp(act, user_max_hr=200) is None

    def test_user_max_hr_takes_priority(self):
        """user_max_hr est utilise a la place de activity.max_heartrate."""
        # activity.max_hr = 150 -> 110 bpm = 73% -> zone 3
        # user_max_hr = 200 -> 110 bpm = 55% -> zone 1
        streams = {
            "heartrate": {"data": [110] * 61},
            "time": {"data": list(range(61))},
        }
        act = _make_activity(150, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=200)
        # Avec user_max_hr=200 : 55% -> zone 1, coeff 1 -> (60/60)*1 = 1.0
        assert result == pytest.approx(1.0, abs=0.01)

    def test_no_user_max_hr_returns_none(self):
        """Sans user_max_hr, retourne None meme si activity a un max_heartrate."""
        streams = {
            "heartrate": {"data": [110] * 61},
            "time": {"data": list(range(61))},
        }
        act = _make_activity(200, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=None)
        assert result is None

    def test_zone_1_only(self):
        """HR constante en zone 1 (55% HRmax) pendant 60 secondes."""
        hr = 110  # 55% de 200 -> zone 1, coeff 1
        streams = {
            "heartrate": {"data": [hr] * 61},
            "time": {"data": list(range(61))},
        }
        act = _make_activity(None, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=200)
        # 60 secondes en zone 1 = (60/60) * 1 = 1.0
        assert result == pytest.approx(1.0, abs=0.01)

    def test_zone_5_only(self):
        """HR constante en zone 5 (95% HRmax) pendant 60 secondes."""
        hr = 190  # 95% de 200 -> zone 5, coeff 5
        streams = {
            "heartrate": {"data": [hr] * 61},
            "time": {"data": list(range(61))},
        }
        act = _make_activity(None, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=200)
        # 60 secondes en zone 5 = (60/60) * 5 = 5.0
        assert result == pytest.approx(5.0, abs=0.01)

    def test_mixed_zones(self):
        """HR qui passe de zone 2 a zone 4."""
        # 30s en zone 2 (130 bpm = 65%) puis 30s en zone 4 (170 bpm = 85%)
        hr_data = [130] * 31 + [170] * 30
        time_data = list(range(61))
        streams = {
            "heartrate": {"data": hr_data},
            "time": {"data": time_data},
        }
        act = _make_activity(None, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=200)
        # 30s zone 2 = (30/60)*2 = 1.0, 30s zone 4 = (30/60)*4 = 2.0 -> total = 3.0
        assert result == pytest.approx(3.0, abs=0.01)

    def test_below_50_pct_not_counted(self):
        """HR en dessous de 50% HRmax ne compte pas."""
        hr = 80  # 40% de 200 -> zone 0, coeff 0
        streams = {
            "heartrate": {"data": [hr] * 61},
            "time": {"data": list(range(61))},
        }
        act = _make_activity(None, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=200)
        assert result is None  # Tout en dessous de 50%, total = 0 -> None

    def test_streams_as_dict_already_parsed(self):
        """streams_data deja sous forme de dict (pas de string JSON)."""
        hr = 150  # 75% -> zone 3, coeff 3
        streams = {
            "heartrate": {"data": [hr] * 61},
            "time": {"data": list(range(61))},
        }
        act = _make_activity(None, streams)
        result = compute_edwards_trimp(act, user_max_hr=200)
        # 60s zone 3 = (60/60)*3 = 3.0
        assert result == pytest.approx(3.0, abs=0.01)

    def test_longer_activity(self):
        """Activite de 10 minutes en zone 3."""
        hr = 150  # 75% -> zone 3, coeff 3
        duration_s = 600
        streams = {
            "heartrate": {"data": [hr] * (duration_s + 1)},
            "time": {"data": list(range(duration_s + 1))},
        }
        act = _make_activity(None, json.dumps(streams))
        result = compute_edwards_trimp(act, user_max_hr=200)
        # 600s zone 3 = (600/60)*3 = 30.0
        assert result == pytest.approx(30.0, abs=0.1)
