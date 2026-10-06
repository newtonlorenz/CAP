"""Keep readiness assessment status local to each review.

Revision ID: a20260920
Revises: f0a1b2c3d4e5
"""

from alembic import op
import sqlalchemy as sa

revision = "a20260920"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("review_items", sa.Column("assessment_status", sa.String(30), nullable=True))
    op.add_column("review_items", sa.Column("assessment_rationale", sa.Text(), nullable=True))
    op.execute(
        """UPDATE review_items SET assessment_status = COALESCE((SELECT status FROM requirement_statuses WHERE requirement_id=review_items.requirement_id ORDER BY changed_at DESC,id DESC LIMIT 1),'not_started'), assessment_rationale = (SELECT comment FROM requirement_statuses WHERE requirement_id=review_items.requirement_id ORDER BY changed_at DESC,id DESC LIMIT 1)"""
    )


def downgrade():
    op.drop_column("review_items", "assessment_rationale")
    op.drop_column("review_items", "assessment_status")
