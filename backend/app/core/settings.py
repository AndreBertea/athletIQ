"""
Configuration centralisée pour l'application StrideDelta
Utilise pydantic-settings pour la gestion des variables d'environnement
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """Configuration de l'application"""
    
    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./stridedelta.db",
        description="URL de la base de données (SQLite par défaut, PostgreSQL en production)"
    )
    
    # JWT Configuration
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Clé secrète pour signer les JWT"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    
    # Strava OAuth
    STRAVA_CLIENT_ID: str = Field(
        default="158144",
        description="Client ID Strava OAuth"
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
        default="http://localhost:8000/api/v1/auth/strava/callback",
        description="URI de callback OAuth Strava"
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
        default="http://localhost:8000/api/v1/auth/google/callback",
        description="URI de callback OAuth Google"
    )
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000", 
            "http://192.168.1.188:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://192.168.1.188:8000",
            "*"  # Fallback pour le développement
        ],
        description="Origines autorisées pour CORS"
    )
    
    # Application
    DEBUG: bool = Field(default=True)
    ENVIRONMENT: str = Field(default="development")
    
    # Encryption (pour les tokens Strava stockés)
    ENCRYPTION_KEY: str = Field(
        default="",
        description="Clé pour chiffrer les tokens Strava"
    )
    
    class Config:
        env_file = ".env"  # Utiliser le fichier .env principal
        case_sensitive = True


def get_settings() -> Settings:
    """Récupère la configuration"""
    return Settings() 