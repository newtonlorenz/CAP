"""backfill null organization ids before tenant scoping

Revision ID: f0a1b2c3d4e5
Revises: e1f4b2c9d8a7
Create Date: 2026-04-26 00:00:00.000000
"""

import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f0a1b2c3d4e5"
down_revision = "e1f4b2c9d8a7"
branch_labels = None
depends_on = None


TENANT_TABLES = [
    "users",
    "documents",
    "requirements",
    "requirement_set_versions",
    "review_cycles",
    "snapshots",
    "audit_logs",
    "certification_projects",
    "baseline_migrations",
    "maintenance_plans",
    "evidence_items",
    "integration_connections",
    "export_manifests",
    "component_registers",
]


def _default_organization_id(connection) -> str:
    org_id = connection.execute(
        sa.text("SELECT id FROM organizations WHERE code = :code"),
        {"code": "default"},
    ).scalar()
    if org_id is not None:
        return str(org_id)

    org_id = connection.execute(
        sa.text("SELECT id FROM organizations ORDER BY created_at, id LIMIT 1")
    ).scalar()
    if org_id is not None:
        return str(org_id)

    org_id = str(uuid.uuid4())
    connection.execute(
        sa.text(
            """
            INSERT INTO organizations (id, code, name, active)
            VALUES (:id, :code, :name, :active)
            """
        ),
        {
            "id": org_id,
            "code": "default",
            "name": "Default Organization",
            "active": True,
        },
    )
    return org_id


def upgrade() -> None:
    connection = op.get_bind()
    organization_id = _default_organization_id(connection)
    for table_name in TENANT_TABLES:
        connection.execute(
            sa.text(
                f"UPDATE {table_name} "
                "SET organization_id = :organization_id "
                "WHERE organization_id IS NULL"
            ),
            {"organization_id": organization_id},
        )


def downgrade() -> None:
    # Data backfill is intentionally irreversible.
    pass
