"""add_sleep_detail_columns

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-02-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i3c4d5e6f7g8'
down_revision: Union[str, None] = 'h2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('garmindaily', sa.Column('deep_sleep_seconds', sa.Integer(), nullable=True))
    op.add_column('garmindaily', sa.Column('light_sleep_seconds', sa.Integer(), nullable=True))
    op.add_column('garmindaily', sa.Column('rem_sleep_seconds', sa.Integer(), nullable=True))
    op.add_column('garmindaily', sa.Column('awake_sleep_seconds', sa.Integer(), nullable=True))
    op.add_column('garmindaily', sa.Column('sleep_start_time', sa.String(), nullable=True))
    op.add_column('garmindaily', sa.Column('sleep_end_time', sa.String(), nullable=True))
    op.add_column('garmindaily', sa.Column('average_respiration', sa.Float(), nullable=True))
    op.add_column('garmindaily', sa.Column('avg_sleep_stress', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('garmindaily', 'avg_sleep_stress')
    op.drop_column('garmindaily', 'average_respiration')
    op.drop_column('garmindaily', 'sleep_end_time')
    op.drop_column('garmindaily', 'sleep_start_time')
    op.drop_column('garmindaily', 'awake_sleep_seconds')
    op.drop_column('garmindaily', 'rem_sleep_seconds')
    op.drop_column('garmindaily', 'light_sleep_seconds')
    op.drop_column('garmindaily', 'deep_sleep_seconds')
