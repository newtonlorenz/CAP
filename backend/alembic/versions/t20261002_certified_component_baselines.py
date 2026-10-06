"""Separate platform-certified baselines from unverified manual snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "t20261002"
down_revision = "s20261002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "component_baselines",
        sa.Column("certification_scope", sa.String(40), nullable=False, server_default="manual"),
    )
    op.add_column(
        "component_baselines",
        sa.Column("certification_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "component_baselines", sa.Column("certification_evidence", sa.Text(), nullable=True)
    )
    op.add_column(
        "component_baselines", sa.Column("certification_ato", sa.String(255), nullable=True)
    )
    op.add_column(
        "change_entry_components", sa.Column("baseline_scope_assessment", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("change_entry_components", "baseline_scope_assessment")
    for name in [
        "certification_ato",
        "certification_evidence",
        "certification_at",
        "certification_scope",
    ]:
        op.drop_column("component_baselines", name)
