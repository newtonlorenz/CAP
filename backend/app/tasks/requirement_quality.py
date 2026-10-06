import asyncio
import copy
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement
from app.models.requirement_quality import RequirementQualityFinding, RequirementQualityRun
from app.models.user import User
from app.services.extraction_jobs import check_lock, run_lock, utcnow
from app.services.quality_jobs import fingerprint, row_snapshot, source_sha
from app.services.source_validation import numbered_hierarchy_errors, structure_errors
from app.tasks import celery_app


@celery_app.task
def check_requirement_quality_task(run_id):
    asyncio.run(check_quality(uuid.UUID(run_id)))


async def check_quality(run_id, session_factory=None):
    own_engine = None
    if session_factory is None:
        own_engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(
            own_engine, class_=AsyncSession, expire_on_commit=False
        )
    try:
        async with run_lock(session_factory, run_id) as lock:
            if lock is None:
                return
            await _check_owned(run_id, session_factory, lock)
    finally:
        if own_engine:
            await own_engine.dispose()


async def _check_owned(run_id, factory, lock):
    from app.services.installation_settings import resolve_installation_settings
    from app.services.jev_provider import JevConfig
    from app.services.pdf_extractor import extract_text_from_pdf
    from app.services.requirement_quality import POLICY_VERSION, evaluate_requirements

    async with factory() as db:
        run = await db.get(RequirementQualityRun, run_id)
        if not run or run.status not in {"pending", "running"}:
            return
        doc = await db.get(Document, run.document_id)
        runtime = await resolve_installation_settings(db)
        try:
            config = JevConfig.from_settings(runtime)
            if not config.enabled or not config.api_key:
                raise ValueError("Unavailable")
            if runtime.jev_settings_revision != run.settings_revision or config.model != run.model:
                raise ValueError("Settings changed")
            if (
                not doc
                or not doc.has_source
                or await asyncio.to_thread(source_sha, doc.file_path) != run.source_sha256
            ):
                raise ValueError("Source changed")
        except (ValueError, OSError):
            run.status = "skipped"
            run.warnings = ["Source or Jev settings changed; request a new check."]
            run.completed_at = utcnow()
            await db.commit()
            return
        cached = []
        previous = list(
            (
                await db.scalars(
                    select(RequirementQualityRun.id)
                    .where(
                        RequirementQualityRun.document_id == run.document_id,
                        RequirementQualityRun.source_sha256 == run.source_sha256,
                        RequirementQualityRun.model == run.model,
                        RequirementQualityRun.question_policy_version == POLICY_VERSION,
                        RequirementQualityRun.status.in_(["completed", "partial"]),
                        RequirementQualityRun.id != run.id,
                    )
                    .order_by(RequirementQualityRun.created_at.desc())
                    .limit(5)
                )
            ).all()
        )
        if previous:
            cached = [
                {"answers": finding.answers}
                for finding in (
                    await db.scalars(
                        select(RequirementQualityFinding).where(
                            RequirementQualityFinding.run_id.in_(previous)
                        )
                    )
                ).all()
            ]
        run.question_policy_version = POLICY_VERSION
        token = str(uuid.uuid4())
        run.owner_token = token
        run.status = "running"
        run.started_at = utcnow()
        snapshot = copy.deepcopy(run.snapshot)
        path = doc.file_path
        await db.commit()

    async def should_continue():
        async with factory() as fresh:
            current = await fresh.get(RequirementQualityRun, run_id)
            current_doc = await fresh.get(Document, run.document_id)
            active_settings = await resolve_installation_settings(fresh)
            active_config = JevConfig.from_settings(active_settings)
            return bool(
                current
                and current.status == "running"
                and current.owner_token == token
                and current_doc
                and current_doc.has_source
                and current_doc.file_path == path
                and (
                    current.mode != "import"
                    or current_doc.current_extraction_id == current.extraction_run_id
                )
                and active_config.enabled
                and active_config.api_key
                and active_config.revision == current.settings_revision
                and active_config.model == current.model
            )

    try:
        pages = snapshot.get("pages") or await asyncio.wait_for(
            asyncio.to_thread(extract_text_from_pdf, path), timeout=30
        )
        result = await evaluate_requirements(
            snapshot.get("rows", []), pages, config, cached=cached, should_continue=should_continue
        )
    except Exception:
        result = {
            "status": "partial",
            "findings": [],
            "coverage": {},
            "usage": {},
            "warnings": [
                "Jev source check could not complete. Baseline requirements remain available."
            ],
        }
    async with factory() as db:
        # Document lock is shared with human edit, submission and approval paths.
        doc = await db.scalar(
            select(Document)
            .where(Document.id == run.document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        run = await db.scalar(
            select(RequirementQualityRun)
            .where(RequirementQualityRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not run or run.status != "running" or run.owner_token != token:
            return
        await check_lock(lock)
        runtime = await resolve_installation_settings(db)
        active_config = JevConfig.from_settings(runtime)
        try:
            same_source = bool(
                doc
                and doc.has_source
                and doc.file_path == path
                and await asyncio.to_thread(source_sha, doc.file_path) == run.source_sha256
            )
        except OSError:
            same_source = False
        if (
            not doc
            or active_config.revision != run.settings_revision
            or not active_config.enabled
            or not active_config.api_key
            or active_config.model != run.model
            or not same_source
        ):
            run.status = "skipped"
            run.warnings = [
                "Source or Jev settings changed during the check; results were discarded."
            ]
            run.completed_at = utcnow()
            await db.commit()
            return
        rows = (
            list(
                (
                    await db.scalars(
                        select(ExtractedRequirement).where(
                            ExtractedRequirement.extraction_run_id == run.extraction_run_id,
                            ExtractedRequirement.status != "rejected",
                        )
                    )
                ).all()
            )
            if run.extraction_run_id
            else []
        )
        baseline = (
            await db.get(ExtractionRun, run.extraction_run_id) if run.extraction_run_id else None
        )
        actor = await db.get(User, run.requested_by) if run.requested_by else None
        can_apply = (
            actor is not None
            and run.mode == "import"
            and baseline is not None
            and baseline.status == "completed"
            and doc.current_extraction_id == run.extraction_run_id
            and doc.status == "extracted"
        )
        originals = {r["id"]: r for r in snapshot.get("rows", [])}
        by_id = {str(r.id): r for r in rows}
        all_fresh = len(originals) == len(rows) and all(
            fingerprint(row_snapshot(r)) == fingerprint(originals.get(str(r.id), {}))
            and r.quality_auto_editable
            for r in rows
        )

        def parent_context_is_fresh(original_parent, proposed_parent):
            # Both scope chains were part of repair verification. An absent or
            # newly created parent cannot be verified against the captured input.
            for starting_parent in (original_parent, proposed_parent):
                parent_id = str(starting_parent) if starting_parent else None
                seen = set()
                while parent_id:
                    if parent_id in seen:
                        return False
                    seen.add(parent_id)
                    original_parent_row = originals.get(parent_id)
                    current_parent_row = by_id.get(parent_id)
                    if (
                        original_parent_row is None
                        or current_parent_row is None
                        or fingerprint(row_snapshot(current_parent_row))
                        != fingerprint(original_parent_row)
                    ):
                        return False
                    parent_id = original_parent_row.get("parent_id")
            return True

        for item in result.get("findings", []):
            finding = RequirementQualityFinding(
                run_id=run.id,
                **{
                    key: item.get(key)
                    for key in (
                        "requirement_id",
                        "kind",
                        "source_page",
                        "source_excerpt",
                        "source_span_id",
                    )
                },
                before=item.get("before") or {},
                after=item.get("after") or {},
                answers=item.get("answers") or {},
                auto_eligible=bool(item.get("auto_eligible")),
                applied=False,
            )
            db.add(finding)
            row = by_id.get(item.get("requirement_id"))
            fresh_row = bool(
                row
                and row.quality_auto_editable
                and fingerprint(row_snapshot(row)) == fingerprint(originals.get(str(row.id), {}))
            )
            answers = finding.answers
            uncertain = bool(finding.after and not finding.auto_eligible)
            if item.get("kind") == "accuracy":
                support = answers.get("supported", {})
                uncertain = uncertain or support.get("noul", 0) < 0.98
                for answer_key in ("source", "type", "parent"):
                    choice = answers.get(answer_key, {})
                    if choice:
                        uncertain = (
                            uncertain
                            or choice.get("choice") == "uncertain"
                            or choice.get("confidence", 0) < 0.98
                            or choice.get("probabilities", {}).get(choice.get("choice"), 0) < 0.98
                        )

            def flag_review():
                if can_apply and fresh_row and uncertain:
                    row.needs_review = True
                    row.review_reason = row.review_reason or "Jev source check needs review"

            if (
                not can_apply
                or not finding.auto_eligible
                or item.get("kind") in {"duplicate", "merge"}
            ):
                flag_review()
                continue
            after = finding.after
            if row and (
                not row.quality_auto_editable
                or fingerprint(row_snapshot(row)) != fingerprint(originals.get(str(row.id), {}))
            ):
                continue
            if not row and (
                not all_fresh or item.get("kind") not in {"omission", "missing_requirement"}
            ):
                continue
            original_parent = originals.get(str(row.id), {}).get("parent_id") if row else None
            proposed_parent = after.get("parent_id", original_parent)
            if not parent_context_is_fresh(original_parent, proposed_parent):
                uncertain = True
                flag_review()
                continue
            if "text" in after and (
                not after["text"] or after["text"] not in (finding.source_excerpt or "")
            ):
                continue
            before = row_snapshot(row) if row else None
            new = row is None
            if new:
                row = ExtractedRequirement(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    extraction_run_id=run.extraction_run_id,
                    reference_id=after.get("reference_id", ""),
                    text=after.get("text", ""),
                    original_text=after.get("text", ""),
                    page_number=finding.source_page or 1,
                    sort_order=len(rows),
                    quality_auto_editable=True,
                    parser_strategy="jev_source_recovery",
                    status="pending",
                )
            for key in ("reference_id", "title", "text", "requirement_type", "parent_id"):
                if key in after:
                    value = after[key]
                    if key == "parent_id":
                        try:
                            value = uuid.UUID(value) if value else None
                        except (ValueError, TypeError):
                            value = row.id  # Rejected by circular hierarchy validation.
                    setattr(row, key, value)
            if not row.requirement_type:
                row.requirement_type = "mandatory"
            candidates = rows + ([row] if new else [])
            errors = structure_errors(candidates)
            if any(r.parser_strategy == "opendataloader" for r in rows):
                errors += numbered_hierarchy_errors(candidates, require_numeric=True)
            if errors:
                if not new:
                    for key in ("reference_id", "title", "text", "requirement_type", "parent_id"):
                        value = before[key]
                        setattr(
                            row, key, uuid.UUID(value) if key == "parent_id" and value else value
                        )
                uncertain = True
                flag_review()
                continue
            row.needs_review = True
            row.review_reason = "Jev source correction requires review"
            row.status = "pending"
            row.source_excerpt = finding.source_excerpt
            if new:
                db.add(row)
                baseline.requirements_found += 1
                rows.append(row)
                by_id[str(row.id)] = row
                finding.requirement_id = str(row.id)
            finding.applied = True
            from app.services.audit import log_action

            await log_action(
                db,
                actor,
                "jev_source_correction",
                "extracted_requirement",
                str(row.id),
                old_value=before,
                new_value={"quality_run_id": str(run.id), "values": row_snapshot(row)},
            )
        run.status = result.get("status", "partial")
        run.model = result.get("model") or run.model
        run.coverage = result.get("coverage") or {}
        run.usage = result.get("usage") or {}
        run.warnings = result.get("warnings") or []
        run.completed_at = utcnow()
        await db.commit()
