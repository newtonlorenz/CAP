"""Preserve legacy change records and add unresolved regulatory attestations."""

from alembic import op
import sqlalchemy as sa

revision = "s20261002"
down_revision = "r20261001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "component_registers",
        sa.Column("responsibility_role", sa.String(40), nullable=False, server_default="unknown"),
    )
    op.add_column("component_registers", sa.Column("programme_assurance", sa.JSON(), nullable=True))
    op.add_column(
        "components",
        sa.Column("regulatory_scope", sa.String(40), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "component_baselines", sa.Column("certification_reference", sa.Text(), nullable=True)
    )
    for name in ["compliance", "approved_scope", "blocking_assessment_ids"]:
        op.add_column("change_entries", sa.Column(name, sa.JSON(), nullable=True))
    op.add_column("change_entry_components", sa.Column("frozen_snapshot", sa.JSON(), nullable=True))
    op.add_column("change_entry_components", sa.Column("baseline_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_change_link_baseline",
        "change_entry_components",
        "component_baselines",
        ["baseline_id"],
        ["id"],
    )
    for name in ["planned_checksum_hash", "implemented_checksum_hash"]:
        op.add_column("change_entry_components", sa.Column(name, sa.String(255), nullable=True))


def downgrade():
    op.drop_constraint("fk_change_link_baseline", "change_entry_components", type_="foreignkey")
    for name in [
        "implemented_checksum_hash",
        "planned_checksum_hash",
        "baseline_id",
        "frozen_snapshot",
    ]:
        op.drop_column("change_entry_components", name)
    for name in ["blocking_assessment_ids", "approved_scope", "compliance"]:
        op.drop_column("change_entries", name)
    op.drop_column("component_baselines", "certification_reference")
    op.drop_column("components", "regulatory_scope")
    op.drop_column("component_registers", "programme_assurance")
    op.drop_column("component_registers", "responsibility_role")
