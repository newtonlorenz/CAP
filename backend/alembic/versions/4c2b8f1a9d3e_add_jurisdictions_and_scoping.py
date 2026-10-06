"""add jurisdictions and scope core entities

Revision ID: 4c2b8f1a9d3e
Revises: 339b623fb4ec
Create Date: 2026-02-07 00:00:00.000000

"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c2b8f1a9d3e"
down_revision: Union[str, None] = "339b623fb4ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jurisdictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("regulator_name", sa.String(length=255), nullable=True),
        sa.Column("report_header_text", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    jurisdictions = sa.table(
        "jurisdictions",
        sa.Column("id", sa.Uuid()),
        sa.Column("code", sa.String(length=20)),
        sa.Column("name", sa.String(length=255)),
        sa.Column("regulator_name", sa.String(length=255)),
        sa.Column("report_header_text", sa.Text()),
        sa.Column("active", sa.Boolean()),
    )
    legacy_id = uuid.uuid4()
    conn = op.get_bind()
    has_records = any(
        conn.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None
        for table in ("documents", "requirements", "review_cycles")
    )
    if has_records:
        op.bulk_insert(jurisdictions, [{
            "id": legacy_id, "code": "legacy", "name": "Imported records",
            "active": True,
        }])

    # Documents
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("jurisdiction_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_documents_jurisdiction_id_jurisdictions",
            "jurisdictions",
            ["jurisdiction_id"],
            ["id"],
        )
        batch_op.create_index("ix_documents_jurisdiction_id", ["jurisdiction_id"], unique=False)
    op.execute(sa.text("UPDATE documents SET jurisdiction_id = :legacy_id").bindparams(legacy_id=legacy_id))
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column("jurisdiction_id", nullable=False)

    # Requirements
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.add_column(sa.Column("jurisdiction_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_requirements_jurisdiction_id_jurisdictions",
            "jurisdictions",
            ["jurisdiction_id"],
            ["id"],
        )
        batch_op.create_index("ix_requirements_jurisdiction_id", ["jurisdiction_id"], unique=False)
    op.execute(sa.text("UPDATE requirements SET jurisdiction_id = :legacy_id").bindparams(legacy_id=legacy_id))
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.alter_column("jurisdiction_id", nullable=False)

    # Review cycles
    with op.batch_alter_table("review_cycles") as batch_op:
        batch_op.add_column(sa.Column("jurisdiction_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_review_cycles_jurisdiction_id_jurisdictions",
            "jurisdictions",
            ["jurisdiction_id"],
            ["id"],
        )
        batch_op.create_index("ix_review_cycles_jurisdiction_id", ["jurisdiction_id"], unique=False)
    op.execute(sa.text("UPDATE review_cycles SET jurisdiction_id = :legacy_id").bindparams(legacy_id=legacy_id))
    with op.batch_alter_table("review_cycles") as batch_op:
        batch_op.alter_column("jurisdiction_id", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("review_cycles") as batch_op:
        batch_op.drop_index("ix_review_cycles_jurisdiction_id")
        batch_op.drop_constraint(
            "fk_review_cycles_jurisdiction_id_jurisdictions", type_="foreignkey"
        )
        batch_op.drop_column("jurisdiction_id")

    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_index("ix_requirements_jurisdiction_id")
        batch_op.drop_constraint(
            "fk_requirements_jurisdiction_id_jurisdictions", type_="foreignkey"
        )
        batch_op.drop_column("jurisdiction_id")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_jurisdiction_id")
        batch_op.drop_constraint("fk_documents_jurisdiction_id_jurisdictions", type_="foreignkey")
        batch_op.drop_column("jurisdiction_id")

    op.drop_table("jurisdictions")
