"""
Tests pour l'API des activités
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from datetime import datetime

from app.main import app
from app.core.database import get_session


# Configuration de la base de test
SQLMODEL_DATABASE_URL = "sqlite:///./test_activities.db"
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
def auth_user(client):
    """Créer un utilisateur et retourner son token"""
    user_data = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }
    response = client.post("/api/v1/auth/signup", json=user_data)
    return response.json()["access_token"]


@pytest.fixture
def activity_data():
    """Données d'activité pour les tests"""
    return {
        "strava_id": 12345,
        "name": "Morning Run",
        "activity_type": "Run",
        "start_date_local": datetime.now().isoformat(),
        "elapsed_time": 3600,
        "distance": 10000.0,
        "average_speed": 2.78,
        "average_heartrate": 150
    }


class TestActivitiesAPI:
    """Tests pour l'API des activités"""
    
    def test_create_activity_success(self, client, auth_user, activity_data):
        """Test création d'activité réussie"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        response = client.post("/api/v1/activities/", json=activity_data, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["strava_id"] == activity_data["strava_id"]
        assert data["name"] == activity_data["name"]
        assert data["activity_type"] == activity_data["activity_type"]
        assert "id" in data
        assert "created_at" in data
    
    def test_create_activity_unauthorized(self, client, activity_data):
        """Test création d'activité sans authentification"""
        response = client.post("/api/v1/activities/", json=activity_data)
        assert response.status_code == 403
    
    def test_get_activities_list(self, client, auth_user, activity_data):
        """Test récupération de la liste des activités"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        
        # Créer une activité d'abord
        client.post("/api/v1/activities/", json=activity_data, headers=headers)
        
        # Récupérer la liste
        response = client.get("/api/v1/activities/", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["strava_id"] == activity_data["strava_id"]
    
    def test_get_activities_list_unauthorized(self, client):
        """Test récupération liste sans authentification"""
        response = client.get("/api/v1/activities/")
        assert response.status_code == 403
    
    def test_get_activity_by_id(self, client, auth_user, activity_data):
        """Test récupération d'activité par ID"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        
        # Créer une activité
        create_response = client.post("/api/v1/activities/", json=activity_data, headers=headers)
        activity_id = create_response.json()["id"]
        
        # Récupérer par ID
        response = client.get(f"/api/v1/activities/{activity_id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == activity_id
        assert data["name"] == activity_data["name"]
    
    def test_get_activity_not_found(self, client, auth_user):
        """Test récupération d'activité inexistante"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        fake_id = "00000000-0000-0000-0000-000000000000"
        
        response = client.get(f"/api/v1/activities/{fake_id}", headers=headers)
        assert response.status_code == 404
    
    def test_create_activity_duplicate_strava_id(self, client, auth_user, activity_data):
        """Test création d'activité avec Strava ID en doublon"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        
        # Créer la première activité
        client.post("/api/v1/activities/", json=activity_data, headers=headers)
        
        # Tentative de créer une activité avec le même strava_id
        response = client.post("/api/v1/activities/", json=activity_data, headers=headers)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]
    
    def test_get_activities_with_filters(self, client, auth_user):
        """Test récupération des activités avec filtres"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        
        # Créer plusieurs activités
        run_data = {
            "strava_id": 12345,
            "name": "Morning Run",
            "activity_type": "Run",
            "start_date_local": datetime.now().isoformat(),
            "elapsed_time": 3600,
            "distance": 10000.0
        }
        
        bike_data = {
            "strava_id": 12346,
            "name": "Evening Bike",
            "activity_type": "Ride",
            "start_date_local": datetime.now().isoformat(),
            "elapsed_time": 7200,
            "distance": 50000.0
        }
        
        client.post("/api/v1/activities/", json=run_data, headers=headers)
        client.post("/api/v1/activities/", json=bike_data, headers=headers)
        
        # Filtrer par type
        response = client.get("/api/v1/activities/?activity_type=Run", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["activity_type"] == "Run"


class TestActivitiesValidation:
    """Tests de validation des données d'activités"""
    
    def test_create_activity_missing_required_fields(self, client, auth_user):
        """Test création d'activité avec champs requis manquants"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        incomplete_data = {
            "name": "Incomplete Activity"
            # Manque strava_id, activity_type, etc.
        }
        
        response = client.post("/api/v1/activities/", json=incomplete_data, headers=headers)
        assert response.status_code == 422  # Validation error
    
    def test_create_activity_invalid_data_types(self, client, auth_user):
        """Test création d'activité avec types de données invalides"""
        headers = {"Authorization": f"Bearer {auth_user}"}
        invalid_data = {
            "strava_id": "not-a-number",  # Devrait être int
            "name": "Test Activity",
            "activity_type": "Run",
            "start_date_local": "not-a-date",  # Devrait être datetime
            "elapsed_time": "not-a-number",  # Devrait être int
            "distance": "not-a-number"  # Devrait être float
        }
        
        response = client.post("/api/v1/activities/", json=invalid_data, headers=headers)
        assert response.status_code == 422  # Validation error 