"""
Entite CoachAthleteRelation - Domain Layer.
Modele coach <-> athlete avec invitations par email.
"""
from sqlmodel import SQLModel, Field, UniqueConstraint
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum


class RelationStatus(str, Enum):
    """Statut d'une relation coach-athlete."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"


class CoachAthleteRelation(SQLModel, table=True):
    """Relation entre un coach et un athlete (ou invitation en attente)."""
    __tablename__ = "coachathleterelation"
    __table_args__ = (
        UniqueConstraint("coach_id", "invited_email", name="uq_coachathlete_coach_email"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    coach_id: UUID = Field(foreign_key="user.id", index=True)
    athlete_id: Optional[UUID] = Field(default=None, foreign_key="user.id", index=True)
    invited_email: str = Field(index=True, max_length=255)
    status: str = Field(default=RelationStatus.PENDING.value, index=True, max_length=16)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    responded_at: Optional[datetime] = None


# ---------- Schemas Read / Create ----------

class CoachAthleteRelationRead(SQLModel):
    """Vue API d'une relation (sans les FK qui ne servent pas au front)."""
    id: UUID
    coach_id: UUID
    athlete_id: Optional[UUID]
    invited_email: str
    status: str
    created_at: datetime
    responded_at: Optional[datetime]


class InviteAthleteRequest(SQLModel):
    """Payload pour inviter un athlete par email."""
    email: str


class AthleteSummary(SQLModel):
    """Vue d'un athlete pour le coach (avec ses infos publiques)."""
    relation_id: UUID
    athlete_id: Optional[UUID]
    email: str
    full_name: Optional[str]
    status: str  # pending / accepted / declined / revoked
    created_at: datetime
    responded_at: Optional[datetime]


class CoachSummary(SQLModel):
    """Vue d'un coach pour l'athlete."""
    relation_id: UUID
    coach_id: UUID
    coach_email: str
    coach_full_name: str
    status: str
    created_at: datetime
    responded_at: Optional[datetime]
