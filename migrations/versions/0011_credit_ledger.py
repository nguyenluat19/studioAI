"""Add credit_ledger audit log for spend/topup/refund/adjustment.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("balance_after", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("ref_type", sa.String(32), nullable=False, server_default=""),
        sa.Column("ref_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])
    op.create_index("ix_credit_ledger_kind", "credit_ledger", ["kind"])
    op.create_index("ix_credit_ledger_created_at", "credit_ledger", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_created_at", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_kind", table_name="credit_ledger")
    op.drop_index("ix_credit_ledger_user_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
