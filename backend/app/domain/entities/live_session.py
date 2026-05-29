"""
Entites LiveSession + LiveTrackpoint - Domain Layer
Suivi d'activites sportives en temps reel (LiveTrack Garmin en phase 1,
Connect IQ data field en phase 2).
"""
from sqlmodel import SQLModel, Field
from sqlalchemy import BigInteger, Column
from typing import Optional, List
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum


class LiveSessionSource(str, Enum):
    """Source d'une session live."""
    LIVETRACK = "livetrack"
    CONNECT_IQ = "connect_iq"


class LiveSessionStatus(str, Enum):
    """Statut d'une session live."""
    ACTIVE = "active"
    FINISHED = "finished"
    STOPPED = "stopped"


class LiveSession(SQLModel, table=True):
    """Session de suivi live (LiveTrack ou Connect IQ)."""

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    source: str = Field(index=True, max_length=32)
    label: Optional[str] = Field(default=None, max_length=255)
    status: str = Field(default=LiveSessionStatus.ACTIVE.value, index=True, max_length=16)

    # LiveTrack-specific (phase 1)
    garmin_session_id: Optional[str] = Field(default=None, max_length=64)
    garmin_token: Optional[str] = Field(default=None, max_length=128)

    # Connect IQ-specific (phase 2)
    device_token: Optional[str] = Field(default=None, max_length=128)
    activity_uuid: Optional[str] = Field(default=None, max_length=64)

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_point_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LiveTrackpoint(SQLModel, table=True):
    """Point de trace recu en temps reel pour une session."""

    session_id: UUID = Field(foreign_key="livesession.id", primary_key=True)
    # Epoch seconds. BigInteger pour parer les timestamps tres futurs.
    ts: int = Field(sa_column=Column(BigInteger, primary_key=True))

    lat: Optional[float] = None
    lng: Optional[float] = None
    hr: Optional[int] = None
    speed: Optional[float] = None       # m/s
    cadence: Optional[int] = None
    power: Optional[int] = None         # watts
    distance: Optional[float] = None    # metres cumules
    altitude: Optional[float] = None    # metres


# ---------- Schemas Read / Create ----------

class LiveSessionRead(SQLModel):
    """Reponse API pour une session (sans le token Garmin)."""
    id: UUID
    user_id: UUID
    source: str
    label: Optional[str]
    status: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    last_point_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class LiveSessionCreate(SQLModel):
    """Payload pour creer une session LiveTrack a partir d'une URL."""
    url: str
    label: Optional[str] = None


class LiveTrackpointRead(SQLModel):
    """Reponse API pour un trackpoint."""
    ts: int
    lat: Optional[float]
    lng: Optional[float]
    hr: Optional[int]
    speed: Optional[float]
    cadence: Optional[int]
    power: Optional[int]
    distance: Optional[float]
    altitude: Optional[float]


class LiveSessionDetail(LiveSessionRead):
    """Session avec snapshot des trackpoints (pour le bootstrap WS)."""
    points: List[LiveTrackpointRead] = []
