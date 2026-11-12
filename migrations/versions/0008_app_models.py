"""Admin-managed models (app_models): add models from the admin UI without code changes.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_models",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("api_key", sa.String(512), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_clip_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_models")
