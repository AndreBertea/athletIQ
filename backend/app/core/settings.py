"""
Configuration centralisée pour l'application StrideDelta
Utilise pydantic-settings pour la gestion des variables d'environnement
"""
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from typing import List
from functools import lru_cache
import json


class Settings(BaseSettings):
    """Configuration de l'application"""
    
    # Database
    DATABASE_URL: str = Field(
        description="URL de la base de données (PostgreSQL en production)"
    )
    
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(
        description="Clé secrète pour signer les JWT (obligatoire, pas de valeur par défaut)"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    
    # Strava OAuth
    STRAVA_CLIENT_ID: str = Field(
        description="Client ID Strava OAuth (obligatoire, pas de valeur par défaut)"
    )
    STRAVA_CLIENT_SECRET: str = Field(
        default="",
        description="Client Secret Strava OAuth"
    )
    STRAVA_REFRESH_TOKEN: str = Field(
        default="",
        description="Refresh Token Strava OAuth (pour l'ETL)"
    )
    STRAVA_REDIRECT_URI: str = Field(
        default="",
        description="URI de callback OAuth Strava (construit automatiquement depuis BACKEND_URL si vide)"
    )
    STRAVA_WEBHOOK_VERIFY_TOKEN: str = Field(
        default="",
        description="Token de verification pour les webhooks Strava (utilisé pour valider la subscription)"
    )
    STRAVA_WEBHOOK_SUBSCRIPTION_ID: str = Field(
        default="",
        description="ID de la subscription webhook Strava (si configuré, les événements avec un subscription_id différent sont rejetés)"
    )
    STRAVA_INTEGRATION_ENABLED: bool = Field(
        default=False,
        description="Autorise les nouvelles connexions, synchronisations et enrichissements Strava",
    )
    
    # Google Calendar OAuth
    GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="Client ID Google OAuth"
    )
    GOOGLE_CLIENT_SECRET: str = Field(
        default="",
        description="Client Secret Google OAuth"
    )
    GOOGLE_REDIRECT_URI: str = Field(
        default="",
        description="URI de callback OAuth Google (construit automatiquement depuis BACKEND_URL si vide)"
    )
    
    # URLs de l'application
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="URL du frontend (utilisée pour les redirections OAuth, CORS, etc.)"
    )
    BACKEND_URL: str = Field(
        default="http://localhost:8000",
        description="URL du backend (utilisée pour construire les redirect URIs OAuth)"
    )

    # CORS
    # Champ stocke en str brut (lit ALLOWED_ORIGINS depuis env) pour eviter
    # le decodage JSON automatique de pydantic-settings (qui casse sur valeurs
    # vides ou format CSV). La List[str] resolue est exposee via la property
    # ALLOWED_ORIGINS plus bas.
    ALLOWED_ORIGINS_RAW: str = Field(
        default="",
        alias="ALLOWED_ORIGINS",
        description="Origines CORS, format JSON ['a','b'] ou CSV 'a,b' ou vide pour defaults selon ENVIRONMENT"
    )

    # Monitoring (Sentry)
    SENTRY_DSN: str = Field(
        default="",
        description="DSN Sentry pour le error tracking (vide = Sentry desactive)"
    )

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="URL de connexion Redis (requis en production pour les quotas Strava)"
    )

    # Application
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(
        default="",
        description="Niveau de logging (auto-configuré selon ENVIRONMENT si vide)"
    )

    @model_validator(mode="after")
    def _configure_environment(self) -> "Settings":
        """Configure DEBUG, LOG_LEVEL et les redirect URIs selon ENVIRONMENT."""
        is_prod = self.ENVIRONMENT == "production"
        # En production, forcer DEBUG=False
        if is_prod:
            self.DEBUG = False
        # LOG_LEVEL par défaut selon ENVIRONMENT
        if not self.LOG_LEVEL:
            self.LOG_LEVEL = "WARNING" if is_prod else "INFO"
        # STRAVA_REDIRECT_URI dynamique basé sur BACKEND_URL
        if not self.STRAVA_REDIRECT_URI:
            self.STRAVA_REDIRECT_URI = f"{self.BACKEND_URL.rstrip('/')}/api/v1/auth/strava/callback"
        # GOOGLE_REDIRECT_URI dynamique basé sur BACKEND_URL
        if not self.GOOGLE_REDIRECT_URI:
            self.GOOGLE_REDIRECT_URI = f"{self.BACKEND_URL.rstrip('/')}/api/v1/auth/google/callback"
        return self

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Liste des origines CORS resolue depuis ALLOWED_ORIGINS_RAW + defaults."""
        raw = (self.ALLOWED_ORIGINS_RAW or "").strip()
        parsed: List[str] = []
        if raw:
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = []
            else:
                parsed = [item.strip() for item in raw.split(",") if item.strip()]

        if not parsed:
            if self.ENVIRONMENT == "production":
                parsed = [
                    "https://athletiq.vercel.app",
                    "https://athlet-iq-beta.vercel.app",
                ]
            else:
                parsed = [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                    "http://localhost:4000",
                    "http://127.0.0.1:4000",
                ]
        # Toujours inclure FRONTEND_URL dans les origines autorisees
        frontend = self.FRONTEND_URL.rstrip("/")
        if frontend and frontend not in parsed:
            parsed.append(frontend)
        return parsed
    
    # Encryption (pour les tokens Strava stockés)
    ENCRYPTION_KEY: str = Field(
        description="Clé Fernet pour chiffrer les tokens Strava (obligatoire, pas de valeur par défaut)"
    )
    
    class Config:
        env_file = ".env"  # Utiliser le fichier .env principal
        case_sensitive = True
        populate_by_name = True  # Permet l'alias ALLOWED_ORIGINS -> ALLOWED_ORIGINS_RAW


def get_settings() -> Settings:
    """Récupère la configuration"""
    return Settings() 
