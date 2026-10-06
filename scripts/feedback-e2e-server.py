"""Disposable CAP + feedback test host. Never reads or resets an existing database.

Run with backend/.venv/bin/python scripts/feedback-e2e-server.py /path/to/page-feedback.
Only loopback is bound. All test databases disappear on normal shutdown.
"""
import os
import secrets
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn


def main():
    repository = Path(sys.argv[1]).resolve()
    if not (repository / "service/page_feedback/app.py").is_file():
        raise SystemExit("Pass the independent page-feedback repository path")
    port = int(os.environ.get("FEEDBACK_E2E_API_PORT", "18192"))
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend"))
    sys.path.insert(0, str(repository / "service"))
    with tempfile.TemporaryDirectory(prefix="cap-feedback-e2e-") as temporary:
        os.environ.update({
            "APP_ENV": "development", "SECRET_KEY": secrets.token_hex(32),
            "DATABASE_URL": f"sqlite+aiosqlite:///{temporary}/cap.sqlite3",
            "FEEDBACK_SERVICE_URL": f"http://127.0.0.1:{port}/_feedback-service",
            "FEEDBACK_SERVICE_KEY": secrets.token_hex(32),
            "FEEDBACK_PROJECT": "cap", "UPLOAD_DIR": temporary + "/uploads",
            "BACKUP_DIR": temporary + "/backups", "EMAIL_MODE": "log",
            "ALLOWED_HOSTS": '["127.0.0.1", "localhost"]',
        })
        from app.database import Base, async_session, engine
        from app.main import app
        from app.models import User, Jurisdiction
        from app.services.auth import hash_password
        from page_feedback.app import create_app

        service = create_app(Path(temporary) / "feedback.sqlite3",
                             os.environ["FEEDBACK_SERVICE_KEY"])

        @asynccontextmanager
        async def lifespan(_):
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_session() as db:
                db.add(Jurisdiction(code="test", name="Test jurisdiction", active=True))
                for role in ("admin", "contributor"):
                    db.add(User(email=f"{role}@feedback.test", full_name=f"Test {role}",
                                role=role, password_hash=hash_password("Disposable feedback fixture 42!")))
                await db.commit()
            async with service.router.lifespan_context(service):
                yield
            await engine.dispose()

        app.router.lifespan_context = lifespan
        app.mount("/_feedback-service", service)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
