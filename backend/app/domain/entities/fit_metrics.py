"""
Entité FitMetrics - Domain Layer
Données extraites des fichiers FIT Garmin (Running Dynamics, power, Training Effect).
Relation 1:1 avec Activity (même pattern que ActivityWeather).
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime


class FitMetrics(SQLModel, table=True):
    """Métriques FIT pour une activité, une entrée par activité."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    activity_id: UUID = Field(foreign_key="activity.id", unique=True, index=True)

    # Running Dynamics
    ground_contact_time_avg: Optional[float] = None  # ms
    vertical_oscillation_avg: Optional[float] = None  # cm
    stance_time_balance_avg: Optional[float] = None  # % (G/D)

    # Puissance
    power_avg: Optional[float] = None  # W

    # Training Effect
    aerobic_training_effect: Optional[float] = None  # 0.0-5.0
    anaerobic_training_effect: Optional[float] = None  # 0.0-5.0

    # Metadata
    record_count: Optional[int] = None
    fit_downloaded_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FitMetricsRead(SQLModel):
    """Schéma pour lire les métriques FIT (réponse API)."""
    id: UUID
    activity_id: UUID
    ground_contact_time_avg: Optional[float]
    vertical_oscillation_avg: Optional[float]
    stance_time_balance_avg: Optional[float]
    power_avg: Optional[float]
    aerobic_training_effect: Optional[float]
    anaerobic_training_effect: Optional[float]
    record_count: Optional[int]
    fit_downloaded_at: Optional[datetime]
