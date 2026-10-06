"""Allow operator-defined parser metadata without rewriting existing records.

Revision ID: g20260926
Revises: s20260924
"""

from alembic import op
import sqlalchemy as sa

revision = "g20260926"
down_revision = "s20260924"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "components", sa.Column("public_cloud_certification", sa.String(255), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE components SET public_cloud_certification = 'ISO/IEC 27001' WHERE public_cloud_iso27001 = true"
        )
    )
    constraints = sa.inspect(op.get_bind()).get_check_constraints("market_packs")
    if any(item["name"] == "ck_market_packs_parser_mode" for item in constraints):
        with op.batch_alter_table("market_packs") as batch:
            batch.drop_constraint("ck_market_packs_parser_mode", type_="check")


def downgrade():
    # Preserve operator-defined metadata on downgrade.
    op.drop_column("components", "public_cloud_certification")
