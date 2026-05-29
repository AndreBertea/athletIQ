"""add_v3_residual_model

Modele residuel V3 entraine automatiquement depuis le top 25% des candidats
de reference Race Predictor.

Revision ID: y8z9a0b1c2d3
Revises: x7y8z9a0b1c2
Create Date: 2026-05-28 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "y8z9a0b1c2d3"
down_revision: Union[str, None] = "x7y8z9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "racepredictorv3residualmodel"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE in inspector.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False, server_default="v3_residual_v1"),
        sa.Column("status", sa.String(), nullable=False, server_default="insufficient_data"),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("history_start_date", sa.DateTime(), nullable=True),
        sa.Column("history_end_date", sa.DateTime(), nullable=True),
        sa.Column("trained_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_racepredictorv3residualmodel_user_id"),
    )
    op.create_index("ix_racepredictorv3residualmodel_user_id", TABLE, ["user_id"])
    op.create_index("ix_racepredictorv3residualmodel_model_version", TABLE, ["model_version"])
    op.create_index("ix_racepredictorv3residualmodel_status", TABLE, ["status"])
    op.create_index("ix_racepredictorv3residualmodel_trained_at", TABLE, ["trained_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    op.drop_index("ix_racepredictorv3residualmodel_trained_at", table_name=TABLE)
    op.drop_index("ix_racepredictorv3residualmodel_status", table_name=TABLE)
    op.drop_index("ix_racepredictorv3residualmodel_model_version", table_name=TABLE)
    op.drop_index("ix_racepredictorv3residualmodel_user_id", table_name=TABLE)
    op.drop_table(TABLE)
