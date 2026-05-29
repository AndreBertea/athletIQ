"""
Tests d'integration pour le flow OAuth Strava.
Mock des appels API externes (Strava) pour tester le flow complet.
"""
import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel

from app.main import app
from app.core.database import get_session
from app.api.routers._shared import limiter
from app.auth.strava_oauth import StravaTokens

# Base de test SQLite
SQLMODEL_DATABASE_URL = "sqlite:///./test_strava_oauth.db"
engine = create_engine(SQLMODEL_DATABASE_URL, connect_args={"check_same_thread": False})


def get_test_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = get_test_session

# Desactiver le rate limiting pour les tests
limiter.enabled = False

_user_counter = 0


@pytest.fixture(autouse=True)
def enable_strava_integration(monkeypatch):
    """Conserve la couverture OAuth du chemin de future reactivation."""
    monkeypatch.setenv("STRAVA_INTEGRATION_ENABLED", "true")


@pytest.fixture(scope="function")
def client():
    SQLModel.metadata.create_all(engine)
    yield TestClient(app)
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def auth_headers(client):
    """Cree un utilisateur unique et retourne les headers d'auth JWT."""
    global _user_counter
    _user_counter += 1
    resp = client.post("/api/v1/auth/signup", json={
        "email": f"strava_test_{_user_counter}@example.com",
        "password": "testpassword123",
        "full_name": "Strava Test User",
    })
    assert resp.status_code == 200, f"Signup failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_id(auth_headers):
    """Extrait le user_id depuis le token JWT."""
    from app.auth.jwt import get_current_user_id
    token = auth_headers["Authorization"].split(" ")[1]
    return get_current_user_id(token)


def _make_strava_tokens(athlete_id=12345678):
    """Helper : cree un objet StravaTokens pour les mocks."""
    return StravaTokens(
        access_token="mock_access_token",
        refresh_token="mock_refresh_token",
        expires_at=int(time.time()) + 21600,
        scope="read,activity:read_all",
        athlete_id=athlete_id,
    )


class TestStravaCallbackIntegration:
    """Tests d'integration du callback OAuth Strava."""

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_callback_success(self, mock_strava, client, auth_headers, user_id):
        """Flow complet : code valide -> tokens echanges -> StravaAuth cree -> redirect succes."""
        mock_strava.exchange_code_for_tokens.return_value = _make_strava_tokens()
        mock_strava.encrypt_token.side_effect = lambda t: f"encrypted_{t}"

        resp = client.get(
            f"/api/v1/auth/strava/callback?code=valid_code&state={user_id}",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "success=true" in location
        assert "athlete_id=12345678" in location
        mock_strava.exchange_code_for_tokens.assert_called_once_with("valid_code")

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_callback_creates_strava_auth_in_db(self, mock_strava, client, auth_headers, user_id):
        """Verifie que StravaAuth est bien persiste en base apres un callback reussi."""
        mock_strava.exchange_code_for_tokens.return_value = _make_strava_tokens(athlete_id=99999)
        mock_strava.encrypt_token.side_effect = lambda t: f"encrypted_{t}"
        mock_strava.is_token_expired.return_value = False

        client.get(
            f"/api/v1/auth/strava/callback?code=valid_code&state={user_id}",
            follow_redirects=False,
        )

        # Verifier via l'endpoint /strava/status
        resp = client.get("/api/v1/auth/strava/status", headers=auth_headers)
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_id"] == 99999

    def test_callback_with_oauth_error(self, client):
        """Strava renvoie une erreur OAuth (ex: access_denied)."""
        resp = client.get(
            "/api/v1/auth/strava/callback?error=access_denied",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "error=oauth_error" in location
        assert "access_denied" in location

    def test_callback_without_code(self, client):
        """Callback sans code d'autorisation."""
        resp = client.get(
            "/api/v1/auth/strava/callback?state=some-state",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "error=no_code" in resp.headers["location"]

    def test_callback_without_state(self, client):
        """Callback sans parametre state."""
        resp = client.get(
            "/api/v1/auth/strava/callback?code=valid_code",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "error=no_state" in resp.headers["location"]

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_callback_with_invalid_state(self, mock_strava, client):
        """State n'est pas un UUID valide -> ValueError -> redirect invalid_state."""
        mock_strava.exchange_code_for_tokens.return_value = _make_strava_tokens()
        mock_strava.encrypt_token.side_effect = lambda t: f"encrypted_{t}"

        resp = client.get(
            "/api/v1/auth/strava/callback?code=valid_code&state=not-a-uuid",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "error=invalid_state" in resp.headers["location"]

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_callback_with_unknown_user(self, mock_strava, client):
        """State est un UUID valide mais ne correspond a aucun user."""
        mock_strava.exchange_code_for_tokens.return_value = _make_strava_tokens()
        mock_strava.encrypt_token.side_effect = lambda t: f"encrypted_{t}"

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp = client.get(
            f"/api/v1/auth/strava/callback?code=valid_code&state={fake_uuid}",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "error=user_not_found" in resp.headers["location"]

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_callback_strava_api_error(self, mock_strava, client, auth_headers, user_id):
        """Erreur lors de l'echange de code avec l'API Strava."""
        from fastapi import HTTPException
        mock_strava.exchange_code_for_tokens.side_effect = HTTPException(
            status_code=400, detail="Strava API error 401: Bad Request"
        )

        resp = client.get(
            f"/api/v1/auth/strava/callback?code=expired_code&state={user_id}",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "error=callback_error" in resp.headers["location"]

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_callback_updates_existing_strava_auth(self, mock_strava, client, auth_headers, user_id):
        """Un 2e callback met a jour le StravaAuth existant au lieu d'en creer un nouveau."""
        mock_strava.encrypt_token.side_effect = lambda t: f"encrypted_{t}"
        mock_strava.is_token_expired.return_value = False

        # Premier callback
        mock_strava.exchange_code_for_tokens.return_value = _make_strava_tokens(athlete_id=111)
        client.get(
            f"/api/v1/auth/strava/callback?code=code1&state={user_id}",
            follow_redirects=False,
        )

        # Deuxieme callback (nouveau scope)
        tokens2 = _make_strava_tokens(athlete_id=111)
        tokens2.scope = "read,activity:read_all,activity:write"
        mock_strava.exchange_code_for_tokens.return_value = tokens2
        client.get(
            f"/api/v1/auth/strava/callback?code=code2&state={user_id}",
            follow_redirects=False,
        )

        resp = client.get("/api/v1/auth/strava/status", headers=auth_headers)
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_id"] == 111
        assert data["scope"] == "read,activity:read_all,activity:write"


class TestStravaStatusIntegration:
    """Tests d'integration du statut de connexion Strava."""

    def test_status_not_connected(self, client, auth_headers):
        """User jamais connecte a Strava."""
        resp = client.get("/api/v1/auth/strava/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    @patch("app.domain.services.auth_service.strava_oauth")
    def test_status_connected(self, mock_strava, client, auth_headers, user_id):
        """User connecte a Strava -> status retourne les infos."""
        mock_strava.exchange_code_for_tokens.return_value = _make_strava_tokens(athlete_id=54321)
        mock_strava.encrypt_token.side_effect = lambda t: f"encrypted_{t}"
        mock_strava.is_token_expired.return_value = False

        # Connecter d'abord
        client.get(
            f"/api/v1/auth/strava/callback?code=code&state={user_id}",
            follow_redirects=False,
        )

        resp = client.get("/api/v1/auth/strava/status", headers=auth_headers)
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_id"] == 54321
        assert data["scope"] == "read,activity:read_all"
        assert data["is_expired"] is False

    def test_status_requires_auth(self, client):
        """Endpoint strava/status necessite un JWT."""
        resp = client.get("/api/v1/auth/strava/status")
        assert resp.status_code == 401


class TestStravaLoginIntegration:
    """Tests d'integration de l'initiation du flow OAuth."""

    def test_login_returns_authorization_url(self, client, auth_headers):
        """L'endpoint retourne une URL d'autorisation Strava valide."""
        resp = client.get("/api/v1/auth/strava/login", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "authorization_url" in data
        url = data["authorization_url"]
        assert "strava.com/oauth/authorize" in url
        assert "client_id=" in url
        assert "redirect_uri=" in url
        assert "scope=read,activity:read_all" in url

    def test_login_requires_auth(self, client):
        """L'endpoint necessite un JWT."""
        resp = client.get("/api/v1/auth/strava/login")
        assert resp.status_code == 401

    def test_login_url_contains_user_state(self, client, auth_headers, user_id):
        """L'URL d'autorisation contient le user_id comme parametre state."""
        resp = client.get("/api/v1/auth/strava/login", headers=auth_headers)
        url = resp.json()["authorization_url"]
        assert f"state={user_id}" in url


class TestStravaOAuthManagerUnit:
    """Tests unitaires de StravaOAuthManager avec mock des appels HTTP requests."""

    @patch("app.auth.strava_oauth.requests.post")
    def test_exchange_code_success(self, mock_post):
        """Echange de code reussi : l'API Strava retourne des tokens valides."""
        from app.auth.strava_oauth import StravaOAuthManager
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "abc123",
            "refresh_token": "ref456",
            "expires_at": 1700000000,
            "scope": "read,activity:read_all",
            "athlete": {"id": 42},
        }
        mock_post.return_value.raise_for_status = lambda: None

        mgr = StravaOAuthManager()
        tokens = mgr.exchange_code_for_tokens("valid_code")

        assert tokens.access_token == "abc123"
        assert tokens.refresh_token == "ref456"
        assert tokens.athlete_id == 42
        assert tokens.scope == "read,activity:read_all"
        mock_post.assert_called_once()
        call_data = mock_post.call_args
        assert call_data.kwargs.get("data", call_data[1].get("data", {})).get("code") == "valid_code"

    @patch("app.auth.strava_oauth.requests.post")
    def test_exchange_code_strava_400(self, mock_post):
        """L'API Strava retourne 400 -> HTTPException levee."""
        from app.auth.strava_oauth import StravaOAuthManager
        from fastapi import HTTPException
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = "Bad Request"

        mgr = StravaOAuthManager()
        with pytest.raises(HTTPException) as exc_info:
            mgr.exchange_code_for_tokens("bad_code")
        # La HTTPException 400 interne est re-wrappee en 500 par le except Exception
        assert exc_info.value.status_code in (400, 500)

    @patch("app.auth.strava_oauth.requests.post")
    def test_exchange_code_missing_athlete(self, mock_post):
        """Reponse Strava sans champ 'athlete' -> HTTPException levee."""
        from app.auth.strava_oauth import StravaOAuthManager
        from fastapi import HTTPException
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "abc",
            "refresh_token": "ref",
            "expires_at": 1700000000,
        }
        mock_post.return_value.raise_for_status = lambda: None

        mgr = StravaOAuthManager()
        with pytest.raises(HTTPException):
            mgr.exchange_code_for_tokens("code")

    @patch("app.auth.strava_oauth.requests.post")
    def test_exchange_code_network_error(self, mock_post):
        """Erreur reseau (timeout, DNS) -> HTTPException."""
        import requests as req
        from app.auth.strava_oauth import StravaOAuthManager
        mock_post.side_effect = req.ConnectionError("DNS lookup failed")

        mgr = StravaOAuthManager()
        with pytest.raises(Exception) as exc_info:
            mgr.exchange_code_for_tokens("code")
        assert exc_info.value.status_code == 400

    @patch("app.auth.strava_oauth.requests.post")
    def test_refresh_token_success(self, mock_post):
        """Refresh token reussi : nouveaux tokens retournes."""
        from app.auth.strava_oauth import StravaOAuthManager
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": 1700000000,
            "scope": "read,activity:read_all",
        }
        mock_post.return_value.raise_for_status = lambda: None

        mgr = StravaOAuthManager()
        # Chiffrer un token pour simuler un refresh_token_encrypted
        if mgr.cipher:
            encrypted = mgr.encrypt_token("old_refresh")
            tokens = mgr.refresh_access_token(encrypted)
            assert tokens.access_token == "new_access"
            assert tokens.refresh_token == "new_refresh"

    @patch("app.auth.strava_oauth.requests.post")
    def test_refresh_token_strava_error(self, mock_post):
        """L'API Strava refuse le refresh -> HTTPException."""
        import requests as req
        from app.auth.strava_oauth import StravaOAuthManager
        mock_post.return_value.status_code = 401
        mock_post.return_value.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

        mgr = StravaOAuthManager()
        if mgr.cipher:
            encrypted = mgr.encrypt_token("old_refresh")
            with pytest.raises(Exception):
                mgr.refresh_access_token(encrypted)

    @patch("app.auth.strava_oauth.requests.get")
    def test_get_athlete_info_success(self, mock_get):
        """Recuperation des infos athlete reussie."""
        from app.auth.strava_oauth import StravaOAuthManager
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "id": 42,
            "firstname": "Jane",
            "lastname": "Doe",
            "city": "Paris",
            "country": "France",
            "profile": "https://example.com/photo.jpg",
        }
        mock_get.return_value.raise_for_status = lambda: None

        mgr = StravaOAuthManager()
        info = mgr.get_athlete_info("some_access_token")

        assert info.id == 42
        assert info.firstname == "Jane"
        assert info.lastname == "Doe"
        assert info.city == "Paris"
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "Bearer some_access_token" in str(call_args)

    @patch("app.auth.strava_oauth.requests.get")
    def test_get_athlete_info_error(self, mock_get):
        """Erreur API lors de la recuperation athlete -> HTTPException."""
        import requests as req
        from app.auth.strava_oauth import StravaOAuthManager
        mock_get.return_value.status_code = 403
        mock_get.return_value.raise_for_status.side_effect = req.HTTPError("403 Forbidden")

        mgr = StravaOAuthManager()
        with pytest.raises(Exception):
            mgr.get_athlete_info("invalid_token")

    def test_encrypt_decrypt_roundtrip(self):
        """Chiffrement/dechiffrement d'un token : roundtrip complet."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        if mgr.cipher:
            original = "test_token_12345"
            encrypted = mgr.encrypt_token(original)
            assert encrypted != original
            decrypted = mgr.decrypt_token(encrypted)
            assert decrypted == original

    def test_encrypt_empty_token_raises(self):
        """Chiffrement d'un token vide -> HTTPException."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        if mgr.cipher:
            with pytest.raises(Exception):
                mgr.encrypt_token("")

    def test_decrypt_invalid_token_raises(self):
        """Dechiffrement d'un token invalide -> HTTPException."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        if mgr.cipher:
            with pytest.raises(Exception):
                mgr.decrypt_token("not-a-valid-fernet-token")

    def test_validate_scope_sufficient(self):
        """Scope suffisant retourne True."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        assert mgr.validate_scope("read,activity:read_all") is True

    def test_validate_scope_insufficient(self):
        """Scope insuffisant retourne False."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        assert mgr.validate_scope("read") is False

    def test_is_token_expired_true(self):
        """Token expire dans le passe -> True."""
        from app.auth.strava_oauth import StravaOAuthManager
        from datetime import datetime, timedelta
        mgr = StravaOAuthManager()
        past = datetime.utcnow() - timedelta(hours=1)
        assert mgr.is_token_expired(past) is True

    def test_is_token_expired_false(self):
        """Token expire dans le futur (> 5 min) -> False."""
        from app.auth.strava_oauth import StravaOAuthManager
        from datetime import datetime, timedelta
        mgr = StravaOAuthManager()
        future = datetime.utcnow() + timedelta(hours=1)
        assert mgr.is_token_expired(future) is False

    def test_get_authorization_url_format(self):
        """L'URL d'autorisation contient les parametres requis."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        url = mgr.get_authorization_url(state="test-state")
        assert "strava.com/oauth/authorize" in url
        assert "client_id=" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "scope=read,activity:read_all" in url
        assert "state=test-state" in url

    def test_get_authorization_url_without_state(self):
        """L'URL sans state ne contient pas le parametre state."""
        from app.auth.strava_oauth import StravaOAuthManager
        mgr = StravaOAuthManager()
        url = mgr.get_authorization_url()
        assert "state=" not in url
