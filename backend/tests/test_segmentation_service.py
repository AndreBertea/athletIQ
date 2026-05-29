"""
Tests pour segmentation_service — Tache 1.5.1
Mock streams_data avec 5-10 points GPS pour tester le decoupage en segments de ~100m.
"""
import pytest
import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.domain.entities.segment import Segment
from app.domain.entities.segment_features import SegmentFeatures
from app.domain.services.segmentation_service import (
    segment_activity,
    is_activity_segmented,
    _parse_streams,
    _get_data,
    _mean,
    SEGMENT_LENGTH_M,
)


def _make_activity(streams_data, distance=1000.0, user_id=None):
    """Cree un mock Activity avec streams_data."""
    activity = MagicMock()
    activity.id = uuid4()
    activity.user_id = user_id or uuid4()
    activity.streams_data = streams_data
    activity.distance = distance
    return activity


def _make_mock_session():
    """Cree un mock Session SQLModel."""
    session = MagicMock()
    # exec().all() retourne une liste vide (pas d'anciens segments)
    session.exec.return_value.all.return_value = []
    session.exec.return_value.first.return_value = None
    return session


# --- Donnees de test ---
# 10 points GPS simulant un parcours de ~900m (9 segments de ~100m attendus)
MOCK_STREAMS_10_POINTS = {
    "distance": {"data": [0, 100, 200, 300, 400, 500, 600, 700, 800, 900]},
    "time": {"data": [0, 30, 62, 90, 120, 155, 185, 215, 248, 280]},
    "heartrate": {"data": [120, 135, 140, 145, 150, 152, 155, 158, 160, 162]},
    "cadence": {"data": [80, 82, 83, 84, 85, 84, 83, 82, 81, 80]},
    "grade_smooth": {"data": [0.0, 1.0, 2.0, -1.0, 0.5, 3.0, -2.0, 0.0, 1.5, -0.5]},
    "altitude": {"data": [100, 101, 103, 102, 102.5, 105, 103, 103, 104.5, 104]},
    "latlng": {"data": [
        [48.8566, 2.3522],
        [48.8570, 2.3530],
        [48.8575, 2.3538],
        [48.8580, 2.3546],
        [48.8585, 2.3554],
        [48.8590, 2.3562],
        [48.8595, 2.3570],
        [48.8600, 2.3578],
        [48.8605, 2.3586],
        [48.8610, 2.3594],
    ]},
}

# 5 points GPS - parcours minimal ~400m
MOCK_STREAMS_5_POINTS = {
    "distance": {"data": [0, 100, 200, 300, 400]},
    "time": {"data": [0, 30, 60, 92, 125]},
    "heartrate": {"data": [130, 140, 145, 150, 155]},
    "cadence": {"data": [82, 84, 85, 83, 81]},
    "altitude": {"data": [200, 202, 205, 203, 201]},
    "latlng": {"data": [
        [45.0, 3.0],
        [45.001, 3.001],
        [45.002, 3.002],
        [45.003, 3.003],
        [45.004, 3.004],
    ]},
}


class TestParseStreams:
    """Tests pour _parse_streams (gestion du bug 'null' string)."""

    def test_parse_streams_none(self):
        activity = _make_activity(streams_data=None)
        assert _parse_streams(activity) is None

    def test_parse_streams_null_string(self):
        activity = _make_activity(streams_data="null")
        assert _parse_streams(activity) is None

    def test_parse_streams_null_string_uppercase(self):
        activity = _make_activity(streams_data="  NULL  ")
        assert _parse_streams(activity) is None

    def test_parse_streams_valid_dict(self):
        data = {"distance": {"data": [0, 100]}}
        activity = _make_activity(streams_data=data)
        result = _parse_streams(activity)
        assert result == data

    def test_parse_streams_json_string(self):
        data = {"distance": {"data": [0, 100]}}
        activity = _make_activity(streams_data=json.dumps(data))
        result = _parse_streams(activity)
        assert result == data

    def test_parse_streams_invalid_json(self):
        activity = _make_activity(streams_data="not valid json {{{")
        assert _parse_streams(activity) is None

    def test_parse_streams_non_dict(self):
        activity = _make_activity(streams_data=[1, 2, 3])
        assert _parse_streams(activity) is None


class TestGetData:
    """Tests pour _get_data."""

    def test_dict_format(self):
        streams = {"distance": {"data": [0, 100, 200]}}
        assert _get_data(streams, "distance") == [0, 100, 200]

    def test_list_format(self):
        streams = {"distance": [0, 100, 200]}
        assert _get_data(streams, "distance") == [0, 100, 200]

    def test_missing_key(self):
        assert _get_data({}, "distance") is None

    def test_none_value(self):
        streams = {"distance": None}
        assert _get_data(streams, "distance") is None


class TestMean:
    """Tests pour _mean."""

    def test_mean_normal(self):
        assert _mean([10, 20, 30]) == 20.0

    def test_mean_empty(self):
        assert _mean([]) is None

    def test_mean_single(self):
        assert _mean([42.0]) == 42.0


class TestSegmentActivity:
    """Tests pour segment_activity avec mock streams_data."""

    def test_segment_10_points(self):
        """10 points a 100m d'intervalle → 9 segments."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)

        assert count == 9
        segments = [o for o in added_objects if isinstance(o, Segment)]
        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        assert len(segments) == 9
        assert len(features) == 9

    def test_segment_5_points(self):
        """5 points a 100m → 4 segments."""
        activity = _make_activity(MOCK_STREAMS_5_POINTS, distance=400.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)

        assert count == 4
        segments = [o for o in added_objects if isinstance(o, Segment)]
        assert len(segments) == 4

    def test_segment_distances(self):
        """Chaque segment doit avoir ~100m de distance."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        segments = [o for o in added_objects if isinstance(o, Segment)]
        for seg in segments:
            assert seg.distance_m == pytest.approx(100.0, abs=1.0)

    def test_segment_indices_sequential(self):
        """Les segment_index doivent etre sequentiels (0, 1, 2, ...)."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        segments = [o for o in added_objects if isinstance(o, Segment)]
        indices = [s.segment_index for s in segments]
        assert indices == list(range(9))

    def test_pace_calculated(self):
        """pace_min_per_km doit etre calcule pour chaque segment."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        segments = [o for o in added_objects if isinstance(o, Segment)]
        for seg in segments:
            assert seg.pace_min_per_km is not None
            assert seg.pace_min_per_km > 0
            # Pace = (elapsed_s / 60) / (dist_m / 1000)
            # Pour 100m en 30s : (30/60) / (100/1000) = 0.5/0.1 = 5.0 min/km
            assert 3.0 < seg.pace_min_per_km < 10.0

    def test_hr_and_cadence_populated(self):
        """avg_hr et avg_cadence doivent etre remplis quand les streams existent."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        segments = [o for o in added_objects if isinstance(o, Segment)]
        for seg in segments:
            assert seg.avg_hr is not None
            assert 100 < seg.avg_hr < 200
            assert seg.avg_cadence is not None
            assert 70 < seg.avg_cadence < 100

    def test_gps_midpoint_populated(self):
        """lat et lon doivent etre remplis quand latlng est present."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        segments = [o for o in added_objects if isinstance(o, Segment)]
        for seg in segments:
            assert seg.lat is not None
            assert seg.lon is not None
            assert 48.0 < seg.lat < 49.0
            assert 2.0 < seg.lon < 3.0

    def test_elevation_gain_loss(self):
        """elevation_gain_m et elevation_loss_m doivent etre calcules."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        segments = [o for o in added_objects if isinstance(o, Segment)]
        total_gain = sum(s.elevation_gain_m for s in segments)
        total_loss = sum(s.elevation_loss_m for s in segments)
        assert total_gain > 0
        assert total_loss > 0

    def test_segment_features_created(self):
        """Un SegmentFeatures doit etre cree pour chaque Segment."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        assert len(features) == 9
        for feat in features:
            assert feat.cumulative_distance_km is not None
            assert feat.elapsed_time_min is not None

    def test_cumulative_distance_increases(self):
        """cumulative_distance_km doit augmenter a chaque segment."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        dists = [f.cumulative_distance_km for f in features]
        assert dists == sorted(dists)
        assert dists[-1] == pytest.approx(0.9, abs=0.01)

    def test_streams_null_string_returns_zero(self):
        """streams_data = 'null' doit retourner 0 segments."""
        activity = _make_activity(streams_data="null")
        session = _make_mock_session()

        count = segment_activity(session, activity)
        assert count == 0

    def test_streams_none_returns_zero(self):
        """streams_data = None doit retourner 0 segments."""
        activity = _make_activity(streams_data=None)
        session = _make_mock_session()

        count = segment_activity(session, activity)
        assert count == 0

    def test_missing_distance_returns_zero(self):
        """Pas de stream distance → 0 segments."""
        streams = {"time": {"data": [0, 30, 60]}}
        activity = _make_activity(streams_data=streams)
        session = _make_mock_session()

        count = segment_activity(session, activity)
        assert count == 0

    def test_without_optional_streams(self):
        """Segmentation fonctionne sans HR, cadence, grade, altitude, GPS."""
        streams = {
            "distance": {"data": [0, 100, 200, 300]},
            "time": {"data": [0, 30, 60, 90]},
        }
        activity = _make_activity(streams_data=streams, distance=300.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)
        assert count == 3

        segments = [o for o in added_objects if isinstance(o, Segment)]
        for seg in segments:
            assert seg.avg_hr is None
            assert seg.avg_cadence is None
            assert seg.lat is None
            assert seg.lon is None

    def test_intensity_proxy_with_hr(self):
        """intensity_proxy = avg_hr * (dist_m / 1000) quand HR present."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        for feat in features:
            assert feat.intensity_proxy is not None
            assert feat.intensity_proxy > 0

    def test_old_segments_deleted_on_resegmentation(self):
        """Les anciens segments doivent etre supprimes avant re-segmentation."""
        activity = _make_activity(MOCK_STREAMS_5_POINTS, distance=400.0)
        session = _make_mock_session()

        old_seg = MagicMock(spec=Segment)
        old_seg.id = uuid4()
        session.exec.return_value.all.side_effect = [
            [old_seg],  # anciens segments
            [],  # anciennes features
        ]

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        session.delete.assert_any_call(old_seg)


class TestRaceCompletionPct:
    """Tests pour race_completion_pct — Tache 1.5.2.
    Verifie que race_completion_pct va de 0 (premier segment) a ~100 (dernier segment).
    """

    def test_race_completion_pct_range_10_points(self):
        """race_completion_pct doit aller de >0 a 100.0 pour 10 points."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        pcts = [f.race_completion_pct for f in features]

        # Aucune valeur ne doit etre None
        assert all(p is not None for p in pcts)
        # Le premier segment doit etre > 0 (course deja entamee)
        assert pcts[0] > 0
        # Le dernier segment doit etre ~100 (course terminee)
        assert pcts[-1] == pytest.approx(100.0, abs=0.1)
        # Toutes les valeurs entre 0 et 100 inclus
        for p in pcts:
            assert 0 < p <= 100.0

    def test_race_completion_pct_monotonically_increasing(self):
        """race_completion_pct doit etre strictement croissant."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        pcts = [f.race_completion_pct for f in features]

        for i in range(1, len(pcts)):
            assert pcts[i] > pcts[i - 1], f"pct[{i}]={pcts[i]} <= pct[{i-1}]={pcts[i-1]}"

    def test_race_completion_pct_5_points(self):
        """race_completion_pct fonctionne aussi avec 5 points (400m)."""
        activity = _make_activity(MOCK_STREAMS_5_POINTS, distance=400.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        pcts = [f.race_completion_pct for f in features]

        assert all(p is not None for p in pcts)
        assert pcts[0] > 0
        assert pcts[-1] == pytest.approx(100.0, abs=0.1)
        # Strictement croissant
        for i in range(1, len(pcts)):
            assert pcts[i] > pcts[i - 1]

    def test_race_completion_pct_expected_values(self):
        """Verifie les valeurs attendues pour 10 points espaces de 100m (total 900m)."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        segment_activity(session, activity)

        features = [o for o in added_objects if isinstance(o, SegmentFeatures)]
        pcts = [f.race_completion_pct for f in features]

        # 9 segments, chacun a end_distance/900 * 100
        # Segment 0: 100/900*100 ≈ 11.11, Segment 8: 900/900*100 = 100.0
        expected = [(i + 1) * 100 / 900 * 100 for i in range(9)]
        for actual, exp in zip(pcts, expected):
            assert actual == pytest.approx(exp, abs=0.1)


class TestSegmentCountApprox:
    """Tests pour tache 1.5.3 — Verifier que le nombre de segments ≈ distance_totale / 100."""

    def test_segment_count_900m(self):
        """900m → attendu ~9 segments (900/100)."""
        activity = _make_activity(MOCK_STREAMS_10_POINTS, distance=900.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)
        expected = 900.0 / SEGMENT_LENGTH_M
        assert count == pytest.approx(expected, abs=1)

    def test_segment_count_400m(self):
        """400m → attendu ~4 segments (400/100)."""
        activity = _make_activity(MOCK_STREAMS_5_POINTS, distance=400.0)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)
        expected = 400.0 / SEGMENT_LENGTH_M
        assert count == pytest.approx(expected, abs=1)

    def test_segment_count_long_distance(self):
        """2km (20 points a 100m) → attendu ~20 segments."""
        n_points = 21
        streams = {
            "distance": {"data": [i * 100 for i in range(n_points)]},
            "time": {"data": [i * 30 for i in range(n_points)]},
            "heartrate": {"data": [140 + i % 10 for i in range(n_points)]},
            "cadence": {"data": [80 + i % 5 for i in range(n_points)]},
            "altitude": {"data": [100 + i * 0.5 for i in range(n_points)]},
            "latlng": {"data": [[48.85 + i * 0.0005, 2.35 + i * 0.0008] for i in range(n_points)]},
        }
        total_dist = 2000.0
        activity = _make_activity(streams, distance=total_dist)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)
        expected = total_dist / SEGMENT_LENGTH_M
        assert count == pytest.approx(expected, abs=1)

    def test_segment_count_irregular_spacing(self):
        """Points non-reguliers (50m, 150m, 250m, 320m, 480m, 600m) → ~6 segments attendus (600/100)."""
        streams = {
            "distance": {"data": [0, 50, 150, 250, 320, 480, 600]},
            "time": {"data": [0, 15, 45, 75, 100, 150, 185]},
        }
        total_dist = 600.0
        activity = _make_activity(streams, distance=total_dist)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)
        expected = total_dist / SEGMENT_LENGTH_M
        # Avec des points irreguliers, la tolerance est un peu plus grande
        assert count == pytest.approx(expected, abs=2)

    def test_segment_count_short_distance(self):
        """150m → attendu 1-2 segments (150/100 = 1.5)."""
        streams = {
            "distance": {"data": [0, 50, 100, 150]},
            "time": {"data": [0, 15, 30, 45]},
        }
        total_dist = 150.0
        activity = _make_activity(streams, distance=total_dist)
        session = _make_mock_session()

        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        count = segment_activity(session, activity)
        expected = total_dist / SEGMENT_LENGTH_M
        assert count == pytest.approx(expected, abs=1)


class TestIsActivitySegmented:
    """Tests pour is_activity_segmented."""

    def test_not_segmented(self):
        session = _make_mock_session()
        assert is_activity_segmented(session, uuid4()) is False

    def test_segmented(self):
        session = _make_mock_session()
        session.exec.return_value.first.return_value = MagicMock(spec=Segment)
        assert is_activity_segmented(session, uuid4()) is True
