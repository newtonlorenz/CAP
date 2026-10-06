#!/usr/bin/env python3
"""Rehearse image installation, upgrade and backup restoration using disposable Docker data."""

import argparse
import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTGRES = "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"


def compare_contents(before, after):
    """Check all original columns and bytes; migrations may add tables or columns."""
    for name, table in before["tables"].items():
        current = after["tables"].get(name)
        if current is None or not set(table["columns"]).issubset(current["columns"]):
            raise ValueError(f"Restore/upgrade removed table or columns: {name}")
        indices = [current["columns"].index(column) for column in table["columns"]]
        expected = sorted(json.dumps(row, sort_keys=True) for row in table["rows"])
        actual = sorted(json.dumps([row[i] for i in indices], sort_keys=True) for row in current["rows"])
        if expected != actual:
            raise ValueError(f"Restore/upgrade changed stored content: {name}")
    if before["uploads"] != after["uploads"]:
        raise ValueError("Restore/upgrade changed uploaded file paths or bytes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", required=True, help="Locally available candidate image")
    parser.add_argument("--previous-backend-image", help="Previous image for a real upgrade rehearsal")
    parser.add_argument("--context", default="default", help="Explicit Docker context")
    args = parser.parse_args()
    prefix = "cap-rehearsal-" + uuid.uuid4().hex[:12]
    docker = ["docker", "--context", args.context]
    containers, volumes = [], []
    network_created = False
    password = secrets.token_hex(20)
    secret = secrets.token_hex(32)
    fixture = ROOT / "backend/tests/release_lifecycle_fixture.py"

    def run(*arguments, check=True, timeout=180):
        return subprocess.run(
            [*docker, *arguments], text=True, capture_output=True, check=check, timeout=timeout,
        )

    def environment(database, bootstrap=False):
        values = {
            "APP_ENV": "test", "SECRET_KEY": secret, "AI_PROVIDER": "none", "EMAIL_MODE": "disabled",
            "DATABASE_URL": f"postgresql+asyncpg://cap_test:{password}@{database}:5432/cap_rehearsal",
            "REDIS_URL": "redis://127.0.0.1:6379/0", "FEEDBACK_SERVICE_URL": "", "FEEDBACK_SERVICE_KEY": "",
            "UPLOAD_DIR": "/app/uploads", "BACKUP_DIR": "/app/uploads/.system_backups",
            "FRONTEND_BASE_URL": "http://localhost", "ALLOWED_HOSTS": '["localhost","127.0.0.1"]',
        }
        if bootstrap:
            values.update(BOOTSTRAP_ADMIN_EMAIL="rehearsal@example.com", BOOTSTRAP_ADMIN_NAME="Synthetic operator",
                          BOOTSTRAP_ADMIN_PASSWORD=password)
        return [value for key, value in values.items() for value in ("-e", f"{key}={value}")]

    def start_database(name):
        run("run", "-d", "--name", name, "--network", prefix,
            "-e", "POSTGRES_USER=cap_test", "-e", f"POSTGRES_PASSWORD={password}",
            "-e", "POSTGRES_DB=cap_rehearsal", POSTGRES)
        containers.append(name)

    def start_app(name, image, database, volume, bootstrap=False):
        run("run", "-d", "--name", name, "--network", prefix, *environment(database, bootstrap),
            "-v", f"{volume}:/app/uploads", "-v", f"{fixture}:/tmp/release_fixture.py:ro", image)
        containers.append(name)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            health = run("exec", name, "python", "-m", "app.deploy", "check-http-health", check=False, timeout=15)
            if health.returncode == 0:
                return
            if run("inspect", "--format", "{{.State.Running}}", name).stdout.strip() != "true":
                raise RuntimeError(f"Rehearsal app stopped: {run('logs', name).stdout[-3000:]}")
            time.sleep(1)
        raise RuntimeError("Rehearsal app did not become healthy within 120 seconds")

    def fixture_action(name, action):
        output = run("exec", "-e", "PYTHONPATH=/app", name, "python", "/tmp/release_fixture.py", action).stdout
        return json.loads(output) if output.strip() else None

    try:
        image_ids = {}
        for image in {args.backend_image, args.previous_backend_image or args.backend_image}:
            image_ids[image] = run("image", "inspect", "--format", "{{.Id}}", image).stdout.strip()
        previous_image = args.previous_backend_image or args.backend_image
        distinct_upgrade = image_ids[previous_image] != image_ids[args.backend_image]
        run("network", "create", prefix)
        network_created = True
        for suffix in ("source", "restored"):
            volume = f"{prefix}-{suffix}-uploads"
            run("volume", "create", volume)
            volumes.append(volume)
            start_database(f"{prefix}-{suffix}-db")
        source_db, restored_db = f"{prefix}-source-db", f"{prefix}-restored-db"
        source_app = f"{prefix}-installed"
        start_app(source_app, args.previous_backend_image or args.backend_image, source_db, volumes[0], True)
        fixture_action(source_app, "seed")
        before = fixture_action(source_app, "fingerprint")
        backup = fixture_action(source_app, "backup")
        run("stop", source_app)

        upgraded_app = f"{prefix}-upgraded"
        start_app(upgraded_app, args.backend_image, source_db, volumes[0])
        compare_contents(before, fixture_action(upgraded_app, "fingerprint"))
        restore_command = [
            "run", "--rm", "--network", prefix, *environment(restored_db),
            "-v", f"{volumes[1]}:/app/uploads", "-v", f"{volumes[0]}:/backup:ro",
            "--entrypoint", "python", args.backend_image, "-m", "app.deploy",
            "restore-empty-installation", f"/backup/.system_backups/{backup['archive_filename']}",
        ]
        run(*restore_command)
        restored_app = f"{prefix}-restored"
        start_app(restored_app, args.backend_image, restored_db, volumes[1])
        compare_contents(before, fixture_action(restored_app, "fingerprint"))
        run("stop", restored_app)
        repeated = run(*restore_command, check=False)
        if repeated.returncode == 0 or "empty" not in (repeated.stderr + repeated.stdout).lower():
            raise RuntimeError("Restore into populated storage was not explicitly rejected")
        print(json.dumps({
            "status": "passed", "candidate": args.backend_image,
            "previous": previous_image,
            "upgrade_from_distinct_image": distinct_upgrade,
            "tables_compared": len(before["tables"]), "uploads_compared": len(before["uploads"]),
            "checks": ["installation", "upgrade" if distinct_upgrade else "same_image_restart",
                       "backup_restore", "populated_restore_rejection"],
        }, indent=2))
    except subprocess.CalledProcessError as exc:
        # Command arguments contain generated credentials. Only show the command's diagnostic output.
        raise SystemExit((exc.stderr or exc.stdout or "Docker rehearsal command failed")[-4000:]) from None
    finally:
        for name in reversed(containers):
            run("rm", "-f", name, check=False)
        for volume in volumes:
            run("volume", "rm", volume, check=False)
        if network_created:
            run("network", "rm", prefix, check=False)


if __name__ == "__main__":
    main()
