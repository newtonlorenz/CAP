"""Allow each documentation row to choose an independent review scope."""
from alembic import op
import sqlalchemy as sa

revision = "aa20261015"
down_revision = "z20261014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documentation_expectations", sa.Column("review_cycle_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_documentation_expectation_review", "documentation_expectations", "review_cycles", ["review_cycle_id"], ["id"])
    op.create_index("ix_documentation_expectations_review_cycle_id", "documentation_expectations", ["review_cycle_id"])


def downgrade():
    raise RuntimeError("Retain documentation review associations; roll back application code without downgrading this additive schema")
