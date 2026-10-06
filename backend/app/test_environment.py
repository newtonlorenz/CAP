"""Fail closed before any database seeding by development/test tools."""

from pathlib import Path
from sqlalchemy.engine import make_url


def validate_test_database(environ) -> str:
    if environ.get("APP_ENV") != "test" or environ.get("CAP_ALLOW_TEST_SEED") != "1":
        raise RuntimeError("Test seeding requires APP_ENV=test and CAP_ALLOW_TEST_SEED=1.")
    raw = environ.get("E2E_DATABASE_URL", "")
    if not raw or raw != environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL must explicitly equal E2E_DATABASE_URL.")
    url = make_url(raw)
    if url.drivername.startswith("postgresql"):
        valid = url.host == "127.0.0.1" and url.port == 25489 and url.database == "cap_e2e"
    elif url.drivername == "sqlite+aiosqlite":
        workspace = environ.get("E2E_WORK_DIR")
        path = Path(url.database or "")
        valid = bool(
            workspace
            and path.is_absolute()
            and path.name == "cap_e2e.db"
            and path.resolve().parent == Path(workspace).resolve()
        )
    else:
        valid = False
    if not valid:
        raise RuntimeError(
            "Refusing to seed a database outside the dedicated disposable test target."
        )
    return raw
