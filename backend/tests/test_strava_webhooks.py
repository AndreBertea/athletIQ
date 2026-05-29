"""
Tests pour les webhooks Strava.
Couvre : validation du challenge, validation du payload, dispatch des evenements,
handlers activity.create/update/delete, et endpoints HTTP.
"""
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID
from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel

from app.main import app
from app.core.database import get_session
from app.api.routers._shared import limiter
from app.domain.services.strava_webhook_handler import (
    validate_webhook_challenge,
    validate_and_dispatch_event,
    process_webhook_event,
    handle_activity_create,
    handle_activity_update,
    handle_activity_delete,
    _get_user_id_by_strava_athlete,
    _get_activity_by_strava_id,
)

# Base de test SQLite
SQLMODEL_DATABASE_URL = "sqlite:///./test_strava_webhooks.db"
engine = create_engine(SQLMODEL_DATABASE_URL, connect_args={"check_same_thread": False})


def get_test_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = get_test_session
limiter.enabled = False


@pytest.fixture(scope="function")
def client():
    SQLModel.metadata.create_all(engine)
    yield TestClient(app)
    SQLModel.metadata.drop_all(engine)


def _make_valid_event(**overrides):
    """Helper : cree un payload webhook Strava valide."""
    event = {
        "object_type": "activity",
        "object_id": 12345678901,
        "aspect_type": "create",
        "owner_id": 99887766,
        "subscription_id": 328992,
    }
    event.update(overrides)
    return event


# ============================================================
# Tests unitaires : validate_webhook_challenge
# ============================================================

class TestValidateWebhookChallenge:
    """Tests de validation du challenge webhook Strava."""

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_challenge_valid_token(self, mock_settings):
        """Verify token correct -> retourne le challenge."""
        mock_settings.return_value.STRAVA_WEBHOOK_VERIFY_TOKEN = "my-secret-token"
        result = validate_webhook_challenge("my-secret-token", "challenge_abc123")
        assert result == {"hub.challenge": "challenge_abc123"}

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_challenge_invalid_token(self, mock_settings):
        """Verify token incorrect -> ValueError."""
        mock_settings.return_value.STRAVA_WEBHOOK_VERIFY_TOKEN = "my-secret-token"
        with pytest.raises(ValueError, match="Invalid verify token"):
            validate_webhook_challenge("wrong-token", "challenge_abc123")

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_challenge_empty_token(self, mock_settings):
        """Verify token vide -> ValueError."""
        mock_settings.return_value.STRAVA_WEBHOOK_VERIFY_TOKEN = "my-secret-token"
        with pytest.raises(ValueError):
            validate_webhook_challenge("", "challenge_abc123")


# ============================================================
# Tests unitaires : validate_and_dispatch_event
# ============================================================

class TestValidateAndDispatchEvent:
    """Tests de validation de la structure du payload webhook."""

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_valid_event(self, mock_settings):
        """Payload complet et valide -> retourne {'status': 'ok'}."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        result = validate_and_dispatch_event(_make_valid_event())
        assert result == {"status": "ok"}

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_missing_required_fields(self, mock_settings):
        """Payload avec champs manquants -> ValueError."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        incomplete = {"object_type": "activity", "object_id": 123}
        with pytest.raises(ValueError, match="missing fields"):
            validate_and_dispatch_event(incomplete)

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_empty_payload(self, mock_settings):
        """Payload vide -> ValueError."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        with pytest.raises(ValueError, match="missing fields"):
            validate_and_dispatch_event({})

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_valid_subscription_id(self, mock_settings):
        """Subscription ID valide -> ok."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = "328992"
        result = validate_and_dispatch_event(_make_valid_event(subscription_id=328992))
        assert result == {"status": "ok"}

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_invalid_subscription_id(self, mock_settings):
        """Subscription ID incorrect -> ValueError."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = "328992"
        with pytest.raises(ValueError, match="invalid subscription"):
            validate_and_dispatch_event(_make_valid_event(subscription_id=999999))

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_subscription_id_not_configured(self, mock_settings):
        """Subscription ID non configure -> verification ignoree."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        result = validate_and_dispatch_event(_make_valid_event(subscription_id=999999))
        assert result == {"status": "ok"}


# ============================================================
# Tests unitaires : process_webhook_event (dispatch)
# ============================================================

class TestProcessWebhookEvent:
    """Tests du dispatch des evenements webhook."""

    @patch("app.domain.services.strava_webhook_handler.handle_activity_create")
    def test_dispatch_activity_create(self, mock_create):
        """activity.create -> appelle handle_activity_create."""
        event = _make_valid_event(aspect_type="create")
        process_webhook_event(event)
        mock_create.assert_called_once_with(99887766, 12345678901)

    @patch("app.domain.services.strava_webhook_handler.handle_activity_update")
    def test_dispatch_activity_update(self, mock_update):
        """activity.update -> appelle handle_activity_update."""
        event = _make_valid_event(aspect_type="update")
        process_webhook_event(event)
        mock_update.assert_called_once_with(99887766, 12345678901)

    @patch("app.domain.services.strava_webhook_handler.handle_activity_delete")
    def test_dispatch_activity_delete(self, mock_delete):
        """activity.delete -> appelle handle_activity_delete."""
        event = _make_valid_event(aspect_type="delete")
        process_webhook_event(event)
        mock_delete.assert_called_once_with(99887766, 12345678901)

    @patch("app.domain.services.strava_webhook_handler.handle_activity_create")
    @patch("app.domain.services.strava_webhook_handler.handle_activity_update")
    @patch("app.domain.services.strava_webhook_handler.handle_activity_delete")
    def test_dispatch_non_activity_ignored(self, mock_delete, mock_update, mock_create):
        """object_type != 'activity' -> aucun handler appele."""
        event = _make_valid_event(object_type="athlete")
        process_webhook_event(event)
        mock_create.assert_not_called()
        mock_update.assert_not_called()
        mock_delete.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.handle_activity_create")
    @patch("app.domain.services.strava_webhook_handler.handle_activity_update")
    @patch("app.domain.services.strava_webhook_handler.handle_activity_delete")
    def test_dispatch_unknown_aspect_type(self, mock_delete, mock_update, mock_create):
        """aspect_type inconnu -> aucun handler appele."""
        event = _make_valid_event(aspect_type="unknown")
        process_webhook_event(event)
        mock_create.assert_not_called()
        mock_update.assert_not_called()
        mock_delete.assert_not_called()


# ============================================================
# Tests unitaires : handle_activity_create
# ============================================================

class TestHandleActivityCreate:
    """Tests du handler activity.create."""

    @patch("app.domain.services.strava_webhook_handler.auto_enrichment_service")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_create_owner_not_found(self, mock_engine, mock_sync, mock_enrich):
        """owner_id inconnu en DB -> retour silencieux."""
        mock_session = MagicMock(spec=Session)
        mock_session.exec.return_value.first.return_value = None

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_create(owner_id=999999, strava_activity_id=123)

        mock_sync.fetch_single_activity.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.auto_enrichment_service")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_create_activity_already_exists(self, mock_engine, mock_sync, mock_enrich):
        """Activite deja en DB -> pas de doublon, retour silencieux."""
        mock_session = MagicMock(spec=Session)
        # Simuler : user trouve, activite existe deja
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = uuid4()
        mock_existing_activity = MagicMock()

        # exec().first() retourne d'abord strava_auth, puis l'activite existante
        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, mock_existing_activity]

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_create(owner_id=12345, strava_activity_id=67890)

        mock_sync.fetch_single_activity.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.auto_enrichment_service")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_create_success(self, mock_engine, mock_sync, mock_enrich):
        """Activite creee avec succes : fetch + save + ajout queue."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id

        # exec().first() : strava_auth, puis None (activite n'existe pas)
        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, None]

        mock_sync.get_user_strava_tokens.return_value = ("access_tok", "athlete_id")
        mock_sync.fetch_single_activity.return_value = {"id": 67890, "name": "Morning Run"}

        mock_activity_create = MagicMock()
        mock_activity_create.model_dump.return_value = {
            "name": "Morning Run",
            "activity_type": "Run",
            "start_date": datetime(2025, 1, 1),
            "distance": 10000.0,
            "moving_time": 3600,
            "elapsed_time": 3700,
            "total_elevation_gain": 50.0,
            "strava_id": 67890,
            "average_pace": None,
            "streams_data": None,
            "laps_data": None,
        }
        mock_sync.convert_strava_activity.return_value = mock_activity_create
        activity = MagicMock(id=uuid4(), start_date=datetime(2025, 1, 1))
        mock_sync.save_or_link_activity.return_value = (activity, False)

        mock_enrich.scheduler.add_to_queue.return_value = True

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_create(owner_id=12345, strava_activity_id=67890)

        mock_sync.fetch_single_activity.assert_called_once_with("access_tok", 67890)
        mock_sync.convert_strava_activity.assert_called_once()
        mock_sync.save_or_link_activity.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_enrich.notify_new_items.assert_called_once()

    @patch("app.domain.services.strava_webhook_handler.auto_enrichment_service")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_create_token_error(self, mock_engine, mock_sync, mock_enrich):
        """Erreur lors de la recuperation des tokens -> retour silencieux."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id

        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, None]
        mock_sync.get_user_strava_tokens.side_effect = Exception("Token refresh failed")

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_create(owner_id=12345, strava_activity_id=67890)

        mock_sync.fetch_single_activity.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.auto_enrichment_service")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_create_strava_api_returns_none(self, mock_engine, mock_sync, mock_enrich):
        """fetch_single_activity retourne None -> retour silencieux."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id

        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, None]
        mock_sync.get_user_strava_tokens.return_value = ("access_tok", "athlete_id")
        mock_sync.fetch_single_activity.return_value = None

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_create(owner_id=12345, strava_activity_id=67890)

        mock_session.add.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.auto_enrichment_service")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_create_enrichment_queue_error_does_not_block(self, mock_engine, mock_sync, mock_enrich):
        """Erreur ajout queue d'enrichissement -> l'activite est quand meme sauvegardee."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id

        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, None]
        mock_sync.get_user_strava_tokens.return_value = ("access_tok", "athlete_id")
        mock_sync.fetch_single_activity.return_value = {"id": 67890, "name": "Run"}

        mock_activity_create = MagicMock()
        mock_activity_create.model_dump.return_value = {
            "name": "Run", "activity_type": "Run", "start_date": datetime(2025, 1, 1),
            "distance": 5000.0, "moving_time": 1800, "elapsed_time": 1900,
            "total_elevation_gain": 20.0, "strava_id": 67890,
            "average_pace": None, "streams_data": None, "laps_data": None,
        }
        mock_sync.convert_strava_activity.return_value = mock_activity_create
        activity = MagicMock(id=uuid4(), start_date=datetime(2025, 1, 1))
        mock_sync.save_or_link_activity.return_value = (activity, False)
        mock_enrich.scheduler.add_to_queue.side_effect = Exception("Redis down")

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            # Ne doit pas lever d'exception
            handle_activity_create(owner_id=12345, strava_activity_id=67890)

        # L'activite a quand meme ete sauvegardee
        mock_sync.save_or_link_activity.assert_called_once()
        mock_session.commit.assert_called_once()


# ============================================================
# Tests unitaires : handle_activity_update
# ============================================================

class TestHandleActivityUpdate:
    """Tests du handler activity.update."""

    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_update_owner_not_found(self, mock_engine, mock_sync):
        """owner_id inconnu -> retour silencieux."""
        mock_session = MagicMock(spec=Session)
        mock_session.exec.return_value.first.return_value = None

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_update(owner_id=999999, strava_activity_id=123)

        mock_sync.fetch_single_activity.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.handle_activity_create")
    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_update_activity_not_in_db_falls_back_to_create(self, mock_engine, mock_sync, mock_create):
        """Activite pas en DB -> fallback vers handle_activity_create."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id

        # exec().first() : strava_auth, puis None (activite non trouvee)
        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, None]

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_update(owner_id=12345, strava_activity_id=67890)

        mock_create.assert_called_once_with(12345, 67890)

    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_update_success(self, mock_engine, mock_sync):
        """Mise a jour reussie : re-sync depuis Strava."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id
        mock_activity = MagicMock()
        mock_activity.name = "Old Name"

        # exec().first() : strava_auth, puis activite existante
        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, mock_activity]

        mock_sync.get_user_strava_tokens.return_value = ("access_tok", "athlete_id")
        mock_sync.fetch_single_activity.return_value = {"id": 67890, "name": "Updated Run"}

        mock_updated = MagicMock()
        mock_updated.model_dump.return_value = {"name": "Updated Run", "distance": 12000.0}
        mock_sync.convert_strava_activity.return_value = mock_updated

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_update(owner_id=12345, strava_activity_id=67890)

        mock_sync.fetch_single_activity.assert_called_once_with("access_tok", 67890)
        mock_session.commit.assert_called_once()

    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_update_token_error(self, mock_engine, mock_sync):
        """Erreur tokens lors de l'update -> retour silencieux."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id
        mock_activity = MagicMock()

        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, mock_activity]
        mock_sync.get_user_strava_tokens.side_effect = Exception("Token error")

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_update(owner_id=12345, strava_activity_id=67890)

        mock_sync.fetch_single_activity.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.strava_sync_service")
    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_update_strava_returns_none(self, mock_engine, mock_sync):
        """Strava retourne None lors de l'update -> retour silencieux."""
        user_id = uuid4()
        mock_session = MagicMock(spec=Session)
        mock_strava_auth = MagicMock()
        mock_strava_auth.user_id = user_id
        mock_activity = MagicMock()

        mock_session.exec.return_value.first.side_effect = [mock_strava_auth, mock_activity]
        mock_sync.get_user_strava_tokens.return_value = ("access_tok", "athlete_id")
        mock_sync.fetch_single_activity.return_value = None

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_update(owner_id=12345, strava_activity_id=67890)

        mock_session.commit.assert_not_called()


# ============================================================
# Tests unitaires : handle_activity_delete
# ============================================================

class TestHandleActivityDelete:
    """Tests du handler activity.delete."""

    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_delete_activity_not_found(self, mock_engine):
        """Activite non trouvee en DB -> retour silencieux."""
        mock_session = MagicMock(spec=Session)
        mock_session.exec.return_value.first.return_value = None

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_delete(owner_id=12345, strava_activity_id=67890)

        mock_session.delete.assert_not_called()

    @patch("app.domain.services.strava_webhook_handler.engine")
    def test_delete_success(self, mock_engine):
        """Suppression reussie de l'activite."""
        mock_session = MagicMock(spec=Session)
        mock_activity = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_activity

        with patch("app.domain.services.strava_webhook_handler.Session", return_value=MagicMock(__enter__=MagicMock(return_value=mock_session), __exit__=MagicMock(return_value=False))):
            handle_activity_delete(owner_id=12345, strava_activity_id=67890)

        mock_session.delete.assert_called_once_with(mock_activity)
        mock_session.commit.assert_called_once()


# ============================================================
# Tests d'integration : endpoints HTTP webhook
# ============================================================

class TestWebhookEndpoints:
    """Tests des endpoints HTTP GET/POST /webhooks/strava."""

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_get_webhook_challenge_success(self, mock_settings, client):
        """GET /webhooks/strava avec verify_token valide -> 200 + challenge."""
        mock_settings.return_value.STRAVA_WEBHOOK_VERIFY_TOKEN = "test-verify-token"
        resp = client.get(
            "/api/v1/webhooks/strava",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge_xyz",
                "hub.verify_token": "test-verify-token",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"hub.challenge": "challenge_xyz"}

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_get_webhook_challenge_invalid_token(self, mock_settings, client):
        """GET /webhooks/strava avec verify_token invalide -> 403."""
        mock_settings.return_value.STRAVA_WEBHOOK_VERIFY_TOKEN = "test-verify-token"
        resp = client.get(
            "/api/v1/webhooks/strava",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge_xyz",
                "hub.verify_token": "wrong-token",
            },
        )
        assert resp.status_code == 403

    def test_get_webhook_missing_params(self, client):
        """GET /webhooks/strava sans parametres obligatoires -> 422."""
        resp = client.get("/api/v1/webhooks/strava")
        assert resp.status_code == 422

    @patch("app.domain.services.strava_webhook_handler.process_webhook_event")
    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_post_webhook_valid_event(self, mock_settings, mock_process, client):
        """POST /webhooks/strava avec payload valide -> 200."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        event = _make_valid_event()
        resp = client.post("/api/v1/webhooks/strava", json=event)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_post_webhook_missing_fields(self, mock_settings, client):
        """POST /webhooks/strava avec payload incomplet -> 200 + status error."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        resp = client.post("/api/v1/webhooks/strava", json={"object_type": "activity"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "missing fields" in data["detail"]

    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_post_webhook_invalid_subscription(self, mock_settings, client):
        """POST /webhooks/strava avec subscription_id invalide -> 200 + status error."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = "328992"
        event = _make_valid_event(subscription_id=111111)
        resp = client.post("/api/v1/webhooks/strava", json=event)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "invalid subscription" in data["detail"]

    def test_post_webhook_invalid_json(self, client):
        """POST /webhooks/strava avec body non-JSON -> 200 + error."""
        resp = client.post(
            "/api/v1/webhooks/strava",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    @patch("app.domain.services.strava_webhook_handler.process_webhook_event")
    @patch("app.domain.services.strava_webhook_handler.get_settings")
    def test_post_webhook_always_returns_200(self, mock_settings, mock_process, client):
        """L'endpoint POST retourne toujours 200 (requis par Strava)."""
        mock_settings.return_value.STRAVA_WEBHOOK_SUBSCRIPTION_ID = ""
        # Payload valide
        resp1 = client.post("/api/v1/webhooks/strava", json=_make_valid_event())
        assert resp1.status_code == 200
        # Payload invalide
        resp2 = client.post("/api/v1/webhooks/strava", json={})
        assert resp2.status_code == 200
@pytest.fixture(autouse=True)
def enable_strava_integration(monkeypatch):
    """Les tests historiques couvrent le traitement webhook lorsque Strava est actif."""
    monkeypatch.setenv("STRAVA_INTEGRATION_ENABLED", "true")

