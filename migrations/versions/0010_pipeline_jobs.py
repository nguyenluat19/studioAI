"""Persistent snapshots of pipeline jobs (survive restarts).

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False, server_default=""),
        sa.Column("mode", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("step", sa.String(512), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("selections", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("duration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aspect_ratio", sa.String(8), nullable=False, server_default="9:16"),
        sa.Column("character_image_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("voice", sa.String(32), nullable=False, server_default="native"),
        sa.Column("use_tts", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("language", sa.String(8), nullable=False, server_default="vi"),
        sa.Column("outfit_image_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("hook_seconds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
    )
    op.create_index("ix_pipeline_jobs_user_id", "pipeline_jobs", ["user_id"])
    op.create_index("ix_pipeline_jobs_status", "pipeline_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_jobs_status", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_user_id", table_name="pipeline_jobs")
    op.drop_table("pipeline_jobs")
