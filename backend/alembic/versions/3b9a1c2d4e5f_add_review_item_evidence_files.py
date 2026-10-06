"""add review item evidence files

Revision ID: 3b9a1c2d4e5f
Revises: 7c3a9d4e2f1b
Create Date: 2026-02-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3b9a1c2d4e5f"
down_revision = "7c3a9d4e2f1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_item_evidence_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_item_evidence_files_item_id_uploaded_at",
        "review_item_evidence_files",
        ["review_item_id", "uploaded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_review_item_evidence_files_item_id_uploaded_at",
        table_name="review_item_evidence_files",
    )
    op.drop_table("review_item_evidence_files")
