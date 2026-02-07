"""add_activity_weather

Revision ID: c4e5f6a7b8d9
Revises: b3f4a5c6d7e8
Create Date: 2026-02-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c4e5f6a7b8d9'
down_revision: Union[str, None] = 'b3f4a5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('activityweather',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('activity_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('humidity_pct', sa.Float(), nullable=True),
        sa.Column('wind_speed_kmh', sa.Float(), nullable=True),
        sa.Column('wind_direction_deg', sa.Float(), nullable=True),
        sa.Column('pressure_hpa', sa.Float(), nullable=True),
        sa.Column('precipitation_mm', sa.Float(), nullable=True),
        sa.Column('cloud_cover_pct', sa.Float(), nullable=True),
        sa.Column('weather_code', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['activity_id'], ['activity.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('activity_id'),
    )
    op.create_index('ix_activityweather_activity_id', 'activityweather', ['activity_id'])


def downgrade() -> None:
    op.drop_index('ix_activityweather_activity_id', table_name='activityweather')
    op.drop_table('activityweather')
