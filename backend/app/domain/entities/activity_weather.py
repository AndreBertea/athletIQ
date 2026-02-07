"""
Entité ActivityWeather - Domain Layer
Données météo associées à une activité (source : Open-Meteo).
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime


class ActivityWeather(SQLModel, table=True):
    """Données météo pour une activité, une entrée par activité."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    activity_id: UUID = Field(foreign_key="activity.id", unique=True, index=True)

    # Conditions météo
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    pressure_hpa: Optional[float] = None
    precipitation_mm: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    weather_code: Optional[int] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ActivityWeatherRead(SQLModel):
    """Schéma pour lire les données météo (réponse API)."""
    id: UUID
    activity_id: UUID
    temperature_c: Optional[float]
    humidity_pct: Optional[float]
    wind_speed_kmh: Optional[float]
    wind_direction_deg: Optional[float]
    pressure_hpa: Optional[float]
    precipitation_mm: Optional[float]
    cloud_cover_pct: Optional[float]
    weather_code: Optional[int]
