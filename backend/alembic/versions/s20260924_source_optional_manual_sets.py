"""Allow requirement sets without an uploaded source PDF.

Revision ID: s20260924
Revises: a20260924
"""

from alembic import op
import sqlalchemy as sa


revision = "s20260924"
down_revision = "a20260924"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column("filename", existing_type=sa.String(length=500), nullable=True)
        batch_op.alter_column("file_path", existing_type=sa.String(length=500), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    source_free_count = connection.scalar(
        sa.text("SELECT count(*) FROM documents WHERE filename IS NULL OR file_path IS NULL")
    )
    if source_free_count:
        raise RuntimeError(
            "Cannot restore required PDF columns while source-free requirement sets exist. "
            "Move or remove those rows explicitly before downgrading."
        )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column("filename", existing_type=sa.String(length=500), nullable=False)
        batch_op.alter_column("file_path", existing_type=sa.String(length=500), nullable=False)
