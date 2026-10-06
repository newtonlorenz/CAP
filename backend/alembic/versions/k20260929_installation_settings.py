"""Persist installation email and AI settings with encrypted credentials.

Revision ID: k20260929
Revises: j20260929
"""

import sqlalchemy as sa

from alembic import op

revision = "k20260929"
down_revision = "j20260929"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "installation_settings",
        sa.Column("section", sa.String(20), primary_key=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("installation_settings")
