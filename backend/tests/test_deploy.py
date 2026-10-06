from datetime import datetime, timedelta, timezone

import pytest

from app.deploy import bootstrap_status_for, check_http_health, frontend_host
from app.models.user import User


class _FakeResponse:
    def __init__(self, *, status: int = 200, body: bytes = b'{"status":"ok"}'):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def test_frontend_host_uses_public_hostname():
    assert frontend_host("https://app.example.com:8443") == "app.example.com"


def test_check_http_health_uses_public_host_header():
    captured = {}

    def fake_opener(request, timeout=0):
        captured["host"] = request.get_header("Host")
        captured["timeout"] = timeout
        return _FakeResponse()

    check_http_health(
        frontend_base_url="https://app.example.com",
        opener=fake_opener,
    )

    assert captured == {"host": "app.example.com", "timeout": 5}


@pytest.mark.asyncio
async def test_bootstrap_status_for_reports_disabled_without_complete_settings():
    status = await bootstrap_status_for(
        bootstrap_admin_email="",
        bootstrap_admin_name="",
        bootstrap_admin_password="",
    )

    assert status == "disabled"


@pytest.mark.asyncio
async def test_bootstrap_status_for_reports_ready_for_new_user(setup_database):
    deploy_start = datetime.now(timezone.utc)

    async with setup_database() as session:
        session.add(
            User(
                email="admin@example.com",
                full_name="Admin User",
                password_hash="hashed",
                role="admin",
                active=True,
                created_at=deploy_start + timedelta(seconds=1),
            )
        )
        await session.commit()

    status = await bootstrap_status_for(
        bootstrap_admin_email="admin@example.com",
        bootstrap_admin_name="Admin User",
        bootstrap_admin_password="temporary-password",
        deploy_start_epoch=deploy_start.timestamp(),
        session_factory=setup_database,
    )

    assert status == "ready"


@pytest.mark.asyncio
async def test_bootstrap_status_for_reports_existing_user(setup_database):
    deploy_start = datetime.now(timezone.utc)

    async with setup_database() as session:
        session.add(
            User(
                email="admin@example.com",
                full_name="Admin User",
                password_hash="hashed",
                role="admin",
                active=True,
                created_at=deploy_start - timedelta(minutes=5),
            )
        )
        await session.commit()

    status = await bootstrap_status_for(
        bootstrap_admin_email="admin@example.com",
        bootstrap_admin_name="Admin User",
        bootstrap_admin_password="temporary-password",
        deploy_start_epoch=deploy_start.timestamp(),
        session_factory=setup_database,
    )

    assert status == "already-present"


@pytest.mark.asyncio
async def test_bootstrap_status_for_reports_missing_user(setup_database):
    status = await bootstrap_status_for(
        bootstrap_admin_email="admin@example.com",
        bootstrap_admin_name="Admin User",
        bootstrap_admin_password="temporary-password",
        deploy_start_epoch=datetime.now(timezone.utc).timestamp(),
        session_factory=setup_database,
    )

    assert status == "missing"
