"""add_gpx_route_user_settings

Reglages personnels Race Predictor par couple utilisateur + trace GPX.

Revision ID: w6x7y8z9a0b1
Revises: u5v6w7x8y9z0
Create Date: 2026-05-28 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "w6x7y8z9a0b1"
down_revision: Union[str, None] = "u5v6w7x8y9z0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "gpxrouteusersettings"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE in inspector.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("route_id", sa.Uuid(), sa.ForeignKey("gpxroute.id"), nullable=False),
        sa.Column("preferred_engine", sa.String(), nullable=False, server_default="v3"),
        sa.Column("analysis_mode", sa.String(), nullable=False, server_default="auto"),
        sa.Column("effort_mode", sa.String(), nullable=False, server_default="steady"),
        sa.Column("ravito_mode", sa.String(), nullable=False, server_default="auto"),
        sa.Column("weather_mode", sa.String(), nullable=False, server_default="auto"),
        sa.Column("manual_temperature_c", sa.Float(), nullable=True),
        sa.Column("history_start_date", sa.String(), nullable=True),
        sa.Column("race_datetime", sa.String(), nullable=True),
        sa.Column("custom_ravitos", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "route_id", name="uq_gpxrouteusersettings_user_route"),
    )
    op.create_index("ix_gpxrouteusersettings_user_id", TABLE, ["user_id"])
    op.create_index("ix_gpxrouteusersettings_route_id", TABLE, ["route_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    op.drop_index("ix_gpxrouteusersettings_route_id", table_name=TABLE)
    op.drop_index("ix_gpxrouteusersettings_user_id", table_name=TABLE)
    op.drop_table(TABLE)
