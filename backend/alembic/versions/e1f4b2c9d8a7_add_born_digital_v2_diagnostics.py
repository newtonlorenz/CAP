"""add born-digital v2 diagnostics

Revision ID: e1f4b2c9d8a7
Revises: d7a1c3e9f4b2
Create Date: 2026-02-19 12:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1f4b2c9d8a7"
down_revision = "d7a1c3e9f4b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("extraction_runs", sa.Column("parseability_score", sa.Float(), nullable=True))
    op.add_column("extraction_runs", sa.Column("fallback_trigger_reason", sa.Text(), nullable=True))
    op.add_column("extraction_runs", sa.Column("strategy_counts", sa.JSON(), nullable=True))
    op.add_column(
        "extraction_runs",
        sa.Column(
            "diagnostics_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("extraction_runs", "diagnostics_available", server_default=None)

    op.create_table(
        "extraction_run_diagnostics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("extraction_run_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("parseability_score", sa.Float(), nullable=True),
        sa.Column("fallback_trigger_reason", sa.Text(), nullable=True),
        sa.Column("strategy_counts", sa.JSON(), nullable=True),
        sa.Column("decision_payload", sa.JSON(), nullable=True),
        sa.Column("page_metrics", sa.JSON(), nullable=True),
        sa.Column("canonical_blocks", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("extraction_run_id"),
    )
    op.create_index(
        "ix_extraction_run_diagnostics_document_id",
        "extraction_run_diagnostics",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_run_diagnostics_created_at",
        "extraction_run_diagnostics",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_extraction_run_diagnostics_created_at", table_name="extraction_run_diagnostics"
    )
    op.drop_index(
        "ix_extraction_run_diagnostics_document_id", table_name="extraction_run_diagnostics"
    )
    op.drop_table("extraction_run_diagnostics")

    op.drop_column("extraction_runs", "diagnostics_available")
    op.drop_column("extraction_runs", "strategy_counts")
    op.drop_column("extraction_runs", "fallback_trigger_reason")
    op.drop_column("extraction_runs", "parseability_score")
