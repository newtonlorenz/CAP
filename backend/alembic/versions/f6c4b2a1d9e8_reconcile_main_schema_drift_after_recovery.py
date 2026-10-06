"""reconcile main schema drift after recovery

Revision ID: f6c4b2a1d9e8
Revises: e7f8a9b0c1d2
Create Date: 2026-02-12 16:34:00.000000
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6c4b2a1d9e8"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn: sa.engine.Connection, table_name: str) -> bool:
    result = conn.execute(
        sa.text("SELECT to_regclass(:qualified_name) IS NOT NULL"),
        {"qualified_name": f"public.{table_name}"},
    )
    return bool(result.scalar_one())


def _column_exists(conn: sa.engine.Connection, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar_one())


def _index_exists(conn: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = :table_name
                  AND indexname = :index_name
            )
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    return bool(result.scalar_one())


def _constraint_exists(conn: sa.engine.Connection, constraint_name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = :constraint_name
            )
            """
        ),
        {"constraint_name": constraint_name},
    )
    return bool(result.scalar_one())


def _ensure_default_organization(conn: sa.engine.Connection) -> uuid.UUID | None:
    if not _table_exists(conn, "organizations"):
        return None

    existing = conn.execute(
        sa.text(
            """
            SELECT id
            FROM organizations
            WHERE code = 'default'
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    fallback = conn.execute(sa.text("SELECT id FROM organizations LIMIT 1")).scalar_one_or_none()
    if fallback is not None:
        conn.execute(
            sa.text("UPDATE organizations SET code = 'default' WHERE id = :org_id"),
            {"org_id": fallback},
        )
        return fallback

    org_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO organizations (id, code, name, active)
            VALUES (:org_id, 'default', 'Default Organization', true)
            """
        ),
        {"org_id": org_id},
    )
    return org_id


def _backfill_organization_ids(
    conn: sa.engine.Connection, default_org_id: uuid.UUID | None
) -> None:
    if default_org_id is None:
        return

    if _table_exists(conn, "users") and _column_exists(conn, "users", "organization_id"):
        conn.execute(
            sa.text(
                """
                UPDATE users
                SET organization_id = :default_org_id
                WHERE organization_id IS NULL
                """
            ),
            {"default_org_id": default_org_id},
        )

    if _table_exists(conn, "documents") and _column_exists(conn, "documents", "organization_id"):
        conn.execute(
            sa.text(
                """
                UPDATE documents d
                SET organization_id = COALESCE(u.organization_id, :default_org_id)
                FROM users u
                WHERE d.organization_id IS NULL
                  AND d.uploaded_by = u.id
                """
            ),
            {"default_org_id": default_org_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE documents
                SET organization_id = :default_org_id
                WHERE organization_id IS NULL
                """
            ),
            {"default_org_id": default_org_id},
        )

    if _table_exists(conn, "requirements") and _column_exists(
        conn, "requirements", "organization_id"
    ):
        conn.execute(
            sa.text(
                """
                UPDATE requirements r
                SET organization_id = COALESCE(d.organization_id, :default_org_id)
                FROM documents d
                WHERE r.organization_id IS NULL
                  AND r.document_id = d.id
                """
            ),
            {"default_org_id": default_org_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE requirements
                SET organization_id = :default_org_id
                WHERE organization_id IS NULL
                """
            ),
            {"default_org_id": default_org_id},
        )

    if _table_exists(conn, "review_cycles") and _column_exists(
        conn, "review_cycles", "organization_id"
    ):
        conn.execute(
            sa.text(
                """
                UPDATE review_cycles rc
                SET organization_id = COALESCE(u.organization_id, :default_org_id)
                FROM users u
                WHERE rc.organization_id IS NULL
                  AND rc.created_by = u.id
                """
            ),
            {"default_org_id": default_org_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE review_cycles
                SET organization_id = :default_org_id
                WHERE organization_id IS NULL
                """
            ),
            {"default_org_id": default_org_id},
        )

    if _table_exists(conn, "snapshots") and _column_exists(conn, "snapshots", "organization_id"):
        conn.execute(
            sa.text(
                """
                UPDATE snapshots s
                SET organization_id = COALESCE(u.organization_id, :default_org_id)
                FROM users u
                WHERE s.organization_id IS NULL
                  AND s.created_by = u.id
                """
            ),
            {"default_org_id": default_org_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE snapshots
                SET organization_id = :default_org_id
                WHERE organization_id IS NULL
                """
            ),
            {"default_org_id": default_org_id},
        )

    if _table_exists(conn, "audit_logs") and _column_exists(conn, "audit_logs", "organization_id"):
        conn.execute(
            sa.text(
                """
                UPDATE audit_logs a
                SET organization_id = COALESCE(u.organization_id, :default_org_id)
                FROM users u
                WHERE a.organization_id IS NULL
                  AND a.user_id = u.id
                """
            ),
            {"default_org_id": default_org_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE audit_logs
                SET organization_id = :default_org_id
                WHERE organization_id IS NULL
                """
            ),
            {"default_org_id": default_org_id},
        )


def upgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "review_items"):
        missing_review_item_cols = {
            "jira_issue_key": sa.Column("jira_issue_key", sa.String(length=50), nullable=True),
            "jira_issue_url": sa.Column("jira_issue_url", sa.String(length=500), nullable=True),
            "jira_status": sa.Column("jira_status", sa.String(length=120), nullable=True),
            "jira_summary": sa.Column("jira_summary", sa.Text(), nullable=True),
            "jira_assignee": sa.Column("jira_assignee", sa.String(length=255), nullable=True),
            "jira_priority": sa.Column("jira_priority", sa.String(length=120), nullable=True),
            "jira_updated_at": sa.Column(
                "jira_updated_at", sa.DateTime(timezone=True), nullable=True
            ),
            "jira_synced_at": sa.Column(
                "jira_synced_at", sa.DateTime(timezone=True), nullable=True
            ),
            "jira_sync_error": sa.Column("jira_sync_error", sa.Text(), nullable=True),
        }
        for column_name, column in missing_review_item_cols.items():
            if not _column_exists(conn, "review_items", column_name):
                op.add_column("review_items", column)

        if not _index_exists(
            conn, "review_items", "ix_review_items_review_cycle_id_jira_issue_key"
        ):
            op.create_index(
                "ix_review_items_review_cycle_id_jira_issue_key",
                "review_items",
                ["review_cycle_id", "jira_issue_key"],
            )

    if _table_exists(conn, "audit_logs"):
        if not _column_exists(conn, "audit_logs", "organization_id"):
            op.add_column("audit_logs", sa.Column("organization_id", sa.Uuid(), nullable=True))
        if not _column_exists(conn, "audit_logs", "prev_hash"):
            op.add_column(
                "audit_logs", sa.Column("prev_hash", sa.String(length=128), nullable=True)
            )
        if not _column_exists(conn, "audit_logs", "event_hash"):
            op.add_column(
                "audit_logs", sa.Column("event_hash", sa.String(length=128), nullable=True)
            )

        if _table_exists(conn, "organizations") and not _constraint_exists(
            conn, "fk_audit_logs_organization_id_organizations"
        ):
            op.create_foreign_key(
                "fk_audit_logs_organization_id_organizations",
                "audit_logs",
                "organizations",
                ["organization_id"],
                ["id"],
            )
        if not _index_exists(conn, "audit_logs", "ix_audit_logs_organization_id"):
            op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
        if not _index_exists(conn, "audit_logs", "ix_audit_logs_event_hash"):
            op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"])

    default_org_id = _ensure_default_organization(conn)



def downgrade() -> None:
    # Intentional no-op: this reconciliation migration repairs drifted environments.
    pass
