"""add partial unique index for active submission cycles per project

Revision ID: e7f8a9b0c1d2
Revises: d2e3f4a5b6c7
Create Date: 2026-02-12 19:20:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_review_cycles_active_submission_per_project",
        "review_cycles",
        ["certification_project_id"],
        unique=True,
        postgresql_where=sa.text(
            "cycle_type = 'submission' "
            "AND status <> 'archived' "
            "AND certification_project_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_review_cycles_active_submission_per_project",
        table_name="review_cycles",
    )
