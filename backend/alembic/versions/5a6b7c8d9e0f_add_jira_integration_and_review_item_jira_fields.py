"""add jira integration and review item jira fields

Revision ID: 5a6b7c8d9e0f
Revises: 4c2b8f1a9d3e
Create Date: 2026-02-12 08:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5a6b7c8d9e0f"
down_revision = "4c2b8f1a9d3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jira_integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("project_key", sa.String(length=50), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=False),
        sa.Column("api_token_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=30), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("review_items", sa.Column("jira_issue_key", sa.String(length=50), nullable=True))
    op.add_column("review_items", sa.Column("jira_issue_url", sa.String(length=500), nullable=True))
    op.add_column("review_items", sa.Column("jira_status", sa.String(length=120), nullable=True))
    op.add_column("review_items", sa.Column("jira_summary", sa.Text(), nullable=True))
    op.add_column("review_items", sa.Column("jira_assignee", sa.String(length=255), nullable=True))
    op.add_column("review_items", sa.Column("jira_priority", sa.String(length=120), nullable=True))
    op.add_column(
        "review_items",
        sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "review_items",
        sa.Column("jira_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("review_items", sa.Column("jira_sync_error", sa.Text(), nullable=True))

    op.create_index(
        "ix_review_items_review_cycle_id_jira_issue_key",
        "review_items",
        ["review_cycle_id", "jira_issue_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_review_items_review_cycle_id_jira_issue_key",
        table_name="review_items",
    )

    op.drop_column("review_items", "jira_sync_error")
    op.drop_column("review_items", "jira_synced_at")
    op.drop_column("review_items", "jira_updated_at")
    op.drop_column("review_items", "jira_priority")
    op.drop_column("review_items", "jira_assignee")
    op.drop_column("review_items", "jira_summary")
    op.drop_column("review_items", "jira_status")
    op.drop_column("review_items", "jira_issue_url")
    op.drop_column("review_items", "jira_issue_key")

    op.drop_table("jira_integrations")
