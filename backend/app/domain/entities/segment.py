"""
Entité Segment - Domain Layer
Représente un segment de ~100m découpé à partir des streams_data d'une activité.
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime


class Segment(SQLModel, table=True):
    """Segment de ~100m d'une activité, issu de la segmentation des streams."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    activity_id: UUID = Field(foreign_key="activity.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    segment_index: int

    # Métriques de distance et temps
    distance_m: float
    elapsed_time_s: float

    # Terrain
    avg_grade_percent: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    elevation_loss_m: Optional[float] = None
    altitude_m: Optional[float] = None

    # Physiologie
    avg_hr: Optional[float] = None
    avg_cadence: Optional[float] = None

    # Position GPS (midpoint du segment)
    lat: Optional[float] = None
    lon: Optional[float] = None

    # Variable cible
    pace_min_per_km: Optional[float] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SegmentRead(SQLModel):
    """Schéma pour lire un segment (réponse API)."""
    id: UUID
    activity_id: UUID
    segment_index: int
    distance_m: float
    elapsed_time_s: float
    avg_grade_percent: Optional[float]
    elevation_gain_m: Optional[float]
    elevation_loss_m: Optional[float]
    altitude_m: Optional[float]
    avg_hr: Optional[float]
    avg_cadence: Optional[float]
    lat: Optional[float]
    lon: Optional[float]
    pace_min_per_km: Optional[float]
