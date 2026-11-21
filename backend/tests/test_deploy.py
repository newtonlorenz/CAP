from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

import pytest

from app.deploy import bootstrap_status_for, check_http_health, frontend_host
from app.models.user import User

ROOT = Path(__file__).resolve().parents[2]


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


def test_deploy_common_env_value_handles_quotes_comments_and_last_override(tmp_path):
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=development # overridden below",
                'export APP_ENV="production" # inline comment',
                "FRONTEND_BASE_URL='https://cap.example.com' # quoted",
                "AI_PROVIDER=none   # unquoted comment",
            ]
        )
        + "\n"
    )
    script = f'. "{ROOT / "scripts/deploy/common.sh"}"; printf "%s|%s|%s" "$(env_value APP_ENV)" "$(env_value FRONTEND_BASE_URL)" "$(env_value AI_PROVIDER)"'
    result = subprocess.run(
        ["sh", "-c", script],
        env={"CAP_ENV_FILE": str(env_file), "PATH": "/usr/bin:/bin"},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == "production|https://cap.example.com|none"


def test_deploy_common_supports_compose_overlays_and_celery_healthcheck():
    prod_compose = (ROOT / "docker-compose.prod.yml").read_text()
    assert "celery -A app.tasks inspect ping" in prod_compose

    script = f'. "{ROOT / "scripts/deploy/common.sh"}"; require_compose_files; compose_file_list'
    result = subprocess.run(
        ["sh", "-c", script],
        env={
            "CAP_COMPOSE_OVERLAYS": "structured,site-content",
            "CAP_EDGE_MODE": "bundled",
            "PATH": "/usr/bin:/bin",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    files = [Path(line).name for line in result.stdout.strip().splitlines()]
    assert files == [
        "docker-compose.prod.yml",
        "docker-compose.edge.yml",
        "docker-compose.structured.yml",
        "docker-compose.site-content.yml",
    ]


def test_deploy_detect_auto_mode_classifies_frontend_backend_mixed_and_dirty_trees(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)

    (repo / "frontend").mkdir()
    (repo / "backend" / "app").mkdir(parents=True)
    (repo / "backend" / "alembic").mkdir(parents=True)
    (repo / "frontend" / "App.tsx").write_text("v1\n")
    (repo / "backend" / "app" / "main.py").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "initial"], check=True)
    base_rev = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    receipt = tmp_path / "deploy-receipt.json"
    receipt.write_text(f'{{"git_revision": "{base_rev}"}}\n')

    def run_detect() -> str:
        deploy_text = (ROOT / "scripts/deploy/deploy.sh").read_text()
        detect_fn = deploy_text.split("detect_auto_mode() {", 1)[1].split("\n}\n", 1)[0]
        script = (
            f'REPO_ROOT="{repo}"; RECEIPT_FILE="{receipt}"; '
            f'. "{ROOT / "scripts/deploy/common.sh"}" 2>/dev/null || true; '
            f'REPO_ROOT="{repo}"; RECEIPT_FILE="{receipt}"; '
            f"detect_auto_mode() {{\n{detect_fn}\n}}; detect_auto_mode"
        )
        res = subprocess.run(
            ["sh", "-c", script],
            env={"CAP_REPO_ROOT": str(repo), "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()

    # 1. Frontend-only commit -> frontend
    (repo / "frontend" / "App.tsx").write_text("v2\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-am", "fe", "-q"], check=True)
    assert run_detect() == "frontend"

    # 2. Dirty backend working tree on top of frontend commit -> full
    (repo / "backend" / "app" / "main.py").write_text("v2-dirty\n")
    assert run_detect() == "full"

    # 3. Committed mixed frontend + backend change since base_rev -> full
    subprocess.run(["git", "-C", str(repo), "commit", "-am", "be", "-q"], check=True)
    assert run_detect() == "full"

    # 4. Update receipt to current HEAD, then make backend-only change -> backend
    fe_be_rev = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    receipt.write_text(f'{{"git_revision": "{fe_be_rev}"}}\n')
    (repo / "backend" / "app" / "main.py").write_text("v3\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-am", "be-only", "-q"], check=True)
    assert run_detect() == "backend"

    # 5. Alembic migration change -> full
    (repo / "backend" / "alembic" / "001.py").write_text("migration\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "alembic", "-q"], check=True)
    assert run_detect() == "full"

