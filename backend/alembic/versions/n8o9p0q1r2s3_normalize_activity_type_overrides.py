"""normalize_activity_type_overrides_and_add_validation_references

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-05-25 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "n8o9p0q1r2s3"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "racevalidationreference" not in inspector.get_table_names():
        op.create_table(
            "racevalidationreference",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("activity_id", sa.Uuid(), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("potential_gain_min_low", sa.Float(), nullable=True),
            sa.Column("potential_gain_min_high", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.ForeignKeyConstraint(["activity_id"], ["activity.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_racevalidationreference_user_id",
            "racevalidationreference",
            ["user_id"],
        )
        op.create_index(
            "ix_racevalidationreference_category",
            "racevalidationreference",
            ["category"],
        )
        op.create_index(
            "ix_racevalidationreference_activity_id",
            "racevalidationreference",
            ["activity_id"],
            unique=True,
        )

    value_to_enum_name = {
        "Run": "RUN",
        "TrailRun": "TRAIL_RUN",
        "Ride": "RIDE",
        "Swim": "SWIM",
        "Walk": "WALK",
        "RacketSport": "RACKET_SPORT",
        "Tennis": "TENNIS",
        "Badminton": "BADMINTON",
        "Squash": "SQUASH",
        "Padel": "PADEL",
        "WeightTraining": "WEIGHT_TRAINING",
        "RockClimbing": "ROCK_CLIMBING",
        "Hiking": "HIKING",
        "Yoga": "YOGA",
        "Pilates": "PILATES",
        "Crossfit": "CROSSFIT",
        "Gym": "GYM",
        "VirtualRun": "VIRTUAL_RUN",
        "VirtualRide": "VIRTUAL_RIDE",
        "Other": "OTHER",
    }
    for value, enum_name in value_to_enum_name.items():
        op.execute(
            f"UPDATE activity SET activity_type_override = '{enum_name}' "
            f"WHERE activity_type_override = '{value}'"
        )


def downgrade() -> None:
    # Expanded override types cannot be represented by the previous Python enum.
    inspector = sa.inspect(op.get_bind())
    if "racevalidationreference" in inspector.get_table_names():
        op.drop_index("ix_racevalidationreference_activity_id", table_name="racevalidationreference")
        op.drop_index("ix_racevalidationreference_category", table_name="racevalidationreference")
        op.drop_index("ix_racevalidationreference_user_id", table_name="racevalidationreference")
        op.drop_table("racevalidationreference")
