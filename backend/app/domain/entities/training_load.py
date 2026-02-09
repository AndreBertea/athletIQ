"""
Entité TrainingLoad - Domain Layer
Métriques de charge d'entraînement quotidiennes (CTL, ATL, TSB, Banister).
"""
from sqlmodel import SQLModel, Field, UniqueConstraint
from typing import Optional
from uuid import UUID, uuid4
from datetime import date as date_type, datetime


class TrainingLoad(SQLModel, table=True):
    """Charge d'entraînement quotidienne par utilisateur (modèle Banister)."""
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_training_load_user_date"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    date: date_type = Field(index=True)

    # Métriques Banister
    ctl_42d: Optional[float] = None
    atl_7d: Optional[float] = None
    tsb: Optional[float] = None

    # Métriques Edwards
    edwards_trimp_daily: Optional[float] = None
    ctl_42d_edwards: Optional[float] = None
    atl_7d_edwards: Optional[float] = None
    tsb_edwards: Optional[float] = None

    # Delta RHR (si Garmin disponible)
    rhr_delta_7d: Optional[float] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TrainingLoadRead(SQLModel):
    """Schéma pour lire les données de charge d'entraînement (réponse API)."""
    id: UUID
    user_id: UUID
    date: date_type
    ctl_42d: Optional[float]
    atl_7d: Optional[float]
    tsb: Optional[float]
    edwards_trimp_daily: Optional[float]
    ctl_42d_edwards: Optional[float]
    atl_7d_edwards: Optional[float]
    tsb_edwards: Optional[float]
    rhr_delta_7d: Optional[float]
    created_at: datetime
    updated_at: datetime
