"""Persist extraction dispatch intent and worker ownership."""

from alembic import op
import sqlalchemy as sa

revision = "a20260924"
down_revision = "a20260922"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("extraction_runs", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("extraction_runs", sa.Column("dispatch_after", sa.DateTime(timezone=True), nullable=True))
    op.add_column("extraction_runs", sa.Column("owner_token", sa.String(36), nullable=True))
    op.add_column("extraction_runs", sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_extraction_runs_dispatch", "extraction_runs", ["status", "dispatch_after"])


def downgrade():
    op.drop_index("ix_extraction_runs_dispatch", "extraction_runs")
    op.drop_column("extraction_runs", "last_progress_at")
    op.drop_column("extraction_runs", "owner_token")
    op.drop_column("extraction_runs", "dispatch_after")
    op.drop_column("extraction_runs", "attempt_count")
