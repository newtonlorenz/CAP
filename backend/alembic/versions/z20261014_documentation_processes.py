"""Link documentation rows to existing process-owned evidence collections."""
from alembic import op
import sqlalchemy as sa

revision = "z20261014"
down_revision = "y20261014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documentation_registers", sa.Column("review_cycle_id", sa.Uuid(), nullable=True))
    op.add_column("documentation_registers", sa.Column("application_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_documentation_register_review", "documentation_registers", "review_cycles", ["review_cycle_id"], ["id"])
    op.create_foreign_key("fk_documentation_register_application", "documentation_registers", "applications", ["application_id"], ["id"])
    op.create_index("ix_documentation_registers_review_cycle_id", "documentation_registers", ["review_cycle_id"])
    op.create_index("ix_documentation_registers_application_id", "documentation_registers", ["application_id"])
    op.create_check_constraint("ck_documentation_register_one_process", "documentation_registers", "review_cycle_id IS NULL OR application_id IS NULL")
    op.add_column("documentation_expectations", sa.Column("process_review_fingerprint", sa.String(64), nullable=True))
    op.create_table("documentation_process_targets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("expectation_id", sa.Uuid(), sa.ForeignKey("documentation_expectations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), sa.ForeignKey("review_items.id"), nullable=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("preparation_cases.id"), nullable=True),
        sa.Column("field_key", sa.String(64), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("requirement_set_version_id", sa.Uuid(), sa.ForeignKey("requirement_set_versions.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(review_item_id IS NOT NULL AND case_id IS NULL AND field_key IS NULL) OR (review_item_id IS NULL AND case_id IS NOT NULL AND field_key IS NOT NULL)", name="ck_documentation_process_target_kind"),
        sa.UniqueConstraint("expectation_id", "review_item_id", name="uq_documentation_review_target"),
        sa.UniqueConstraint("expectation_id", "case_id", "field_key", name="uq_documentation_response_target"),
    )
    op.create_index("ix_documentation_process_targets_expectation_id", "documentation_process_targets", ["expectation_id"])
    for column, target in (("application_id", "applications"), ("review_cycle_id", "review_cycles"), ("review_item_id", "review_items"), ("review_file_id", "review_item_evidence_files")):
        op.add_column("documentation_snapshot_sources", sa.Column(column, sa.Uuid(), nullable=True))
        op.create_foreign_key(f"fk_documentation_snapshot_source_{column}", "documentation_snapshot_sources", target, [column], ["id"], ondelete="CASCADE" if column == "review_file_id" else None)
    op.drop_constraint("ck_documentation_snapshot_typed_source", "documentation_snapshot_sources", type_="check")
    columns = ("evidence_id", "project_id", "case_id", "expectation_id", "request_id", "application_id", "review_cycle_id", "review_item_id", "review_file_id")
    expression = " + ".join(f"CASE WHEN {column} IS NOT NULL THEN 1 ELSE 0 END" for column in columns)
    op.create_check_constraint("ck_documentation_snapshot_typed_source", "documentation_snapshot_sources", f"({expression}) = 1")


def downgrade():
    raise RuntimeError("Retain process mappings and historical source identities; roll back application code without downgrading this additive schema")
