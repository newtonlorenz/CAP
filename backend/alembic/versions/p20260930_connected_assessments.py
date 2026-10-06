"""Connect change and maintenance assessments to pinned workflow scopes."""

import sqlalchemy as sa
from alembic import op

revision = "p20260930"
down_revision = "o20260930"
branch_labels = None
depends_on = None


def upgrade():
    for table, column, target in [
        ("review_cycles", "change_entry_id", "change_entries"),
        ("maintenance_plans", "certification_project_id", "certification_projects"),
    ]:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(column, sa.Uuid(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_{column}", target, [column], ["id"])
            batch.create_index(f"ix_{table}_{column}", [column])
    op.create_table(
        "change_requirement_impacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("change_entry_id", sa.Uuid(), sa.ForeignKey("change_entries.id"), nullable=False),
        sa.Column(
            "requirement_set_version_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_set_versions.id"),
            nullable=False,
        ),
        sa.Column("requirement_id", sa.Uuid(), sa.ForeignKey("requirements.id")),
        sa.Column(
            "certification_project_id", sa.Uuid(), sa.ForeignKey("certification_projects.id")
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
    )
    for column in ("change_entry_id", "requirement_set_version_id", "certification_project_id"):
        op.create_index(
            f"ix_change_requirement_impacts_{column}", "change_requirement_impacts", [column]
        )


def downgrade():
    op.drop_table("change_requirement_impacts")
    for table, column in [
        ("maintenance_plans", "certification_project_id"),
        ("review_cycles", "change_entry_id"),
    ]:
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_{column}")
            batch.drop_constraint(f"fk_{table}_{column}", type_="foreignkey")
            batch.drop_column(column)
