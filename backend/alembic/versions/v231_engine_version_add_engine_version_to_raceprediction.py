"""add_engine_version_to_raceprediction

Migration V2.3.1 - Lot R6 partiel.

Ajoute la colonne `engine_version` a la table `raceprediction`. Cette colonne
etait jusqu'ici creee a la volee par `_ensure_race_prediction_table()` dans
`prediction_router.py` via un DDL runtime. La migration officialise cette
colonne dans Alembic.

Caracteristiques :
- Type VARCHAR.
- Default `v1_random_forest` (engine V1 historique).
- NOT NULL (toutes les anciennes lignes prennent le default au remplissage).
- Index `ix_raceprediction_engine_version` pour le filtrage rapide par moteur.

La migration est idempotente : si la colonne ou l'index existe deja (cas des
DBs ou le DDL runtime a deja agi), l'ajout est skippe sans erreur.

Reference : `docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md` section "R6 - Dette
technique et infrastructure", livrable 2.

Revision ID: v231_engine_version
Revises: p0q1r2s3t4u5
Create Date: 2026-05-26 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "v231_engine_version"
down_revision: Union[str, None] = "p0q1r2s3t4u5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "raceprediction"
_COLUMN_NAME = "engine_version"
_INDEX_NAME = "ix_raceprediction_engine_version"
_DEFAULT_VALUE = "v1_random_forest"


def upgrade() -> None:
    """Ajoute la colonne `engine_version` et son index (idempotent)."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if _TABLE_NAME not in inspector.get_table_names():
        # Si la table n'existe pas encore (cas tres rare : DB fraiche sans
        # initialisation runtime des modeles Race Predictor), on ne fait
        # rien : la table sera creee par `_ensure_race_prediction_table()`
        # au prochain demarrage avec deja la bonne colonne grace au modele
        # SQLModel (engine_version est declare en NOT NULL avec default).
        return

    columns = {col["name"] for col in inspector.get_columns(_TABLE_NAME)}
    if _COLUMN_NAME not in columns:
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                _COLUMN_NAME,
                sa.String(),
                nullable=False,
                server_default=_DEFAULT_VALUE,
            ),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE_NAME)}
    if _INDEX_NAME not in existing_indexes:
        op.create_index(_INDEX_NAME, _TABLE_NAME, [_COLUMN_NAME])


def downgrade() -> None:
    """Supprime l'index et la colonne `engine_version` (idempotent)."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if _TABLE_NAME not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE_NAME)}
    if _INDEX_NAME in existing_indexes:
        op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)

    columns = {col["name"] for col in inspector.get_columns(_TABLE_NAME)}
    if _COLUMN_NAME in columns:
        # SQLite ne supporte pas DROP COLUMN avant la version 3.35 ; Alembic
        # bascule alors automatiquement en mode batch (recreate table).
        with op.batch_alter_table(_TABLE_NAME) as batch_op:
            batch_op.drop_column(_COLUMN_NAME)
