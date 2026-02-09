"""extend_fitmetrics_columns

Revision ID: g1a2b3c4d5e6
Revises: f8a1b2c3d4e5
Create Date: 2026-02-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, None] = 'f7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Running Dynamics supplementaires
    op.add_column('fitmetrics', sa.Column('stance_time_percent_avg', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('step_length_avg', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('vertical_ratio_avg', sa.Float(), nullable=True))

    # Puissance supplementaire
    op.add_column('fitmetrics', sa.Column('power_max', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('normalized_power', sa.Float(), nullable=True))

    # Cadence
    op.add_column('fitmetrics', sa.Column('cadence_avg', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('cadence_max', sa.Float(), nullable=True))

    # FC
    op.add_column('fitmetrics', sa.Column('heart_rate_avg', sa.Integer(), nullable=True))
    op.add_column('fitmetrics', sa.Column('heart_rate_max', sa.Integer(), nullable=True))

    # Vitesse
    op.add_column('fitmetrics', sa.Column('speed_avg', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('speed_max', sa.Float(), nullable=True))

    # Temperature
    op.add_column('fitmetrics', sa.Column('temperature_avg', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('temperature_max', sa.Float(), nullable=True))

    # Totaux session
    op.add_column('fitmetrics', sa.Column('total_calories', sa.Integer(), nullable=True))
    op.add_column('fitmetrics', sa.Column('total_strides', sa.Integer(), nullable=True))
    op.add_column('fitmetrics', sa.Column('total_ascent', sa.Integer(), nullable=True))
    op.add_column('fitmetrics', sa.Column('total_descent', sa.Integer(), nullable=True))
    op.add_column('fitmetrics', sa.Column('total_distance', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('total_timer_time', sa.Float(), nullable=True))
    op.add_column('fitmetrics', sa.Column('total_elapsed_time', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('fitmetrics', 'total_elapsed_time')
    op.drop_column('fitmetrics', 'total_timer_time')
    op.drop_column('fitmetrics', 'total_distance')
    op.drop_column('fitmetrics', 'total_descent')
    op.drop_column('fitmetrics', 'total_ascent')
    op.drop_column('fitmetrics', 'total_strides')
    op.drop_column('fitmetrics', 'total_calories')
    op.drop_column('fitmetrics', 'temperature_max')
    op.drop_column('fitmetrics', 'temperature_avg')
    op.drop_column('fitmetrics', 'speed_max')
    op.drop_column('fitmetrics', 'speed_avg')
    op.drop_column('fitmetrics', 'heart_rate_max')
    op.drop_column('fitmetrics', 'heart_rate_avg')
    op.drop_column('fitmetrics', 'cadence_max')
    op.drop_column('fitmetrics', 'cadence_avg')
    op.drop_column('fitmetrics', 'normalized_power')
    op.drop_column('fitmetrics', 'power_max')
    op.drop_column('fitmetrics', 'vertical_ratio_avg')
    op.drop_column('fitmetrics', 'step_length_avg')
    op.drop_column('fitmetrics', 'stance_time_percent_avg')
