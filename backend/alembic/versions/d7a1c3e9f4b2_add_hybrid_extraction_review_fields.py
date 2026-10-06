"""add hybrid extraction pipeline fields and feedback table

Revision ID: d7a1c3e9f4b2
Revises: c4f1d8a7b9e2
Create Date: 2026-02-19 12:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7a1c3e9f4b2"
down_revision: Union[str, Sequence[str], None] = "c4f1d8a7b9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "extraction_runs",
        sa.Column(
            "pipeline_version", sa.String(length=40), nullable=False, server_default="legacy_v1"
        ),
    )
    op.add_column(
        "extraction_runs",
        sa.Column("ocr_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "extraction_runs",
        sa.Column("ocr_pages", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "extraction_runs",
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "extraction_runs",
        sa.Column("family_fingerprint", sa.String(length=160), nullable=True),
    )

    op.add_column(
        "extracted_requirements",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "extracted_requirements",
        sa.Column("review_reason", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "extracted_requirements",
        sa.Column("source_excerpt", sa.Text(), nullable=True),
    )
    op.add_column(
        "extracted_requirements",
        sa.Column(
            "parser_strategy", sa.String(length=50), nullable=False, server_default="rule_based"
        ),
    )
    op.create_index(
        "ix_extracted_requirements_needs_review",
        "extracted_requirements",
        ["needs_review"],
        unique=False,
    )

    op.create_table(
        "extraction_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("extracted_requirement_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("corrected_reference_id", sa.String(length=100), nullable=True),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["extracted_requirement_id"], ["extracted_requirements.id"]),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_extraction_feedback_extraction_run_id",
        "extraction_feedback",
        ["extraction_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_feedback_extracted_requirement_id",
        "extraction_feedback",
        ["extracted_requirement_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_extraction_feedback_extracted_requirement_id", table_name="extraction_feedback"
    )
    op.drop_index("ix_extraction_feedback_extraction_run_id", table_name="extraction_feedback")
    op.drop_table("extraction_feedback")

    op.drop_index("ix_extracted_requirements_needs_review", table_name="extracted_requirements")
    op.drop_column("extracted_requirements", "parser_strategy")
    op.drop_column("extracted_requirements", "source_excerpt")
    op.drop_column("extracted_requirements", "review_reason")
    op.drop_column("extracted_requirements", "needs_review")

    op.drop_column("extraction_runs", "family_fingerprint")
    op.drop_column("extraction_runs", "warning_count")
    op.drop_column("extraction_runs", "ocr_pages")
    op.drop_column("extraction_runs", "ocr_applied")
    op.drop_column("extraction_runs", "pipeline_version")
