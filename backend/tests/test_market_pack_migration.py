from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "5a8d2c1f7e4b_add_market_packs.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_5a8d2c1f7e4b", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_pre_migration_jurisdictions_schema(conn: sa.Connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "jurisdictions",
        metadata,
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("code", sa.String(length=20), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("regulator_name", sa.String(length=255), nullable=True),
        sa.Column("report_header_text", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    metadata.create_all(conn)


def _run_migration_upgrade(conn: sa.Connection) -> None:
    migration_module = _load_migration_module()
    context = MigrationContext.configure(conn)
    operations = Operations(context)
    migration_module.op = operations
    original_text = migration_module.sa.text

    # SQLite has no now() function; map it for this migration test harness.
    def sqlite_compatible_text(value):
        if value == "now()":
            return original_text("CURRENT_TIMESTAMP")
        return original_text(value)

    migration_module.sa.text = sqlite_compatible_text
    try:
        migration_module.upgrade()
    finally:
        migration_module.sa.text = original_text


def _seed_jurisdiction(conn: sa.Connection, code: str, name: str, regulator_name: str) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO jurisdictions (id, code, name, regulator_name, report_header_text, active)
            VALUES (:id, :code, :name, :regulator_name, NULL, 1)
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "code": code,
            "name": name,
            "regulator_name": regulator_name,
        },
    )


def test_fresh_pack_schema_does_not_seed_markets_or_packs():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _create_pre_migration_jurisdictions_schema(conn)
        _run_migration_upgrade(conn)
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM jurisdictions")) == 0
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM market_packs")) == 0


def test_pack_schema_preserves_operator_jurisdictions_without_installing_packs():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _create_pre_migration_jurisdictions_schema(conn)
        _seed_jurisdiction(conn, "area-a", "Operator jurisdiction", "Operator authority")
        _run_migration_upgrade(conn)
        assert conn.execute(sa.text("SELECT code, name FROM jurisdictions")).all() == [
            ("area-a", "Operator jurisdiction")
        ]
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM market_packs")) == 0
