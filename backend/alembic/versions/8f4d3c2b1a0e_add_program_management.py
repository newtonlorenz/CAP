"""add program management entities

Revision ID: 8f4d3c2b1a0e
Revises: 5a8d2c1f7e4b, 5a6b7c8d9e0f
Create Date: 2026-02-12 10:30:00.000000

"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f4d3c2b1a0e"
down_revision: Union[str, tuple[str, str], None] = ("5a8d2c1f7e4b", "5a6b7c8d9e0f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _seed_default_organization(conn: sa.engine.Connection) -> uuid.UUID:
    organizations = sa.table(
        "organizations",
        sa.Column("id", sa.Uuid()),
        sa.Column("code", sa.String(length=50)),
        sa.Column("name", sa.String(length=255)),
        sa.Column("active", sa.Boolean()),
    )
    existing = conn.execute(
        sa.select(organizations.c.id).where(organizations.c.code == "default")
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    organization_id = uuid.uuid4()
    conn.execute(
        organizations.insert().values(
            id=organization_id,
            code="default",
            name="Default Organization",
            active=True,
        )
    )
    return organization_id


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    conn = op.get_bind()
    default_org_id = _seed_default_organization(conn)

    op.add_column("users", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_users_organization_id_organizations",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False)
    op.execute(
        sa.text(
            "UPDATE users SET organization_id = :org_id WHERE organization_id IS NULL"
        ).bindparams(org_id=default_org_id)
    )

    op.add_column("documents", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("maintenance_plan_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("cadence_interval_days", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_documents_organization_id_organizations",
        "documents",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"], unique=False)
    op.execute(
        sa.text(
            """
            UPDATE documents
            SET organization_id = (
                SELECT users.organization_id FROM users WHERE users.id = documents.uploaded_by
            )
            WHERE organization_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE documents
            SET cadence_interval_days = CASE
                WHEN testing_frequency IS NULL THEN NULL
                WHEN lower(testing_frequency) LIKE '%week%' THEN 7
                WHEN lower(testing_frequency) LIKE '%month%' THEN 30
                WHEN lower(testing_frequency) LIKE '%quarter%' THEN 90
                WHEN lower(testing_frequency) LIKE '%year%' THEN 365
                ELSE NULL
            END
            WHERE cadence_interval_days IS NULL
            """
        )
    )

    op.add_column("requirements", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_requirements_organization_id_organizations",
        "requirements",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(
        "ix_requirements_organization_id", "requirements", ["organization_id"], unique=False
    )
    op.execute(
        sa.text(
            """
            UPDATE requirements
            SET organization_id = (
                SELECT documents.organization_id
                FROM documents
                WHERE documents.id = requirements.document_id
            )
            WHERE organization_id IS NULL
            """
        )
    )

    op.add_column("review_cycles", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_review_cycles_organization_id_organizations",
        "review_cycles",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(
        "ix_review_cycles_organization_id", "review_cycles", ["organization_id"], unique=False
    )
    op.execute(
        sa.text(
            """
            UPDATE review_cycles
            SET organization_id = (
                SELECT users.organization_id FROM users WHERE users.id = review_cycles.created_by
            )
            WHERE organization_id IS NULL
            """
        )
    )

    op.add_column("snapshots", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_snapshots_organization_id_organizations",
        "snapshots",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index("ix_snapshots_organization_id", "snapshots", ["organization_id"], unique=False)
    op.execute(
        sa.text(
            """
            UPDATE snapshots
            SET organization_id = (
                SELECT users.organization_id FROM users WHERE users.id = snapshots.created_by
            )
            WHERE organization_id IS NULL
            """
        )
    )

    op.add_column("audit_logs", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("audit_logs", sa.Column("prev_hash", sa.String(length=128), nullable=True))
    op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=128), nullable=True))
    op.create_foreign_key(
        "fk_audit_logs_organization_id_organizations",
        "audit_logs",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_index(
        "ix_audit_logs_organization_id", "audit_logs", ["organization_id"], unique=False
    )
    op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"], unique=False)
    op.execute(
        sa.text(
            """
            UPDATE audit_logs
            SET organization_id = (
                SELECT users.organization_id FROM users WHERE users.id = audit_logs.user_id
            )
            WHERE organization_id IS NULL
            """
        )
    )

    op.create_table(
        "controls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jurisdiction_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("test_method", sa.Text(), nullable=True),
        sa.Column("evidence_expectations", sa.Text(), nullable=True),
        sa.Column("cadence_days", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jurisdiction_id", "code", name="uq_controls_jurisdiction_code"),
    )
    op.create_index("ix_controls_jurisdiction_id", "controls", ["jurisdiction_id"], unique=False)

    op.create_table(
        "obligations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jurisdiction_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("legal_reference", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jurisdiction_id", "code", name="uq_obligations_jurisdiction_code"),
    )
    op.create_index(
        "ix_obligations_jurisdiction_id", "obligations", ["jurisdiction_id"], unique=False
    )

    op.create_table(
        "control_crosswalks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_control_id", sa.Uuid(), nullable=False),
        sa.Column("target_obligation_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_strength", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["source_control_id"], ["controls.id"]),
        sa.ForeignKeyConstraint(["target_obligation_id"], ["obligations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_control_id",
            "target_obligation_id",
            name="uq_control_crosswalks_source_target",
        ),
    )
    op.create_index(
        "ix_control_crosswalks_source_control_id",
        "control_crosswalks",
        ["source_control_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_crosswalks_target_obligation_id",
        "control_crosswalks",
        ["target_obligation_id"],
        unique=False,
    )

    op.create_table(
        "certification_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("jurisdiction_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_submission_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_certification_projects_organization_id",
        "certification_projects",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_certification_projects_jurisdiction_id",
        "certification_projects",
        ["jurisdiction_id"],
        unique=False,
    )

    op.create_table(
        "certification_project_milestones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["certification_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_certification_project_milestones_project_id",
        "certification_project_milestones",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "submission_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("checklist_json", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["certification_projects.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_submission_packages_project_version"),
    )
    op.create_index(
        "ix_submission_packages_project_id",
        "submission_packages",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "submission_package_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_package_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("link_url", sa.String(length=2000), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["submission_package_id"], ["submission_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_submission_package_artifacts_submission_package_id",
        "submission_package_artifacts",
        ["submission_package_id"],
        unique=False,
    )

    op.create_table(
        "maintenance_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("jurisdiction_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cadence_days", sa.Integer(), nullable=False),
        sa.Column("reminder_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
        sa.Column("escalation_days", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_maintenance_plans_organization_id",
        "maintenance_plans",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_plans_jurisdiction_id",
        "maintenance_plans",
        ["jurisdiction_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_plans_document_id",
        "maintenance_plans",
        ["document_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_documents_maintenance_plan_id_maintenance_plans",
        "documents",
        "maintenance_plans",
        ["maintenance_plan_id"],
        ["id"],
    )

    op.create_table(
        "maintenance_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("maintenance_plan_id", sa.Uuid(), nullable=False),
        sa.Column("review_cycle_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["maintenance_plan_id"], ["maintenance_plans.id"]),
        sa.ForeignKeyConstraint(["review_cycle_id"], ["review_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_maintenance_events_maintenance_plan_id",
        "maintenance_events",
        ["maintenance_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_events_review_cycle_id",
        "maintenance_events",
        ["review_cycle_id"],
        unique=False,
    )

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("link_url", sa.String(length=2000), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_in_days", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_items_organization_id", "evidence_items", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_evidence_items_requirement_id", "evidence_items", ["requirement_id"], unique=False
    )

    op.create_table(
        "evidence_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.Column("validator_id", sa.Uuid(), nullable=True),
        sa.Column("validation_status", sa.String(length=30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"]),
        sa.ForeignKeyConstraint(["validator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_validations_evidence_item_id",
        "evidence_validations",
        ["evidence_item_id"],
        unique=False,
    )

    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=30), nullable=True),
        sa.Column("last_sync_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_connections_organization_id",
        "integration_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_integration_connections_provider",
        "integration_connections",
        ["provider"],
        unique=False,
    )

    op.create_table(
        "export_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_id", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("hash_algo", sa.String(length=30), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["signed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_export_manifests_organization_id",
        "export_manifests",
        ["organization_id"],
        unique=False,
    )
    op.create_index("ix_export_manifests_scope_id", "export_manifests", ["scope_id"], unique=False)

    jurisdictions = sa.table(
        "jurisdictions",
        sa.Column("id", sa.Uuid()),
        sa.Column("code", sa.String(length=20)),
    )
    controls = sa.table(
        "controls",
        sa.Column("id", sa.Uuid()),
        sa.Column("jurisdiction_id", sa.Uuid()),
        sa.Column("code", sa.String(length=100)),
        sa.Column("title", sa.String(length=500)),
        sa.Column("description", sa.Text()),
        sa.Column("test_method", sa.Text()),
        sa.Column("evidence_expectations", sa.Text()),
        sa.Column("cadence_days", sa.Integer()),
        sa.Column("status", sa.String(length=30)),
    )
    obligations = sa.table(
        "obligations",
        sa.Column("id", sa.Uuid()),
        sa.Column("jurisdiction_id", sa.Uuid()),
        sa.Column("code", sa.String(length=100)),
        sa.Column("legal_reference", sa.String(length=255)),
        sa.Column("title", sa.String(length=500)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(length=30)),
    )
    crosswalks = sa.table(
        "control_crosswalks",
        sa.Column("id", sa.Uuid()),
        sa.Column("source_control_id", sa.Uuid()),
        sa.Column("target_obligation_id", sa.Uuid()),
        sa.Column("mapping_strength", sa.String(length=30)),
        sa.Column("notes", sa.Text()),
    )

    jurisdiction_rows = conn.execute(sa.select(jurisdictions.c.id, jurisdictions.c.code)).all()
    for jurisdiction_id, code in jurisdiction_rows:
        base_code = (code or "").lower()
        control_id = uuid.uuid4()
        obligation_id = uuid.uuid4()
        conn.execute(
            controls.insert().values(
                id=control_id,
                jurisdiction_id=jurisdiction_id,
                code=f"{base_code.upper()}-BASE-001",
                title="Base governance control",
                description="Starter control to map governance obligations in this market pack.",
                test_method="Document review + evidence sampling",
                evidence_expectations="Policy, ownership and implementation evidence",
                cadence_days=90,
                status="active",
            )
        )
        conn.execute(
            obligations.insert().values(
                id=obligation_id,
                jurisdiction_id=jurisdiction_id,
                code=f"{base_code.upper()}-OBL-001",
                legal_reference="Market-pack baseline",
                title="Governance obligation baseline",
                description="Starter obligation entry for crosswalk and project planning.",
                status="active",
            )
        )
        conn.execute(
            crosswalks.insert().values(
                id=uuid.uuid4(),
                source_control_id=control_id,
                target_obligation_id=obligation_id,
                mapping_strength="full",
                notes="Seeded baseline mapping",
            )
        )


def downgrade() -> None:
    op.drop_index("ix_export_manifests_scope_id", table_name="export_manifests")
    op.drop_index("ix_export_manifests_organization_id", table_name="export_manifests")
    op.drop_table("export_manifests")

    op.drop_index("ix_integration_connections_provider", table_name="integration_connections")
    op.drop_index(
        "ix_integration_connections_organization_id", table_name="integration_connections"
    )
    op.drop_table("integration_connections")

    op.drop_index("ix_evidence_validations_evidence_item_id", table_name="evidence_validations")
    op.drop_table("evidence_validations")

    op.drop_index("ix_evidence_items_requirement_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_organization_id", table_name="evidence_items")
    op.drop_table("evidence_items")

    op.drop_index("ix_maintenance_events_review_cycle_id", table_name="maintenance_events")
    op.drop_index("ix_maintenance_events_maintenance_plan_id", table_name="maintenance_events")
    op.drop_table("maintenance_events")

    op.drop_constraint(
        "fk_documents_maintenance_plan_id_maintenance_plans", "documents", type_="foreignkey"
    )

    op.drop_index("ix_maintenance_plans_document_id", table_name="maintenance_plans")
    op.drop_index("ix_maintenance_plans_jurisdiction_id", table_name="maintenance_plans")
    op.drop_index("ix_maintenance_plans_organization_id", table_name="maintenance_plans")
    op.drop_table("maintenance_plans")

    op.drop_index(
        "ix_submission_package_artifacts_submission_package_id",
        table_name="submission_package_artifacts",
    )
    op.drop_table("submission_package_artifacts")

    op.drop_index("ix_submission_packages_project_id", table_name="submission_packages")
    op.drop_table("submission_packages")

    op.drop_index(
        "ix_certification_project_milestones_project_id",
        table_name="certification_project_milestones",
    )
    op.drop_table("certification_project_milestones")

    op.drop_index("ix_certification_projects_jurisdiction_id", table_name="certification_projects")
    op.drop_index("ix_certification_projects_organization_id", table_name="certification_projects")
    op.drop_table("certification_projects")

    op.drop_index("ix_control_crosswalks_target_obligation_id", table_name="control_crosswalks")
    op.drop_index("ix_control_crosswalks_source_control_id", table_name="control_crosswalks")
    op.drop_table("control_crosswalks")

    op.drop_index("ix_obligations_jurisdiction_id", table_name="obligations")
    op.drop_table("obligations")

    op.drop_index("ix_controls_jurisdiction_id", table_name="controls")
    op.drop_table("controls")

    op.drop_index("ix_audit_logs_event_hash", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_constraint(
        "fk_audit_logs_organization_id_organizations", "audit_logs", type_="foreignkey"
    )
    op.drop_column("audit_logs", "event_hash")
    op.drop_column("audit_logs", "prev_hash")
    op.drop_column("audit_logs", "organization_id")

    op.drop_index("ix_snapshots_organization_id", table_name="snapshots")
    op.drop_constraint(
        "fk_snapshots_organization_id_organizations", "snapshots", type_="foreignkey"
    )
    op.drop_column("snapshots", "organization_id")

    op.drop_index("ix_review_cycles_organization_id", table_name="review_cycles")
    op.drop_constraint(
        "fk_review_cycles_organization_id_organizations", "review_cycles", type_="foreignkey"
    )
    op.drop_column("review_cycles", "organization_id")

    op.drop_index("ix_requirements_organization_id", table_name="requirements")
    op.drop_constraint(
        "fk_requirements_organization_id_organizations", "requirements", type_="foreignkey"
    )
    op.drop_column("requirements", "organization_id")

    op.drop_index("ix_documents_organization_id", table_name="documents")
    op.drop_constraint(
        "fk_documents_organization_id_organizations", "documents", type_="foreignkey"
    )
    op.drop_column("documents", "cadence_interval_days")
    op.drop_column("documents", "maintenance_plan_id")
    op.drop_column("documents", "organization_id")

    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_constraint("fk_users_organization_id_organizations", "users", type_="foreignkey")
    op.drop_column("users", "organization_id")

    op.drop_table("organizations")
