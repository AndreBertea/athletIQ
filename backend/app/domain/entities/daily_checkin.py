"""
Entite DailyCheckin - Domain Layer.
Modele readiness Saw 2017 : 4 wellness (1-5) + sRPE veille + tags contextuels.
"""
from sqlmodel import SQLModel, Field, JSON, Column
from typing import Optional, List
from uuid import UUID, uuid4
from datetime import date as date_type, datetime
from decimal import Decimal
from sqlalchemy import UniqueConstraint, Text


class DailyCheckin(SQLModel, table=True):
    """Une saisie quotidienne par utilisateur."""
    __tablename__ = "dailycheckin"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_date", name="uq_dailycheckin_user_date"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    entry_date: date_type = Field(index=True)

    # 4 wellness Saw (1-5)
    wellbeing: int
    sleep_quality: int
    legs: int
    motivation: int

    # sRPE veille (0-10, hors score readiness)
    srpe_yesterday: Optional[int] = None
    session_duration_min: Optional[int] = None

    # Tags contextuels (catalogue ferme front)
    context_tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    # V2 wearables (NULL en V1)
    hrv_ln_rmssd: Optional[Decimal] = None
    resting_hr_bpm: Optional[int] = None
    sleep_duration_h: Optional[Decimal] = None

    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    source: str = Field(default="manual", max_length=16)
    client_origin: str = Field(default="pwa", max_length=24)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Schemas API ----------

class DailyCheckinRead(SQLModel):
    """Vue API d'une saisie."""
    id: UUID
    entry_date: date_type
    wellbeing: int
    sleep_quality: int
    legs: int
    motivation: int
    srpe_yesterday: Optional[int]
    session_duration_min: Optional[int]
    context_tags: List[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class DailyCheckinCreate(SQLModel):
    """Payload pour creer/upsert une saisie du jour."""
    wellbeing: int = Field(ge=1, le=5)
    sleep_quality: int = Field(ge=1, le=5)
    legs: int = Field(ge=1, le=5)
    motivation: int = Field(ge=1, le=5)
    srpe_yesterday: Optional[int] = Field(default=None, ge=0, le=10)
    session_duration_min: Optional[int] = Field(default=None, ge=0)
    context_tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    entry_date: Optional[date_type] = None  # default: today (server-side)


class ReadinessScore(SQLModel):
    """Score readiness consolide pour l'affichage Home."""
    phase: str  # 'no_entries' | 'calibration' | 'stable'
    days_recorded: int
    days_required: int = 14
    # Si stable : score 0-100 + breakdown
    score_0_100: Optional[float] = None
    z_wellbeing: Optional[float] = None
    z_sleep: Optional[float] = None
    z_legs: Optional[float] = None
    z_motivation: Optional[float] = None
    # Si calibration : valeurs brutes du jour
    today: Optional[DailyCheckinRead] = None
    # Insight bref pour l'UI
    insight: Optional[str] = None
