"""Flexible application workflow and immutable approval versions.

Revision ID: l20260929
Revises: k20260929
"""

import sqlalchemy as sa

from alembic import op

revision = "l20260929"
down_revision = "k20260929"
branch_labels = None
depends_on = None


def identity():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def user_column(name):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id"))


def application_column():
    return sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), nullable=False)


def upgrade():
    op.create_table(
        "applications",
        identity(),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id")),
        sa.Column("jurisdiction_id", sa.Uuid(), sa.ForeignKey("jurisdictions.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("applicant", sa.String(255)),
        sa.Column("authority", sa.String(255)),
        sa.Column("description", sa.Text()),
        user_column("owner_id"),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("outcome", sa.Text()),
        sa.Column("review_fingerprint", sa.String(64)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "application_components",
        identity(),
        application_column(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        user_column("owner_id"),
        sa.Column("due_date", sa.Date()),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("preparation_cases.id")),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("preparation_evidence.id")),
    )
    op.create_table(
        "application_followups",
        identity(),
        application_column(),
        sa.Column("question", sa.Text(), nullable=False),
        user_column("owner_id"),
        sa.Column("due_date", sa.Date()),
        sa.Column("response", sa.Text()),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "application_snapshots",
        identity(),
        application_column(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reference", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("archive", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint("application_id", "version", name="uq_application_snapshot_version"),
    )
    for table, columns in {
        "applications": ["organization_id", "jurisdiction_id", "status"],
        "application_components": ["application_id", "case_id"],
        "application_followups": ["application_id"],
        "application_snapshots": ["application_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in [
        "application_snapshots",
        "application_followups",
        "application_components",
        "applications",
    ]:
        op.drop_table(table)
