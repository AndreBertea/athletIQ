"""
Entite AthleticProfile - Domain Layer (Race Predictor V2.2)

Profil athlete facultatif separe de l'entite User afin de :
  - garder l'authentification stable ;
  - permettre l'evolution des donnees de profil sans toucher au coeur auth ;
  - alimenter le prior populationnel du moteur de prediction V2.2.

Specification : `docs/RACE_PREDICTOR_V2_2_PLAN.md`, section "AthleticProfile".

Aucune logique metier ici : couche donnees uniquement.
Les validations physiologiques (taille/poids plausibles) sont laissees
volontairement au service applicatif pour autoriser des champs vides.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class AthleticSex(str, Enum):
    """Sexe declare par l'athlete."""
    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class ActivityLevel(str, Enum):
    """Indicateur d'activite physique declaree (cf. Jackson et al. 1990)."""
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class ExperienceLevel(str, Enum):
    """Niveau d'experience auto-declare."""
    BEGINNER = "beginner"
    REGULAR = "regular"
    COMPETITOR = "competitor"
    ELITE = "elite"


class PracticeDominant(str, Enum):
    """Pratique principale renseignee par l'athlete."""
    ROAD = "road"
    TRAIL = "trail"
    MIXED = "mixed"


class WeeklyVolumeBand(str, Enum):
    """Tranche de volume hebdomadaire en km (moins fragile qu'un chiffre exact)."""
    UNDER_20KM = "under_20km"
    BAND_20_40KM = "20_40km"
    BAND_40_60KM = "40_60km"
    BAND_60_80KM = "60_80km"
    OVER_80KM = "over_80km"


class AthleticProfile(SQLModel, table=True):
    """Profil athlete facultatif, un seul par utilisateur."""
    __tablename__ = "athleticprofile"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", unique=True, index=True)

    # Donnees demographiques (toutes facultatives)
    sex: Optional[AthleticSex] = Field(default=None)
    birth_date: Optional[date] = Field(default=None)
    height_cm: Optional[float] = Field(default=None)
    weight_kg: Optional[float] = Field(default=None)

    # Donnees comportementales pour resserrer le prior
    activity_level: Optional[ActivityLevel] = Field(default=None)
    experience_level: Optional[ExperienceLevel] = Field(default=None)
    practice_dominant: Optional[PracticeDominant] = Field(default=None)
    weekly_volume_band: Optional[WeeklyVolumeBand] = Field(default=None)

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AthleticProfileRead(SQLModel):
    """Schema de lecture du profil (reponse API)."""
    id: UUID
    user_id: UUID
    sex: Optional[AthleticSex]
    birth_date: Optional[date]
    height_cm: Optional[float]
    weight_kg: Optional[float]
    activity_level: Optional[ActivityLevel]
    experience_level: Optional[ExperienceLevel]
    practice_dominant: Optional[PracticeDominant]
    weekly_volume_band: Optional[WeeklyVolumeBand]
    created_at: datetime
    updated_at: datetime


class AthleticProfileUpdate(SQLModel):
    """Schema PATCH : tous les champs sont optionnels."""
    sex: Optional[AthleticSex] = None
    birth_date: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    activity_level: Optional[ActivityLevel] = None
    experience_level: Optional[ExperienceLevel] = None
    practice_dominant: Optional[PracticeDominant] = None
    weekly_volume_band: Optional[WeeklyVolumeBand] = None
