"""add optional jurisdiction pack metadata

Revision ID: 5a8d2c1f7e4b
Revises: 4c2b8f1a9d3e
Create Date: 2026-02-12 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5a8d2c1f7e4b"
down_revision: Union[str, None] = "4c2b8f1a9d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jurisdiction_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("parser_mode", sa.String(length=30), nullable=False),
        sa.Column(
            "supports_deterministic_import",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("coverage_notes", sa.Text(), nullable=True),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('published', 'scaffold', 'draft')",
            name="ck_market_packs_status",
        ),
        sa.CheckConstraint(
            "length(parser_mode) > 0",
            name="ck_market_packs_parser_mode",
        ),
        sa.ForeignKeyConstraint(["jurisdiction_id"], ["jurisdictions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jurisdiction_id"),
    )
    op.create_index("ix_market_packs_status", "market_packs", ["status"])



def downgrade() -> None:
    op.drop_index("ix_market_packs_status", table_name="market_packs")
    op.drop_table("market_packs")
