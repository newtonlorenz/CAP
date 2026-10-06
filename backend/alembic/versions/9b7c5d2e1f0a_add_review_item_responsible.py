"""add review item responsible user

Revision ID: 9b7c5d2e1f0a
Revises: 3b9a1c2d4e5f
Create Date: 2026-02-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b7c5d2e1f0a"
down_revision = "3b9a1c2d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_items",
        sa.Column("responsible_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_items_responsible_user_id_users",
        "review_items",
        "users",
        ["responsible_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_review_items_responsible_user_id",
        "review_items",
        ["responsible_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_items_responsible_user_id", table_name="review_items")
    op.drop_constraint(
        "fk_review_items_responsible_user_id_users",
        "review_items",
        type_="foreignkey",
    )
    op.drop_column("review_items", "responsible_user_id")
