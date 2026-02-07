"""
Entité GarminDaily - Domain Layer
Données physiologiques quotidiennes Garmin Connect (HRV, sommeil, stress, etc.).
"""
from sqlmodel import SQLModel, Field, UniqueConstraint
from typing import Optional
from uuid import UUID, uuid4
from datetime import date as date_type, datetime


class GarminDaily(SQLModel, table=True):
    """Données physiologiques quotidiennes Garmin, une entrée par utilisateur par jour."""
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_garmin_daily_user_date"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    date: date_type = Field(index=True)

    # Données physiologiques
    training_readiness: Optional[float] = None
    hrv_rmssd: Optional[float] = None
    sleep_score: Optional[float] = None
    sleep_duration_min: Optional[float] = None
    resting_hr: Optional[int] = None
    stress_score: Optional[float] = None
    spo2: Optional[float] = None
    vo2max_estimated: Optional[float] = None
    weight_kg: Optional[float] = None
    body_battery_max: Optional[int] = None
    body_battery_min: Optional[int] = None
    training_status: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GarminDailyRead(SQLModel):
    """Schéma pour lire les données Garmin quotidiennes (réponse API)."""
    id: UUID
    user_id: UUID
    date: date_type
    training_readiness: Optional[float]
    hrv_rmssd: Optional[float]
    sleep_score: Optional[float]
    sleep_duration_min: Optional[float]
    resting_hr: Optional[int]
    stress_score: Optional[float]
    spo2: Optional[float]
    vo2max_estimated: Optional[float]
    weight_kg: Optional[float]
    body_battery_max: Optional[int]
    body_battery_min: Optional[int]
    training_status: Optional[str]
    created_at: datetime
    updated_at: datetime
