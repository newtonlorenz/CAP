"""Retain the typed immutable documentation source of submission artifacts."""
from alembic import op
import sqlalchemy as sa

revision = "x20261014"
down_revision = "w20261014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("submission_package_artifacts", sa.Column("documentation_snapshot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_package_artifact_documentation_snapshot", "submission_package_artifacts", "documentation_snapshots", ["documentation_snapshot_id"], ["id"])
    op.create_index("ix_submission_package_artifacts_documentation_snapshot_id", "submission_package_artifacts", ["documentation_snapshot_id"])

    op.create_table("documentation_snapshot_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("documentation_snapshots.id"), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("preparation_evidence.id"), nullable=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("certification_projects.id"), nullable=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("preparation_cases.id"), nullable=True),
        sa.Column("expectation_id", sa.Uuid(), sa.ForeignKey("documentation_expectations.id"), nullable=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("documentation_auditor_requests.id"), nullable=True),
        sa.CheckConstraint("(CASE WHEN evidence_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN case_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN expectation_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN request_id IS NOT NULL THEN 1 ELSE 0 END) = 1", name="ck_documentation_snapshot_typed_source"),
    )
    op.create_index("ix_documentation_snapshot_sources_snapshot_id", "documentation_snapshot_sources", ["snapshot_id"])


def downgrade():
    raise RuntimeError("Retain immutable documentation artifact sources; roll back application code without downgrading the schema")
