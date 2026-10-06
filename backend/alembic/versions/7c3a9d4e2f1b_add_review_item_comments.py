"""add review item comments

Revision ID: 7c3a9d4e2f1b
Revises: f2a9b6d4c1e3
Create Date: 2026-02-04 00:00:00.000000
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c3a9d4e2f1b"
down_revision = "1f2c3d4e5a6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_item_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_item_comments_item_id_created_at",
        "review_item_comments",
        ["review_item_id", "created_at"],
    )

    review_items = sa.table(
        "review_items",
        sa.column("id", sa.Uuid()),
        sa.column("reviewer_id", sa.Uuid()),
        sa.column("review_comment", sa.Text()),
        sa.column("reviewed_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    review_item_comments = sa.table(
        "review_item_comments",
        sa.column("id", sa.Uuid()),
        sa.column("review_item_id", sa.Uuid()),
        sa.column("author_id", sa.Uuid()),
        sa.column("body", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.select(
            review_items.c.id,
            review_items.c.reviewer_id,
            review_items.c.review_comment,
            review_items.c.reviewed_at,
            review_items.c.created_at,
        )
    ).fetchall()

    for row in rows:
        if not row.review_comment:
            continue
        comment_body = row.review_comment.strip()
        if not comment_body:
            continue
        created_at = row.reviewed_at or row.created_at
        conn.execute(
            review_item_comments.insert().values(
                id=uuid.uuid4(),
                review_item_id=row.id,
                author_id=row.reviewer_id,
                body=comment_body,
                created_at=created_at,
                updated_at=None,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_review_item_comments_item_id_created_at", table_name="review_item_comments")
    op.drop_table("review_item_comments")
