"""scope_strava_unique_to_user

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-05-24 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "m7n8o9p0q1r2"
down_revision = "l6m7n8o9p0q1"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _unique_constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint["name"] == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def upgrade() -> None:
    if _index_exists("activity", "ix_activity_strava_id"):
        op.drop_index("ix_activity_strava_id", table_name="activity")

    if not _unique_constraint_exists("activity", "uq_activity_user_strava_id"):
        with op.batch_alter_table("activity") as batch_op:
            batch_op.create_unique_constraint(
                "uq_activity_user_strava_id",
                ["user_id", "strava_id"],
            )

    if not _index_exists("activity", "ix_activity_strava_id"):
        op.create_index("ix_activity_strava_id", "activity", ["strava_id"], unique=False)


def downgrade() -> None:
    if _index_exists("activity", "ix_activity_strava_id"):
        op.drop_index("ix_activity_strava_id", table_name="activity")

    if _unique_constraint_exists("activity", "uq_activity_user_strava_id"):
        with op.batch_alter_table("activity") as batch_op:
            batch_op.drop_constraint("uq_activity_user_strava_id", type_="unique")

    if not _index_exists("activity", "ix_activity_strava_id"):
        op.create_index("ix_activity_strava_id", "activity", ["strava_id"], unique=True)
