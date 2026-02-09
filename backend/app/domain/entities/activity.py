"""
Entité Activity - Domain Layer
Représente une activité sportive réelle (vs WorkoutPlan qui est planifiée)
"""
from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import BigInteger
import sqlalchemy as sa
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum

if TYPE_CHECKING:
    from .user import User
    from .workout_plan import WorkoutPlan


class ActivitySource(str, Enum):
    """Source de l'activité"""
    STRAVA = "strava"
    GARMIN = "garmin"
    MANUAL = "manual"


class ActivityType(str, Enum):
    """Types d'activités supportés"""
    RUN = "Run"
    TRAIL_RUN = "TrailRun"
    RIDE = "Ride"
    SWIM = "Swim"
    WALK = "Walk"


class ActivityBase(SQLModel):
    """Modèle de base pour Activity"""
    name: str
    activity_type: ActivityType
    start_date: datetime
    distance: float  # en mètres
    moving_time: int  # en secondes
    elapsed_time: int  # en secondes
    total_elevation_gain: float  # en mètres
    average_speed: Optional[float] = None  # m/s
    max_speed: Optional[float] = None  # m/s
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    average_cadence: Optional[float] = None
    description: Optional[str] = None


class Activity(ActivityBase, table=True):
    """Entité Activity complète pour la base de données"""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    
    # Source de l'activité
    source: str = Field(default=ActivitySource.STRAVA.value, index=True)

    # Identifiants externes
    strava_id: Optional[int] = Field(sa_column=Column(BigInteger, unique=True, index=True))
    garmin_activity_id: Optional[int] = Field(sa_column=Column(BigInteger, unique=True, index=True))
    external_id: Optional[str] = None
    
    # Données techniques détaillées (JSON)
    streams_data: Optional[Dict[str, Any]] = Field(
        sa_column=Column(JSON),
        description="Données détaillées (temps, lat/lng, altitude, etc.)"
    )
    laps_data: Optional[List[Dict[str, Any]]] = Field(
        sa_column=Column(JSON),
        description="Données des tours/segments"
    )
    
    # Métriques calculées
    average_pace: Optional[float] = None  # min/km
    normalized_power: Optional[float] = None
    training_stress_score: Optional[float] = None
    
    # Métriques supplémentaires
    calories: Optional[float] = None
    start_date_local: Optional[datetime] = None
    workout_type: Optional[int] = None
    trainer: Optional[bool] = None
    commute: Optional[bool] = None
    manual: Optional[bool] = None
    suffer_score: Optional[int] = None

    # Puissance
    average_watts: Optional[float] = None
    max_watts: Optional[float] = None
    weighted_average_watts: Optional[float] = None
    kilojoules: Optional[float] = None

    # Données GPS
    start_latlng: Optional[List] = Field(sa_column=Column(JSON), default=None)
    end_latlng: Optional[List] = Field(sa_column=Column(JSON), default=None)
    summary_polyline: Optional[str] = Field(sa_column=Column(sa.Text), default=None)
    polyline: Optional[str] = Field(sa_column=Column(sa.Text), default=None)

    # Métadonnées
    gear_id: Optional[str] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    timezone: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relations
    user: "User" = Relationship(back_populates="activities")
    planned_workout: Optional["WorkoutPlan"] = Relationship(back_populates="actual_activity")


class ActivityCreate(ActivityBase):
    """Schéma pour créer une activité"""
    source: str = ActivitySource.STRAVA.value
    strava_id: Optional[int] = None
    garmin_activity_id: Optional[int] = None
    average_pace: Optional[float] = None
    streams_data: Optional[Dict[str, Any]] = None
    laps_data: Optional[List[Dict[str, Any]]] = None
    # Métriques supplémentaires
    calories: Optional[float] = None
    start_date_local: Optional[datetime] = None
    workout_type: Optional[int] = None
    trainer: Optional[bool] = None
    commute: Optional[bool] = None
    manual: Optional[bool] = None
    suffer_score: Optional[int] = None
    # Puissance
    average_watts: Optional[float] = None
    max_watts: Optional[float] = None
    weighted_average_watts: Optional[float] = None
    kilojoules: Optional[float] = None
    # Données GPS
    start_latlng: Optional[List] = None
    end_latlng: Optional[List] = None
    summary_polyline: Optional[str] = None


class ActivityRead(ActivityBase):
    """Schéma pour lire une activité (réponse API)"""
    id: UUID
    source: str
    strava_id: Optional[int]
    garmin_activity_id: Optional[int]
    average_pace: Optional[float]
    location_city: Optional[str]
    created_at: datetime
    updated_at: datetime


class ActivityUpdate(SQLModel):
    """Schéma pour mettre à jour une activité"""
    name: Optional[str] = None
    description: Optional[str] = None
    activity_type: Optional[ActivityType] = None


class ActivityWithStreams(ActivityRead):
    """Activité avec données détaillées pour la visualisation"""
    streams_data: Optional[Dict[str, Any]]
    laps_data: Optional[List[Dict[str, Any]]]


class ActivityStats(SQLModel):
    """Statistiques d'activité calculées"""
    total_activities: int
    total_distance: float  # km
    total_time: int  # secondes
    average_pace: float  # min/km
    activities_by_type: Dict[str, int]
    distance_by_month: Dict[str, float] 