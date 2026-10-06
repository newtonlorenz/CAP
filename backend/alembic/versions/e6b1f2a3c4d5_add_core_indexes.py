"""Add core indexes

Revision ID: e6b1f2a3c4d5
Revises: d1c2e3f4a5b6
Create Date: 2026-02-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e6b1f2a3c4d5"
down_revision: Union[str, None] = "d1c2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_document_type", "documents", ["document_type"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    op.create_index("ix_extraction_runs_document_id", "extraction_runs", ["document_id"])
    op.create_index("ix_extraction_runs_status", "extraction_runs", ["status"])

    op.create_index(
        "ix_extracted_requirements_document_id",
        "extracted_requirements",
        ["document_id"],
    )
    op.create_index(
        "ix_extracted_requirements_extraction_run_id",
        "extracted_requirements",
        ["extraction_run_id"],
    )
    op.create_index(
        "ix_extracted_requirements_parent_id",
        "extracted_requirements",
        ["parent_id"],
    )
    op.create_index(
        "ix_extracted_requirements_reference_id",
        "extracted_requirements",
        ["reference_id"],
    )

    op.create_index("ix_requirements_document_id", "requirements", ["document_id"])
    op.create_index("ix_requirements_parent_id", "requirements", ["parent_id"])
    op.create_index("ix_requirements_reference_id", "requirements", ["reference_id"])
    op.create_index("ix_requirements_sort_order", "requirements", ["sort_order"])

    op.create_index(
        "ix_requirement_statuses_requirement_id",
        "requirement_statuses",
        ["requirement_id"],
    )
    op.create_index(
        "ix_requirement_statuses_changed_at",
        "requirement_statuses",
        ["changed_at"],
    )

    op.create_index("ix_evidence_notes_requirement_id", "evidence_notes", ["requirement_id"])
    op.create_index("ix_evidence_files_requirement_id", "evidence_files", ["requirement_id"])
    op.create_index("ix_evidence_links_requirement_id", "evidence_links", ["requirement_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_links_requirement_id", table_name="evidence_links")
    op.drop_index("ix_evidence_files_requirement_id", table_name="evidence_files")
    op.drop_index("ix_evidence_notes_requirement_id", table_name="evidence_notes")

    op.drop_index("ix_requirement_statuses_changed_at", table_name="requirement_statuses")
    op.drop_index("ix_requirement_statuses_requirement_id", table_name="requirement_statuses")

    op.drop_index("ix_requirements_sort_order", table_name="requirements")
    op.drop_index("ix_requirements_reference_id", table_name="requirements")
    op.drop_index("ix_requirements_parent_id", table_name="requirements")
    op.drop_index("ix_requirements_document_id", table_name="requirements")

    op.drop_index(
        "ix_extracted_requirements_reference_id",
        table_name="extracted_requirements",
    )
    op.drop_index(
        "ix_extracted_requirements_parent_id",
        table_name="extracted_requirements",
    )
    op.drop_index(
        "ix_extracted_requirements_extraction_run_id",
        table_name="extracted_requirements",
    )
    op.drop_index(
        "ix_extracted_requirements_document_id",
        table_name="extracted_requirements",
    )

    op.drop_index("ix_extraction_runs_status", table_name="extraction_runs")
    op.drop_index("ix_extraction_runs_document_id", table_name="extraction_runs")

    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
