"""add document metadata

Revision ID: e4f7a9c2d8b1
Revises: d1c2e3f4a5b6
Create Date: 2026-02-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4f7a9c2d8b1"
down_revision = "d1c2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("testing_frequency", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "testing_frequency")
    op.drop_column("documents", "name")
