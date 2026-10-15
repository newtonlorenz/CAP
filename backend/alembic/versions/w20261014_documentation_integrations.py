"""Persist source provenance, suggestion progress and immutable handover records."""

from alembic import op
import sqlalchemy as sa

revision = "w20261014"
down_revision = "v20261014"
branch_labels = None
depends_on = None


def upgrade():
    for name, columns, constraints in [
        (
            "documentation_imports",
            [
                sa.Column("input_fingerprint", sa.String(64), nullable=False),
                sa.Column("filename", sa.String(255), nullable=False),
                sa.Column("register_revision", sa.Integer(), nullable=False),
                sa.Column("preview_json", sa.Text(), nullable=False),
            ],
            [],
        ),
        (
            "documentation_import_rows",
            [
                sa.Column("input_fingerprint", sa.String(64), nullable=False),
                sa.Column("sheet", sa.String(255), nullable=False),
                sa.Column("row_number", sa.Integer(), nullable=False),
                sa.Column(
                    "expectation_id",
                    sa.Uuid(),
                    sa.ForeignKey("documentation_expectations.id"),
                    nullable=False,
                ),
                sa.Column("original_json", sa.Text(), nullable=False),
            ],
            [
                sa.UniqueConstraint(
                    "register_id",
                    "input_fingerprint",
                    "sheet",
                    "row_number",
                    name="uq_doc_import_source_row",
                )
            ],
        ),
        (
            "documentation_suggestion_runs",
            [
                sa.Column("register_revision", sa.Integer(), nullable=False),
                sa.Column("input_fingerprint", sa.String(64), nullable=False),
                sa.Column("settings_fingerprint", sa.String(64), nullable=False),
                sa.Column("policy_version", sa.String(40), nullable=False),
                sa.Column("provider", sa.String(30), nullable=False),
                sa.Column("model", sa.String(255), nullable=False),
                sa.Column("status", sa.String(30), nullable=False),
                sa.Column("cursor", sa.Integer(), nullable=False),
                sa.Column("last_error", sa.Text(), nullable=True),
                sa.Column("input_json", sa.Text(), nullable=False),
                sa.Column("suggestions_json", sa.Text(), nullable=False),
            ],
            [],
        ),
        (
            "documentation_snapshots",
            [
                sa.Column("register_revision", sa.Integer(), nullable=False),
                sa.Column("content_json", sa.Text(), nullable=False),
                sa.Column("evidence_ids_json", sa.Text(), nullable=False),
            ],
            [],
        ),
    ]:
        common = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "register_id",
                sa.Uuid(),
                sa.ForeignKey("documentation_registers.id"),
                nullable=False,
            ),
        ]
        if name != "documentation_import_rows":
            common += [
                sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            ]
        op.create_table(name, *common, *columns, *constraints)
        op.create_index(f"ix_{name}_register_id", name, ["register_id"])
    op.create_index(
        "ix_documentation_import_rows_expectation_id",
        "documentation_import_rows",
        ["expectation_id"],
    )


def downgrade():
    for name in (
        "documentation_snapshots",
        "documentation_suggestion_runs",
        "documentation_import_rows",
        "documentation_imports",
    ):
        op.drop_table(name)
