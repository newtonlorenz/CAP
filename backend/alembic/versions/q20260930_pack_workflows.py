"""Guided application packs, private form originals and assurance metadata."""

import sqlalchemy as sa

from alembic import op

revision = "q20260930"
down_revision = "p20260930"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_market_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("jurisdiction_id", sa.Uuid(), sa.ForeignKey("jurisdictions.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "organization_id",
            "jurisdiction_id",
            name="uq_application_market_profile_org_jurisdiction",
        ),
    )
    with op.batch_alter_table("applications") as batch:
        batch.add_column(sa.Column("profile_snapshot_json", sa.Text()))
        batch.add_column(sa.Column("setup_answers_json", sa.Text()))
    with op.batch_alter_table("application_components") as batch:
        batch.add_column(sa.Column("profile_item_key", sa.String(100)))
    with op.batch_alter_table("preparation_cases") as batch:
        batch.alter_column("template_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(
            sa.Column("original_evidence_ids_json", sa.Text(), nullable=False, server_default="[]")
        )
    with op.batch_alter_table("certification_projects") as batch:
        batch.add_column(sa.Column("assurance_type", sa.String(20)))
        batch.add_column(sa.Column("provider_name", sa.String(255)))
        batch.add_column(sa.Column("engagement_reference", sa.String(255)))
        batch.add_column(sa.Column("assurance_scope", sa.Text()))
        batch.add_column(sa.Column("system_version", sa.String(255)))
        batch.add_column(sa.Column("scheduled_test_date", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("actual_test_date", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("report_reference", sa.String(255)))
        batch.add_column(sa.Column("report_outcome", sa.String(30)))
        batch.add_column(sa.Column("report_issued_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("report_link", sa.String(2048)))


def downgrade():
    private_count = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM preparation_cases WHERE template_id IS NULL"))
        .scalar_one()
    )
    if private_count:
        raise RuntimeError(
            "Cannot downgrade q20260930 while private preparation cases exist; "
            "export or migrate them explicitly before restoring template_id NOT NULL"
        )
    with op.batch_alter_table("certification_projects") as batch:
        for name in (
            "report_link",
            "report_issued_at",
            "report_outcome",
            "report_reference",
            "actual_test_date",
            "scheduled_test_date",
            "system_version",
            "assurance_scope",
            "engagement_reference",
            "provider_name",
            "assurance_type",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("preparation_cases") as batch:
        batch.drop_column("original_evidence_ids_json")
        batch.alter_column("template_id", existing_type=sa.Uuid(), nullable=False)
    with op.batch_alter_table("application_components") as batch:
        batch.drop_column("profile_item_key")
    with op.batch_alter_table("applications") as batch:
        batch.drop_column("setup_answers_json")
        batch.drop_column("profile_snapshot_json")
    op.drop_table("application_market_profiles")
