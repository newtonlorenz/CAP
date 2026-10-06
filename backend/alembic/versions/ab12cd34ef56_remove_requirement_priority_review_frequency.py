"""remove requirement priority and review frequency

Revision ID: ab12cd34ef56
Revises: f2a9b6d4c1e3
Create Date: 2026-02-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ab12cd34ef56"
down_revision = "f2a9b6d4c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("requirements", "priority")
    op.drop_column("requirements", "review_frequency")


def downgrade() -> None:
    op.add_column(
        "requirements", sa.Column("review_frequency", sa.String(length=50), nullable=True)
    )
    op.add_column("requirements", sa.Column("priority", sa.String(length=20), nullable=True))
