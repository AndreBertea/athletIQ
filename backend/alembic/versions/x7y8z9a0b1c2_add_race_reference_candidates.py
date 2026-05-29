"""add_race_reference_candidates

Candidats automatiques pour qualifier les activites de reference du Race
Predictor. Ces lignes ne remplacent pas les validations humaines :
elles alimentent l'Analytics avec des propositions acceptables/rejetables.

Revision ID: x7y8z9a0b1c2
Revises: w6x7y8z9a0b1
Create Date: 2026-05-28 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "x7y8z9a0b1c2"
down_revision: Union[str, None] = "w6x7y8z9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "racereferencecandidate"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE in inspector.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("activity_id", sa.Uuid(), sa.ForeignKey("activity.id"), nullable=False),
        sa.Column("suggested_category", sa.String(), nullable=False, server_default="training_control"),
        sa.Column("confidence", sa.String(), nullable=False, server_default="medium"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reasons", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("features", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("potential_gain_min_low", sa.Float(), nullable=True),
        sa.Column("potential_gain_min_high", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", name="uq_racereferencecandidate_activity_id"),
    )
    op.create_index("ix_racereferencecandidate_user_id", TABLE, ["user_id"])
    op.create_index("ix_racereferencecandidate_activity_id", TABLE, ["activity_id"])
    op.create_index("ix_racereferencecandidate_suggested_category", TABLE, ["suggested_category"])
    op.create_index("ix_racereferencecandidate_confidence", TABLE, ["confidence"])
    op.create_index("ix_racereferencecandidate_score", TABLE, ["score"])
    op.create_index("ix_racereferencecandidate_status", TABLE, ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    op.drop_index("ix_racereferencecandidate_status", table_name=TABLE)
    op.drop_index("ix_racereferencecandidate_score", table_name=TABLE)
    op.drop_index("ix_racereferencecandidate_confidence", table_name=TABLE)
    op.drop_index("ix_racereferencecandidate_suggested_category", table_name=TABLE)
    op.drop_index("ix_racereferencecandidate_activity_id", table_name=TABLE)
    op.drop_index("ix_racereferencecandidate_user_id", table_name=TABLE)
    op.drop_table(TABLE)
