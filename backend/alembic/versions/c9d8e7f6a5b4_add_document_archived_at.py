"""add document archived at

Revision ID: c9d8e7f6a5b4
Revises: f2a9b6d4c1e3
Create Date: 2026-02-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9d8e7f6a5b4"
down_revision = "f2a9b6d4c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_documents_archived_at", "documents", ["archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_archived_at", table_name="documents")
    op.drop_column("documents", "archived_at")
