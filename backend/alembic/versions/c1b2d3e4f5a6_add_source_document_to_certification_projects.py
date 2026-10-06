"""add source_document_id to certification_projects

Revision ID: c1b2d3e4f5a6
Revises: 8f4d3c2b1a0e
Create Date: 2026-02-12 12:40:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1b2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "8f4d3c2b1a0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "certification_projects",
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_certification_projects_source_document_id_documents",
        "certification_projects",
        "documents",
        ["source_document_id"],
        ["id"],
    )
    op.create_index(
        "ix_certification_projects_source_document_id",
        "certification_projects",
        ["source_document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_certification_projects_source_document_id",
        table_name="certification_projects",
    )
    op.drop_constraint(
        "fk_certification_projects_source_document_id_documents",
        "certification_projects",
        type_="foreignkey",
    )
    op.drop_column("certification_projects", "source_document_id")
