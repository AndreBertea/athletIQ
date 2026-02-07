"""
Entité SegmentFeatures - Domain Layer
Features cumulatives et dérivées calculées pour chaque segment.
Les champs Minetti/drift/cadence_decay sont remplis à l'étape 4.
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime


class SegmentFeatures(SQLModel, table=True):
    """Features cumulatives et dérivées associées à un segment."""
    __tablename__ = "segmentfeatures"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    segment_id: UUID = Field(foreign_key="segment.id", index=True, unique=True)
    activity_id: UUID = Field(foreign_key="activity.id", index=True)

    # Features cumulatives (calculées à l'étape 1)
    cumulative_distance_km: float
    elapsed_time_min: float
    cumulative_elev_gain_m: Optional[float] = None
    cumulative_elev_loss_m: Optional[float] = None
    race_completion_pct: Optional[float] = None
    intensity_proxy: Optional[float] = None

    # Features dérivées avancées (remplies à l'étape 4)
    minetti_cost: Optional[float] = None
    cardiac_drift: Optional[float] = None
    cadence_decay: Optional[float] = None
    grade_variability: Optional[float] = None
    efficiency_factor: Optional[float] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SegmentFeaturesRead(SQLModel):
    """Schéma pour lire les features d'un segment (réponse API)."""
    id: UUID
    segment_id: UUID
    activity_id: UUID
    cumulative_distance_km: float
    elapsed_time_min: float
    cumulative_elev_gain_m: Optional[float]
    cumulative_elev_loss_m: Optional[float]
    race_completion_pct: Optional[float]
    intensity_proxy: Optional[float]
    minetti_cost: Optional[float]
    cardiac_drift: Optional[float]
    cadence_decay: Optional[float]
    grade_variability: Optional[float]
    efficiency_factor: Optional[float]
