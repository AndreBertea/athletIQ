"""add_garmin_tables

Revision ID: d5f6a7b8c9e0
Revises: c4e5f6a7b8d9
Create Date: 2026-02-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd5f6a7b8c9e0'
down_revision: Union[str, None] = 'c4e5f6a7b8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('garminauth',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('garmin_display_name', sa.String(), nullable=True),
        sa.Column('oauth_token_encrypted', sa.String(), nullable=False),
        sa.Column('token_created_at', sa.DateTime(), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_garminauth_user_id', 'garminauth', ['user_id'])

    op.create_table('garmindaily',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('training_readiness', sa.Float(), nullable=True),
        sa.Column('hrv_rmssd', sa.Float(), nullable=True),
        sa.Column('sleep_score', sa.Float(), nullable=True),
        sa.Column('sleep_duration_min', sa.Float(), nullable=True),
        sa.Column('resting_hr', sa.Integer(), nullable=True),
        sa.Column('stress_score', sa.Float(), nullable=True),
        sa.Column('spo2', sa.Float(), nullable=True),
        sa.Column('vo2max_estimated', sa.Float(), nullable=True),
        sa.Column('weight_kg', sa.Float(), nullable=True),
        sa.Column('body_battery_max', sa.Integer(), nullable=True),
        sa.Column('body_battery_min', sa.Integer(), nullable=True),
        sa.Column('training_status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_garmin_daily_user_date'),
    )
    op.create_index('ix_garmindaily_user_id', 'garmindaily', ['user_id'])
    op.create_index('ix_garmindaily_date', 'garmindaily', ['date'])


def downgrade() -> None:
    op.drop_index('ix_garmindaily_date', table_name='garmindaily')
    op.drop_index('ix_garmindaily_user_id', table_name='garmindaily')
    op.drop_table('garmindaily')
    op.drop_index('ix_garminauth_user_id', table_name='garminauth')
    op.drop_table('garminauth')
