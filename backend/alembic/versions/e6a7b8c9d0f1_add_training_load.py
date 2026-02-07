"""add_training_load

Revision ID: e6a7b8c9d0f1
Revises: d5f6a7b8c9e0
Create Date: 2026-02-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e6a7b8c9d0f1'
down_revision: Union[str, None] = 'd5f6a7b8c9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('trainingload',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('ctl_42d', sa.Float(), nullable=True),
        sa.Column('atl_7d', sa.Float(), nullable=True),
        sa.Column('tsb', sa.Float(), nullable=True),
        sa.Column('rhr_delta_7d', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trainingload_user_id'), 'trainingload', ['user_id'])
    op.create_index(op.f('ix_trainingload_date'), 'trainingload', ['date'])
    op.create_unique_constraint('uq_training_load_user_date', 'trainingload', ['user_id', 'date'])


def downgrade() -> None:
    op.drop_constraint('uq_training_load_user_date', 'trainingload', type_='unique')
    op.drop_index(op.f('ix_trainingload_date'), table_name='trainingload')
    op.drop_index(op.f('ix_trainingload_user_id'), table_name='trainingload')
    op.drop_table('trainingload')
