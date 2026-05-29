"""add_garmin_daily_performance_metrics

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s3t4u5v6w7x8"
down_revision: Union[str, None] = "r2s3t4u5v6w7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS total_steps INTEGER")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS total_kilocalories INTEGER")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS active_kilocalories INTEGER")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS lactate_threshold_speed_mps DOUBLE PRECISION")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS lactate_threshold_hr INTEGER")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS race_prediction_5k_seconds DOUBLE PRECISION")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS race_prediction_10k_seconds DOUBLE PRECISION")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS race_prediction_half_seconds DOUBLE PRECISION")
    op.execute("ALTER TABLE garmindaily ADD COLUMN IF NOT EXISTS race_prediction_marathon_seconds DOUBLE PRECISION")


def downgrade() -> None:
    op.drop_column("garmindaily", "race_prediction_marathon_seconds")
    op.drop_column("garmindaily", "race_prediction_half_seconds")
    op.drop_column("garmindaily", "race_prediction_10k_seconds")
    op.drop_column("garmindaily", "race_prediction_5k_seconds")
    op.drop_column("garmindaily", "lactate_threshold_hr")
    op.drop_column("garmindaily", "lactate_threshold_speed_mps")
    op.drop_column("garmindaily", "active_kilocalories")
    op.drop_column("garmindaily", "total_kilocalories")
    op.drop_column("garmindaily", "total_steps")
