"""
Entite ReferenceTest - Domain Layer (Race Predictor V2.2)

Test de reference saisi manuellement par l'athlete (5/10 km route, sortie
continue, kilometre vertical, etc.). Sert d'ancre pour la mise a jour des
parametres latents du moteur V2.2 (`flat_capacity_mps`, `durability_alpha`...).

Specification : `docs/RACE_PREDICTOR_V2_2_PLAN.md`, section "ReferenceTest".

Plusieurs tests peuvent etre stockes par utilisateur. Le champ `performed_at`
est obligatoire pour autoriser le replay chronologique sans fuite temporelle.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ReferenceTestType(str, Enum):
    """Protocole du test de reference."""
    ROAD_5K = "road_5k"
    ROAD_10K = "road_10k"
    LONG_STEADY = "long_steady"
    HILL_CLIMB = "hill_climb"
    VERTICAL_KM = "vertical_km"


class ReferenceTestSurface(str, Enum):
    """Surface du test (qualification documentaire)."""
    ASPHALT = "asphalt"
    GRAVEL = "gravel"
    DIRT = "dirt"
    TECHNICAL_TRAIL = "technical_trail"
    TRACK = "track"


class ReferenceTestQuality(str, Enum):
    """Statut qualite ; un test invalide ne contribue pas au posterior."""
    VALID = "valid"
    QUESTIONABLE = "questionable"
    INVALIDATED = "invalidated"


class ReferenceTest(SQLModel, table=True):
    """Test de reference d'un utilisateur (plusieurs tests par user autorises)."""
    __tablename__ = "referencetest"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    test_type: ReferenceTestType = Field(nullable=False)
    performed_at: datetime = Field(nullable=False)
    duration_seconds: int = Field(nullable=False)

    # Selon protocole : seul `duration_seconds` est requis, les autres champs
    # de mesure peuvent etre nuls (ex. hill_climb n'a pas forcement de distance).
    distance_m: Optional[float] = Field(default=None)
    elevation_gain_m: Optional[float] = Field(default=None)

    # Conditions externes
    temperature_c: Optional[float] = Field(default=None)
    surface: Optional[ReferenceTestSurface] = Field(default=None)
    conditions_notes: Optional[str] = Field(default=None)

    # Qualification : par defaut valide ; le service peut le degrader.
    quality_status: ReferenceTestQuality = Field(
        default=ReferenceTestQuality.VALID,
        nullable=False,
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReferenceTestRead(SQLModel):
    """Schema de lecture d'un test (reponse API)."""
    id: UUID
    user_id: UUID
    test_type: ReferenceTestType
    performed_at: datetime
    duration_seconds: int
    distance_m: Optional[float]
    elevation_gain_m: Optional[float]
    temperature_c: Optional[float]
    surface: Optional[ReferenceTestSurface]
    conditions_notes: Optional[str]
    quality_status: ReferenceTestQuality
    created_at: datetime
    updated_at: datetime


class ReferenceTestCreate(SQLModel):
    """Schema POST pour creer un test."""
    test_type: ReferenceTestType
    performed_at: datetime
    duration_seconds: int
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    temperature_c: Optional[float] = None
    surface: Optional[ReferenceTestSurface] = None
    conditions_notes: Optional[str] = None
    quality_status: ReferenceTestQuality = ReferenceTestQuality.VALID


class ReferenceTestUpdate(SQLModel):
    """Schema PATCH : tous les champs sont optionnels (ex. invalider un test)."""
    test_type: Optional[ReferenceTestType] = None
    performed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    temperature_c: Optional[float] = None
    surface: Optional[ReferenceTestSurface] = None
    conditions_notes: Optional[str] = None
    quality_status: Optional[ReferenceTestQuality] = None
