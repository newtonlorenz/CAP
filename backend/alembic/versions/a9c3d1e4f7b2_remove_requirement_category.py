"""remove requirement category fields

Revision ID: a9c3d1e4f7b2
Revises: f2a9b6d4c1e3
Create Date: 2026-02-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a9c3d1e4f7b2"
down_revision = "f2a9b6d4c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_column("category")
    with op.batch_alter_table("extracted_requirements") as batch_op:
        batch_op.drop_column("category")


def downgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=100), nullable=True))
    with op.batch_alter_table("extracted_requirements") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=100), nullable=True))
