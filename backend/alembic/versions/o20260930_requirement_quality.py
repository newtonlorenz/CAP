"""Durable optional Jev source quality runs and edit protection."""

import sqlalchemy as sa
from alembic import op

revision = "o20260930"
down_revision = "n20260930"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("extracted_requirements") as batch:
        batch.add_column(
            sa.Column(
                "quality_auto_editable", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    op.create_table(
        "requirement_quality_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "extraction_run_id", sa.Uuid(), sa.ForeignKey("extraction_runs.id", ondelete="CASCADE")
        ),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_set_versions.id", ondelete="CASCADE"),
        ),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("settings_revision", sa.Integer(), nullable=False),
        sa.Column("question_policy_version", sa.String(40), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("dispatch_after", sa.DateTime(timezone=True)),
        sa.Column("owner_token", sa.String(36)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_requirement_quality_runs_document_id", "requirement_quality_runs", ["document_id"]
    )
    op.create_table(
        "requirement_quality_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_quality_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requirement_id", sa.String(36)),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("source_page", sa.Integer()),
        sa.Column("source_excerpt", sa.Text()),
        sa.Column("source_span_id", sa.String(100)),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("auto_eligible", sa.Boolean(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_requirement_quality_findings_run_id", "requirement_quality_findings", ["run_id"]
    )


def downgrade():
    op.drop_table("requirement_quality_findings")
    op.drop_table("requirement_quality_runs")
    with op.batch_alter_table("extracted_requirements") as batch:
        batch.drop_column("quality_auto_editable")
