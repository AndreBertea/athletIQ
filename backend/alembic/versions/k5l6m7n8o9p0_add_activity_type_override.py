"""add_activity_type_override

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-05-22 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k5l6m7n8o9p0'
down_revision = 'j4k5l6m7n8o9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ajouter la colonne activity_type_override
    op.add_column('activity', sa.Column('activity_type_override', sa.String(), nullable=True))


def downgrade() -> None:
    # Supprimer la colonne
    op.drop_column('activity', 'activity_type_override')
