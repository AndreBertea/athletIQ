"""add_missing_activity_columns_and_fix_strava_id_bigint

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-02-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h2b3c4d5e6f7'
down_revision: Union[str, None] = 'g1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix strava_id: Integer → BigInteger
    op.alter_column('activity', 'strava_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)

    # Métriques supplémentaires
    op.add_column('activity', sa.Column('calories', sa.Float(), nullable=True))
    op.add_column('activity', sa.Column('start_date_local', sa.DateTime(), nullable=True))
    op.add_column('activity', sa.Column('workout_type', sa.Integer(), nullable=True))
    op.add_column('activity', sa.Column('trainer', sa.Boolean(), nullable=True))
    op.add_column('activity', sa.Column('commute', sa.Boolean(), nullable=True))
    op.add_column('activity', sa.Column('manual', sa.Boolean(), nullable=True))
    op.add_column('activity', sa.Column('suffer_score', sa.Integer(), nullable=True))

    # Puissance
    op.add_column('activity', sa.Column('average_watts', sa.Float(), nullable=True))
    op.add_column('activity', sa.Column('max_watts', sa.Float(), nullable=True))
    op.add_column('activity', sa.Column('weighted_average_watts', sa.Float(), nullable=True))
    op.add_column('activity', sa.Column('kilojoules', sa.Float(), nullable=True))

    # Données GPS
    op.add_column('activity', sa.Column('start_latlng', sa.JSON(), nullable=True))
    op.add_column('activity', sa.Column('end_latlng', sa.JSON(), nullable=True))
    op.add_column('activity', sa.Column('summary_polyline', sa.Text(), nullable=True))
    op.add_column('activity', sa.Column('polyline', sa.Text(), nullable=True))


def downgrade() -> None:
    # Supprimer les colonnes GPS
    op.drop_column('activity', 'polyline')
    op.drop_column('activity', 'summary_polyline')
    op.drop_column('activity', 'end_latlng')
    op.drop_column('activity', 'start_latlng')

    # Supprimer les colonnes puissance
    op.drop_column('activity', 'kilojoules')
    op.drop_column('activity', 'weighted_average_watts')
    op.drop_column('activity', 'max_watts')
    op.drop_column('activity', 'average_watts')

    # Supprimer les métriques
    op.drop_column('activity', 'suffer_score')
    op.drop_column('activity', 'manual')
    op.drop_column('activity', 'commute')
    op.drop_column('activity', 'trainer')
    op.drop_column('activity', 'workout_type')
    op.drop_column('activity', 'start_date_local')
    op.drop_column('activity', 'calories')

    # Reverter strava_id BigInteger → Integer
    op.alter_column('activity', 'strava_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
