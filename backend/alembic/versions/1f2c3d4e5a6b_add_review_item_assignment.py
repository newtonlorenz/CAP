"""add review item assignment

Revision ID: 1f2c3d4e5a6b
Revises: f2a9b6d4c1e3
Create Date: 2026-02-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1f2c3d4e5a6b"
down_revision = "f2a9b6d4c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_items",
        sa.Column("assigned_reviewer_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_items_assigned_reviewer_id_users",
        "review_items",
        "users",
        ["assigned_reviewer_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_review_items_assigned_reviewer_id_users",
        "review_items",
        type_="foreignkey",
    )
    op.drop_column("review_items", "assigned_reviewer_id")
