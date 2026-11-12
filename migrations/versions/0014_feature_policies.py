"""Add feature price/free-trial policies and per-user usage ledger."""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_jobs", sa.Column("usage_id", sa.Integer(), nullable=True))
    op.create_table(
        "feature_policies",
        sa.Column("feature_key", sa.String(64), primary_key=True),
        sa.Column("model_id", sa.String(64), primary_key=True, server_default=""),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("free_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "feature_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feature_key", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("charge", sa.Float(), nullable=False, server_default="0"),
        sa.Column("model_unit_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("service_unit_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="reserved"),
        sa.Column("ref_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_feature_usage_user_id", "feature_usage", ["user_id"])
    op.create_index("ix_feature_usage_feature_key", "feature_usage", ["feature_key"])
    op.create_index("ix_feature_usage_created_at", "feature_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_feature_usage_created_at", table_name="feature_usage")
    op.drop_index("ix_feature_usage_feature_key", table_name="feature_usage")
    op.drop_index("ix_feature_usage_user_id", table_name="feature_usage")
    op.drop_table("feature_usage")
    op.drop_table("feature_policies")
    op.drop_column("pipeline_jobs", "usage_id")
