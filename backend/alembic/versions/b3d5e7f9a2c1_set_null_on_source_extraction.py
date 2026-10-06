"""set null on source_extraction_id

Revision ID: b3d5e7f9a2c1
Revises: a1c4b2d9e0f7
Create Date: 2026-02-03 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b3d5e7f9a2c1"
down_revision = "a1c4b2d9e0f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_constraint("requirements_source_extraction_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "requirements_source_extraction_id_fkey",
            "extracted_requirements",
            ["source_extraction_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_constraint("requirements_source_extraction_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "requirements_source_extraction_id_fkey",
            "extracted_requirements",
            ["source_extraction_id"],
            ["id"],
        )
