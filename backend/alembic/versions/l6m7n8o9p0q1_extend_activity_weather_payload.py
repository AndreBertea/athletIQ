"""extend_activity_weather_payload

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-05-24 02:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "l6m7n8o9p0q1"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activityweather", sa.Column("sampled_at", sa.DateTime(), nullable=True))
    op.add_column("activityweather", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("activityweather", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("activityweather", sa.Column("elevation_m", sa.Float(), nullable=True))
    op.add_column("activityweather", sa.Column("source_endpoint", sa.String(length=64), nullable=True))
    op.add_column("activityweather", sa.Column("source_url", sa.String(length=255), nullable=True))
    op.add_column("activityweather", sa.Column("request_params", sa.JSON(), nullable=True))
    op.add_column("activityweather", sa.Column("hourly_units", sa.JSON(), nullable=True))
    op.add_column("activityweather", sa.Column("hourly_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("activityweather", "hourly_snapshot")
    op.drop_column("activityweather", "hourly_units")
    op.drop_column("activityweather", "request_params")
    op.drop_column("activityweather", "source_url")
    op.drop_column("activityweather", "source_endpoint")
    op.drop_column("activityweather", "elevation_m")
    op.drop_column("activityweather", "longitude")
    op.drop_column("activityweather", "latitude")
    op.drop_column("activityweather", "sampled_at")
