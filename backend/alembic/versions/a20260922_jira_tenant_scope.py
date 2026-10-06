"""Scope Jira integration credentials to their configuring organisation."""

from alembic import op
import sqlalchemy as sa

revision = "a20260922"
down_revision = "a20260921"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jira_integrations", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jira_organization", "jira_integrations", "organizations", ["organization_id"], ["id"]
    )
    op.create_index(
        "ix_jira_integrations_organization_id", "jira_integrations", ["organization_id"]
    )
    op.execute(
        "UPDATE jira_integrations SET organization_id = users.organization_id FROM users WHERE users.id = jira_integrations.updated_by"
    )
    # Unattributed legacy credentials are disabled, not shared across companies.
    op.execute("UPDATE jira_integrations SET enabled = false WHERE updated_by IS NULL")


def downgrade():
    op.drop_index("ix_jira_integrations_organization_id", "jira_integrations")
    op.drop_constraint("fk_jira_organization", "jira_integrations", type_="foreignkey")
    op.drop_column("jira_integrations", "organization_id")
