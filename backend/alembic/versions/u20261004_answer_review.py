"""Add reversible answer review coordination without altering existing answers."""

from alembic import op
import sqlalchemy as sa

revision = "u20261004"
down_revision = "t20261002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "preparation_cases",
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_preparation_cases_reviewer_id", "preparation_cases", ["reviewer_id"])
    op.add_column(
        "preparation_responses",
        sa.Column("review_status", sa.String(30), nullable=False, server_default="pending_review"),
    )
    op.add_column(
        "preparation_responses",
        sa.Column("last_saved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "preparation_responses",
        sa.Column("last_saved_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "preparation_review_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "response_id",
            sa.Uuid(),
            sa.ForeignKey("preparation_responses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("returned_revision", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "ix_preparation_review_feedback_response_id", "preparation_review_feedback", ["response_id"]
    )


def downgrade():
    # Roll back application code with the additive schema left in place. Retain feedback/audit data.
    raise RuntimeError(
        "Retain the additive review schema; roll back application code without downgrading the database"
    )
