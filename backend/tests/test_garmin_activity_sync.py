"""
Tests pour la sync des activites Garmin → table Activity.
Couvre : _map_garmin_activity, _deduplicate_activity, sync_garmin_activities.
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

from app.domain.entities.activity import Activity, ActivitySource, ActivityType
from app.domain.services.garmin_sync_service import (
    _map_garmin_activity,
    _deduplicate_activity,
    sync_garmin_activities,
    GARMIN_TYPE_MAP,
    DEDUP_TIME_TOLERANCE_S,
    DEDUP_DISTANCE_TOLERANCE_M,
)


# ============================================================
# Mock garth.Activity
# ============================================================

@dataclass
class MockActivityType:
    type_key: str = "running"
    type_id: int = 1
    parent_type_id: Optional[int] = None
    is_hidden: Optional[bool] = None
    restricted: Optional[bool] = None
    trimmable: Optional[bool] = None


@dataclass
class MockGarminActivity:
    activity_id: int = 12345678901
    activity_name: str = "Morning Run"
    activity_type: Optional[MockActivityType] = None
    start_time_local: Optional[datetime] = None
    start_time_gmt: Optional[datetime] = None
    user_profile_id: Optional[int] = None
    is_multi_sport_parent: Optional[bool] = None
    event_type: Optional[str] = None
    summary: Optional[str] = None
    location_name: Optional[str] = None
    distance: Optional[float] = 10000.0  # 10km en metres
    duration: Optional[float] = 3000.0  # 50min
    elapsed_duration: Optional[float] = 3200.0
    moving_duration: Optional[float] = 3000.0
    elevation_gain: Optional[float] = 150.0
    elevation_loss: Optional[float] = 140.0
    average_speed: Optional[float] = 3.33
    max_speed: Optional[float] = 5.0
    calories: Optional[float] = 500.0
    average_hr: Optional[float] = 155.0
    max_hr: Optional[float] = 180.0
    owner_id: Optional[int] = None
    owner_display_name: Optional[str] = None
    owner_full_name: Optional[str] = None
    steps: Optional[int] = None
    average_running_cadence_in_steps_per_minute: Optional[float] = 172.0
    max_running_cadence_in_steps_per_minute: Optional[float] = 185.0

    def __post_init__(self):
        if self.activity_type is None:
            self.activity_type = MockActivityType()
        if self.start_time_gmt is None:
            self.start_time_gmt = datetime(2026, 2, 7, 7, 0, 0)
        if self.start_time_local is None:
            self.start_time_local = datetime(2026, 2, 7, 8, 0, 0)


USER_ID = uuid4()


# ============================================================
# Tests _map_garmin_activity
# ============================================================

class TestMapGarminActivity:
    def test_basic_mapping(self):
        act = MockGarminActivity()
        result = _map_garmin_activity(act, USER_ID)

        assert result["user_id"] == USER_ID
        assert result["source"] == ActivitySource.GARMIN.value
        assert result["garmin_activity_id"] == 12345678901
        assert result["name"] == "Morning Run"
        assert result["activity_type"] == ActivityType.RUN
        assert result["distance"] == 10000.0
        assert result["moving_time"] == 3000
        assert result["elapsed_time"] == 3200
        assert result["total_elevation_gain"] == 150.0
        assert result["average_speed"] == 3.33
        assert result["max_speed"] == 5.0
        assert result["average_heartrate"] == 155.0
        assert result["max_heartrate"] == 180.0
        assert result["average_cadence"] == 172.0

    def test_pace_calculation(self):
        act = MockGarminActivity(distance=10000.0, moving_duration=3000.0)
        result = _map_garmin_activity(act, USER_ID)
        # 3000s / 60 = 50min, 10000m / 1000 = 10km, pace = 50/10 = 5.0 min/km
        assert result["average_pace"] == 5.0

    def test_pace_zero_distance(self):
        act = MockGarminActivity(distance=0.0)
        result = _map_garmin_activity(act, USER_ID)
        assert result["average_pace"] is None

    def test_type_mapping_trail_run(self):
        act = MockGarminActivity(
            activity_type=MockActivityType(type_key="trail_running")
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["activity_type"] == ActivityType.TRAIL_RUN

    def test_type_mapping_cycling(self):
        act = MockGarminActivity(
            activity_type=MockActivityType(type_key="cycling")
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["activity_type"] == ActivityType.RIDE

    def test_type_mapping_swimming(self):
        act = MockGarminActivity(
            activity_type=MockActivityType(type_key="pool_swimming")
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["activity_type"] == ActivityType.SWIM

    def test_type_mapping_walking(self):
        act = MockGarminActivity(
            activity_type=MockActivityType(type_key="hiking")
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["activity_type"] == ActivityType.WALK

    def test_type_mapping_unknown_defaults_to_run(self):
        act = MockGarminActivity(
            activity_type=MockActivityType(type_key="yoga")
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["activity_type"] == ActivityType.RUN

    def test_no_activity_type(self):
        act = MockGarminActivity()
        act.activity_type = None
        result = _map_garmin_activity(act, USER_ID)
        assert result["activity_type"] == ActivityType.RUN

    def test_missing_name_defaults(self):
        act = MockGarminActivity(activity_name=None)
        result = _map_garmin_activity(act, USER_ID)
        assert result["name"] == "Garmin Activity"

    def test_missing_distance_defaults_zero(self):
        act = MockGarminActivity(distance=None)
        result = _map_garmin_activity(act, USER_ID)
        assert result["distance"] == 0.0

    def test_missing_durations_fallback(self):
        act = MockGarminActivity(
            moving_duration=None, elapsed_duration=None, duration=2400.0
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["moving_time"] == 2400
        assert result["elapsed_time"] == 2400

    def test_uses_gmt_time_over_local(self):
        gmt = datetime(2026, 2, 7, 7, 0, 0)
        local = datetime(2026, 2, 7, 8, 0, 0)
        act = MockGarminActivity(start_time_gmt=gmt, start_time_local=local)
        result = _map_garmin_activity(act, USER_ID)
        assert result["start_date"] == gmt

    def test_nullable_fields(self):
        act = MockGarminActivity(
            average_hr=None, max_hr=None, average_speed=None,
            max_speed=None, average_running_cadence_in_steps_per_minute=None,
        )
        result = _map_garmin_activity(act, USER_ID)
        assert result["average_heartrate"] is None
        assert result["max_heartrate"] is None
        assert result["average_speed"] is None
        assert result["max_speed"] is None
        assert result["average_cadence"] is None


# ============================================================
# Tests _deduplicate_activity
# ============================================================

class TestDeduplicateActivity:
    def _make_session(self, activities=None):
        """Cree un mock session qui retourne les activites specifiees."""
        session = MagicMock()
        if activities is None:
            activities = []

        results_iter = iter(activities)

        def fake_exec(query):
            result = MagicMock()
            try:
                result.first.return_value = next(results_iter)
            except StopIteration:
                result.first.return_value = None
            return result

        session.exec = fake_exec
        return session

    def test_exact_match_garmin_id(self):
        existing = Activity(
            id=uuid4(), user_id=USER_ID, name="Run",
            activity_type=ActivityType.RUN, start_date=datetime.utcnow(),
            distance=10000, moving_time=3000, elapsed_time=3200,
            total_elevation_gain=100, garmin_activity_id=12345678901,
            source=ActivitySource.GARMIN.value,
        )
        session = self._make_session([existing])

        result = _deduplicate_activity(
            session, USER_ID, 12345678901,
            datetime.utcnow(), 10000,
        )
        assert result is existing

    def test_no_match(self):
        session = self._make_session([None, None])
        result = _deduplicate_activity(
            session, USER_ID, 99999,
            datetime.utcnow(), 10000,
        )
        assert result is None

    def test_fuzzy_match_strava_activity(self):
        """Une activite Strava avec meme heure/distance est retrouvee."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        strava_activity = Activity(
            id=uuid4(), user_id=USER_ID, name="Strava Run",
            activity_type=ActivityType.RUN, start_date=start,
            distance=10000, moving_time=3000, elapsed_time=3200,
            total_elevation_gain=100, strava_id=987654321,
            source=ActivitySource.STRAVA.value,
        )
        # Premier exec (exact garmin_id) : None, deuxieme (fuzzy) : strava_activity
        session = self._make_session([None, strava_activity])

        result = _deduplicate_activity(
            session, USER_ID, 12345678901,
            start + timedelta(seconds=60),  # 1min d'ecart
            10050,  # 50m d'ecart
        )
        assert result is strava_activity

    def test_fuzzy_no_match_time_too_far(self):
        """Activite avec meme distance mais heure trop differente."""
        session = self._make_session([None, None])
        result = _deduplicate_activity(
            session, USER_ID, 99999,
            datetime(2026, 2, 7, 7, 0, 0),
            10000,
        )
        assert result is None


# ============================================================
# Tests sync_garmin_activities
# ============================================================

class TestSyncGarminActivities:
    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        # GarminAuth lookup
        auth_record = MagicMock()
        auth_record.oauth_token_encrypted = "encrypted_token"
        auth_record.last_sync_at = None

        exec_results = [auth_record]  # Premier exec = GarminAuth
        call_count = [0]

        def fake_exec(query):
            result = MagicMock()
            if call_count[0] < len(exec_results):
                result.first.return_value = exec_results[call_count[0]]
            else:
                result.first.return_value = None
            call_count[0] += 1
            return result

        session.exec = fake_exec
        return session

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sync_creates_new_activities(self, mock_garth, mock_auth, mock_session):
        mock_client = MagicMock()
        mock_auth.get_client.return_value = mock_client

        act1 = MockGarminActivity(
            activity_id=111, start_time_gmt=datetime.utcnow() - timedelta(days=1),
        )
        act2 = MockGarminActivity(
            activity_id=222, start_time_gmt=datetime.utcnow() - timedelta(days=2),
        )

        mock_garth.Activity.list.side_effect = [[act1, act2], []]

        result = asyncio.get_event_loop().run_until_complete(
            sync_garmin_activities(mock_session, USER_ID, days_back=30)
        )

        assert result["created"] == 2
        assert result["errors"] == 0
        assert result["total"] == 2

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sync_no_auth_raises(self, mock_garth, mock_auth):
        session = MagicMock()
        result = MagicMock()
        result.first.return_value = None
        session.exec.return_value = result

        with pytest.raises(ValueError, match="Aucune authentification Garmin"):
            asyncio.get_event_loop().run_until_complete(
                sync_garmin_activities(session, USER_ID, days_back=30)
            )

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sync_skips_already_synced(self, mock_garth, mock_auth, mock_session):
        mock_client = MagicMock()
        mock_auth.get_client.return_value = mock_client

        act1 = MockGarminActivity(
            activity_id=111, start_time_gmt=datetime.utcnow() - timedelta(days=1),
        )
        mock_garth.Activity.list.side_effect = [[act1], []]

        # Simulate that _deduplicate finds existing with same garmin_activity_id
        existing = MagicMock()
        existing.garmin_activity_id = 111
        existing.source = ActivitySource.GARMIN.value

        original_exec = mock_session.exec
        call_count = [0]

        def patched_exec(query):
            call_count[0] += 1
            if call_count[0] == 1:
                # GarminAuth lookup
                return original_exec(query)
            # Dedup queries: first one (exact match) returns existing
            result = MagicMock()
            result.first.return_value = existing
            return result

        mock_session.exec = patched_exec

        result = asyncio.get_event_loop().run_until_complete(
            sync_garmin_activities(mock_session, USER_ID, days_back=30)
        )

        assert result["skipped"] == 1
        assert result["created"] == 0

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sync_links_strava_activity(self, mock_garth, mock_auth, mock_session):
        mock_client = MagicMock()
        mock_auth.get_client.return_value = mock_client

        act1 = MockGarminActivity(
            activity_id=111, start_time_gmt=datetime.utcnow() - timedelta(days=1),
        )
        mock_garth.Activity.list.side_effect = [[act1], []]

        # Dedup returns strava activity (no garmin_activity_id)
        strava_act = MagicMock()
        strava_act.garmin_activity_id = None
        strava_act.source = ActivitySource.STRAVA.value

        original_exec = mock_session.exec
        call_count = [0]

        def patched_exec(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_exec(query)
            # First dedup (exact garmin_id): None, second (fuzzy): strava_act
            result = MagicMock()
            if call_count[0] == 2:
                result.first.return_value = None
            else:
                result.first.return_value = strava_act
            return result

        mock_session.exec = patched_exec

        result = asyncio.get_event_loop().run_until_complete(
            sync_garmin_activities(mock_session, USER_ID, days_back=30)
        )

        assert result["linked"] == 1
        assert strava_act.garmin_activity_id == 111

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sync_listing_error_returns_gracefully(self, mock_garth, mock_auth, mock_session):
        mock_client = MagicMock()
        mock_auth.get_client.return_value = mock_client
        mock_garth.Activity.list.side_effect = Exception("API Error")

        result = asyncio.get_event_loop().run_until_complete(
            sync_garmin_activities(mock_session, USER_ID, days_back=30)
        )

        assert result["errors"] == 1
        assert result["total"] == 0


# ============================================================
# Tests GARMIN_TYPE_MAP coverage
# ============================================================

class TestGarminTypeMap:
    def test_all_running_types(self):
        for key in ["running", "treadmill_running"]:
            assert GARMIN_TYPE_MAP[key] == ActivityType.RUN

    def test_trail_running(self):
        assert GARMIN_TYPE_MAP["trail_running"] == ActivityType.TRAIL_RUN

    def test_all_cycling_types(self):
        for key in ["cycling", "indoor_cycling", "mountain_biking", "gravel_cycling"]:
            assert GARMIN_TYPE_MAP[key] == ActivityType.RIDE

    def test_all_swimming_types(self):
        for key in ["swimming", "open_water_swimming", "pool_swimming"]:
            assert GARMIN_TYPE_MAP[key] == ActivityType.SWIM

    def test_walking_types(self):
        for key in ["walking", "hiking"]:
            assert GARMIN_TYPE_MAP[key] == ActivityType.WALK
