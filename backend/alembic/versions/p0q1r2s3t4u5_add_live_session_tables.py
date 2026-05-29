"""add_live_session_tables

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-05-25 15:00:00.000000

Tables pour le suivi live d'activites :
- livesession : une session live (source LiveTrack ou Connect IQ a venir)
- livetrackpoint : points de trace recus en temps reel
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "p0q1r2s3t4u5"
down_revision = "o9p0q1r2s3t4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "livesession",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        # LiveTrack-specific
        sa.Column("garmin_session_id", sa.String(length=64), nullable=True),
        sa.Column("garmin_token", sa.String(length=128), nullable=True),
        # Connect IQ-specific (phase 2)
        sa.Column("device_token", sa.String(length=128), nullable=True),
        sa.Column("activity_uuid", sa.String(length=64), nullable=True),
        # Timestamps
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("last_point_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_livesession_user_id", "livesession", ["user_id"])
    op.create_index("ix_livesession_status", "livesession", ["status"])
    op.create_index("ix_livesession_source", "livesession", ["source"])

    op.create_table(
        "livetrackpoint",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("ts", sa.BigInteger(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("hr", sa.Integer(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("cadence", sa.Integer(), nullable=True),
        sa.Column("power", sa.Integer(), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("session_id", "ts"),
        sa.ForeignKeyConstraint(["session_id"], ["livesession.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_livetrackpoint_session_ts", "livetrackpoint", ["session_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_livetrackpoint_session_ts", table_name="livetrackpoint")
    op.drop_table("livetrackpoint")
    op.drop_index("ix_livesession_source", table_name="livesession")
    op.drop_index("ix_livesession_status", table_name="livesession")
    op.drop_index("ix_livesession_user_id", table_name="livesession")
    op.drop_table("livesession")
