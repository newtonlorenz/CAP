"""harden change management register and workflow quality

Revision ID: c4f1d8a7b9e2
Revises: aa7d9c3e1b2f
Create Date: 2026-02-17 18:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f1d8a7b9e2"
down_revision: Union[str, Sequence[str], None] = "aa7d9c3e1b2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE component_registers DROP CONSTRAINT IF EXISTS uq_component_registers_org_jurisdiction_status"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_component_registers_active_org_jurisdiction
        ON component_registers (
            COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid),
            jurisdiction_id
        )
        WHERE status = 'active'
        """
    )

    op.add_column(
        "change_entries",
        sa.Column("change_type", sa.String(length=30), nullable=False, server_default="normal"),
    )
    op.add_column(
        "change_entries",
        sa.Column("proposed_by_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("affected_components_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("affected_docs_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("implemented_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("implemented_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("testing_org_cycle", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "change_entries",
        sa.Column("testing_org_next_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_change_entries_change_type", "change_entries", ["change_type"], unique=False
    )
    op.create_index(
        "ix_change_entries_testing_org_next_due_at",
        "change_entries",
        ["testing_org_next_due_at"],
        unique=False,
    )

    op.add_column("change_events", sa.Column("updated_by", sa.Uuid(), nullable=True))
    op.add_column(
        "change_events", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("change_events", sa.Column("deleted_by", sa.Uuid(), nullable=True))
    op.add_column(
        "change_events", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("change_events", sa.Column("deletion_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_change_events_updated_by_users",
        "change_events",
        "users",
        ["updated_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_change_events_deleted_by_users",
        "change_events",
        "users",
        ["deleted_by"],
        ["id"],
    )
    op.create_index("ix_change_events_deleted_at", "change_events", ["deleted_at"], unique=False)

    op.add_column(
        "integration_checks", sa.Column("action_reference", sa.String(length=255), nullable=True)
    )
    op.add_column("integration_checks", sa.Column("evidence_notes", sa.Text(), nullable=True))
    op.add_column("integration_checks", sa.Column("updated_by", sa.Uuid(), nullable=True))
    op.add_column(
        "integration_checks", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("integration_checks", sa.Column("deleted_by", sa.Uuid(), nullable=True))
    op.add_column(
        "integration_checks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("integration_checks", sa.Column("deletion_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_integration_checks_updated_by_users",
        "integration_checks",
        "users",
        ["updated_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_integration_checks_deleted_by_users",
        "integration_checks",
        "users",
        ["deleted_by"],
        ["id"],
    )
    op.create_index(
        "ix_integration_checks_deleted_at",
        "integration_checks",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_integration_checks_deleted_at", table_name="integration_checks")
    op.drop_constraint(
        "fk_integration_checks_deleted_by_users",
        "integration_checks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_integration_checks_updated_by_users",
        "integration_checks",
        type_="foreignkey",
    )
    op.drop_column("integration_checks", "deletion_reason")
    op.drop_column("integration_checks", "deleted_at")
    op.drop_column("integration_checks", "deleted_by")
    op.drop_column("integration_checks", "updated_at")
    op.drop_column("integration_checks", "updated_by")
    op.drop_column("integration_checks", "evidence_notes")
    op.drop_column("integration_checks", "action_reference")

    op.drop_index("ix_change_events_deleted_at", table_name="change_events")
    op.drop_constraint("fk_change_events_deleted_by_users", "change_events", type_="foreignkey")
    op.drop_constraint("fk_change_events_updated_by_users", "change_events", type_="foreignkey")
    op.drop_column("change_events", "deletion_reason")
    op.drop_column("change_events", "deleted_at")
    op.drop_column("change_events", "deleted_by")
    op.drop_column("change_events", "updated_at")
    op.drop_column("change_events", "updated_by")

    op.drop_index("ix_change_entries_testing_org_next_due_at", table_name="change_entries")
    op.drop_index("ix_change_entries_change_type", table_name="change_entries")
    op.drop_column("change_entries", "testing_org_next_due_at")
    op.drop_column("change_entries", "testing_org_cycle")
    op.drop_column("change_entries", "implemented_end_at")
    op.drop_column("change_entries", "implemented_start_at")
    op.drop_column("change_entries", "planned_end_at")
    op.drop_column("change_entries", "planned_start_at")
    op.drop_column("change_entries", "affected_docs_summary")
    op.drop_column("change_entries", "affected_components_summary")
    op.drop_column("change_entries", "proposed_by_name_snapshot")
    op.drop_column("change_entries", "change_type")

    op.execute("DROP INDEX IF EXISTS uq_component_registers_active_org_jurisdiction")
    op.create_unique_constraint(
        "uq_component_registers_org_jurisdiction_status",
        "component_registers",
        ["organization_id", "jurisdiction_id", "status"],
    )
