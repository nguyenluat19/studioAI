"""Add supported_durations (JSON list of seconds) to app_models.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_models",
                  sa.Column("supported_durations", sa.JSON(), nullable=False,
                            server_default=sa.text("'[]'")))


def downgrade() -> None:
    op.drop_column("app_models", "supported_durations")
