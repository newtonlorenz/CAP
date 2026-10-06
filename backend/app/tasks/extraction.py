import asyncio
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.document import Document
from app.models.extraction import ExtractionRun, ExtractionRunDiagnostic
from app.models.requirement import ExtractedRequirement
from app.services.pdf_parser import PdfParser, NATIVE_PIPELINE_VERSION
from app.services.extraction_events import publish_event
from app.services.extraction_jobs import MAX_ATTEMPTS, check_lock, run_lock, utcnow
from app.services.parser_feedback import apply_parser_template, load_parser_template
from app.services.pdf_preprocessor import (
    cleanup_preprocess_artifacts,
)
from app.services.pdf_worker import bounded_preprocess
from app.services.ai_provider import ProviderConfig
from app.services.vision_parser import parse_requirements_from_page_image
from app.services.structured_pdf import PIPELINE_VERSION
from app.tasks import celery_app


def attach_page_continuation(page_text, reference_index):
    """Retain cross-page prose and split table rows on their original source control."""
    continuation = re.match(r"\s*\[SECTION_CONTINUATION:([^\]]+)\]\s*\n", page_text)
    if not continuation:
        return page_text
    section = continuation.group(1)
    lines = page_text[continuation.end():].splitlines()
    boundary = next((i for i, line in enumerate(lines)
                     if re.match(r"^\s*\d+(?:\.\d+)*[.)]?(?:\s+|$)", line)), len(lines))
    tail = "\n".join(line for line in lines[:boundary] if not re.fullmatch(r"\s*(?:https?://)?[\w.-]+\.[a-zA-Z]{2,}/?\s*", line)).strip()
    previous = [(ref, entry) for ref, entry in reference_index.items()
                if ref.startswith(section + ".") and ref[len(section) + 1:].isdigit()]
    entry = (max(previous, key=lambda pair: int(pair[0][len(section) + 1:]))[1]
             if previous else reference_index.get(section))
    if tail and entry is not None:
        if tail not in entry.text:
            entry.text = entry.text.rstrip() + "\n" + tail
            entry.original_text = entry.text
            entry.source_excerpt = entry.text
        return continuation.group(0) + "\n".join(lines[boundary:])
    return page_text


def _strategy_bucket(strategy: Optional[str]) -> str:
    normalized = (strategy or "").strip().lower()
    if "vision" in normalized:
        return "vision"
    if "table" in normalized:
        return "table"
    return "rule"


def _should_try_vision_fallback(
    *,
    document_type: str,
    page_is_low_parseability: bool,
    current_requirements: list[dict],
) -> bool:
    if not settings.vision_fallback_enabled:
        return False
    if not page_is_low_parseability:
        return False
    if not current_requirements:
        return True
    mandatory_count = sum(
        1
        for req in current_requirements
        if req.get("requirement_type") in {"mandatory", "recommended"}
    )
    review_count = sum(1 for req in current_requirements if req.get("needs_review"))
    return mandatory_count == 0 or review_count >= max(1, len(current_requirements) // 2)


def _merge_requirement_candidates(primary: list[dict], secondary: list[dict]) -> list[dict]:
    if not secondary:
        return primary
    merged = list(primary)
    seen = {
        (
            (item.get("reference_id") or "").strip().lower(),
            (item.get("text") or "").strip().lower(),
        )
        for item in merged
    }
    for item in secondary:
        key = (
            (item.get("reference_id") or "").strip().lower(),
            (item.get("text") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _get_session_factory():
    """Create a fresh engine and session factory for this task."""
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    factory._task_owned_engine = engine
    return factory


@celery_app.task
def extract_requirements_task(document_id: str, extraction_run_id: str):
    """Celery task to extract requirements from a document."""
    asyncio.run(_extract(document_id, extraction_run_id))


async def _extract(
    document_id: str,
    extraction_run_id: str,
):
    """Hold a dedicated ownership connection for the complete task lifetime."""
    session_factory = _get_session_factory()
    try:
        document_id = uuid.UUID(str(document_id))
        extraction_run_id = uuid.UUID(str(extraction_run_id))
        async with run_lock(session_factory, extraction_run_id) as lock:
            if lock is None:
                return
            await _extract_owned(document_id, extraction_run_id, session_factory, lock)
    finally:
        engine = getattr(session_factory, "_task_owned_engine", None)
        if engine is not None:
            await engine.dispose()


class _OwnershipLost(Exception):
    pass


async def _extract_owned(document_id, extraction_run_id, session_factory, lock):
    """Async implementation of requirement extraction with progress tracking."""
    commit_every_pages = 3
    preprocess_cleanup_paths: list[str] = []

    async with session_factory() as db:
        # Load document and extraction run
        doc_result = await db.execute(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        doc = doc_result.scalar_one_or_none()
        if not doc:
            return
        doc_id = doc.id

        run_result = await db.execute(
            select(ExtractionRun).where(ExtractionRun.id == extraction_run_id)
        )
        run = run_result.scalar_one_or_none()
        if not run:
            return
        run_id = run.id

        if run.document_id != doc.id or doc.current_extraction_id != run.id:
            return
        if run.status not in {"pending", "running"}:
            return
        await check_lock(lock)
        if run.attempt_count >= MAX_ATTEMPTS:
            run.status = "failed"
            run.error_message = "Extraction exceeded retry limit"
            run.completed_at = utcnow()
            doc.status = "extraction_failed"
            await check_lock(lock)
            await db.commit()
            return
        owner_token = str(uuid.uuid4())
        claim = await db.execute(
            update(ExtractionRun)
            .where(ExtractionRun.id == run.id, ExtractionRun.status.in_(("pending", "running")))
            .values(status="running", owner_token=owner_token,
                    attempt_count=ExtractionRun.attempt_count + 1, last_progress_at=utcnow())
        )
        if claim.rowcount != 1:
            await db.rollback()
            return
        # Reset run state to make retries idempotent
        await db.execute(
            delete(ExtractedRequirement).where(ExtractedRequirement.extraction_run_id == run.id)
        )
        run.requirements_found = 0
        run.current_page = 0
        run.error_message = None
        run.error_page = None
        run.warning_count = 0
        run.parseability_score = None
        run.fallback_trigger_reason = None
        run.strategy_counts = {"rule": 0, "table": 0, "vision": 0}
        run.diagnostics_available = False
        await check_lock(lock)

        async def assert_owner():
            await check_lock(lock)
            # Read the persisted state without flushing this worker's changes.
            # Document lock serialises cancellation and newer-run selection.
            with db.no_autoflush:
                current_doc = await db.scalar(
                    select(Document.current_extraction_id)
                    .where(Document.id == doc_id).with_for_update()
                )
                current = (
                    await db.execute(
                        select(ExtractionRun.status, ExtractionRun.owner_token)
                        .where(ExtractionRun.id == run_id).with_for_update()
                    )
                ).one_or_none()
            if current_doc != run_id or current != ("running", owner_token):
                await db.rollback()
                raise _OwnershipLost()

        async def guarded_commit():
            await assert_owner()
            run.last_progress_at = utcnow()
            await db.commit()

        async def log_event(
            stage: str,
            message: str,
            level: str = "info",
            page: Optional[int] = None,
            duration_ms: Optional[int] = None,
        ) -> None:
            await publish_event(
                str(run.id),
                {
                    "stage": stage,
                    "message": message,
                    "level": level,
                    "page_number": page,
                    "duration_ms": duration_ms,
                },
            )

        async def set_document_status(value):
            # A cancelled worker must never overwrite the newer run's document state.
            await assert_owner()
            await db.execute(
                update(Document)
                .where(Document.id == doc_id, Document.current_extraction_id == run_id)
                .values(status=value)
            )

        # Update status to running
        await set_document_status("extracting")
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await guarded_commit()

        try:
            if run.pipeline_version not in {NATIVE_PIPELINE_VERSION, PIPELINE_VERSION} or run.ai_provider == "deterministic":
                raise ValueError("This queued run uses a retired parser. Start a new extraction run.")
            from app.services.installation_settings import resolve_installation_settings

            runtime_settings = await resolve_installation_settings(db)
            provider_config = ProviderConfig.from_settings(
                runtime_settings, provider=run.ai_provider, model=run.ai_model
            )
            # Extract pages from PDF
            await log_event("pdf_extract_start", "Extracting pages")
            pdf_start = time.monotonic()
            diagnostics_record: Optional[ExtractionRunDiagnostic] = None
            parser = PdfParser()

            structured_run = run.pipeline_version == PIPELINE_VERSION
            preprocess_options = {"structure_engine": "opendataloader"} if structured_run else {}
            preprocess_result = await bounded_preprocess(
                doc.file_path, doc.document_type, **preprocess_options
            )
            structured_by_page: dict[int, list[dict]] = {}
            if structured_run:
                if not preprocess_result.structured_requirements:
                    raise ValueError("Structured extraction returned no requirement candidates.")
                source_page_numbers = {page["page_number"] for page in preprocess_result.pages}
                for candidate in preprocess_result.structured_requirements:
                    if candidate.get("page_number") not in source_page_numbers:
                        raise ValueError("Structured requirement has an invalid source page.")
                    structured_by_page.setdefault(candidate["page_number"], []).append(candidate)
            preprocess_cleanup_paths = preprocess_result.cleanup_paths
            pages = preprocess_result.pages
            run.pipeline_version = PIPELINE_VERSION if structured_run else NATIVE_PIPELINE_VERSION
            run.ocr_applied = preprocess_result.ocr_applied
            run.ocr_pages = preprocess_result.ocr_pages
            run.warning_count = preprocess_result.warning_count
            run.family_fingerprint = preprocess_result.family_fingerprint
            run.parseability_score = preprocess_result.parseability_score
            run.fallback_trigger_reason = preprocess_result.fallback_trigger_reason
            run.strategy_counts = {"rule": 0, "table": 0, "vision": 0}
            run.diagnostics_available = bool(preprocess_result.diagnostics)
            base_warning_count = preprocess_result.warning_count

            await db.execute(
                delete(ExtractionRunDiagnostic).where(
                    ExtractionRunDiagnostic.extraction_run_id == run.id
                )
            )
            diagnostics_record = ExtractionRunDiagnostic(
                extraction_run_id=run.id,
                document_id=doc.id,
                parseability_score=preprocess_result.parseability_score,
                fallback_trigger_reason=preprocess_result.fallback_trigger_reason,
                strategy_counts={"rule": 0, "table": 0, "vision": 0},
                decision_payload={
                    "structured_source": preprocess_result.diagnostics.get("structured_source"),
                    "structured_recovery": preprocess_result.diagnostics.get("structured_recovery"),
                    "low_parseability_pages": preprocess_result.low_quality_pages,
                    "fallback_trigger_reason": preprocess_result.fallback_trigger_reason,
                    "ocr_applied": preprocess_result.ocr_applied,
                    "ocr_pages": preprocess_result.ocr_pages,
                },
                page_metrics=preprocess_result.diagnostics.get("page_metrics"),
                canonical_blocks=preprocess_result.diagnostics.get("canonical_blocks"),
            )
            db.add(diagnostics_record)

            parser_template = None
            if not structured_run:
                parser_template = await load_parser_template(
                    db,
                    jurisdiction_id=doc.jurisdiction_id,
                    document_type=doc.document_type,
                    family_fingerprint=run.family_fingerprint,
                    organization_id=doc.organization_id,
                )
            if parser_template:
                await log_event(
                    "template_apply",
                    f"Applying learned parser template ({parser_template.support_runs} runs)",
                )
            await log_event(
                "pdf_extract_end",
                f"Extracted {len(pages)} pages",
                duration_ms=int((time.monotonic() - pdf_start) * 1000),
            )
            run.total_pages = len(pages)
            await guarded_commit()

            sort_order = 0
            pages_since_commit = 0
            review_queue_count = 0
            parser_strategy_counts: dict[str, int] = {"rule": 0, "table": 0, "vision": 0}
            runtime_warning_count = 0
            vision_fallback_pages_used = 0
            reference_index: dict[str, ExtractedRequirement] = {}
            all_parent_refs: list[tuple[ExtractedRequirement, str]] = []
            page_quality_by_number = {
                item.page_number: item for item in preprocess_result.page_quality
            }
            run_timeout_minutes = settings.extraction_timeout_minutes

            async def persist_runtime_metrics() -> None:
                run.warning_count = base_warning_count + review_queue_count + runtime_warning_count
                run.strategy_counts = parser_strategy_counts
                if diagnostics_record is not None:
                    diagnostics_record.strategy_counts = parser_strategy_counts
                    payload = diagnostics_record.decision_payload or {}
                    payload["review_queue_count"] = review_queue_count
                    payload["runtime_warning_count"] = runtime_warning_count
                    payload["vision_fallback_pages_used"] = vision_fallback_pages_used
                    diagnostics_record.decision_payload = payload

            for page in pages:
                # Only refresh the cancellation status; refreshing the full row would
                # overwrite uncommitted progress counters (e.g., requirements_found).
                await db.refresh(run, attribute_names=["status"])
                if run.status == "cancelled":
                    await db.rollback()
                    return

                if run.started_at and datetime.now(timezone.utc) - run.started_at > timedelta(
                    minutes=run_timeout_minutes
                ):
                    await set_document_status("extraction_failed")
                    run.status = "timed_out"
                    run.error_message = f"Extraction timed out after {run_timeout_minutes} minutes"
                    run.error_page = page["page_number"]
                    run.current_page = page["page_number"]
                    run.completed_at = datetime.now(timezone.utc)
                    await persist_runtime_metrics()
                    await guarded_commit()
                    return

                page_number = page["page_number"]
                run.current_page = page_number
                run_remaining = (
                    run_timeout_minutes * 60
                    - (utcnow() - run.started_at).total_seconds()
                )
                page_deadline = time.monotonic() + min(
                    settings.extraction_page_timeout_seconds, run_remaining
                )

                try:
                    await log_event("page_start", f"Page {page_number} start", page=page_number)
                    async def event_logger(payload: dict) -> None:
                        payload.setdefault("page_number", page_number)
                        await publish_event(str(run.id), payload)

                    page_text = page["text"]
                    if parser_template is not None:
                        page_text = apply_parser_template(page_text, parser_template)

                    if structured_run:
                        requirements = structured_by_page.get(page_number, [])
                    else:
                        page_text = attach_page_continuation(page_text, reference_index)

                        requirements = await asyncio.wait_for(
                            parser.parse_requirements(
                                text=page_text,
                                document_type=doc.document_type,
                                page_number=page_number,
                                event_logger=event_logger,
                                provider_config=provider_config,
                            ),
                            timeout=max(0, page_deadline - time.monotonic()),
                        )
                    page_quality = page_quality_by_number.get(page_number)
                    if not structured_run and provider_config.provider != "none" and _should_try_vision_fallback(
                        document_type=doc.document_type,
                        page_is_low_parseability=bool(page_quality and page_quality.is_low_quality),
                        current_requirements=requirements,
                    ):
                        if (
                            vision_fallback_pages_used
                            >= settings.vision_fallback_max_regions_per_doc
                        ):
                            await log_event(
                                "vision_fallback_end",
                                (
                                    "Skipped vision fallback: reached per-document region/page "
                                    f"limit ({settings.vision_fallback_max_regions_per_doc})"
                                ),
                                page=page_number,
                                level="warn",
                            )
                        else:
                            vision_fallback_pages_used += 1
                            await log_event(
                                "vision_fallback_start",
                                "Running vision fallback for low-parseability page",
                                page=page_number,
                            )
                            vision_result = await parse_requirements_from_page_image(
                                file_path=doc.file_path,
                                page_number=page_number,
                                document_type=doc.document_type,
                                page_text=page_text,
                                event_logger=event_logger,
                                provider_config=provider_config,
                                deadline=page_deadline,
                            )
                            runtime_warning_count += len(vision_result.warnings)
                            requirements = _merge_requirement_candidates(
                                requirements, vision_result.items
                            )
                            await log_event(
                                "vision_fallback_end",
                                f"{len(vision_result.items)} items ({len(vision_result.warnings)} warnings)",
                                page=page_number,
                            )

                    extracted_requirements = []
                    pending_parent_refs: list[tuple[ExtractedRequirement, str]] = []
                    for req in requirements:
                        reference_id = req.get("reference_id")
                        if not reference_id:
                            reference_id = f"p{page_number}-{sort_order}"
                        parent_reference = req.get("parent_reference")
                        existing = reference_index.get(reference_id)
                        if existing:
                            if structured_run:
                                raise ValueError(f"Duplicate structured reference: {reference_id}")
                            new_text = req.get("text", "")
                            if new_text and new_text not in existing.text:
                                existing.text = f"{existing.text} {new_text}".strip()
                                existing.original_text = existing.text
                            if (
                                existing.requirement_type != "mandatory"
                                and req.get("requirement_type") == "mandatory"
                            ):
                                existing.requirement_type = "mandatory"
                            sort_order += 1
                            continue
                        if run.ai_provider == "local":
                            req["needs_review"] = True
                            reason = "Local draft extraction: compare wording, type and hierarchy with the source PDF"
                            if req.get("review_reason"):
                                reason += "; " + req["review_reason"]
                            req["review_reason"] = reason[:255]
                        extracted_requirements.append(
                            ExtractedRequirement(
                                document_id=doc.id,
                                extraction_run_id=run.id,
                                quality_auto_editable=True,
                                reference_id=reference_id,
                                title=req.get("title"),
                                text=req.get("text", ""),
                                original_text=req.get("original_text", req.get("text", "")),
                                requirement_type=req.get("requirement_type", "mandatory"),
                                page_number=req.get("page_number", page_number),
                                confidence_score=req.get("confidence_score", req.get("confidence", 1.0)),
                                needs_review=bool(req.get("needs_review", False)),
                                review_reason=req.get("review_reason"),
                                source_excerpt=req.get("source_excerpt"),
                                parser_strategy=req.get("parser_strategy", "rule_based"),
                                sort_order=sort_order,
                            )
                        )
                        parser_bucket = _strategy_bucket(req.get("parser_strategy"))
                        parser_strategy_counts[parser_bucket] = (
                            parser_strategy_counts.get(parser_bucket, 0) + 1
                        )
                        if req.get("needs_review", False):
                            review_queue_count += 1
                        if parent_reference:
                            pending_parent_refs.append(
                                (extracted_requirements[-1], parent_reference)
                            )
                        reference_index[reference_id] = extracted_requirements[-1]
                        sort_order += 1

                    if extracted_requirements:
                        all_parent_refs.extend(pending_parent_refs)
                        db.add_all(extracted_requirements)
                        await db.flush()
                        for extracted, parent_reference in pending_parent_refs:
                            parent_req = reference_index.get(parent_reference)
                            if parent_req:
                                extracted.parent_id = parent_req.id
                        await db.flush()
                        run.requirements_found += len(extracted_requirements)

                    await log_event(
                        "page_end",
                        f"Page {page_number} complete ({len(requirements)} requirements)",
                        page=page_number,
                    )
                    await log_event(
                        "review_queue_count",
                        f"{review_queue_count} requirements flagged for review",
                        page=page_number,
                    )
                    pages_since_commit += 1
                    if pages_since_commit >= commit_every_pages:
                        await log_event("commit", "Committed batch")
                        await guarded_commit()
                        pages_since_commit = 0

                except asyncio.TimeoutError:
                    run_expired = (
                        utcnow() - run.started_at
                    ).total_seconds() >= run_timeout_minutes * 60
                    timeout_message = (
                        f"Extraction timed out after {run_timeout_minutes} minutes"
                        if run_expired else
                        f"Page {page_number} timed out after {settings.extraction_page_timeout_seconds}s"
                    )
                    await log_event(
                        "timeout",
                        timeout_message,
                        level="error",
                        page=page_number,
                    )
                    await set_document_status("extraction_failed")
                    run.status = "timed_out"
                    run.error_message = timeout_message
                    run.error_page = page_number
                    run.completed_at = datetime.now(timezone.utc)
                    await persist_runtime_metrics()
                    await guarded_commit()
                    return
                except Exception as page_exc:
                    # Preserve the page error before scheduling a durable retry.
                    await log_event(
                        "error",
                        f"Page {page_number} error: {page_exc}",
                        level="error",
                        page=page_number,
                    )
                    run.error_message = str(page_exc)
                    run.error_page = page_number
                    await persist_runtime_metrics()
                    await guarded_commit()
                    raise  # Outer handler records a durable retry.

            # Resolve after every row exists; source order can place children before parents.
            for child, parent_reference in all_parent_refs:
                parent = reference_index.get(parent_reference)
                if parent is None:
                    if structured_run:
                        child.needs_review = True
                        reason = f"Missing immediate parent {parent_reference}; repair the hierarchy before approval"
                        child.review_reason = reason
                    continue
                child.parent_id = parent.id
            if structured_run:
                from app.services.source_validation import structure_errors
                errors = structure_errors(list(reference_index.values()))
                if errors:
                    raise ValueError("Invalid structured hierarchy: " + "; ".join(errors[:10]))
                # A final parent reconciliation can update rows from previously committed pages.
                await db.flush()

            if pages_since_commit:
                await guarded_commit()

            await persist_runtime_metrics()

            # Mark as completed
            await set_document_status("extracted")
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await guarded_commit()
            # Enhancement is an independent durable job after baseline success.
            from app.services.quality_jobs import complete_import_quality
            try:
                await complete_import_quality(db, run, pages)
            except Exception:
                await db.rollback()  # Watchdog recovers the committed enhancement intent.

        except _OwnershipLost:
            await db.rollback()
            return
        except Exception as exc:
            # Retry is durable; Celery redelivery is an additional recovery path.
            await db.rollback()
            run = await db.get(ExtractionRun, extraction_run_id)
            if run.attempt_count < MAX_ATTEMPTS:
                await set_document_status("pending_extraction")
                run.status = "pending"
                run.dispatch_after = utcnow() + timedelta(seconds=60)
            else:
                await set_document_status("extraction_failed")
                run.status = "failed"
                run.completed_at = utcnow()
            if not run.error_message:
                run.error_message = str(exc)
            try:
                await guarded_commit()
            except _OwnershipLost:
                return
            await log_event("retry" if run.status == "pending" else "failed", str(exc), level="error")
        finally:
            cleanup_preprocess_artifacts(preprocess_cleanup_paths)
