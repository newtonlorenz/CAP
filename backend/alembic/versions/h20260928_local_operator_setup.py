"""Persist local installation operator designation.

Revision ID: h20260928
Revises: g20260926
"""

from alembic import op
import sqlalchemy as sa

revision = "h20260928"
down_revision = "g20260926"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("operator_trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("users", "operator_trusted")
