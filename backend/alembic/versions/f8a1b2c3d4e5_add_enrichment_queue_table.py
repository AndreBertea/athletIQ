"""add enrichment_queue table

Revision ID: f8a1b2c3d4e5
Revises: e4dce9164f1b
Create Date: 2026-02-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a1b2c3d4e5'
down_revision: Union[str, None] = 'e4dce9164f1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('enrichment_queue',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('activity_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', name='enrichmentstatus'), nullable=False, server_default='PENDING'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['activity_id'], ['activity.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_enrichment_queue_activity_id', 'enrichment_queue', ['activity_id'])
    op.create_index('ix_enrichment_queue_user_id', 'enrichment_queue', ['user_id'])
    op.create_index('ix_enrichment_queue_priority', 'enrichment_queue', ['priority'])
    op.create_index('ix_enrichment_queue_status', 'enrichment_queue', ['status'])


def downgrade() -> None:
    op.drop_index('ix_enrichment_queue_status', table_name='enrichment_queue')
    op.drop_index('ix_enrichment_queue_priority', table_name='enrichment_queue')
    op.drop_index('ix_enrichment_queue_user_id', table_name='enrichment_queue')
    op.drop_index('ix_enrichment_queue_activity_id', table_name='enrichment_queue')
    op.drop_table('enrichment_queue')
