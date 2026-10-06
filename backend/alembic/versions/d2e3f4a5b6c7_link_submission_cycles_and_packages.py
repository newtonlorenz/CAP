"""link submission cycles and submission packages

Revision ID: d2e3f4a5b6c7
Revises: c1b2d3e4f5a6
Create Date: 2026-02-12 16:20:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1b2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_cycles",
        sa.Column("certification_project_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "review_cycles",
        sa.Column(
            "cycle_type",
            sa.String(length=30),
            nullable=False,
            server_default="operational",
        ),
    )
    op.create_foreign_key(
        "fk_review_cycles_project_id",
        "review_cycles",
        "certification_projects",
        ["certification_project_id"],
        ["id"],
    )
    op.create_index(
        "ix_review_cycles_certification_project_id",
        "review_cycles",
        ["certification_project_id"],
        unique=False,
    )
    op.alter_column("review_cycles", "cycle_type", server_default=None)

    op.add_column(
        "submission_packages",
        sa.Column("review_cycle_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "submission_packages",
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "submission_packages",
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_submission_packages_review_cycle_id_review_cycles",
        "submission_packages",
        "review_cycles",
        ["review_cycle_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_submission_packages_snapshot_id_snapshots",
        "submission_packages",
        "snapshots",
        ["snapshot_id"],
        ["id"],
    )
    op.create_index(
        "ix_submission_packages_review_cycle_id",
        "submission_packages",
        ["review_cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_submission_packages_snapshot_id",
        "submission_packages",
        ["snapshot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_submission_packages_snapshot_id", table_name="submission_packages")
    op.drop_index("ix_submission_packages_review_cycle_id", table_name="submission_packages")
    op.drop_constraint(
        "fk_submission_packages_snapshot_id_snapshots",
        "submission_packages",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_submission_packages_review_cycle_id_review_cycles",
        "submission_packages",
        type_="foreignkey",
    )
    op.drop_column("submission_packages", "approval_requested_at")
    op.drop_column("submission_packages", "snapshot_id")
    op.drop_column("submission_packages", "review_cycle_id")

    op.drop_index("ix_review_cycles_certification_project_id", table_name="review_cycles")
    op.drop_constraint(
        "fk_review_cycles_project_id",
        "review_cycles",
        type_="foreignkey",
    )
    op.drop_column("review_cycles", "cycle_type")
    op.drop_column("review_cycles", "certification_project_id")
