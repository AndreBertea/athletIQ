"""
Configuration de la base de données avec SQLModel
"""
from sqlmodel import create_engine, SQLModel, Session
from app.core.settings import get_settings

settings = get_settings()

# Créer l'engine de base de données
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True
)


def create_db_and_tables():
    """Créer toutes les tables de la base de données"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Générateur de session de base de données pour l'injection de dépendance"""
    with Session(engine) as session:
        yield session 