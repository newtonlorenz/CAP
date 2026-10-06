"""Explicit content privacy and access teams, independent of account administration.

Revision ID: m20260930
Revises: l20260929
"""

import sqlalchemy as sa

from alembic import op

revision = "m20260930"
down_revision = "l20260929"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resource_access",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id")),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("resource_access.id")),
        sa.UniqueConstraint("resource_type", "resource_id"),
    )
    op.create_index("ix_resource_access_resource_id", "resource_access", ["resource_id"])
    op.create_table(
        "access_teams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "access_team_members",
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("access_teams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
    )
    op.create_table(
        "access_grants",
        sa.Column(
            "policy_id",
            sa.Uuid(),
            sa.ForeignKey("resource_access.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("subject_type", sa.String(10), primary_key=True),
        sa.Column("subject_id", sa.Uuid(), primary_key=True),
        sa.Column("permission", sa.String(20), primary_key=True),
    )


def downgrade():
    op.drop_table("access_grants")
    op.drop_table("access_team_members")
    op.drop_table("access_teams")
    op.drop_index("ix_resource_access_resource_id", table_name="resource_access")
    op.drop_table("resource_access")
