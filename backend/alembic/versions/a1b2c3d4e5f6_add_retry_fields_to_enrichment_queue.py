"""add retry fields to enrichment_queue

Revision ID: a1b2c3d4e5f6
Revises: f8a1b2c3d4e5
Create Date: 2026-02-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f8a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('enrichment_queue', sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('enrichment_queue', sa.Column('next_retry_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('enrichment_queue', 'next_retry_at')
    op.drop_column('enrichment_queue', 'max_attempts')
