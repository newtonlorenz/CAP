"""make requirement document nullable

Revision ID: a1c4b2d9e0f7
Revises: f2a9b6d4c1e3
Create Date: 2026-02-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1c4b2d9e0f7"
down_revision = "f2a9b6d4c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_constraint("requirements_document_id_fkey", type_="foreignkey")
        batch_op.alter_column(
            "document_id",
            existing_type=sa.UUID(),
            nullable=True,
        )
        batch_op.create_foreign_key(
            "requirements_document_id_fkey",
            "documents",
            ["document_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_constraint("requirements_document_id_fkey", type_="foreignkey")
        batch_op.alter_column(
            "document_id",
            existing_type=sa.UUID(),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "requirements_document_id_fkey",
            "documents",
            ["document_id"],
            ["id"],
        )
