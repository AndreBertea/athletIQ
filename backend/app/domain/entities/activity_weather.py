"""
Entité ActivityWeather - Domain Layer
Données météo associées à une activité (source : Open-Meteo).
"""
from sqlmodel import SQLModel, Field, JSON, Column
from typing import Any, Dict, Optional
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

    # Donnees Open-Meteo extensibles pour analyses futures
    sampled_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_m: Optional[float] = None
    source_endpoint: Optional[str] = None
    source_url: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    hourly_units: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    hourly_snapshot: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

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
    sampled_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_m: Optional[float] = None
    source_endpoint: Optional[str] = None
    source_url: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = None
    hourly_units: Optional[Dict[str, Any]] = None
    hourly_snapshot: Optional[Dict[str, Any]] = None
