"""add_v22_athletic_profile_and_reference_test

Tables de la couche donnees du Race Predictor V2.2 :
- `athleticprofile` : profil athlete facultatif (un par utilisateur)
- `referencetest`   : tests de reference saisis par l'athlete

Specification : `docs/RACE_PREDICTOR_V2_2_PLAN.md`, sections AthleticProfile/
ReferenceTest. Les enums sont stockes en colonnes `String` (pattern deja
utilise par `RaceValidationReference.category` / `ActivityType` override)
afin de rester portable Postgres/SQLite sans dependre d'un type ENUM serveur.

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-05-25 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "o9p0q1r2s3t4"
down_revision: Union[str, None] = "n8o9p0q1r2s3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if "athleticprofile" not in inspector.get_table_names():
        op.create_table(
            "athleticprofile",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("sex", sa.String(), nullable=True),
            sa.Column("birth_date", sa.Date(), nullable=True),
            sa.Column("height_cm", sa.Float(), nullable=True),
            sa.Column("weight_kg", sa.Float(), nullable=True),
            sa.Column("activity_level", sa.String(), nullable=True),
            sa.Column("experience_level", sa.String(), nullable=True),
            sa.Column("practice_dominant", sa.String(), nullable=True),
            sa.Column("weekly_volume_band", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_athleticprofile_user_id"),
        )
        op.create_index(
            "ix_athleticprofile_user_id",
            "athleticprofile",
            ["user_id"],
        )

    if "referencetest" not in inspector.get_table_names():
        op.create_table(
            "referencetest",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("test_type", sa.String(), nullable=False),
            sa.Column("performed_at", sa.DateTime(), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=False),
            sa.Column("distance_m", sa.Float(), nullable=True),
            sa.Column("elevation_gain_m", sa.Float(), nullable=True),
            sa.Column("temperature_c", sa.Float(), nullable=True),
            sa.Column("surface", sa.String(), nullable=True),
            sa.Column("conditions_notes", sa.Text(), nullable=True),
            sa.Column("quality_status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_referencetest_user_id",
            "referencetest",
            ["user_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if "referencetest" in inspector.get_table_names():
        op.drop_index("ix_referencetest_user_id", table_name="referencetest")
        op.drop_table("referencetest")

    if "athleticprofile" in inspector.get_table_names():
        op.drop_index("ix_athleticprofile_user_id", table_name="athleticprofile")
        op.drop_table("athleticprofile")
