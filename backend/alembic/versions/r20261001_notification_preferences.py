"""Persist personal review email preferences, enabled for existing accounts."""

import sqlalchemy as sa

from alembic import op

revision = "r20261001"
down_revision = "q20260930"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("review_mentions", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(
            sa.Column("review_reminders", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("review_reminders")
        batch.drop_column("review_mentions")
