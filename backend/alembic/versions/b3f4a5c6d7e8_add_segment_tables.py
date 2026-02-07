"""add_segment_tables

Revision ID: b3f4a5c6d7e8
Revises: add_parsing_fields
Create Date: 2026-02-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b3f4a5c6d7e8'
down_revision: Union[str, None] = 'add_parsing_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('segment',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('activity_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('segment_index', sa.Integer(), nullable=False),
        sa.Column('distance_m', sa.Float(), nullable=False),
        sa.Column('elapsed_time_s', sa.Float(), nullable=False),
        sa.Column('avg_grade_percent', sa.Float(), nullable=True),
        sa.Column('elevation_gain_m', sa.Float(), nullable=True),
        sa.Column('elevation_loss_m', sa.Float(), nullable=True),
        sa.Column('altitude_m', sa.Float(), nullable=True),
        sa.Column('avg_hr', sa.Float(), nullable=True),
        sa.Column('avg_cadence', sa.Float(), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lon', sa.Float(), nullable=True),
        sa.Column('pace_min_per_km', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['activity_id'], ['activity.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_segment_activity_id', 'segment', ['activity_id'])
    op.create_index('ix_segment_user_id', 'segment', ['user_id'])

    op.create_table('segmentfeatures',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('segment_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('activity_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('cumulative_distance_km', sa.Float(), nullable=False),
        sa.Column('elapsed_time_min', sa.Float(), nullable=False),
        sa.Column('cumulative_elev_gain_m', sa.Float(), nullable=True),
        sa.Column('cumulative_elev_loss_m', sa.Float(), nullable=True),
        sa.Column('race_completion_pct', sa.Float(), nullable=True),
        sa.Column('intensity_proxy', sa.Float(), nullable=True),
        sa.Column('minetti_cost', sa.Float(), nullable=True),
        sa.Column('cardiac_drift', sa.Float(), nullable=True),
        sa.Column('cadence_decay', sa.Float(), nullable=True),
        sa.Column('grade_variability', sa.Float(), nullable=True),
        sa.Column('efficiency_factor', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['segment_id'], ['segment.id']),
        sa.ForeignKeyConstraint(['activity_id'], ['activity.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('segment_id'),
    )
    op.create_index('ix_segmentfeatures_segment_id', 'segmentfeatures', ['segment_id'])
    op.create_index('ix_segmentfeatures_activity_id', 'segmentfeatures', ['activity_id'])


def downgrade() -> None:
    op.drop_index('ix_segmentfeatures_activity_id', table_name='segmentfeatures')
    op.drop_index('ix_segmentfeatures_segment_id', table_name='segmentfeatures')
    op.drop_table('segmentfeatures')
    op.drop_index('ix_segment_user_id', table_name='segment')
    op.drop_index('ix_segment_activity_id', table_name='segment')
    op.drop_table('segment')
