"""Add extraction runs

Revision ID: c8a2d3e4f5b6
Revises: b4f65951ccc4
Create Date: 2026-01-29 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8a2d3e4f5b6"
down_revision: Union[str, None] = "b4f65951ccc4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create extraction_runs table
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("current_page", sa.Integer(), nullable=False),
        sa.Column("requirements_found", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_page", sa.Integer(), nullable=True),
        sa.Column("ai_provider", sa.String(length=30), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add current_extraction_id to documents
    op.add_column("documents", sa.Column("current_extraction_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_documents_current_extraction_id",
        "documents",
        "extraction_runs",
        ["current_extraction_id"],
        ["id"],
    )

    # Add extraction_run_id to extracted_requirements
    op.add_column(
        "extracted_requirements", sa.Column("extraction_run_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_extracted_requirements_extraction_run_id",
        "extracted_requirements",
        "extraction_runs",
        ["extraction_run_id"],
        ["id"],
    )


def downgrade() -> None:
    # Drop extraction_run_id from extracted_requirements
    op.drop_constraint(
        "fk_extracted_requirements_extraction_run_id", "extracted_requirements", type_="foreignkey"
    )
    op.drop_column("extracted_requirements", "extraction_run_id")

    # Drop current_extraction_id from documents
    op.drop_constraint("fk_documents_current_extraction_id", "documents", type_="foreignkey")
    op.drop_column("documents", "current_extraction_id")

    # Drop extraction_runs table
    op.drop_table("extraction_runs")
