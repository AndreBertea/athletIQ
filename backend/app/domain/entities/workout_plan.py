"""
Entité WorkoutPlan - Domain Layer
Représente un entraînement planifié (prévision) à comparer avec l'Activity réelle
"""
from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import Enum as SQLEnum, String
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, date
from uuid import UUID, uuid4
from enum import Enum

if TYPE_CHECKING:
    from .user import User
    from .activity import Activity, ActivityRead


class WorkoutType(str, Enum):
    """Types d'entraînements planifiés"""
    EASY_RUN = "easy_run"
    INTERVAL = "interval"
    TEMPO = "tempo"
    LONG_RUN = "long_run"
    RECOVERY = "recovery"
    FARTLEK = "fartlek"
    HILL_REPEAT = "hill_repeat"
    RACE = "race"


class IntensityZone(str, Enum):
    """Zones d'intensité d'entraînement"""
    ZONE_1 = "zone_1"  # Récupération active
    ZONE_2 = "zone_2"  # Endurance de base
    ZONE_3 = "zone_3"  # Tempo
    ZONE_4 = "zone_4"  # Seuil lactique
    ZONE_5 = "zone_5"  # VO2 Max


class WorkoutPlanBase(SQLModel):
    """Modèle de base pour WorkoutPlan"""
    name: str
    workout_type: WorkoutType
    planned_date: date
    
    # Objectifs planifiés
    planned_distance: float  # km
    planned_duration: Optional[int] = None  # secondes
    planned_pace: Optional[float] = None  # min/km
    planned_elevation_gain: Optional[float] = None  # mètres
    
    # Intensité et structure
    intensity_zone: Optional[IntensityZone] = None
    description: Optional[str] = None
    coach_notes: Optional[str] = None


class WorkoutPlan(WorkoutPlanBase, table=True):
    """Entité WorkoutPlan complète pour la base de données"""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    
    # Utiliser des colonnes TEXT pour éviter les problèmes d'enum SQLAlchemy
    workout_type: WorkoutType = Field(sa_column=Column("workout_type", String))
    intensity_zone: Optional[IntensityZone] = Field(
        default=None, 
        sa_column=Column("intensity_zone", String)
    )
    
    # Détails de structure d'entraînement (pour intervalles, etc.)
    workout_structure: Optional[Dict[str, Any]] = Field(
        sa_column=Column(JSON),
        description="Structure détaillée (intervalles, récupération, etc.)"
    )
    
    # Route planifiée (optionnel)
    planned_route: Optional[List[Dict[str, float]]] = Field(
        sa_column=Column(JSON),
        description="Points GPS du parcours planifié"
    )
    
    # Statut et réalisation
    is_completed: bool = Field(default=False)
    completion_percentage: Optional[float] = None
    actual_activity_id: Optional[UUID] = Field(foreign_key="activity.id")
    
    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Nouveaux champs pour l'import CSV
    phase: Optional[str] = None  # Phase d'entraînement (base 1, base 2, build, peak, affu)
    week: Optional[int] = None  # Numéro de semaine
    rpe: Optional[int] = None  # Rate of Perceived Exertion (1-10)
    
    # Relations
    user: "User" = Relationship(back_populates="workout_plans")
    actual_activity: Optional["Activity"] = Relationship(back_populates="planned_workout")


class WorkoutPlanCreate(WorkoutPlanBase):
    """Schéma pour créer un plan d'entraînement"""
    workout_structure: Optional[Dict[str, Any]] = None
    planned_route: Optional[List[Dict[str, float]]] = None
    phase: Optional[str] = None
    week: Optional[int] = None
    rpe: Optional[int] = None


class WorkoutPlanRead(WorkoutPlanBase):
    """Schéma pour lire un plan d'entraînement (réponse API)"""
    id: UUID
    is_completed: bool
    completion_percentage: Optional[float]
    actual_activity_id: Optional[UUID]
    created_at: datetime
    phase: Optional[str] = None
    week: Optional[int] = None
    rpe: Optional[int] = None


class WorkoutPlanUpdate(SQLModel):
    """Schéma pour mettre à jour un plan d'entraînement"""
    name: Optional[str] = None
    workout_type: Optional[WorkoutType] = None
    planned_date: Optional[date] = None
    planned_distance: Optional[float] = None
    planned_duration: Optional[int] = None
    planned_pace: Optional[float] = None
    planned_elevation_gain: Optional[float] = None
    intensity_zone: Optional[IntensityZone] = None
    description: Optional[str] = None
    coach_notes: Optional[str] = None
    is_completed: Optional[bool] = None
    completion_percentage: Optional[float] = None
    phase: Optional[str] = None
    week: Optional[int] = None
    rpe: Optional[int] = None





 