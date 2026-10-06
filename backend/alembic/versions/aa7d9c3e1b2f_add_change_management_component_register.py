"""add change management component register domain

Revision ID: aa7d9c3e1b2f
Revises: f6c4b2a1d9e8, f9a8b7c6d5e4
Create Date: 2026-02-17 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aa7d9c3e1b2f"
down_revision: Union[str, Sequence[str], None] = ("f6c4b2a1d9e8", "f9a8b7c6d5e4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "component_registers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("jurisdiction_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "jurisdiction_id",
            "status",
            name="uq_component_registers_org_jurisdiction_status",
        ),
    )
    op.create_index(
        "ix_component_registers_organization_id",
        "component_registers",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_component_registers_jurisdiction_id",
        "component_registers",
        ["jurisdiction_id"],
        unique=False,
    )

    op.create_table(
        "components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("register_id", sa.Uuid(), nullable=False),
        sa.Column("component_uid", sa.String(length=100), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("identifying_characteristics", sa.Text(), nullable=False),
        sa.Column("change_owner_id", sa.Uuid(), nullable=True),
        sa.Column("change_owner_name", sa.String(length=255), nullable=True),
        sa.Column("confidentiality_code", sa.Integer(), nullable=False),
        sa.Column("integrity_code", sa.Integer(), nullable=False),
        sa.Column("availability_code", sa.Integer(), nullable=False),
        sa.Column("accountability_code", sa.Integer(), nullable=False),
        sa.Column("classification_code", sa.Integer(), nullable=False),
        sa.Column("checksum_hash", sa.String(length=255), nullable=True),
        sa.Column("is_hardware", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("geographic_location", sa.String(length=255), nullable=True),
        sa.Column("hosting_model", sa.String(length=40), nullable=False),
        sa.Column("virtualized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("public_cloud_provider", sa.String(length=255), nullable=True),
        sa.Column(
            "public_cloud_iso27001", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "public_cloud_independent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "public_cloud_redundancy", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["register_id"], ["component_registers.id"]),
        sa.ForeignKeyConstraint(["change_owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("register_id", "component_uid", name="uq_components_register_uid"),
    )
    op.create_index("ix_components_register_id", "components", ["register_id"], unique=False)
    op.create_index(
        "ix_components_classification_code", "components", ["classification_code"], unique=False
    )
    op.create_index("ix_components_status", "components", ["status"], unique=False)

    op.create_table(
        "component_baselines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("register_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("established_by", sa.Uuid(), nullable=False),
        sa.Column(
            "established_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["register_id"], ["component_registers.id"]),
        sa.ForeignKeyConstraint(["established_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_component_baselines_register_id", "component_baselines", ["register_id"], unique=False
    )

    op.create_table(
        "component_baseline_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("baseline_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=True),
        sa.Column("component_uid", sa.String(length=100), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("classification_code", sa.Integer(), nullable=False),
        sa.Column("checksum_hash", sa.String(length=255), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["baseline_id"], ["component_baselines.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "baseline_id",
            "component_uid",
            name="uq_component_baseline_items_baseline_uid",
        ),
    )
    op.create_index(
        "ix_component_baseline_items_baseline_id",
        "component_baseline_items",
        ["baseline_id"],
        unique=False,
    )

    op.create_table(
        "change_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("register_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("complexity_classification", sa.String(length=100), nullable=True),
        sa.Column("resource_assessment", sa.Text(), nullable=True),
        sa.Column("scheduling_assessment", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("affected_documentation", sa.Text(), nullable=True),
        sa.Column("evaluation_effect", sa.Text(), nullable=True),
        sa.Column("evaluation_risk", sa.Text(), nullable=True),
        sa.Column("evaluation_regulatory_impact", sa.Text(), nullable=True),
        sa.Column("evaluation_ciaa_impact", sa.Text(), nullable=True),
        sa.Column("approval_decision", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("implementation_notes", sa.Text(), nullable=True),
        sa.Column("implemented_by", sa.Uuid(), nullable=True),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "testing_org_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("testing_org_status", sa.String(length=40), nullable=True),
        sa.Column("testing_org_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("testing_org_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "integration_related", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("proposed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["register_id"], ["component_registers.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["implemented_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["proposed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_change_entries_register_id", "change_entries", ["register_id"], unique=False
    )
    op.create_index("ix_change_entries_status", "change_entries", ["status"], unique=False)
    op.create_index(
        "ix_change_entries_implemented_at", "change_entries", ["implemented_at"], unique=False
    )
    op.create_index(
        "ix_change_entries_verified_at", "change_entries", ["verified_at"], unique=False
    )

    op.create_table(
        "change_entry_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("change_entry_id", sa.Uuid(), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=False),
        sa.Column("version_at_proposal", sa.String(length=100), nullable=True),
        sa.Column("planned_version", sa.String(length=100), nullable=True),
        sa.Column("implemented_version", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["change_entry_id"], ["change_entries.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "change_entry_id",
            "component_id",
            name="uq_change_entry_components_change_component",
        ),
    )
    op.create_index(
        "ix_change_entry_components_change_entry_id",
        "change_entry_components",
        ["change_entry_id"],
        unique=False,
    )
    op.create_index(
        "ix_change_entry_components_component_id",
        "change_entry_components",
        ["component_id"],
        unique=False,
    )

    op.create_table(
        "change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("change_entry_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("status_from", sa.String(length=40), nullable=True),
        sa.Column("status_to", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["change_entry_id"], ["change_entries.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_change_events_change_entry_id", "change_events", ["change_entry_id"], unique=False
    )

    op.create_table(
        "integration_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("change_entry_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("completed_by", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["change_entry_id"], ["change_entries.id"]),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_checks_change_entry_id",
        "integration_checks",
        ["change_entry_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_integration_checks_change_entry_id", table_name="integration_checks")
    op.drop_table("integration_checks")

    op.drop_index("ix_change_events_change_entry_id", table_name="change_events")
    op.drop_table("change_events")

    op.drop_index("ix_change_entry_components_component_id", table_name="change_entry_components")
    op.drop_index(
        "ix_change_entry_components_change_entry_id", table_name="change_entry_components"
    )
    op.drop_table("change_entry_components")

    op.drop_index("ix_change_entries_verified_at", table_name="change_entries")
    op.drop_index("ix_change_entries_implemented_at", table_name="change_entries")
    op.drop_index("ix_change_entries_status", table_name="change_entries")
    op.drop_index("ix_change_entries_register_id", table_name="change_entries")
    op.drop_table("change_entries")

    op.drop_index("ix_component_baseline_items_baseline_id", table_name="component_baseline_items")
    op.drop_table("component_baseline_items")

    op.drop_index("ix_component_baselines_register_id", table_name="component_baselines")
    op.drop_table("component_baselines")

    op.drop_index("ix_components_status", table_name="components")
    op.drop_index("ix_components_classification_code", table_name="components")
    op.drop_index("ix_components_register_id", table_name="components")
    op.drop_table("components")

    op.drop_index("ix_component_registers_jurisdiction_id", table_name="component_registers")
    op.drop_index("ix_component_registers_organization_id", table_name="component_registers")
    op.drop_table("component_registers")
