"""Add ordered documentation sections and preserve full spreadsheet cell content."""
from alembic import op
import sqlalchemy as sa

revision = "y20261014"
down_revision = "x20261014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documentation_sections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("register_id", sa.Uuid(), sa.ForeignKey("documentation_registers.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(1024), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("register_id", "name_key", name="uq_documentation_section_name"),
        sa.CheckConstraint("position >= 0", name="ck_documentation_section_position"),
    )
    op.create_index("ix_documentation_sections_register_id", "documentation_sections", ["register_id"])
    op.add_column("documentation_expectations", sa.Column("section_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_documentation_expectation_section", "documentation_expectations", "documentation_sections", ["section_id"], ["id"])
    op.create_index("ix_documentation_expectations_section_id", "documentation_expectations", ["section_id"])
    op.add_column("documentation_expectations", sa.Column("required_documentation", sa.Text(), nullable=True))
    op.add_column("documentation_expectations", sa.Column("document_name", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError("Retain documentation sections and original cell content; roll back application code without downgrading this additive schema")
