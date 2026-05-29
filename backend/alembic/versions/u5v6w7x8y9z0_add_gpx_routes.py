"""add_gpx_routes_and_attachments

Catalogue de traces GPX pre-enregistrees + attachments (PDF, image...).

- `gpxroute`     : binaire GPX + metadata (distance, D+). Visibilite via
  `is_public` (catalogue global) ou `user_id` (import perso).
- `gpxattachment`: fichier annexe (PDF "trace A4" du Swiss Canyon par ex).

Revision ID: u5v6w7x8y9z0
Revises: v231_engine_version
Create Date: 2026-05-28 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "u5v6w7x8y9z0"
down_revision: Union[str, None] = "s3t4u5v6w7x8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "gpxroute" not in existing_tables:
        op.create_table(
            "gpxroute",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("gpx_data", sa.LargeBinary(), nullable=False),
            sa.Column("distance_km", sa.Float(), nullable=True),
            sa.Column("elevation_gain_m", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_gpxroute_user_id", "gpxroute", ["user_id"])
        op.create_index("ix_gpxroute_is_public", "gpxroute", ["is_public"])
        op.create_index("ix_gpxroute_name", "gpxroute", ["name"])

    if "gpxattachment" not in existing_tables:
        op.create_table(
            "gpxattachment",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "route_id",
                sa.Uuid(),
                sa.ForeignKey("gpxroute.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("mime_type", sa.String(), nullable=False, server_default="application/octet-stream"),
            sa.Column("kind", sa.String(), nullable=False, server_default="other"),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_gpxattachment_route_id", "gpxattachment", ["route_id"])
        op.create_index("ix_gpxattachment_name", "gpxattachment", ["name"])
        op.create_index("ix_gpxattachment_kind", "gpxattachment", ["kind"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "gpxattachment" in existing_tables:
        op.drop_index("ix_gpxattachment_kind", table_name="gpxattachment")
        op.drop_index("ix_gpxattachment_name", table_name="gpxattachment")
        op.drop_index("ix_gpxattachment_route_id", table_name="gpxattachment")
        op.drop_table("gpxattachment")

    if "gpxroute" in existing_tables:
        op.drop_index("ix_gpxroute_name", table_name="gpxroute")
        op.drop_index("ix_gpxroute_is_public", table_name="gpxroute")
        op.drop_index("ix_gpxroute_user_id", table_name="gpxroute")
        op.drop_table("gpxroute")
