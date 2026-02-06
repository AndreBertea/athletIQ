"""
Entite EnrichmentQueue - Domain Layer
File d'attente pour l'enrichissement des activites Strava (streams, laps, segments)
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum


class EnrichmentStatus(str, Enum):
    """Statuts possibles d'un item dans la queue"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class EnrichmentQueue(SQLModel, table=True):
    """Table enrichment_queue pour gerer la file d'attente d'enrichissement"""
    __tablename__ = "enrichment_queue"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    activity_id: UUID = Field(foreign_key="activity.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    priority: int = Field(default=0, index=True)
    status: EnrichmentStatus = Field(default=EnrichmentStatus.PENDING, index=True)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    last_error: Optional[str] = None
    next_retry_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
