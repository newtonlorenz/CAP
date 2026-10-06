#!/usr/bin/env python3
"""Run browsers against an explicitly selected disposable PostgreSQL database."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.test_environment import validate_test_database


def main():
    env = dict(os.environ)
    env.update(
        APP_ENV="test",
        CAP_ALLOW_TEST_SEED="1",
        DATABASE_URL=env.get("E2E_DATABASE_URL", ""),
        AI_PROVIDER="none",
        EMAIL_MODE="disabled",
        OCR_ENABLED="false",
        FEEDBACK_SERVICE_URL="",
        FEEDBACK_SERVICE_KEY="",
        CELERY_TASK_ALWAYS_EAGER="false",
        REDIS_URL=env.get("E2E_REDIS_URL", "redis://127.0.0.1:25490/0"),
        CAP_PYTHON=sys.executable,
        VITE_API_PROXY_TARGET="http://127.0.0.1:18000",
        FRONTEND_BASE_URL="http://127.0.0.1:15173",
        CORS_ORIGINS='["http://127.0.0.1:15173"]',
        ALLOWED_HOSTS='["127.0.0.1","localhost"]',
    )
    validate_test_database(env)
    broker = urlparse(env["REDIS_URL"])
    if (broker.scheme, broker.hostname, broker.port, broker.path) != (
        "redis",
        "127.0.0.1",
        25490,
        "/0",
    ):
        raise RuntimeError(
            "The test broker must be the dedicated loopback Redis on port 25490, database 0."
        )
    if not env.get("E2E_ADMIN_PASSWORD") or not env.get("SECRET_KEY"):
        raise RuntimeError("Set E2E_ADMIN_PASSWORD and SECRET_KEY for this test run.")
    for port in (18000, 15173):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    work = ROOT / "tmp" / "e2e"
    work.mkdir(parents=True, exist_ok=True)
    env.update(
        UPLOAD_DIR=str(work / "uploads"),
        BACKUP_DIR=str(work / "backups"),
        BOOTSTRAP_ADMIN_EMAIL=env.get("E2E_ADMIN_EMAIL", "admin@example.com"),
        BOOTSTRAP_ADMIN_NAME="E2E Admin",
        BOOTSTRAP_ADMIN_PASSWORD=env["E2E_ADMIN_PASSWORD"],
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )
    with (work / "backend.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18000",
            ],
            cwd=ROOT / "backend",
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(f'Test backend failed; see {work / "backend.log"}')
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:18000/api/v1/health", timeout=1
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Test backend did not become healthy.")
            return subprocess.run(
                ["npm", "run", "test:e2e", "--", *sys.argv[1:]], cwd=ROOT / "frontend", env=env
            ).returncode
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    sys.exit(main())
