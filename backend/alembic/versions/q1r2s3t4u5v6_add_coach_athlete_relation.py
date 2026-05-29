"""add_coach_athlete_relation

Revision ID: q1r2s3t4u5v6
Revises: v231_engine_version
Create Date: 2026-05-26 01:30:00.000000

Table coachathleterelation : modele coach <-> athlete avec invitations.
- coach_id : user qui invite (cote suivi)
- athlete_id : user qui est suivi (nullable si pas encore signup)
- invited_email : email de l'athlete invite (pour matcher au signup futur)
- status : pending / accepted / declined / revoked
"""
from alembic import op
import sqlalchemy as sa


revision = "q1r2s3t4u5v6"
down_revision = "v231_engine_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coachathleterelation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("coach_id", sa.UUID(), nullable=False),
        sa.Column("athlete_id", sa.UUID(), nullable=True),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["coach_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["athlete_id"], ["user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("coach_id", "invited_email", name="uq_coachathlete_coach_email"),
    )
    op.create_index("ix_coachathlete_coach_id", "coachathleterelation", ["coach_id"])
    op.create_index("ix_coachathlete_athlete_id", "coachathleterelation", ["athlete_id"])
    op.create_index("ix_coachathlete_invited_email", "coachathleterelation", ["invited_email"])
    op.create_index("ix_coachathlete_status", "coachathleterelation", ["status"])


def downgrade() -> None:
    op.drop_index("ix_coachathlete_status", table_name="coachathleterelation")
    op.drop_index("ix_coachathlete_invited_email", table_name="coachathleterelation")
    op.drop_index("ix_coachathlete_athlete_id", table_name="coachathleterelation")
    op.drop_index("ix_coachathlete_coach_id", table_name="coachathleterelation")
    op.drop_table("coachathleterelation")
