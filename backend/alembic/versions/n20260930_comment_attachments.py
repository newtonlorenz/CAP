"""Associate stored review files with comments.

Revision ID: n20260930
Revises: m20260930
"""

import sqlalchemy as sa

from alembic import op

revision = "n20260930"
down_revision = "m20260930"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("review_item_evidence_files") as batch:
        batch.add_column(sa.Column("comment_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_review_file_comment",
            "review_item_comments",
            ["comment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_review_item_evidence_files_comment_id", ["comment_id"])


def downgrade():
    with op.batch_alter_table("review_item_evidence_files") as batch:
        batch.drop_index("ix_review_item_evidence_files_comment_id")
        batch.drop_constraint("fk_review_file_comment", type_="foreignkey")
        batch.drop_column("comment_id")
