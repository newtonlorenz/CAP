"""Track evidence edits after the latest review decision.

Revision ID: j20260929
Revises: i20260929
"""

from alembic import op
import sqlalchemy as sa

revision = "j20260929"
down_revision = "i20260929"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("review_items", sa.Column("evidence_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("review_items", "evidence_changed_at")
