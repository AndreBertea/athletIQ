"""add_garmin_activity_and_fitmetrics

Revision ID: f7b8c9d0e1f2
Revises: e6a7b8c9d0f1
Create Date: 2026-02-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f7b8c9d0e1f2'
down_revision: Union[str, None] = 'e6a7b8c9d0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Ajout de source + garmin_activity_id a la table activity ---
    op.add_column('activity', sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('activity', sa.Column('garmin_activity_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_activity_source'), 'activity', ['source'], unique=False)
    op.create_index(op.f('ix_activity_garmin_activity_id'), 'activity', ['garmin_activity_id'], unique=True)

    # Backfill : toutes les activites existantes viennent de Strava
    op.execute("UPDATE activity SET source = 'strava' WHERE source IS NULL")

    # Rendre source NOT NULL apres backfill
    op.alter_column('activity', 'source', nullable=False, server_default='strava')

    # --- Creer la table fitmetrics ---
    op.create_table(
        'fitmetrics',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('activity_id', sa.Uuid(), nullable=False),
        sa.Column('ground_contact_time_avg', sa.Float(), nullable=True),
        sa.Column('vertical_oscillation_avg', sa.Float(), nullable=True),
        sa.Column('stance_time_balance_avg', sa.Float(), nullable=True),
        sa.Column('power_avg', sa.Float(), nullable=True),
        sa.Column('aerobic_training_effect', sa.Float(), nullable=True),
        sa.Column('anaerobic_training_effect', sa.Float(), nullable=True),
        sa.Column('record_count', sa.Integer(), nullable=True),
        sa.Column('fit_downloaded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['activity_id'], ['activity.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fitmetrics_activity_id'), 'fitmetrics', ['activity_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_fitmetrics_activity_id'), table_name='fitmetrics')
    op.drop_table('fitmetrics')
    op.drop_index(op.f('ix_activity_garmin_activity_id'), table_name='activity')
    op.drop_index(op.f('ix_activity_source'), table_name='activity')
    op.drop_column('activity', 'garmin_activity_id')
    op.drop_column('activity', 'source')
