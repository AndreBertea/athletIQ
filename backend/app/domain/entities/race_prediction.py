"""
Entites Race Predictor - Domain Layer
Predictions GPX sauvegardees et comparaisons avec une activite reelle.
"""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlmodel import Column, Field, JSON, SQLModel


class RacePrediction(SQLModel, table=True):
    """Prediction Race Predictor sauvegardee par utilisateur."""
    __tablename__ = "raceprediction"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    name: str = Field(index=True)
    filename: Optional[str] = None
    engine_version: str = Field(default="v1_random_forest", index=True)
    analysis_mode: str = Field(default="trail", index=True)
    ravito_mode: str = Field(default="auto")
    history_start_date: Optional[datetime] = None

    total_distance_km: Optional[float] = None
    total_elevation_gain_m: Optional[float] = None
    moving_time_min: Optional[float] = None
    total_pause_min: Optional[float] = None
    total_time_min: Optional[float] = None
    avg_pace: Optional[float] = None

    prediction_data: Dict[str, Any] = Field(sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RacePredictionRead(SQLModel):
    """Schema de lecture d'une prediction sauvegardee."""
    id: UUID
    name: str
    filename: Optional[str]
    engine_version: str
    analysis_mode: str
    ravito_mode: str
    history_start_date: Optional[datetime]
    total_distance_km: Optional[float]
    total_elevation_gain_m: Optional[float]
    moving_time_min: Optional[float]
    total_pause_min: Optional[float]
    total_time_min: Optional[float]
    avg_pace: Optional[float]
    prediction_data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RacePredictionComparison(SQLModel, table=True):
    """Comparaison sauvegardee entre une prediction GPX et une activite reelle."""
    __tablename__ = "racepredictioncomparison"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    prediction_id: UUID = Field(foreign_key="raceprediction.id", index=True)
    activity_id: Optional[UUID] = Field(default=None, foreign_key="activity.id", index=True)

    name: str = Field(index=True)
    comparison_data: Dict[str, Any] = Field(sa_column=Column(JSON))

    total_delta_min: Optional[float] = None
    moving_delta_min: Optional[float] = None
    pause_delta_min: Optional[float] = None
    avg_abs_segment_delta_min: Optional[float] = None
    comparable_distance_km: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RacePredictionComparisonRead(SQLModel):
    """Schema de lecture d'une comparaison sauvegardee."""
    id: UUID
    user_id: UUID
    prediction_id: UUID
    activity_id: Optional[UUID]
    name: str
    comparison_data: Dict[str, Any]
    total_delta_min: Optional[float]
    moving_delta_min: Optional[float]
    pause_delta_min: Optional[float]
    avg_abs_segment_delta_min: Optional[float]
    comparable_distance_km: Optional[float]
    created_at: datetime
    updated_at: datetime


class RaceValidationReference(SQLModel, table=True):
    """Qualification durable d'une activité réelle utilisée en validation."""
    __tablename__ = "racevalidationreference"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    activity_id: UUID = Field(foreign_key="activity.id", unique=True, index=True)
    category: str = Field(default="unclassified", index=True)
    notes: Optional[str] = None
    potential_gain_min_low: Optional[float] = None
    potential_gain_min_high: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RaceReferenceCandidate(SQLModel, table=True):
    """Candidat automatique pour qualifier une activite comme reference."""
    __tablename__ = "racereferencecandidate"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    activity_id: UUID = Field(foreign_key="activity.id", unique=True, index=True)

    suggested_category: str = Field(default="training_control", index=True)
    confidence: str = Field(default="medium", index=True)
    score: float = Field(default=0.0, index=True)
    status: str = Field(default="pending", index=True)

    reasons: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    features: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    notes: Optional[str] = None
    potential_gain_min_low: Optional[float] = None
    potential_gain_min_high: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RacePredictorV3ResidualModel(SQLModel, table=True):
    """Modele residuel V3 appris automatiquement depuis les references."""
    __tablename__ = "racepredictorv3residualmodel"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", unique=True, index=True)
    model_version: str = Field(default="v3_residual_v1", index=True)
    status: str = Field(default="insufficient_data", index=True)

    eligible_count: int = Field(default=0)
    selected_count: int = Field(default=0)
    observation_count: int = Field(default=0)
    model_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    history_start_date: Optional[datetime] = None
    history_end_date: Optional[datetime] = None
    trained_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
