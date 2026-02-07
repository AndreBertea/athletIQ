"""
Entité User - Domain Layer
Représente un utilisateur de l'application AthlétIQ
"""
# L'import de sqlmodel apparaît en jaune probablement parce que le paquet n'est pas installé dans votre environnement Python,
# ou bien votre IDE ne le trouve pas. Assurez-vous d'avoir installé sqlmodel avec : pip install sqlmodel
from sqlmodel import SQLModel, Field, Relationship
from pydantic import EmailStr, field_validator
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from .activity import Activity
    from .workout_plan import WorkoutPlan


class UserBase(SQLModel):
    """Modèle de base pour User"""
    email: str = Field(unique=True, index=True, max_length=255)
    full_name: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()


class User(UserBase, table=True):
    """Entité User complète pour la base de données"""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    hashed_password: str

    # Relations
    activities: List["Activity"] = Relationship(back_populates="user")
    workout_plans: List["WorkoutPlan"] = Relationship(back_populates="user")
    strava_auth: Optional["StravaAuth"] = Relationship(back_populates="user")
    google_auth: Optional["GoogleAuth"] = Relationship(back_populates="user")
    garmin_auth: Optional["GarminAuth"] = Relationship(back_populates="user")


class UserCreate(UserBase):
    """Schéma pour créer un utilisateur"""
    password: str


class UserRead(UserBase):
    """Schéma pour lire un utilisateur (réponse API)"""
    id: UUID
    created_at: datetime


class UserUpdate(SQLModel):
    """Schéma pour mettre à jour un utilisateur"""
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    
    @field_validator('email', mode='before')
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()


class StravaAuthBase(SQLModel):
    """Modèle de base pour l'authentification Strava"""
    strava_athlete_id: int = Field(unique=True, index=True)
    access_token_encrypted: str
    refresh_token_encrypted: str
    expires_at: datetime
    scope: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StravaAuth(StravaAuthBase, table=True):
    """Authentification Strava d'un utilisateur"""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    strava_athlete_id: int
    access_token_encrypted: str
    refresh_token_encrypted: str
    expires_at: datetime
    scope: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relations
    user: "User" = Relationship(back_populates="strava_auth")


class GoogleAuth(SQLModel, table=True):
    """Authentification Google Calendar d'un utilisateur"""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    google_user_id: str
    access_token_encrypted: str
    refresh_token_encrypted: str
    expires_at: datetime
    scope: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relations
    user: "User" = Relationship(back_populates="google_auth")


class GarminAuth(SQLModel, table=True):
    """Authentification Garmin Connect d'un utilisateur"""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", unique=True, index=True)
    garmin_display_name: Optional[str] = None
    oauth_token_encrypted: str
    token_created_at: datetime = Field(default_factory=datetime.utcnow)
    last_sync_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relations
    user: "User" = Relationship(back_populates="garmin_auth")


class GarminAuthRead(SQLModel):
    """Schéma pour lire l'auth Garmin (sans token)"""
    id: UUID
    garmin_display_name: Optional[str]
    token_created_at: datetime
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class StravaAuthRead(StravaAuthBase):
    """Schéma pour lire l'auth Strava (sans tokens)"""
    id: UUID
    strava_athlete_id: int
    scope: str
    created_at: datetime
    updated_at: datetime