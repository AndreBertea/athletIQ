"""add_daily_checkin

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-05-26 02:30:00.000000

Table dailycheckin : saisie quotidienne du user (4 wellness + sRPE + tags).
Modele readiness Saw 2017 (gating J14, z-scores sur baseline 28j).
"""
from alembic import op
import sqlalchemy as sa


revision = "r2s3t4u5v6w7"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dailycheckin",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        # Wellness 1-5
        sa.Column("wellbeing", sa.SmallInteger(), nullable=False),
        sa.Column("sleep_quality", sa.SmallInteger(), nullable=False),
        sa.Column("legs", sa.SmallInteger(), nullable=False),
        sa.Column("motivation", sa.SmallInteger(), nullable=False),
        # sRPE veille (CR-10 Foster, 0-10, NULL si pas de seance)
        sa.Column("srpe_yesterday", sa.SmallInteger(), nullable=True),
        sa.Column("session_duration_min", sa.Integer(), nullable=True),
        # Tags contextuels (array JSON)
        sa.Column("context_tags", sa.JSON(), nullable=False, server_default="[]"),
        # V2 wearables
        sa.Column("hrv_ln_rmssd", sa.Numeric(5, 2), nullable=True),
        sa.Column("resting_hr_bpm", sa.SmallInteger(), nullable=True),
        sa.Column("sleep_duration_h", sa.Numeric(3, 1), nullable=True),
        # Meta
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("client_origin", sa.String(length=24), nullable=False, server_default="pwa"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "entry_date", name="uq_dailycheckin_user_date"),
        sa.CheckConstraint("wellbeing BETWEEN 1 AND 5", name="ck_dailycheckin_wellbeing"),
        sa.CheckConstraint("sleep_quality BETWEEN 1 AND 5", name="ck_dailycheckin_sleep"),
        sa.CheckConstraint("legs BETWEEN 1 AND 5", name="ck_dailycheckin_legs"),
        sa.CheckConstraint("motivation BETWEEN 1 AND 5", name="ck_dailycheckin_motivation"),
        sa.CheckConstraint(
            "srpe_yesterday IS NULL OR srpe_yesterday BETWEEN 0 AND 10",
            name="ck_dailycheckin_srpe",
        ),
    )
    op.create_index(
        "ix_dailycheckin_user_date",
        "dailycheckin",
        ["user_id", "entry_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dailycheckin_user_date", table_name="dailycheckin")
    op.drop_table("dailycheckin")
