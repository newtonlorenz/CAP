"""Stable account identities and explicit session revocation.

Revision ID: a20260921
Revises: a20260920
"""

from alembic import op
import sqlalchemy as sa

revision = "a20260921"
down_revision = "a20260920"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_table(
        "revoked_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_sessions_expires_at", "revoked_sessions", ["expires_at"])

    op.create_table(
        "login_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window", sa.Integer(), nullable=False),
    )
    op.create_index("ix_login_throttles_window", "login_throttles", ["window"])


def downgrade():
    op.drop_table("login_throttles")
    op.drop_table("revoked_sessions")
    op.drop_column("users", "auth_version")
