"""
Entites GPX Route - Domain Layer

Bibliotheque de traces GPX stockees en base. Sert le menu deroulant
du Race Predictor (catalogue global d'epreuves cibles) et l'import
de traces personnelles par l'utilisateur.

Une `GpxRoute` peut etre :
  - publique (`is_public=True`, `user_id=None`) : seed visible par tous,
    typiquement les courses cibles preremplies par l'app.
  - privee (`user_id=<uuid>`) : trace importee par l'utilisateur, visible
    uniquement par lui.

Chaque `GpxRoute` peut porter N `GpxAttachment` (PDF, image, etc.) :
typiquement un trace A4 pour preparer la course. Les attachments suivent
la visibilite de leur route.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Column, Field, JSON, LargeBinary, SQLModel


class GpxRoute(SQLModel, table=True):
    """Trace GPX enregistree (catalogue public ou import utilisateur)."""

    __tablename__ = "gpxroute"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="user.id", index=True)
    is_public: bool = Field(default=False, index=True)

    name: str = Field(index=True)
    filename: str
    gpx_data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))

    distance_km: Optional[float] = None
    elevation_gain_m: Optional[float] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GpxAttachment(SQLModel, table=True):
    """Fichier annexe (PDF, image...) attache a une GpxRoute."""

    __tablename__ = "gpxattachment"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    route_id: UUID = Field(foreign_key="gpxroute.id", index=True)

    name: str = Field(index=True)
    filename: str
    mime_type: str = Field(default="application/octet-stream")
    kind: str = Field(default="other", index=True)
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class GpxRouteUserSettings(SQLModel, table=True):
    """Reglages personnels d'un utilisateur pour une trace GPX."""

    __tablename__ = "gpxrouteusersettings"
    __table_args__ = (
        UniqueConstraint("user_id", "route_id", name="uq_gpxrouteusersettings_user_route"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    route_id: UUID = Field(foreign_key="gpxroute.id", index=True)

    preferred_engine: str = Field(default="v3")
    analysis_mode: str = Field(default="auto")
    effort_mode: str = Field(default="steady")
    ravito_mode: str = Field(default="auto")
    weather_mode: str = Field(default="auto")
    manual_temperature_c: Optional[float] = Field(default=None)
    history_start_date: Optional[str] = Field(default=None)
    race_datetime: Optional[str] = Field(default=None)
    custom_ravitos: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GpxRouteSummary(SQLModel):
    """Vue de liste : sans le binaire GPX (gain de bande passante)."""

    id: UUID
    name: str
    filename: str
    is_public: bool
    distance_km: Optional[float]
    elevation_gain_m: Optional[float]
    owned_by_user: bool
    attachment_count: int
    created_at: datetime


class GpxAttachmentRead(SQLModel):
    """Vue d'un attachment (sans data binaire)."""

    id: UUID
    route_id: UUID
    name: str
    filename: str
    mime_type: str
    kind: str
    created_at: datetime


class GpxRouteDetail(SQLModel):
    """Vue detaillee d'une route avec ses attachments (sans binaires)."""

    id: UUID
    name: str
    filename: str
    is_public: bool
    distance_km: Optional[float]
    elevation_gain_m: Optional[float]
    owned_by_user: bool
    attachments: list[GpxAttachmentRead]
    created_at: datetime
    updated_at: datetime


class GpxRouteUserSettingsRead(SQLModel):
    """Vue des reglages personnels d'un utilisateur pour une route."""

    id: UUID
    route_id: UUID
    preferred_engine: str
    analysis_mode: str
    effort_mode: str
    ravito_mode: str
    weather_mode: str
    manual_temperature_c: Optional[float]
    history_start_date: Optional[str]
    race_datetime: Optional[str]
    custom_ravitos: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class GpxRouteUserSettingsUpdate(SQLModel):
    """Payload de sauvegarde partielle des reglages Race Predictor."""

    preferred_engine: Optional[str] = None
    analysis_mode: Optional[str] = None
    effort_mode: Optional[str] = None
    ravito_mode: Optional[str] = None
    weather_mode: Optional[str] = None
    manual_temperature_c: Optional[float] = None
    history_start_date: Optional[str] = None
    race_datetime: Optional[str] = None
    custom_ravitos: Optional[list[dict[str, Any]]] = None
