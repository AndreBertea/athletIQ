import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ajouter le chemin de l'app pour les imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

# Import des modèles SQLModel
from app.domain.entities.user import User
from app.domain.entities.activity import Activity
from app.domain.entities.workout_plan import WorkoutPlan
from app.domain.entities.enrichment_queue import EnrichmentQueue
from app.domain.entities.segment import Segment
from app.domain.entities.segment_features import SegmentFeatures
from app.domain.entities.activity_weather import ActivityWeather
from app.core.database import engine
from sqlmodel import SQLModel

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Utiliser les métadonnées SQLModel pour l'autogenerate
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    from app.core.settings import get_settings
    settings = get_settings()
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Utiliser notre engine configuré au lieu de créer un nouveau
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
