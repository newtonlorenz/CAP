from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import asyncpg
from sqlalchemy import select
from sqlalchemy.engine import make_url


def validate_config() -> None:
    from app.config import settings  # noqa: F401


async def wait_for_database(*, timeout_seconds: int, interval_seconds: float) -> None:
    from app.config import settings

    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        return

    host = str(url.host or "localhost")
    port = int(url.port or 5432)
    user = str(url.username or "postgres")
    database = str(url.database or "postgres")
    password = str(url.password or "")

    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            connection = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                timeout=min(5, timeout_seconds),
            )
            try:
                await connection.execute("SELECT 1")
            finally:
                await connection.close()
            return
        except Exception as exc:  # pragma: no cover - exercised through shell entrypoint
            last_error = exc
            await asyncio.sleep(interval_seconds)

    message = f"Database not ready after {timeout_seconds} seconds."
    if last_error is not None:
        message = f"{message} Last error: {last_error}"
    raise RuntimeError(message)


def frontend_host(frontend_base_url: str) -> str:
    parsed = urlparse(frontend_base_url.strip())
    return parsed.hostname or "localhost"


def check_http_health(
    *,
    frontend_base_url: str | None = None,
    health_url: str = "http://127.0.0.1:8000/api/v1/health",
    opener: Callable[..., object] = urlopen,
) -> None:
    from app.config import settings

    base_url = frontend_base_url if frontend_base_url is not None else settings.frontend_base_url
    host = frontend_host(base_url)
    request = Request(health_url, headers={"Host": host})

    try:
        with opener(request, timeout=5) as response:
            body = response.read()
            status_code = getattr(response, "status", 200)
    except Exception as exc:  # pragma: no cover - exercised through shell entrypoint
        raise RuntimeError(f"Internal HTTP health check failed for host {host}: {exc}") from exc

    if status_code != 200:
        raise RuntimeError(f"Internal HTTP health check returned {status_code} for host {host}.")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"Internal HTTP health check returned invalid JSON for host {host}."
        ) from exc

    if payload.get("status") != "ok":
        raise RuntimeError(f"Internal HTTP health check returned unexpected payload: {payload}")


async def bootstrap_status_for(
    *,
    bootstrap_admin_email: str,
    bootstrap_admin_name: str,
    bootstrap_admin_password: str,
    deploy_start_epoch: float | None = None,
    session_factory=None,
) -> str:
    if (
        not bootstrap_admin_email.strip()
        or not bootstrap_admin_name.strip()
        or not bootstrap_admin_password
    ):
        return "disabled"

    if session_factory is None:
        from app.database import async_session as session_factory

    from app.models.user import User

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == bootstrap_admin_email.strip())
        )
        user = result.scalar_one_or_none()

    if user is None:
        return "missing"

    if deploy_start_epoch is not None and user.created_at is not None:
        created_at = user.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at >= datetime.fromtimestamp(deploy_start_epoch - 5, tz=timezone.utc):
            return "ready"

    return "already-present"


async def bootstrap_status(*, deploy_start_epoch: float | None = None) -> str:
    from app.config import settings

    return await bootstrap_status_for(
        bootstrap_admin_email=settings.bootstrap_admin_email,
        bootstrap_admin_name=settings.bootstrap_admin_name,
        bootstrap_admin_password=settings.bootstrap_admin_password,
        deploy_start_epoch=deploy_start_epoch,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deployment helpers for CAP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("capabilities", help="Print non-secret installation capabilities.")
    subparsers.add_parser("validate-config", help="Validate runtime configuration.")
    subparsers.add_parser("check-http-health", help="Run the internal HTTP health check.")

    restore_parser = subparsers.add_parser(
        "restore-empty-installation",
        help="Restore a verified .capbak into an empty PostgreSQL database and uploads volume.",
    )
    restore_parser.add_argument("archive", type=Path)

    wait_parser = subparsers.add_parser("wait-for-db", help="Wait until the database is reachable.")
    wait_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("DB_WAIT_TIMEOUT_SECONDS", "90")),
        help="Maximum time to wait for the database.",
    )
    wait_parser.add_argument(
        "--interval-seconds",
        type=float,
        default=float(os.getenv("DB_WAIT_INTERVAL_SECONDS", "2")),
        help="Delay between connection attempts.",
    )

    bootstrap_parser = subparsers.add_parser(
        "bootstrap-status",
        help="Report bootstrap-admin state for deploy guidance.",
    )
    bootstrap_parser.add_argument(
        "--deploy-start-epoch",
        type=float,
        default=None,
        help="Unix epoch used to distinguish a newly created bootstrap user from an existing one.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "capabilities":
            from app.config import settings
            from app.services.capabilities import installation_capabilities
            print(json.dumps(installation_capabilities(settings), indent=2))
            return 0
        if args.command == "validate-config":
            validate_config()
            print("Runtime configuration validated.")
            return 0
        if args.command == "check-http-health":
            check_http_health()
            print("Internal HTTP health check passed.")
            return 0
        if args.command == "restore-empty-installation":
            from app.services.backups import restore_into_empty_installation

            manifest = restore_into_empty_installation(args.archive)
            print(f"Restored backup {manifest['backup_id']} into empty installation.")
            return 0
        if args.command == "wait-for-db":
            asyncio.run(
                wait_for_database(
                    timeout_seconds=args.timeout_seconds,
                    interval_seconds=args.interval_seconds,
                )
            )
            print("Database is reachable.")
            return 0
        if args.command == "bootstrap-status":
            print(asyncio.run(bootstrap_status(deploy_start_epoch=args.deploy_start_epoch)))
            return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
