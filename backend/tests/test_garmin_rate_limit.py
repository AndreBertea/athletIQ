"""
Tests pour le rate limit sur POST /auth/garmin/login — Tache 3.6.4
Verifie que le rate limit 3/hour est bien applique sur l'endpoint login Garmin.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routers._shared import security, limiter
from app.api.routers.garmin_router import router
from app.core.database import get_session


# ============================================================
# Fixtures
# ============================================================

def _mock_security():
    creds = MagicMock()
    creds.credentials = "fake-jwt-token"
    return creds


def _mock_get_session():
    return MagicMock()


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Reset le limiter avant chaque test pour isoler les compteurs."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def rate_limit_client():
    """
    Cree un TestClient avec une mini-app FastAPI qui inclut le garmin_router
    et le limiter global. headers_enabled desactive pour eviter le bug slowapi
    quand les routes retournent des dicts.
    """
    # Desactiver les headers le temps du test (evite le bug _inject_headers sur dict)
    original_headers = limiter._headers_enabled
    limiter._headers_enabled = False

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.dependency_overrides[security] = _mock_security
    app.dependency_overrides[get_session] = _mock_get_session

    app.include_router(router)

    with (
        patch("app.api.routers.garmin_router.get_current_user_id", return_value="user-123"),
        patch("app.api.routers.garmin_router.auth_service") as mock_auth,
    ):
        mock_auth.handle_garmin_login.return_value = {
            "message": "Garmin connecte",
            "display_name": "TestUser",
        }
        mock_auth.get_garmin_status.return_value = {"connected": False}

        client = TestClient(app)
        yield client

    app.dependency_overrides.clear()
    limiter._headers_enabled = original_headers


# ============================================================
# Tests
# ============================================================

class TestGarminLoginRateLimit:
    """Verifie que le rate limit 3/hour est applique sur POST /auth/garmin/login."""

    LOGIN_URL = "/auth/garmin/login"
    VALID_BODY = {"email": "test@example.com", "password": "password123"}

    def test_first_three_requests_succeed(self, rate_limit_client):
        """Les 3 premieres requetes doivent retourner 200."""
        client = rate_limit_client

        for i in range(3):
            resp = client.post(self.LOGIN_URL, json=self.VALID_BODY)
            assert resp.status_code == 200, f"Requete {i+1}/3 aurait du reussir, got {resp.status_code}"

    def test_fourth_request_returns_429(self, rate_limit_client):
        """La 4e requete dans la meme heure doit retourner 429."""
        client = rate_limit_client

        for _ in range(3):
            resp = client.post(self.LOGIN_URL, json=self.VALID_BODY)
            assert resp.status_code == 200

        resp = client.post(self.LOGIN_URL, json=self.VALID_BODY)
        assert resp.status_code == 429

    def test_429_response_body(self, rate_limit_client):
        """La reponse 429 doit contenir un message d'erreur."""
        client = rate_limit_client

        for _ in range(3):
            client.post(self.LOGIN_URL, json=self.VALID_BODY)

        resp = client.post(self.LOGIN_URL, json=self.VALID_BODY)
        assert resp.status_code == 429
        body = resp.json()
        assert "error" in body or "detail" in body or "message" in body

    def test_exactly_3_allowed_then_blocked(self, rate_limit_client):
        """Exactement 3 requetes autorisees, les suivantes bloquees."""
        client = rate_limit_client

        results = []
        for _ in range(5):
            resp = client.post(self.LOGIN_URL, json=self.VALID_BODY)
            results.append(resp.status_code)

        assert results[:3] == [200, 200, 200]
        assert all(code == 429 for code in results[3:])

    def test_rate_limit_does_not_affect_other_endpoints(self, rate_limit_client):
        """Le rate limit 3/hour sur login ne doit pas bloquer GET /auth/garmin/status."""
        client = rate_limit_client

        # Epuiser le rate limit du login
        for _ in range(3):
            client.post(self.LOGIN_URL, json=self.VALID_BODY)

        # Verifier que login est bien bloque
        resp = client.post(self.LOGIN_URL, json=self.VALID_BODY)
        assert resp.status_code == 429

        # Le status endpoint ne doit pas etre affecte
        resp = client.get("/auth/garmin/status")
        assert resp.status_code == 200
