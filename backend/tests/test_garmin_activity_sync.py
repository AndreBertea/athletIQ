"""
Tests pour la sync des activites Garmin → table Activity.
Couvre : _map_garmin_activity, _deduplicate_activity, sync_garmin_activities.
"""
import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, List
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.domain.entities.activity import Activity, ActivityCreate, ActivitySource, ActivityType
from app.domain.entities.activity_weather import ActivityWeather
from app.domain.entities.fit_metrics import FitMetrics
from app.domain.entities.segment import Segment
from app.domain.services.activity_service import ActivityService
from app.domain.services.activity_matching_service import (
    consolidate_strava_duplicate_into_garmin,
    find_unlinked_provider_activity,
)
from app.domain.services.redis_quota_manager import (
    DAILY_KEY,
    PER_15MIN_LIMIT,
    SHORT_KEY,
    RedisQuotaManager,
)
from app.domain.services.garmin_sync_service import (
    _map_garmin_activity,
    _deduplicate_activity,
    sync_garmin_activities,
    GARMIN_TYPE_MAP,
    DEDUP_TIME_TOLERANCE_S,
    DEDUP_DISTANCE_TOLERANCE_M,
)
from app.domain.services.strava_sync_service import StravaSyncService


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
        assert result["start_date_local"] == datetime(2026, 2, 7, 8, 0, 0)
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
                value = next(results_iter)
            except StopIteration:
                value = None
            result.first.return_value = value
            result.all.return_value = [] if value is None else [value]
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

    def test_strava_activity_is_not_reused_in_garmin_only_mode(self):
        """Une activite Strava equivalente ne devient pas une source Garmin."""
        start = datetime(2026, 2, 7, 7, 0, 0)
        strava_activity = Activity(
            id=uuid4(), user_id=USER_ID, name="Strava Run",
            activity_type=ActivityType.RUN, start_date=start,
            distance=10000, moving_time=3000, elapsed_time=3200,
            total_elevation_gain=100, strava_id=987654321,
            source=ActivitySource.STRAVA.value,
        )
        # Seul l'identifiant Garmin exact est consulte dans ce mode.
        session = self._make_session([None, strava_activity])

        result = _deduplicate_activity(
            session, USER_ID, 12345678901,
            start + timedelta(seconds=60),  # 1min d'ecart
            10050,  # 50m d'ecart
        )
        assert result is None

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
            result.all.return_value = []
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
            result.all.return_value = []
            return result

        mock_session.exec = patched_exec

        result = asyncio.get_event_loop().run_until_complete(
            sync_garmin_activities(mock_session, USER_ID, days_back=30)
        )

        assert result["skipped"] == 1
        assert result["created"] == 0

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sync_does_not_link_strava_activity(self, mock_garth, mock_auth, mock_session):
        mock_client = MagicMock()
        mock_auth.get_client.return_value = mock_client

        act1 = MockGarminActivity(
            activity_id=111, start_time_gmt=datetime.utcnow() - timedelta(days=1),
        )
        mock_garth.Activity.list.side_effect = [[act1], []]

        # Une activite Strava potentiellement equivalente existe deja.
        strava_act = MagicMock()
        strava_act.garmin_activity_id = None
        strava_act.source = ActivitySource.STRAVA.value
        strava_act.start_date = act1.start_time_gmt
        strava_act.start_date_local = None
        strava_act.distance = act1.distance

        original_exec = mock_session.exec
        call_count = [0]

        def patched_exec(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_exec(query)
            # Exact Garmin lookup only: the Strava activity is never selected.
            result = MagicMock()
            if call_count[0] == 2:
                result.first.return_value = None
                result.all.return_value = []
            else:
                result.first.return_value = strava_act
                result.all.return_value = [strava_act]
            return result

        mock_session.exec = patched_exec

        result = asyncio.get_event_loop().run_until_complete(
            sync_garmin_activities(mock_session, USER_ID, days_back=30)
        )

        assert result["created"] == 1
        assert result["linked"] == 0
        assert strava_act.garmin_activity_id is None

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


# ============================================================
# Tests du flux d'affichage multi-source
# ============================================================

class TestMultisourceActivityDisplayFeed:
    @pytest.fixture
    def db_session(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    @staticmethod
    def make_activity(user_id, **overrides):
        values = {
            "user_id": user_id,
            "name": "Morning Run",
            "activity_type": ActivityType.RUN,
            "start_date": datetime(2026, 5, 20, 7, 0),
            "distance": 10000.0,
            "moving_time": 3000,
            "elapsed_time": 3100,
            "total_elevation_gain": 80.0,
        }
        values.update(overrides)
        return Activity(**values)

    def test_includes_garmin_activity_before_fit_enrichment(self, db_session):
        user_id = uuid4()
        garmin_activity = self.make_activity(
            user_id,
            source=ActivitySource.GARMIN.value,
            garmin_activity_id=991,
            name="Garmin only",
        )
        strava_activity = self.make_activity(
            user_id,
            source=ActivitySource.STRAVA.value,
            strava_id=441,
            name="Strava run",
            streams_data={"distance": {"data": [0, 10000]}},
        )
        db_session.add(garmin_activity)
        db_session.add(strava_activity)
        db_session.commit()

        result = ActivityService().get_enriched_activities_paginated(
            db_session,
            str(user_id),
            page=1,
            per_page=10,
        )
        items = {item["name"]: item for item in result["items"]}

        assert result["total"] == 1
        assert items["Garmin only"]["activity_id"] == str(garmin_activity.id)
        assert items["Garmin only"]["source"] == "garmin"
        assert items["Garmin only"]["has_garmin"] is True
        assert items["Garmin only"]["has_strava"] is False
        assert items["Garmin only"]["has_fit_metrics"] is False
        assert items["Garmin only"]["has_streams"] is False
        assert "Strava run" not in items

    def test_separates_garmin_source_from_fit_capability(self, db_session):
        user_id = uuid4()
        garmin_activity = self.make_activity(
            user_id,
            source=ActivitySource.GARMIN.value,
            garmin_activity_id=992,
        )
        db_session.add(garmin_activity)
        db_session.commit()
        db_session.add(FitMetrics(activity_id=garmin_activity.id, record_count=10))
        db_session.commit()

        result = ActivityService().get_enriched_activities_paginated(
            db_session,
            str(user_id),
            page=1,
            per_page=10,
        )

        assert result["items"][0]["has_garmin"] is True
        assert result["items"][0]["has_fit_metrics"] is True


class TestCrossProviderActivityMatching:
    @pytest.fixture
    def db_session(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    @staticmethod
    def make_activity(user_id, **overrides):
        values = {
            "user_id": user_id,
            "name": "Training",
            "activity_type": ActivityType.RUN,
            "start_date": datetime(2026, 5, 25, 18, 2, 10),
            "distance": 10522.2,
            "moving_time": 3000,
            "elapsed_time": 3100,
            "total_elevation_gain": 80.0,
        }
        values.update(overrides)
        return Activity(**values)

    def test_matches_legacy_strava_row_using_garmin_local_time(self, db_session):
        user_id = uuid4()
        strava = self.make_activity(
            user_id,
            source=ActivitySource.STRAVA.value,
            strava_id=101,
            start_date=datetime(2026, 5, 25, 20, 2, 10),
        )
        db_session.add(strava)
        db_session.commit()

        result = find_unlinked_provider_activity(
            db_session,
            user_id,
            provider="strava",
            start_date=datetime(2026, 5, 25, 18, 2, 10),
            start_date_local=datetime(2026, 5, 25, 20, 2, 10),
            distance=10522.24,
        )

        assert result.id == strava.id

    def test_strava_import_links_preexisting_garmin_row(self, db_session):
        user_id = uuid4()
        garmin = self.make_activity(
            user_id,
            source=ActivitySource.GARMIN.value,
            garmin_activity_id=202,
            start_date_local=datetime(2026, 5, 25, 20, 2, 10),
        )
        db_session.add(garmin)
        db_session.commit()
        incoming = ActivityCreate(
            name="Evening Run",
            activity_type=ActivityType.RUN,
            start_date=datetime(2026, 5, 25, 18, 2, 10, tzinfo=timezone.utc),
            start_date_local=datetime(2026, 5, 25, 20, 2, 10),
            distance=10522.2,
            moving_time=3000,
            elapsed_time=3100,
            total_elevation_gain=80.0,
            strava_id=303,
            summary_polyline="strava-polyline",
        )

        activity, linked = StravaSyncService().save_or_link_activity(
            db_session, user_id, incoming
        )
        db_session.commit()

        rows = db_session.exec(select(Activity).where(Activity.user_id == user_id)).all()
        assert linked is True
        assert len(rows) == 1
        assert activity.id == garmin.id
        assert activity.garmin_activity_id == 202
        assert activity.strava_id == 303
        assert activity.summary_polyline == "strava-polyline"

    def test_consolidates_existing_duplicate_without_losing_enrichment(self, db_session):
        user_id = uuid4()
        garmin = self.make_activity(
            user_id,
            source=ActivitySource.GARMIN.value,
            garmin_activity_id=404,
            streams_data={
                "time": {"data": [0, 1]},
                "stance_time": {"data": [250, 252]},
            },
        )
        strava = self.make_activity(
            user_id,
            source=ActivitySource.STRAVA.value,
            strava_id=505,
            name="Evening Run",
            start_date=datetime(2026, 5, 25, 20, 2, 10),
            streams_data={
                "time": {"data": [0, 2]},
                "distance": {"data": [0, 10522.2]},
            },
        )
        db_session.add(garmin)
        db_session.add(strava)
        db_session.commit()
        db_session.add(FitMetrics(activity_id=garmin.id, record_count=2))
        db_session.add(ActivityWeather(activity_id=garmin.id, temperature_c=18.0))
        db_session.add(
            Segment(
                activity_id=garmin.id,
                user_id=user_id,
                segment_index=0,
                distance_m=100.0,
                elapsed_time_s=30.0,
            )
        )
        db_session.commit()

        consolidate_strava_duplicate_into_garmin(db_session, garmin, strava)
        db_session.commit()

        rows = db_session.exec(select(Activity).where(Activity.user_id == user_id)).all()
        assert len(rows) == 1
        merged = rows[0]
        assert merged.id == garmin.id
        assert merged.name == "Evening Run"
        assert merged.garmin_activity_id == 404
        assert merged.strava_id == 505
        assert merged.streams_data["time"]["data"] == [0, 2]
        assert merged.streams_data["stance_time"]["data"] == [250, 252]
        assert db_session.exec(
            select(FitMetrics).where(FitMetrics.activity_id == merged.id)
        ).first() is not None
        assert db_session.exec(
            select(ActivityWeather).where(ActivityWeather.activity_id == merged.id)
        ).first() is not None
        assert db_session.exec(
            select(Segment).where(Segment.activity_id == merged.id)
        ).first() is not None


class TestNonBlockingStravaQuota:
    def test_full_short_window_does_not_sleep_in_request_path(self):
        redis_client = MagicMock()
        redis_client.get.side_effect = lambda key: (
            "10" if key == DAILY_KEY else str(PER_15MIN_LIMIT)
        )
        redis_client.ttl.side_effect = lambda key: 120
        manager = RedisQuotaManager(redis_client=redis_client)

        with patch("time.sleep") as sleep:
            result = manager.check_and_wait_if_needed()

        assert result is False
        sleep.assert_not_called()
