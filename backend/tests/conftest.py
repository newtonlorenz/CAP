import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models import (  # noqa: F401 - imported to register with Base.metadata
    AuditLog,
    Document,
    EvidenceFile,
    EvidenceLink,
    EvidenceNote,
    ExtractedRequirement,
    JiraIntegration,
    Requirement,
    RequirementStatus,
    Jurisdiction,
    MarketPack,
    ReviewCycle,
    ReviewItem,
    ReviewItemComment,
    ReviewItemEvidenceFile,
    Snapshot,
    User,
)


@pytest.fixture(autouse=True)
async def setup_database(tmp_path, monkeypatch):
    """Create an isolated SQLite DB per test.

    Using a per-test DB avoids flaky teardown around FK cycles (drop_all ordering) and
    prevents data leaking between tests.
    """
    from app.config import settings
    monkeypatch.setattr(settings, "secret_key", "disposable-test-secret-000000000000000000")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    test_db_path = tmp_path / "test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{test_db_path}")
    test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield test_session
    finally:
        app.dependency_overrides.pop(get_db, None)
        await test_engine.dispose()


@pytest.fixture
async def client(setup_database):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client


@pytest.fixture
async def db_session(setup_database):
    Session = setup_database
    async with Session() as session:
        yield session


@pytest.fixture
async def default_jurisdiction(db_session, setup_database) -> Jurisdiction:
    jurisdiction = Jurisdiction(
        code="dk",
        name="Denmark",
        regulator_name="Example Authority",
        report_header_text="Example certification programme",
        active=True,
    )
    db_session.add(jurisdiction)
    await db_session.commit()
    await db_session.refresh(jurisdiction)
    return jurisdiction


@pytest.fixture(autouse=True)
async def seed_default_jurisdiction(default_jurisdiction):  # noqa: F811
    # Ensure every test has at least one jurisdiction available.
    return
