"""Add organisation-scoped preparation templates, cases, responses and shared evidence.

Revision ID: i20260929
Revises: h20260928
"""

from alembic import op
import sqlalchemy as sa

revision = "i20260929"
down_revision = "h20260928"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _org():
    return sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=True)


def _created_by():
    return sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False)


def _timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade():
    op.create_table(
        "preparation_templates",
        _id(),
        _org(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("fields_json", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created_by(),
        *_timestamps(),
    )
    op.create_table(
        "preparation_cases",
        _id(),
        _org(),
        sa.Column(
            "template_id", sa.Uuid(), sa.ForeignKey("preparation_templates.id"), nullable=False
        ),
        sa.Column("template_name", sa.String(255), nullable=False),
        sa.Column("template_revision", sa.Integer(), nullable=False),
        sa.Column("fields_json", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("jurisdiction_id", sa.Uuid(), sa.ForeignKey("jurisdictions.id"), nullable=False),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("certification_projects.id", ondelete="SET NULL")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        _created_by(),
        *_timestamps(),
    )
    op.create_table(
        "preparation_evidence",
        _id(),
        _org(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("link_url", sa.String(2000)),
        sa.Column("filename", sa.String(255)),
        sa.Column("file_path", sa.String(500)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_until", sa.Date()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        _created_by(),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "preparation_responses",
        _id(),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("preparation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(64), nullable=False),
        sa.Column("value_json", sa.Text()),
        sa.Column("not_applicable_reason", sa.Text()),
        sa.Column("accepted_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "reused_from_case_id",
            sa.Uuid(),
            sa.ForeignKey("preparation_cases.id", ondelete="SET NULL"),
        ),
        sa.Column("reused_from_field_key", sa.String(64)),
        sa.UniqueConstraint("case_id", "field_key", name="uq_preparation_response_case_field"),
    )
    op.create_table(
        "preparation_response_evidence",
        sa.Column(
            "response_id",
            sa.Uuid(),
            sa.ForeignKey("preparation_responses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid(), sa.ForeignKey("preparation_evidence.id"), primary_key=True
        ),
    )
    for table, columns in {
        "preparation_templates": ("organization_id", "kind"),
        "preparation_cases": (
            "organization_id",
            "template_id",
            "kind",
            "jurisdiction_id",
            "project_id",
            "owner_id",
            "status",
        ),
        "preparation_evidence": ("organization_id",),
        "preparation_responses": ("case_id", "reused_from_case_id"),
        "preparation_response_evidence": ("evidence_id",),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table, columns in {
        "preparation_response_evidence": ("evidence_id",),
        "preparation_responses": ("case_id", "reused_from_case_id"),
        "preparation_evidence": ("organization_id",),
        "preparation_cases": (
            "organization_id",
            "template_id",
            "kind",
            "jurisdiction_id",
            "project_id",
            "owner_id",
            "status",
        ),
        "preparation_templates": ("organization_id", "kind"),
    }.items():
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_table(table)
