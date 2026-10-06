import asyncio
import secrets
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.models.user import User
from app.services.extraction_jobs import dispatch_run, reconcile_jobs, utcnow
from app.tasks import extraction


@pytest.fixture
async def job(setup_database, default_jurisdiction, monkeypatch):
    factory = setup_database
    async with factory() as db:
        user = User(email="extractor@test.com", password_hash="unused", full_name="Extractor", role="admin")
        db.add(user)
        await db.flush()
        doc = Document(jurisdiction_id=default_jurisdiction.id, filename="synthetic.pdf",
                       document_type="standard", status="pending_extraction",
                       file_path="synthetic.pdf", uploaded_by=user.id)
        db.add(doc)
        await db.flush()
        run = ExtractionRun(document_id=doc.id, status="pending", ai_provider="local", ai_model="local")
        db.add(run)
        await db.flush()
        doc.current_extraction_id = run.id
        await db.commit()
        doc_id, run_id = doc.id, run.id

    monkeypatch.setattr(extraction, "_get_session_factory", lambda: factory)

    async def preprocess(*args):
        return SimpleNamespace(
            cleanup_paths=[], pages=[{"page_number": 1, "text": "synthetic"}],
            ocr_applied=False, ocr_pages=0, warning_count=0, family_fingerprint=None,
            parseability_score=1.0, fallback_trigger_reason=None, diagnostics={},
            low_quality_pages=[], page_quality=[],
        )

    async def parse_requirements(**kwargs):
        return [{"reference_id": "1", "text": "The operator shall keep records.",
                 "requirement_type": "mandatory", "page_number": 1}]

    async def no_event(*args, **kwargs):
        return None

    monkeypatch.setattr(extraction, "bounded_preprocess", preprocess)
    monkeypatch.setattr(extraction, "PdfParser", lambda: SimpleNamespace(parse_requirements=parse_requirements))
    monkeypatch.setattr(extraction, "publish_event", no_event)
    return factory, doc_id, run_id


async def _state(factory, doc_id, run_id):
    async with factory() as db:
        doc = await db.get(Document, doc_id)
        run = await db.get(ExtractionRun, run_id)
        count = await db.scalar(select(func.count(ExtractedRequirement.id)).where(
            ExtractedRequirement.extraction_run_id == run_id))
        return doc.status, run.status, run.attempt_count, count


@pytest.mark.asyncio
async def test_transient_failure_recovers_with_durable_attempt(job, monkeypatch):
    factory, doc_id, run_id = job
    original = extraction.bounded_preprocess
    calls = 0

    async def fail_once(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("transient preprocessing error")
        return await original(*args)

    monkeypatch.setattr(extraction, "bounded_preprocess", fail_once)
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("pending_extraction", "pending", 1, 0)
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        assert run.dispatch_after is not None
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("extracted", "completed", 2, 1)


async def test_vision_receives_remaining_run_deadline(job, monkeypatch):
    factory, doc_id, run_id = job
    original_preprocess = extraction.bounded_preprocess

    async def low_quality_page(*args, **kwargs):
        result = await original_preprocess(*args, **kwargs)
        result.page_quality = [SimpleNamespace(page_number=1, is_low_quality=True)]
        return result

    async def no_text_candidates(**kwargs):
        return []

    deadlines = []

    async def vision_fallback(**kwargs):
        deadlines.append(kwargs["deadline"])
        return SimpleNamespace(items=[], warnings=[])

    monkeypatch.setattr(extraction, "bounded_preprocess", low_quality_page)
    monkeypatch.setattr(extraction, "PdfParser", lambda: SimpleNamespace(parse_requirements=no_text_candidates))
    monkeypatch.setattr(extraction, "parse_requirements_from_page_image", vision_fallback)
    monkeypatch.setattr(extraction.ProviderConfig, "from_settings", classmethod(
        lambda cls, *args, **kwargs: extraction.ProviderConfig("openai", "test", "test", 1)
    ))
    monkeypatch.setattr(extraction.settings, "vision_fallback_enabled", True)
    monkeypatch.setattr(extraction.settings, "extraction_timeout_minutes", 0.1)
    monkeypatch.setattr(extraction.settings, "extraction_page_timeout_seconds", 300)

    start = asyncio.get_running_loop().time()
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("extracted", "completed", 1, 0)
    assert len(deadlines) == 1
    assert 0 < deadlines[0] - start < 7


async def test_vision_render_timeout_marks_page_timed_out(job, monkeypatch):
    factory, doc_id, run_id = job
    original_preprocess = extraction.bounded_preprocess

    async def low_quality_page(*args, **kwargs):
        result = await original_preprocess(*args, **kwargs)
        result.page_quality = [SimpleNamespace(page_number=1, is_low_quality=True)]
        return result

    async def no_text_candidates(**kwargs):
        return []

    async def timed_out_render(**kwargs):
        raise TimeoutError("Vision page deadline exceeded")

    monkeypatch.setattr(extraction, "bounded_preprocess", low_quality_page)
    monkeypatch.setattr(extraction, "PdfParser", lambda: SimpleNamespace(parse_requirements=no_text_candidates))
    monkeypatch.setattr(extraction, "parse_requirements_from_page_image", timed_out_render)
    monkeypatch.setattr(extraction.ProviderConfig, "from_settings", classmethod(
        lambda cls, *args, **kwargs: extraction.ProviderConfig("openai", "test", "test", 1)
    ))
    monkeypatch.setattr(extraction.settings, "vision_fallback_enabled", True)
    await extraction._extract(str(doc_id), str(run_id))

    assert await _state(factory, doc_id, run_id) == ("extraction_failed", "timed_out", 1, 0)
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        assert run.error_page == 1


@pytest.mark.asyncio
async def test_worker_loss_redelivery_and_duplicate_are_single_effective_run(job, monkeypatch):
    factory, doc_id, run_id = job
    entered, release = asyncio.Event(), asyncio.Event()

    async def waiting_parse(**kwargs):
        entered.set()
        await release.wait()
        return [{"reference_id": "1", "text": "shall keep records", "requirement_type": "mandatory"}]

    monkeypatch.setattr(extraction, "PdfParser", lambda: SimpleNamespace(parse_requirements=waiting_parse))
    first = asyncio.create_task(extraction._extract(str(doc_id), str(run_id)))
    await asyncio.wait_for(entered.wait(), 5)
    await extraction._extract(str(doc_id), str(run_id))
    assert (await _state(factory, doc_id, run_id))[2] == 1
    release.set()
    await first
    assert await _state(factory, doc_id, run_id) == ("extracted", "completed", 1, 1)

    # A killed worker leaves running state; release of its connection lock
    # allows redelivery to reclaim and reset partial results.
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        doc = await db.get(Document, doc_id)
        run.status = "running"
        doc.status = "extracting"
        await db.commit()
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("extracted", "completed", 2, 1)


@pytest.mark.asyncio
async def test_cancel_during_last_page_discards_result(job, monkeypatch):
    factory, doc_id, run_id = job
    entered, release = asyncio.Event(), asyncio.Event()

    async def waiting_parse(**kwargs):
        entered.set()
        await release.wait()
        return [{"reference_id": "1", "text": "shall keep records", "requirement_type": "mandatory"}]

    monkeypatch.setattr(extraction, "PdfParser", lambda: SimpleNamespace(parse_requirements=waiting_parse))
    worker = asyncio.create_task(extraction._extract(str(doc_id), str(run_id)))
    await asyncio.wait_for(entered.wait(), 5)
    async with factory() as db:
        doc = await db.get(Document, doc_id)
        run = await db.get(ExtractionRun, run_id)
        doc.status = "extraction_cancelled"
        run.status = "cancelled"
        await db.commit()
    release.set()
    await worker
    assert await _state(factory, doc_id, run_id) == ("extraction_cancelled", "cancelled", 1, 0)


@pytest.mark.asyncio
async def test_ambiguous_publish_reconciles_and_terminal_run_is_safe(job, monkeypatch):
    factory, doc_id, run_id = job
    calls = []

    def ambiguous(*args):
        calls.append(args)
        if len(calls) == 1:
            raise OSError("ack lost after broker accepted task")

    monkeypatch.setattr(extraction.extract_requirements_task, "delay", ambiguous)
    async with factory() as db:
        assert not await dispatch_run(db, run_id)
    assert len(calls) == 1
    assert await reconcile_jobs(factory, now=utcnow() + timedelta(seconds=20)) == 1
    assert len(calls) == 2
    await extraction._extract(str(doc_id), str(run_id))
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("extracted", "completed", 1, 1)


@pytest.mark.asyncio
async def test_attempt_limit_fails_current_run_without_running_parser(job, monkeypatch):
    factory, doc_id, run_id = job
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        run.attempt_count = 4
        await db.commit()

    async def forbidden(*args):
        raise AssertionError("parser must not run")

    monkeypatch.setattr(extraction, "bounded_preprocess", forbidden)
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("extraction_failed", "failed", 4, 0)


@pytest.mark.asyncio
async def test_superseded_run_cannot_change_new_run_or_document(job, monkeypatch):
    factory, doc_id, run_id = job
    async with factory() as db:
        doc = await db.get(Document, doc_id)
        old = await db.get(ExtractionRun, run_id)
        old.status = "running"
        newer = ExtractionRun(document_id=doc_id, status="pending", ai_provider="local", ai_model="local")
        db.add(newer)
        await db.flush()
        doc.current_extraction_id = newer.id
        await db.commit()
        newer_id = newer.id

    async def forbidden(*args):
        raise AssertionError("superseded run must not parse")

    monkeypatch.setattr(extraction, "bounded_preprocess", forbidden)
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("pending_extraction", "running", 0, 0)
    async with factory() as db:
        doc = await db.get(Document, doc_id)
        assert doc.current_extraction_id == newer_id
    monkeypatch.setattr(extraction.extract_requirements_task, "delay", lambda *args: None)
    assert await reconcile_jobs(factory, now=utcnow() + timedelta(hours=2), limit=1) == 1


@pytest.mark.asyncio
async def test_lost_ack_after_completion_does_not_reschedule_terminal_run(job, monkeypatch):
    factory, doc_id, run_id = job

    def accepted_then_ack_lost(*args):
        async def complete():
            async with factory() as db:
                doc = await db.get(Document, doc_id)
                run = await db.get(ExtractionRun, run_id)
                doc.status = "extracted"
                run.status = "completed"
                await db.commit()

        asyncio.run(complete())
        raise OSError("ack lost")

    monkeypatch.setattr(extraction.extract_requirements_task, "delay", accepted_then_ack_lost)
    before = utcnow()
    async with factory() as db:
        assert not await dispatch_run(db, run_id, now=before)
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        assert run.status == "completed"
        assert run.dispatch_after.replace(tzinfo=before.tzinfo) == before + timedelta(seconds=60)


async def test_retired_parser_run_does_not_silently_change_implementation(job, monkeypatch):
    factory, doc_id, run_id = job
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        run.ai_provider = "deterministic"
        run.ai_model = "retired_template"
        run.pipeline_version = "born_digital_v3"
        await db.commit()

    async def forbidden(*args, **kwargs):
        raise AssertionError("Retired runs must not reach PDF parsing")

    monkeypatch.setattr(extraction, "bounded_preprocess", forbidden)
    for _ in range(4):
        await extraction._extract(str(doc_id), str(run_id))
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        assert run.status == "failed"
        assert "retired parser" in run.error_message
        assert await db.scalar(select(func.count(ExtractedRequirement.id))) == 0


async def test_worker_uses_saved_credentials_and_preserves_queued_model(job, monkeypatch):
    from app.schemas.installation_settings import AIUpdate
    from app.services.installation_settings import save_ai_settings

    factory, doc_id, run_id = job
    worker_key = secrets.token_urlsafe(24)
    monkeypatch.setattr(extraction.settings, "ai_provider_setting", "none")
    async with factory() as db:
        await save_ai_settings(db, AIUpdate(
            revision=0, provider="openai", model="new-default-model", api_key=worker_key
        ))
        run = await db.get(ExtractionRun, run_id)
        run.ai_provider, run.ai_model = "openai", "queued-model"
        await db.commit()

    seen = []
    async def parse_with_saved_config(**kwargs):
        config = kwargs["provider_config"]
        seen.append((config.provider, config.model, config.api_key))
        return [{"reference_id": "1", "text": "The operator shall keep records.",
                 "requirement_type": "mandatory", "page_number": 1}]
    monkeypatch.setattr(extraction, "PdfParser", lambda: SimpleNamespace(parse_requirements=parse_with_saved_config))
    await extraction._extract(str(doc_id), str(run_id))
    assert await _state(factory, doc_id, run_id) == ("extracted", "completed", 1, 1)
    assert seen == [("openai", "queued-model", worker_key)]

    # A queued OpenAI run must never consume another provider's credentials.
    async with factory() as db:
        await save_ai_settings(db, AIUpdate(
            revision=1, provider="anthropic", model="different-model", api_key=secrets.token_urlsafe(24)
        ))
        run = await db.get(ExtractionRun, run_id)
        doc = await db.get(Document, doc_id)
        run.status, doc.status = "pending", "pending_extraction"
        run.attempt_count = extraction.MAX_ATTEMPTS - 1
        await db.commit()
    await extraction._extract(str(doc_id), str(run_id))
    assert len(seen) == 1
    async with factory() as db:
        run = await db.get(ExtractionRun, run_id)
        assert run.status == "failed"
        assert "provider changed" in run.error_message
