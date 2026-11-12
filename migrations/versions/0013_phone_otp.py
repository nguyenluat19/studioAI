"""Add phone + phone_verified to users and the phone_otp table.

Existing accounts get phone_verified = 1 (server default) so nobody is locked out.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("phone_verified", sa.Boolean(), nullable=False,
                                     server_default="1"))
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_table(
        "phone_otps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_phone_otps_phone", "phone_otps", ["phone"])
    op.create_index("ix_phone_otps_user_id", "phone_otps", ["user_id"])
    op.create_index("ix_phone_otps_expires_at", "phone_otps", ["expires_at"])
    op.create_index("ix_phone_otps_created_at", "phone_otps", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_phone_otps_created_at", table_name="phone_otps")
    op.drop_index("ix_phone_otps_expires_at", table_name="phone_otps")
    op.drop_index("ix_phone_otps_user_id", table_name="phone_otps")
    op.drop_index("ix_phone_otps_phone", table_name="phone_otps")
    op.drop_table("phone_otps")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
