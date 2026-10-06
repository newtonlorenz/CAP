"""add requirement baseline versioning

Revision ID: f9a8b7c6d5e4
Revises: e7f8a9b0c1d2
Create Date: 2026-02-12 20:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f9a8b7c6d5e4"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "requirement_set_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("based_on_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["based_on_version_id"], ["requirement_set_versions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_requirement_set_versions_document_version",
        ),
    )
    op.create_index(
        "ix_requirement_set_versions_document_id",
        "requirement_set_versions",
        ["document_id"],
    )
    op.create_index(
        "ix_requirement_set_versions_organization_id",
        "requirement_set_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_requirement_set_versions_based_on_version_id",
        "requirement_set_versions",
        ["based_on_version_id"],
    )
    op.create_index(
        "uq_requirement_set_versions_current_per_document",
        "requirement_set_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.add_column(
        "requirements",
        sa.Column("requirement_set_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "requirements",
        sa.Column("source_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_requirements_requirement_set_version_id",
        "requirements",
        "requirement_set_versions",
        ["requirement_set_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_requirements_source_requirement_id",
        "requirements",
        "requirements",
        ["source_requirement_id"],
        ["id"],
    )
    op.create_index(
        "ix_requirements_requirement_set_version_id",
        "requirements",
        ["requirement_set_version_id"],
    )
    op.create_index(
        "ix_requirements_source_requirement_id",
        "requirements",
        ["source_requirement_id"],
    )

    op.create_table(
        "certification_project_requirement_baselines",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_set_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["certification_projects.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["requirement_set_version_id"], ["requirement_set_versions.id"]),
        sa.PrimaryKeyConstraint(
            "project_id",
            "document_id",
            name="pk_certification_project_requirement_baselines",
        ),
    )
    op.create_index(
        "ix_certification_project_requirement_baselines_project_id",
        "certification_project_requirement_baselines",
        ["project_id"],
    )
    op.create_index(
        "ix_certification_project_requirement_baselines_document_id",
        "certification_project_requirement_baselines",
        ["document_id"],
    )
    op.create_index(
        "ix_certification_project_requirement_baselines_version_id",
        "certification_project_requirement_baselines",
        ["requirement_set_version_id"],
    )

    op.add_column(
        "review_cycles",
        sa.Column("predecessor_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_cycles_predecessor_cycle_id",
        "review_cycles",
        "review_cycles",
        ["predecessor_cycle_id"],
        ["id"],
    )
    op.create_index(
        "ix_review_cycles_predecessor_cycle_id",
        "review_cycles",
        ["predecessor_cycle_id"],
    )

    op.create_table(
        "review_cycle_requirement_baselines",
        sa.Column("review_cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_set_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["review_cycle_id"], ["review_cycles.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["requirement_set_version_id"], ["requirement_set_versions.id"]),
        sa.PrimaryKeyConstraint(
            "review_cycle_id",
            "document_id",
            name="pk_review_cycle_requirement_baselines",
        ),
    )
    op.create_index(
        "ix_review_cycle_requirement_baselines_review_cycle_id",
        "review_cycle_requirement_baselines",
        ["review_cycle_id"],
    )
    op.create_index(
        "ix_review_cycle_requirement_baselines_document_id",
        "review_cycle_requirement_baselines",
        ["document_id"],
    )
    op.create_index(
        "ix_review_cycle_requirement_baselines_version_id",
        "review_cycle_requirement_baselines",
        ["requirement_set_version_id"],
    )

    op.create_table(
        "baseline_migrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'previewed'"),
        ),
        sa.Column("preview_json", sa.Text(), nullable=True),
        sa.Column("execution_json", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["certification_projects.id"]),
        sa.ForeignKeyConstraint(["from_cycle_id"], ["review_cycles.id"]),
        sa.ForeignKeyConstraint(["to_cycle_id"], ["review_cycles.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_baseline_migrations_project_id", "baseline_migrations", ["project_id"])
    op.create_index(
        "ix_baseline_migrations_from_cycle_id", "baseline_migrations", ["from_cycle_id"]
    )
    op.create_index("ix_baseline_migrations_to_cycle_id", "baseline_migrations", ["to_cycle_id"])
    op.create_index(
        "ix_baseline_migrations_organization_id",
        "baseline_migrations",
        ["organization_id"],
    )

    # Backfill one initial version per existing requirement set document.
    op.execute(
        sa.text(
            """
            INSERT INTO requirement_set_versions (
                id, organization_id, document_id, version_number, status, is_current,
                created_by, approved_by, created_at, approved_at
            )
            SELECT
                (
                    substr(md5(random()::text || clock_timestamp()::text || d.id::text), 1, 8)
                    || '-' ||
                    substr(md5(random()::text || clock_timestamp()::text || d.id::text), 9, 4)
                    || '-' ||
                    substr(md5(random()::text || clock_timestamp()::text || d.id::text), 13, 4)
                    || '-' ||
                    substr(md5(random()::text || clock_timestamp()::text || d.id::text), 17, 4)
                    || '-' ||
                    substr(md5(random()::text || clock_timestamp()::text || d.id::text), 21, 12)
                )::uuid,
                d.organization_id,
                d.id,
                1,
                CASE WHEN d.status = 'approved' THEN 'approved' ELSE 'draft' END,
                true,
                d.uploaded_by,
                d.approved_by,
                d.created_at,
                CASE WHEN d.status = 'approved' THEN NOW() ELSE NULL END
            FROM documents d
            LEFT JOIN requirement_set_versions rsv
                ON rsv.document_id = d.id AND rsv.version_number = 1
            WHERE rsv.id IS NULL
            """
        )
    )

    # Link existing requirements to the v1 baseline for their document.
    op.execute(
        sa.text(
            """
            UPDATE requirements req
            SET requirement_set_version_id = rsv.id
            FROM requirement_set_versions rsv
            WHERE req.document_id IS NOT NULL
              AND req.document_id = rsv.document_id
              AND rsv.version_number = 1
              AND req.requirement_set_version_id IS NULL
            """
        )
    )

    # Backfill project baselines from source_document_id.
    op.execute(
        sa.text(
            """
            INSERT INTO certification_project_requirement_baselines (
                project_id, document_id, requirement_set_version_id
            )
            SELECT
                cp.id,
                cp.source_document_id,
                rsv.id
            FROM certification_projects cp
            JOIN requirement_set_versions rsv
              ON rsv.document_id = cp.source_document_id
             AND rsv.is_current = true
            WHERE cp.source_document_id IS NOT NULL
            ON CONFLICT (project_id, document_id) DO NOTHING
            """
        )
    )

    # Backfill cycle baselines from review items/requirements.
    op.execute(
        sa.text(
            """
            INSERT INTO review_cycle_requirement_baselines (
                review_cycle_id, document_id, requirement_set_version_id
            )
            SELECT DISTINCT
                ri.review_cycle_id,
                req.document_id,
                req.requirement_set_version_id
            FROM review_items ri
            JOIN requirements req ON req.id = ri.requirement_id
            WHERE req.document_id IS NOT NULL
              AND req.requirement_set_version_id IS NOT NULL
            ON CONFLICT (review_cycle_id, document_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_baseline_migrations_organization_id", table_name="baseline_migrations")
    op.drop_index("ix_baseline_migrations_to_cycle_id", table_name="baseline_migrations")
    op.drop_index("ix_baseline_migrations_from_cycle_id", table_name="baseline_migrations")
    op.drop_index("ix_baseline_migrations_project_id", table_name="baseline_migrations")
    op.drop_table("baseline_migrations")

    op.drop_index(
        "ix_review_cycle_requirement_baselines_version_id",
        table_name="review_cycle_requirement_baselines",
    )
    op.drop_index(
        "ix_review_cycle_requirement_baselines_document_id",
        table_name="review_cycle_requirement_baselines",
    )
    op.drop_index(
        "ix_review_cycle_requirement_baselines_review_cycle_id",
        table_name="review_cycle_requirement_baselines",
    )
    op.drop_table("review_cycle_requirement_baselines")

    op.drop_index("ix_review_cycles_predecessor_cycle_id", table_name="review_cycles")
    op.drop_constraint("fk_review_cycles_predecessor_cycle_id", "review_cycles", type_="foreignkey")
    op.drop_column("review_cycles", "predecessor_cycle_id")

    op.drop_index(
        "ix_certification_project_requirement_baselines_version_id",
        table_name="certification_project_requirement_baselines",
    )
    op.drop_index(
        "ix_certification_project_requirement_baselines_document_id",
        table_name="certification_project_requirement_baselines",
    )
    op.drop_index(
        "ix_certification_project_requirement_baselines_project_id",
        table_name="certification_project_requirement_baselines",
    )
    op.drop_table("certification_project_requirement_baselines")

    op.drop_index("ix_requirements_source_requirement_id", table_name="requirements")
    op.drop_index("ix_requirements_requirement_set_version_id", table_name="requirements")
    op.drop_constraint("fk_requirements_source_requirement_id", "requirements", type_="foreignkey")
    op.drop_constraint(
        "fk_requirements_requirement_set_version_id",
        "requirements",
        type_="foreignkey",
    )
    op.drop_column("requirements", "source_requirement_id")
    op.drop_column("requirements", "requirement_set_version_id")

    op.drop_index(
        "uq_requirement_set_versions_current_per_document",
        table_name="requirement_set_versions",
    )
    op.drop_index(
        "ix_requirement_set_versions_based_on_version_id", table_name="requirement_set_versions"
    )
    op.drop_index(
        "ix_requirement_set_versions_organization_id", table_name="requirement_set_versions"
    )
    op.drop_index("ix_requirement_set_versions_document_id", table_name="requirement_set_versions")
    op.drop_table("requirement_set_versions")
