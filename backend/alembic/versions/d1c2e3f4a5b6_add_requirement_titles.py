"""Add requirement titles

Revision ID: d1c2e3f4a5b6
Revises: c8a2d3e4f5b6
Create Date: 2026-02-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1c2e3f4a5b6"
down_revision: Union[str, None] = "c8a2d3e4f5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "extracted_requirements",
        sa.Column("title", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "requirements",
        sa.Column("title", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("requirements", "title")
    op.drop_column("extracted_requirements", "title")
