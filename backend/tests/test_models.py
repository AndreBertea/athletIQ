"""
Tests pour les modèles de données (entités)
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.domain.entities.user import User, UserCreate, UserUpdate
from app.domain.entities.activity import Activity, ActivityCreate
from app.domain.entities.workout_plan import WorkoutPlan, WorkoutPlanCreate


class TestUserModel:
    """Tests pour l'entité User"""
    
    def test_user_create_valid_email(self):
        """Test création utilisateur avec email valide"""
        user_data = UserCreate(
            email="test@example.com",
            full_name="Test User",
            password="password123"
        )
        assert user_data.email == "test@example.com"
        assert user_data.full_name == "Test User"
        assert user_data.is_active is True
    
    def test_user_create_invalid_email(self):
        """Test création utilisateur avec email invalide"""
        with pytest.raises(ValueError, match="Invalid email format"):
            UserCreate(
                email="invalid-email",
                full_name="Test User", 
                password="password123"
            )
    
    def test_user_email_normalization(self):
        """Test normalisation de l'email (lowercase)"""
        user_data = UserCreate(
            email="TEST@EXAMPLE.COM",
            full_name="Test User",
            password="password123"
        )
        assert user_data.email == "test@example.com"
    
    def test_user_update_partial(self):
        """Test mise à jour partielle d'un utilisateur"""
        update_data = UserUpdate(full_name="Updated Name")
        assert update_data.full_name == "Updated Name"
        assert update_data.email is None
        assert update_data.is_active is None


class TestActivityModel:
    """Tests pour l'entité Activity"""
    
    def test_activity_create_valid(self):
        """Test création activité valide"""
        activity_data = ActivityCreate(
            strava_id=12345,
            name="Morning Run",
            activity_type="Run",
            start_date_local=datetime.now(),
            elapsed_time=3600,
            distance=10000.0
        )
        assert activity_data.strava_id == 12345
        assert activity_data.name == "Morning Run"
        assert activity_data.activity_type == "Run"
        assert activity_data.elapsed_time == 3600
        assert activity_data.distance == 10000.0
    
    def test_activity_with_optional_fields(self):
        """Test création activité avec champs optionnels"""
        activity_data = ActivityCreate(
            strava_id=12345,
            name="Morning Run",
            activity_type="Run",
            start_date_local=datetime.now(),
            elapsed_time=3600,
            distance=10000.0,
            average_speed=2.78,
            average_heartrate=150,
            max_heartrate=180,
            elevation_gain=500.0
        )
        assert activity_data.average_speed == 2.78
        assert activity_data.average_heartrate == 150
        assert activity_data.max_heartrate == 180
        assert activity_data.elevation_gain == 500.0


class TestWorkoutPlanModel:
    """Tests pour l'entité WorkoutPlan"""
    
    def test_workout_plan_create_valid(self):
        """Test création plan d'entraînement valide"""
        plan_data = WorkoutPlanCreate(
            name="Marathon Training",
            description="12-week marathon training plan",
            target_distance=42195.0,
            target_duration=10800,  # 3 heures
            difficulty_level="intermediate"
        )
        assert plan_data.name == "Marathon Training"
        assert plan_data.target_distance == 42195.0
        assert plan_data.target_duration == 10800
        assert plan_data.difficulty_level == "intermediate"
        assert plan_data.is_active is True
    
    def test_workout_plan_create_minimal(self):
        """Test création plan avec champs minimaux"""
        plan_data = WorkoutPlanCreate(
            name="Simple Plan",
            difficulty_level="beginner"
        )
        assert plan_data.name == "Simple Plan"
        assert plan_data.difficulty_level == "beginner"
        assert plan_data.description is None
        assert plan_data.target_distance is None
        assert plan_data.target_duration is None


class TestModelRelationships:
    """Tests pour les relations entre modèles"""
    
    def test_user_activity_relationship_structure(self):
        """Test structure des relations User-Activity"""
        # Vérifier que les annotations de type sont correctes
        from typing import get_type_hints
        
        user_hints = get_type_hints(User)
        assert 'activities' in user_hints
        assert 'workout_plans' in user_hints
    
    def test_datetime_defaults(self):
        """Test que les dates par défaut sont définies"""
        user_data = UserCreate(
            email="test@example.com",
            full_name="Test User",
            password="password123"
        )
        # created_at devrait être défini automatiquement
        assert hasattr(user_data, 'created_at') 