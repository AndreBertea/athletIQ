"""
Tests pour l'authentification JWT et OAuth Strava
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from app.main import app
from app.core.database import get_session
from app.domain.entities.user import User
from app.auth.jwt import password_manager


# Configuration de la base de test
SQLMODEL_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLMODEL_DATABASE_URL, connect_args={"check_same_thread": False})


def get_test_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = get_test_session


@pytest.fixture(scope="function")
def client():
    SQLModel.metadata.create_all(engine)
    yield TestClient(app)
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def test_user_data():
    return {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }


class TestAuth:
    """Tests d'authentification"""
    
    def test_signup_success(self, client, test_user_data):
        """Test inscription réussie"""
        response = client.post("/api/v1/auth/signup", json=test_user_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_signup_duplicate_email(self, client, test_user_data):
        """Test inscription avec email déjà utilisé"""
        # Première inscription
        client.post("/api/v1/auth/signup", json=test_user_data)
        
        # Tentative de doublón
        response = client.post("/api/v1/auth/signup", json=test_user_data)
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]
    
    def test_login_success(self, client, test_user_data):
        """Test connexion réussie"""
        # Inscription d'abord
        client.post("/api/v1/auth/signup", json=test_user_data)
        
        # Connexion
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        }
        response = client.post("/api/v1/auth/login", data=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    def test_login_invalid_credentials(self, client, test_user_data):
        """Test connexion avec mauvais identifiants"""
        login_data = {
            "email": test_user_data["email"],
            "password": "wrongpassword"
        }
        response = client.post("/api/v1/auth/login", data=login_data)
        
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]
    
    def test_get_current_user(self, client, test_user_data):
        """Test récupération utilisateur connecté"""
        # Inscription et récupération du token
        signup_response = client.post("/api/v1/auth/signup", json=test_user_data)
        token = signup_response.json()["access_token"]
        
        # Test endpoint protégé
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/auth/me", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user_data["email"]
        assert data["full_name"] == test_user_data["full_name"]
    
    def test_get_current_user_unauthorized(self, client):
        """Test accès sans token"""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 403  # FastAPI security dependency


class TestStravaOAuth:
    """Tests OAuth Strava"""
    
    def test_strava_login_requires_auth(self, client):
        """Test que l'endpoint Strava nécessite une authentification"""
        response = client.get("/api/v1/auth/strava/login")
        assert response.status_code == 403
    
    def test_strava_login_returns_url(self, client, test_user_data):
        """Test génération URL d'autorisation Strava"""
        # Créer un utilisateur et récupérer le token
        signup_response = client.post("/api/v1/auth/signup", json=test_user_data)
        token = signup_response.json()["access_token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/auth/strava/login", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "strava.com" in data["authorization_url"]
    
    def test_strava_status_not_connected(self, client, test_user_data):
        """Test statut Strava non connecté"""
        signup_response = client.post("/api/v1/auth/signup", json=test_user_data)
        token = signup_response.json()["access_token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/auth/strava/status", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False


class TestPasswordSecurity:
    """Tests sécurité des mots de passe"""
    
    def test_password_hashing(self):
        """Test hashage des mots de passe"""
        password = "testpassword123"
        hashed = password_manager.hash_password(password)
        
        assert hashed != password
        assert password_manager.verify_password(password, hashed)
        assert not password_manager.verify_password("wrongpassword", hashed)
    
    def test_different_hashes_for_same_password(self):
        """Test que le même mot de passe génère des hashes différents (salt)"""
        password = "testpassword123"
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)
        
        assert hash1 != hash2
        assert password_manager.verify_password(password, hash1)
        assert password_manager.verify_password(password, hash2) 