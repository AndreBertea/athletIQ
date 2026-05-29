"""add_edwards_trimp

Revision ID: j4k5l6m7n8o9
Revises: i3c4d5e6f7g8
Create Date: 2026-02-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j4k5l6m7n8o9'
down_revision: Union[str, None] = 'i3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trainingload', sa.Column('edwards_trimp_daily', sa.Float(), nullable=True))
    op.add_column('trainingload', sa.Column('ctl_42d_edwards', sa.Float(), nullable=True))
    op.add_column('trainingload', sa.Column('atl_7d_edwards', sa.Float(), nullable=True))
    op.add_column('trainingload', sa.Column('tsb_edwards', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('trainingload', 'tsb_edwards')
    op.drop_column('trainingload', 'atl_7d_edwards')
    op.drop_column('trainingload', 'ctl_42d_edwards')
    op.drop_column('trainingload', 'edwards_trimp_daily')
