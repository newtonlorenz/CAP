"""add review item evidence

Revision ID: f2a9b6d4c1e3
Revises: e4f7a9c2d8b1
Create Date: 2026-02-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a9b6d4c1e3"
down_revision = "e4f7a9c2d8b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_items", sa.Column("review_evidence", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_items", "review_evidence")
