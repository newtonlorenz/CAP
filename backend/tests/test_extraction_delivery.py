"""Real delivery/recovery with disposable PostgreSQL, Redis and a stubbed work body."""

import asyncio
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Document, ExtractedRequirement, ExtractionRun, Jurisdiction, User
from app.models.organization import Organization
from app.services.extraction_jobs import dispatch_run
from app.tasks import celery_app
from app.tasks.extraction import extract_requirements_task

pytestmark = pytest.mark.skipif(
    not os.getenv("CAP_TEST_JOB_SERVICES"),
    reason="Explicit disposable PostgreSQL/Redis worker test required",
)


async def test_real_deliveries_recover_and_do_not_duplicate(tmp_path):
    database = os.environ["CAP_TEST_POSTGRES_URL"]
    url = make_url(database)
    assert (url.host, url.port, url.database) == ("127.0.0.1", 25489, "cap_e2e")
    redis = os.environ.get("E2E_REDIS_URL", "redis://127.0.0.1:25490/0")
    assert redis == "redis://127.0.0.1:25490/0"
    key = uuid.uuid4().hex
    queue = "cap_verification_" + key
    engine = create_async_engine(database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    previous = {
        name: getattr(celery_app.conf, name)
        for name in ["broker_url", "result_backend", "task_default_queue", "task_always_eager"]
    }
    celery_app.conf.update(
        broker_url=redis, result_backend=redis, task_default_queue=queue, task_always_eager=False
    )
    env = dict(
        os.environ,
        DATABASE_URL=database,
        REDIS_URL=redis,
        APP_ENV="test",
        AI_PROVIDER="none",
        EMAIL_MODE="disabled",
        OCR_ENABLED="false",
        CAP_JOB_FIXTURE_QUEUE=queue,
        CAP_JOB_FIXTURE_DIR=str(tmp_path),
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
    )
    worker = None
    try:
        async with sessions() as db:
            org = Organization(code=key, name="Disposable job verification")
            jurisdiction = Jurisdiction(code=key[:16], name="Synthetic jobs", regulator_name="Fixture")
            db.add_all([org, jurisdiction])
            await db.flush()
            user = User(
                email=key + "@example.test",
                full_name="Fixture",
                role="admin",
                password_hash="not-a-login",
                organization_id=org.id,
            )
            db.add(user)
            await db.commit()

        async def seed(prefix):
            async with sessions() as db:
                doc = Document(
                    organization_id=org.id,
                    jurisdiction_id=jurisdiction.id,
                    filename=prefix + key,
                    file_path=prefix + key,
                    document_type="synthetic_job",
                    uploaded_by=user.id,
                    status="pending_extraction",
                )
                db.add(doc)
                await db.flush()
                run = ExtractionRun(
                    document_id=doc.id, status="pending", ai_provider="local", ai_model="fixture"
                )
                db.add(run)
                await db.flush()
                doc.current_extraction_id = run.id
                await db.commit()
                return doc.id, run.id

        async def state(run_id):
            async with sessions() as db:
                run = await db.get(ExtractionRun, run_id)
                return run.status, run.attempt_count, run.error_message

        async def until(run_id, expected, seconds=35):
            async with asyncio.timeout(seconds):
                while True:
                    result = await state(run_id)
                    if result[0] in expected:
                        return result
                    if result[0] == "failed":
                        pytest.fail(f"Unexpected worker failure: {result}")
                    await asyncio.sleep(0.1)

        async def send(run_id, advance=False):
            async with sessions() as db:
                assert await dispatch_run(
                    db,
                    run_id,
                    now=datetime.now(timezone.utc) + timedelta(seconds=120 if advance else 0),
                )

        log_path = tmp_path / "worker.log"
        with log_path.open("w") as log:
            worker = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name("job_worker_fixture.py"))],
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            # A real broker delivery, followed by two duplicate deliveries while active.
            doc_id, run_id = await seed("slow_")
            await send(run_id)
            await until(run_id, {"running"})
            await asyncio.to_thread(extract_requirements_task.delay, str(doc_id), str(run_id))
            await asyncio.to_thread(extract_requirements_task.delay, str(doc_id), str(run_id))
            assert (await until(run_id, {"completed"}))[1] == 1
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ExtractedRequirement)
                        .where(ExtractedRequirement.extraction_run_id == run_id)
                    )
                    == 1
                )
            # Persist a transient failure, then dispatch its durable retry intent.
            _, retry_id = await seed("fail_once_")
            await send(retry_id)
            async with asyncio.timeout(35):
                while True:
                    value = await state(retry_id)
                    if value[0] == "pending" and value[1] == 1:
                        break
                    if value[0] == "failed":
                        pytest.fail(str(value))
                    await asyncio.sleep(0.1)
            await send(retry_id, advance=True)
            assert (await until(retry_id, {"completed"}))[1] == 2
            # Kill a prefork child once; Redis/Celery must redeliver the unacked job.
            _, crash_id = await seed("crash_once_")
            await send(crash_id)
            assert (await until(crash_id, {"completed"}, seconds=55))[1] == 2
            # Cancel during in-flight work. A late result must not overwrite it.
            cancel_doc, cancel_id = await seed("cancel_")
            await send(cancel_id)
            await until(cancel_id, {"running"})
            async with sessions() as db:
                doc = await db.scalar(
                    select(Document).where(Document.id == cancel_doc).with_for_update()
                )
                run = await db.get(ExtractionRun, cancel_id)
                run.status = "cancelled"
                run.completed_at = datetime.now(timezone.utc)
                doc.status = "extraction_cancelled"
                await db.commit()
            await asyncio.sleep(2.5)
            async with sessions() as db:
                assert (await db.get(ExtractionRun, cancel_id)).status == "cancelled"
                assert (await db.get(Document, cancel_doc)).status == "extraction_cancelled"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ExtractedRequirement)
                        .where(ExtractedRequirement.extraction_run_id == cancel_id)
                    )
                    == 0
                )
    except BaseException:
        if "log_path" in locals() and log_path.exists():
            print(log_path.read_text()[-12000:])
        raise
    finally:
        if worker is not None:
            worker.terminate()
            try:
                await asyncio.to_thread(worker.wait, timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(worker.pid, signal.SIGKILL)
                await asyncio.to_thread(worker.wait, timeout=5)
        celery_app.conf.update(**previous)
        await engine.dispose()
