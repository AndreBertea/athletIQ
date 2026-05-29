"""
Tests pour garmin_sync_service — Tache 3.6.1
Mock Garmin API responses (garminconnect/garth) pour tester le sync quotidien.
"""
import pytest
import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from uuid import uuid4


from app.domain.services.garmin_sync_service import (
    _extract_race_prediction_times,
    _fetch_current_performance,
    _fetch_day,
    _upsert,
    sync_daily_data,
    REQUEST_DELAY_S,
)
from app.domain.entities.garmin_daily import GarminDaily


# ============================================================
# Helpers : mock garth data classes
# ============================================================

def _mock_training_readiness(score=75.0, context="AFTER_WAKEUP_RESET"):
    """Mock garth.TrainingReadinessData.get() response."""
    entry = MagicMock()
    entry.score = score
    entry.input_context = context
    return entry


def _mock_hrv_data(last_night_avg=42.5):
    """Mock garth.HRVData.get() response."""
    hrv = MagicMock()
    hrv.hrv_summary.last_night_avg = last_night_avg
    return hrv


def _mock_sleep_data(sleep_score=82, sleep_seconds=28800, spo2=96.5):
    """Mock garth.SleepData.get() response — 8h de sommeil."""
    sleep = MagicMock()
    dto = MagicMock()
    score_obj = MagicMock()
    score_obj.value = sleep_score
    dto.sleep_scores.overall = score_obj
    dto.sleep_time_seconds = sleep_seconds
    dto.average_sp_o2_value = spo2
    sleep.daily_sleep_dto = dto
    return sleep


def _mock_daily_heart_rate(rhr=52):
    """Mock garth.DailyHeartRate.get() response."""
    hr = MagicMock()
    hr.resting_heart_rate = rhr
    return hr


def _mock_daily_summary(
    stress=35,
    bb_max=95,
    bb_min=22,
    spo2=None,
    steps=None,
    total_kcal=None,
    active_kcal=None,
):
    """Mock garth.DailySummary.get() response."""
    s = MagicMock()
    s.average_stress_level = stress
    s.body_battery_highest_value = bb_max
    s.body_battery_lowest_value = bb_min
    s.average_spo_2 = spo2
    s.total_steps = steps
    s.total_kilocalories = total_kcal
    s.active_kilocalories = active_kcal
    return s


def _mock_weight_data(weight_grams=72500):
    """Mock garth.WeightData.get() response."""
    w = MagicMock()
    w.weight = weight_grams
    return w


def _mock_garmin_scores(vo2max=51.3):
    """Mock garth.GarminScoresData.get() response."""
    s = MagicMock()
    s.vo_2_max_precise_value = vo2max
    return s


def _mock_training_status(phrase="PRODUCTIVE"):
    """Mock garth.stats.DailyTrainingStatus.list() response."""
    ts = MagicMock()
    ts.training_status_feedback_phrase = phrase
    return ts


def _make_garth_client():
    """Cree un mock garth.Client."""
    return MagicMock()


def _make_garmin_auth_record(user_id=None):
    """Cree un mock GarminAuth DB record."""
    record = MagicMock()
    record.user_id = user_id or uuid4()
    record.oauth_token_encrypted = "encrypted_token_data"
    record.last_sync_at = None
    return record


# ============================================================
# Tests : _fetch_day (parsing des mock responses garth)
# ============================================================

class TestFetchDay:
    """Teste le parsing des reponses mockees de l'API Garmin via garth."""

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_fetch_all_data_present(self, mock_garth):
        """Toutes les API Garmin retournent des donnees valides."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = [_mock_training_readiness(75.0)]
        mock_garth.HRVData.get.return_value = _mock_hrv_data(42.5)
        mock_garth.SleepData.get.return_value = _mock_sleep_data(82, 28800, 96.5)
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(52)
        mock_garth.DailySummary.get.return_value = _mock_daily_summary(
            35, 95, 22, steps=10654, total_kcal=2310, active_kcal=612
        )
        mock_garth.WeightData.get.return_value = _mock_weight_data(72500)
        mock_garth.GarminScoresData.get.return_value = _mock_garmin_scores(51.3)

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = [_mock_training_status("PRODUCTIVE")]
            data = _fetch_day(client, day)

        assert data is not None
        assert data["training_readiness"] == 75.0
        assert data["hrv_rmssd"] == 42.5
        assert data["sleep_score"] == 82
        assert data["sleep_duration_min"] == 480.0  # 28800s / 60
        assert data["spo2"] == 96.5
        assert data["resting_hr"] == 52
        assert data["stress_score"] == 35
        assert data["total_steps"] == 10654
        assert data["total_kilocalories"] == 2310
        assert data["active_kilocalories"] == 612
        assert data["body_battery_max"] == 95
        assert data["body_battery_min"] == 22
        assert data["weight_kg"] == 72.5  # 72500g / 1000
        assert data["vo2max_estimated"] == 51.3
        assert data["training_status"] == "PRODUCTIVE"

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_fetch_no_data_returns_none(self, mock_garth):
        """Quand toutes les APIs retournent None, _fetch_day retourne None."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data is None

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_fetch_partial_data(self, mock_garth):
        """Certaines APIs retournent des donnees, d'autres non (montre pas portee)."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = _mock_hrv_data(38.0)
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(55)
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data is not None
        assert data["hrv_rmssd"] == 38.0
        assert data["resting_hr"] == 55
        assert "training_readiness" not in data
        assert "sleep_score" not in data

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_training_readiness_prefers_morning(self, mock_garth):
        """Si plusieurs entrees TR, on prefere AFTER_WAKEUP_RESET."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        entry_morning = _mock_training_readiness(80.0, "AFTER_WAKEUP_RESET")
        entry_other = _mock_training_readiness(60.0, "OTHER")
        mock_garth.TrainingReadinessData.get.return_value = [entry_other, entry_morning]
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["training_readiness"] == 80.0

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_training_readiness_single_entry(self, mock_garth):
        """Un seul objet TR (pas une liste) fonctionne aussi."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        single = _mock_training_readiness(70.0, "UNKNOWN")
        mock_garth.TrainingReadinessData.get.return_value = single
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["training_readiness"] == 70.0

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_spo2_fallback_from_summary(self, mock_garth):
        """SpO2 vient du DailySummary si pas dispo dans SleepData."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        # Sleep sans spo2
        sleep = MagicMock()
        sleep.daily_sleep_dto.sleep_scores.overall = None
        sleep.daily_sleep_dto.sleep_time_seconds = None
        sleep.daily_sleep_dto.average_sp_o2_value = None
        mock_garth.SleepData.get.return_value = sleep

        # Summary avec spo2
        mock_garth.DailySummary.get.return_value = _mock_daily_summary(
            stress=30, bb_max=90, bb_min=20, spo2=95.0
        )

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["spo2"] == 95.0

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_spo2_from_sleep_takes_priority(self, mock_garth):
        """SpO2 du SleepData a priorite sur DailySummary."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.SleepData.get.return_value = _mock_sleep_data(80, 25200, 97.0)
        mock_garth.DailySummary.get.return_value = _mock_daily_summary(
            stress=30, bb_max=90, bb_min=20, spo2=93.0
        )

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["spo2"] == 97.0  # Vient de Sleep, pas de Summary

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_weight_conversion_grams_to_kg(self, mock_garth):
        """Le poids est converti de grammes en kg."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = _mock_weight_data(65200)
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["weight_kg"] == pytest.approx(65.2)

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_vo2max_from_maxmet_endpoint(self, mock_garth):
        """La VO2 max est lue depuis maxmet meme si les scores Garmin sont absents."""
        client = _make_garth_client()
        client.connectapi.return_value = [{"generic": {"vo2MaxValue": 47.8}}]
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None

        with patch("garth.stats.DailyTrainingStatus") as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["vo2max_estimated"] == pytest.approx(47.8)
        mock_garth.GarminScoresData.get.assert_not_called()

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sleep_duration_conversion(self, mock_garth):
        """Le sommeil est converti de secondes en minutes."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = _mock_sleep_data(75, 25200, None)
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data["sleep_duration_min"] == 420.0  # 25200s / 60

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_api_exception_graceful_handling(self, mock_garth):
        """Les exceptions API individuelles sont loguees et ignorees."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.side_effect = Exception("API 429")
        mock_garth.HRVData.get.side_effect = Exception("timeout")
        mock_garth.SleepData.get.side_effect = Exception("network error")
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(60)
        mock_garth.DailySummary.get.side_effect = Exception("500")
        mock_garth.WeightData.get.side_effect = Exception("forbidden")
        mock_garth.GarminScoresData.get.side_effect = Exception("timeout")

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.side_effect = Exception("not found")
            data = _fetch_day(client, day)

        # Seul RHR a marche
        assert data is not None
        assert data["resting_hr"] == 60
        assert len(data) == 1

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_all_api_exceptions_returns_none(self, mock_garth):
        """Si TOUTES les APIs echouent, retourne None."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.side_effect = Exception("error")
        mock_garth.HRVData.get.side_effect = Exception("error")
        mock_garth.SleepData.get.side_effect = Exception("error")
        mock_garth.DailyHeartRate.get.side_effect = Exception("error")
        mock_garth.DailySummary.get.side_effect = Exception("error")
        mock_garth.WeightData.get.side_effect = Exception("error")
        mock_garth.GarminScoresData.get.side_effect = Exception("error")

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.side_effect = Exception("error")
            data = _fetch_day(client, day)

        assert data is None

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_training_status_fallback_to_status_field(self, mock_garth):
        """Si training_status_feedback_phrase est absent, utilise training_status."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        ts = MagicMock()
        ts.training_status_feedback_phrase = None
        ts.training_status = 4  # numeric status

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = [ts]
            data = _fetch_day(client, day)

        assert data["training_status"] == "4"


# ============================================================
# Tests : _upsert (insert et update)
# ============================================================

class TestUpsert:
    """Teste l'insertion et mise a jour des donnees Garmin en DB."""

    def test_insert_new_record(self):
        """Insert quand aucun record existant."""
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        user_id = uuid4()
        day = date(2025, 6, 15)
        data = {"hrv_rmssd": 42.5, "resting_hr": 55}

        _upsert(session, user_id, day, data)

        session.add.assert_called_once()
        session.commit.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, GarminDaily)
        assert added.user_id == user_id
        assert added.date == day
        assert added.hrv_rmssd == 42.5
        assert added.resting_hr == 55

    def test_update_existing_record(self):
        """Update quand un record existe deja pour cette date."""
        existing = MagicMock(spec=GarminDaily)
        existing.hrv_rmssd = 40.0
        existing.resting_hr = 50

        session = MagicMock()
        session.exec.return_value.first.return_value = existing

        user_id = uuid4()
        day = date(2025, 6, 15)
        data = {"hrv_rmssd": 45.0, "resting_hr": 52}

        _upsert(session, user_id, day, data)

        assert existing.hrv_rmssd == 45.0
        assert existing.resting_hr == 52
        session.commit.assert_called_once()


class TestPerformanceMetrics:
    """Teste les donnees courantes exposees par le profil et Race Predictor Garmin."""

    def test_extract_race_predictions_from_flat_payload(self):
        data = _extract_race_prediction_times(
            {
                "racePrediction5KTime": 1519,
                "racePrediction10KTime": 3190,
                "racePredictionHalfTime": 7050,
                "racePredictionMarathonTime": 14820,
            }
        )

        assert data["race_prediction_5k_seconds"] == 1519
        assert data["race_prediction_10k_seconds"] == 3190
        assert data["race_prediction_half_seconds"] == 7050
        assert data["race_prediction_marathon_seconds"] == 14820

    def test_extract_race_predictions_from_entries(self):
        data = _extract_race_prediction_times(
            [
                {"raceDistance": 5000, "racePredictionTime": 1519},
                {"raceDistance": 42195, "racePredictionTime": 14820},
            ]
        )

        assert data["race_prediction_5k_seconds"] == 1519
        assert data["race_prediction_marathon_seconds"] == 14820

    def test_fetch_current_performance(self):
        client = _make_garth_client()
        client.user_profile = {"displayName": "test_runner"}

        def response(path):
            if path == "/userprofile-service/userprofile/user-settings":
                return {
                    "userData": {
                        "vo2MaxRunning": 48.4,
                        "lactateThresholdSpeed": 3.25,
                        "lactateThresholdHeartRate": 178,
                    }
                }
            return {"racePredictionMarathonTime": 14820}

        client.connectapi.side_effect = response

        data = _fetch_current_performance(client)

        assert data["vo2max_estimated"] == pytest.approx(48.4)
        assert data["lactate_threshold_speed_mps"] == pytest.approx(3.25)
        assert data["lactate_threshold_hr"] == 178
        assert data["race_prediction_marathon_seconds"] == 14820


# ============================================================
# Tests : sync_daily_data (orchestration complete)
# ============================================================

class TestSyncDailyData:
    """Teste la boucle de sync complete avec mock garth."""

    @patch("app.domain.services.garmin_sync_service.asyncio.sleep", new=AsyncMock())
    @patch("app.domain.services.garmin_sync_service._upsert")
    @patch("app.domain.services.garmin_sync_service._fetch_day")
    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    def test_sync_success(self, mock_ga, mock_fetch, mock_upsert):
        """Sync reussie pour 3 jours."""
        user_id = uuid4()
        auth_record = _make_garmin_auth_record(user_id)

        session = MagicMock()
        session.exec.return_value.first.return_value = auth_record

        mock_ga.get_client.return_value = _make_garth_client()
        mock_fetch.return_value = {"hrv_rmssd": 42.0}

        result = asyncio.get_event_loop().run_until_complete(
            sync_daily_data(session, user_id, days_back=3)
        )

        assert result["days_synced"] == 3
        assert result["errors"] == 0
        assert result["total_requested"] == 3
        assert mock_fetch.call_count == 3
        assert mock_upsert.call_count == 3

    @patch("app.domain.services.garmin_sync_service.asyncio.sleep", new=AsyncMock())
    @patch("app.domain.services.garmin_sync_service._upsert")
    @patch("app.domain.services.garmin_sync_service._fetch_day")
    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    def test_sync_with_errors(self, mock_ga, mock_fetch, mock_upsert):
        """Sync avec des erreurs sur certains jours."""
        user_id = uuid4()
        auth_record = _make_garmin_auth_record(user_id)

        session = MagicMock()
        session.exec.return_value.first.return_value = auth_record

        mock_ga.get_client.return_value = _make_garth_client()
        mock_fetch.side_effect = [
            {"hrv_rmssd": 42.0},
            Exception("Garmin 429"),
            {"hrv_rmssd": 38.0},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            sync_daily_data(session, user_id, days_back=3)
        )

        assert result["days_synced"] == 2
        assert result["errors"] == 1
        assert result["total_requested"] == 3

    @patch("app.domain.services.garmin_sync_service.asyncio.sleep", new=AsyncMock())
    @patch("app.domain.services.garmin_sync_service._upsert")
    @patch("app.domain.services.garmin_sync_service._fetch_day")
    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    def test_sync_no_data_days(self, mock_ga, mock_fetch, mock_upsert):
        """Les jours sans donnees (None) ne font pas d'upsert."""
        user_id = uuid4()
        auth_record = _make_garmin_auth_record(user_id)

        session = MagicMock()
        session.exec.return_value.first.return_value = auth_record

        mock_ga.get_client.return_value = _make_garth_client()
        mock_fetch.side_effect = [None, {"resting_hr": 52}, None]

        result = asyncio.get_event_loop().run_until_complete(
            sync_daily_data(session, user_id, days_back=3)
        )

        assert result["days_synced"] == 1
        assert result["errors"] == 0
        assert mock_upsert.call_count == 1

    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    def test_sync_no_auth_raises(self, mock_ga):
        """Pas d'auth Garmin en DB → ValueError."""
        user_id = uuid4()
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        with pytest.raises(ValueError, match="Aucune authentification Garmin"):
            asyncio.get_event_loop().run_until_complete(
                sync_daily_data(session, user_id, days_back=3)
            )

    @patch("app.domain.services.garmin_sync_service.asyncio.sleep", new=AsyncMock())
    @patch("app.domain.services.garmin_sync_service._upsert")
    @patch("app.domain.services.garmin_sync_service._fetch_day")
    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    def test_sync_updates_last_sync_at(self, mock_ga, mock_fetch, mock_upsert):
        """Apres sync, last_sync_at est mis a jour."""
        user_id = uuid4()
        auth_record = _make_garmin_auth_record(user_id)
        assert auth_record.last_sync_at is None

        session = MagicMock()
        session.exec.return_value.first.return_value = auth_record

        mock_ga.get_client.return_value = _make_garth_client()
        mock_fetch.return_value = {"resting_hr": 52}

        asyncio.get_event_loop().run_until_complete(
            sync_daily_data(session, user_id, days_back=1)
        )

        assert auth_record.last_sync_at is not None


# ============================================================
# Tests : HRV sans summary (hrv_summary.last_night_avg None)
# ============================================================

class TestHrvEdgeCases:
    """Teste les cas limites HRV."""

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_hrv_no_summary(self, mock_garth):
        """HRVData.hrv_summary est None → pas de hrv_rmssd."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        hrv = MagicMock()
        hrv.hrv_summary = None
        mock_garth.HRVData.get.return_value = hrv

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(55)
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert "hrv_rmssd" not in data
        assert data["resting_hr"] == 55

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_hrv_summary_no_avg(self, mock_garth):
        """HRVData.hrv_summary existe mais last_night_avg est None."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        hrv = MagicMock()
        hrv.hrv_summary.last_night_avg = None
        mock_garth.HRVData.get.return_value = hrv

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(55)
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert "hrv_rmssd" not in data


# ============================================================
# Tests : Sleep edge cases
# ============================================================

class TestSleepEdgeCases:
    """Teste les cas limites SleepData."""

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sleep_no_dto(self, mock_garth):
        """SleepData sans daily_sleep_dto."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        sleep = MagicMock()
        sleep.daily_sleep_dto = None
        mock_garth.SleepData.get.return_value = sleep

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(55)
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert "sleep_score" not in data
        assert "sleep_duration_min" not in data

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_sleep_score_direct_value(self, mock_garth):
        """sleep_scores.overall est directement un nombre, pas un objet .value."""
        client = _make_garth_client()
        day = date(2025, 6, 15)

        sleep = MagicMock()
        dto = MagicMock()
        # overall est un int, pas un objet avec .value
        overall = 85
        dto.sleep_scores.overall = overall
        dto.sleep_time_seconds = 27000
        dto.average_sp_o2_value = None
        sleep.daily_sleep_dto = dto
        mock_garth.SleepData.get.return_value = sleep

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch(
            "garth.stats.DailyTrainingStatus"
        ) as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        # L'int n'a pas de .value, donc le code garde la valeur brute
        assert data["sleep_score"] == 85
        assert data["sleep_duration_min"] == 450.0


# ============================================================
# Tests : Sync avec champs manquants (montre pas portee) — 3.6.3
# ============================================================

class TestSyncMissingFields:
    """
    Teste que quand la montre n'est pas portee un jour (champs manquants),
    les valeurs sont NULL dans GarminDaily apres upsert.
    """

    def test_upsert_partial_data_leaves_nulls(self):
        """Insert avec seulement resting_hr → tous les autres champs restent None."""
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        user_id = uuid4()
        day = date(2025, 6, 15)
        data = {"resting_hr": 55}

        _upsert(session, user_id, day, data)

        added = session.add.call_args[0][0]
        assert isinstance(added, GarminDaily)
        assert added.resting_hr == 55
        # Champs non fournis → None (montre pas portee)
        assert added.training_readiness is None
        assert added.hrv_rmssd is None
        assert added.sleep_score is None
        assert added.sleep_duration_min is None
        assert added.stress_score is None
        assert added.spo2 is None
        assert added.vo2max_estimated is None
        assert added.weight_kg is None
        assert added.body_battery_max is None
        assert added.body_battery_min is None
        assert added.training_status is None

    def test_upsert_only_sleep_data(self):
        """Insert avec uniquement sommeil → HR, HRV, stress etc. sont NULL."""
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        user_id = uuid4()
        day = date(2025, 6, 15)
        data = {"sleep_score": 78.0, "sleep_duration_min": 420.0}

        _upsert(session, user_id, day, data)

        added = session.add.call_args[0][0]
        assert added.sleep_score == 78.0
        assert added.sleep_duration_min == 420.0
        assert added.training_readiness is None
        assert added.hrv_rmssd is None
        assert added.resting_hr is None
        assert added.stress_score is None
        assert added.body_battery_max is None
        assert added.body_battery_min is None

    def test_update_does_not_null_existing_fields(self):
        """Update avec nouveaux champs ne remet pas les anciens a NULL."""
        existing = GarminDaily(
            user_id=uuid4(),
            date=date(2025, 6, 15),
            resting_hr=52,
            hrv_rmssd=40.0,
        )

        session = MagicMock()
        session.exec.return_value.first.return_value = existing

        # On fait un update avec seulement stress_score
        _upsert(session, existing.user_id, existing.date, {"stress_score": 30.0})

        # Les anciens champs sont preserves
        assert existing.resting_hr == 52
        assert existing.hrv_rmssd == 40.0
        # Le nouveau champ est mis a jour
        assert existing.stress_score == 30.0

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_fetch_day_no_watch_worn(self, mock_garth):
        """
        Scenario montre pas portee : toutes les APIs retournent des donnees
        mais sans HR/HRV/sleep (pas de capteur actif). Seuls les champs
        passifs (stress via summary, weight) sont presents.
        """
        client = _make_garth_client()
        day = date(2025, 6, 15)

        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = None
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = None
        mock_garth.DailySummary.get.return_value = _mock_daily_summary(
            stress=28, bb_max=None, bb_min=None, spo2=None
        )
        mock_garth.WeightData.get.return_value = _mock_weight_data(71000)
        mock_garth.GarminScoresData.get.return_value = None

        with patch("garth.stats.DailyTrainingStatus") as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        assert data is not None
        assert data["stress_score"] == 28
        assert data["weight_kg"] == pytest.approx(71.0)
        # Champs capteur absent → pas dans le dict
        assert "training_readiness" not in data
        assert "hrv_rmssd" not in data
        assert "sleep_score" not in data
        assert "sleep_duration_min" not in data
        assert "resting_hr" not in data
        assert "spo2" not in data

    @patch("app.domain.services.garmin_sync_service.garth")
    def test_fetch_then_upsert_missing_fields_are_null(self, mock_garth):
        """
        Bout-en-bout : _fetch_day avec donnees partielles → _upsert →
        les champs absents sont NULL dans GarminDaily.
        """
        client = _make_garth_client()
        day = date(2025, 6, 15)
        user_id = uuid4()

        # Seulement HRV et RHR disponibles
        mock_garth.TrainingReadinessData.get.return_value = None
        mock_garth.HRVData.get.return_value = _mock_hrv_data(35.0)
        mock_garth.SleepData.get.return_value = None
        mock_garth.DailyHeartRate.get.return_value = _mock_daily_heart_rate(58)
        mock_garth.DailySummary.get.return_value = None
        mock_garth.WeightData.get.return_value = None
        mock_garth.GarminScoresData.get.return_value = None

        with patch("garth.stats.DailyTrainingStatus") as mock_dts:
            mock_dts.list.return_value = []
            data = _fetch_day(client, day)

        # Upsert dans un mock session
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        _upsert(session, user_id, day, data)

        record = session.add.call_args[0][0]
        assert isinstance(record, GarminDaily)
        # Champs presents
        assert record.hrv_rmssd == 35.0
        assert record.resting_hr == 58
        # Champs manquants → NULL
        assert record.training_readiness is None
        assert record.sleep_score is None
        assert record.sleep_duration_min is None
        assert record.stress_score is None
        assert record.spo2 is None
        assert record.vo2max_estimated is None
        assert record.weight_kg is None
        assert record.body_battery_max is None
        assert record.body_battery_min is None
        assert record.training_status is None

    @patch("app.domain.services.garmin_sync_service.asyncio.sleep", new=AsyncMock())
    @patch("app.domain.services.garmin_sync_service.garmin_auth")
    @patch("app.domain.services.garmin_sync_service.garth")
    def test_full_sync_mixed_days_partial_and_empty(self, mock_garth, mock_ga):
        """
        Sync 3 jours : jour 1 complet, jour 2 partiel (montre pas portee),
        jour 3 aucune donnee. Verifie days_synced et que l'upsert est appele
        uniquement pour les jours avec donnees.
        """
        user_id = uuid4()
        auth_record = _make_garmin_auth_record(user_id)

        session = MagicMock()
        session.exec.return_value.first.return_value = auth_record
        mock_ga.get_client.return_value = _make_garth_client()

        call_count = [0]
        today = date.today()

        def fake_fetch_day(client, day):
            call_count[0] += 1
            idx = (today - day).days
            if idx == 0:
                # Jour 1 : toutes donnees
                return {
                    "training_readiness": 80.0,
                    "hrv_rmssd": 45.0,
                    "sleep_score": 90.0,
                    "resting_hr": 50,
                }
            elif idx == 1:
                # Jour 2 : montre pas portee, seulement stress via summary
                return {"stress_score": 32.0}
            else:
                # Jour 3 : rien du tout
                return None

        with patch(
            "app.domain.services.garmin_sync_service._fetch_day",
            side_effect=fake_fetch_day,
        ), patch(
            "app.domain.services.garmin_sync_service._upsert"
        ) as mock_upsert:
            result = asyncio.get_event_loop().run_until_complete(
                sync_daily_data(session, user_id, days_back=3)
            )

        assert result["days_synced"] == 2  # jours 1 et 2
        assert result["errors"] == 0
        assert mock_upsert.call_count == 2

        # Jour 2 (partiel) : verifie que seul stress_score est passe a upsert
        day2_call = mock_upsert.call_args_list[1]
        day2_data = day2_call[0][3]  # 4eme arg positional = data dict
        assert day2_data == {"stress_score": 32.0}
