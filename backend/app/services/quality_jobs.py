"""Independent durable enhancement dispatch; baseline extraction never depends on Jev."""

import asyncio
import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import and_, or_, select

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.program import RequirementSetVersion
from app.models.requirement import ExtractedRequirement, Requirement
from app.models.requirement_quality import RequirementQualityRun
from app.services.extraction_jobs import _as_utc, utcnow


def source_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row_snapshot(row):
    return {
        key: str(value) if isinstance(value, uuid.UUID) else value
        for key in (
            "id",
            "reference_id",
            "title",
            "text",
            "requirement_type",
            "parent_id",
            "page_number",
            "status",
            "needs_review",
            "review_reason",
            "sort_order",
            "quality_auto_editable",
        )
        for value in [getattr(row, key, None)]
    }


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


async def quality_config(db, allow_external_ai, revision):
    from app.services.installation_settings import resolve_installation_settings
    from app.services.jev_provider import JevConfig

    runtime = await resolve_installation_settings(db)
    if not allow_external_ai:
        raise HTTPException(400, "Confirm external processing by Jev before checking the source.")
    if revision is None or revision != runtime.jev_settings_revision:
        raise HTTPException(
            409, "Jev settings changed. Refresh and confirm external processing again."
        )
    try:
        config = JevConfig.from_settings(runtime)
        if not config.enabled or not config.api_key:
            raise ValueError("Unavailable")
        return config, revision
    except ValueError:
        raise HTTPException(
            503,
            "Jev enhancement is unavailable. Configure and enable Jev in installation settings.",
        ) from None


async def create_quality_run(
    db, document, user, config, revision, *, extraction_run_id=None, version_id=None, mode="recheck"
):
    if not document.has_source or not document.file_path or not Path(document.file_path).is_file():
        raise HTTPException(
            409, "Source verification is unavailable: restore the source PDF first."
        )
    if version_id:
        version = await db.get(RequirementSetVersion, version_id)
        if not version or version.document_id != document.id:
            raise HTTPException(404, "Requirement-set version not found")
        rows = list(
            (
                await db.scalars(
                    select(Requirement).where(
                        Requirement.requirement_set_version_id == version_id,
                        Requirement.active.is_(True),
                    )
                )
            ).all()
        )
    else:
        extraction_run_id = extraction_run_id or document.current_extraction_id
        extraction = await db.get(ExtractionRun, extraction_run_id) if extraction_run_id else None
        if not extraction or extraction.document_id != document.id:
            raise HTTPException(404, "Extraction run not found")
        if mode != "import" and extraction.status != "completed":
            raise HTTPException(409, "A completed extraction run is required")
        rows = list(
            (
                await db.scalars(
                    select(ExtractedRequirement).where(
                        ExtractedRequirement.extraction_run_id == extraction_run_id,
                        ExtractedRequirement.status != "rejected",
                    )
                )
            ).all()
        )
    snapshots = [row_snapshot(row) for row in rows]
    if version_id:
        for row, snapshot in zip(rows, snapshots):
            source_row = (
                await db.get(ExtractedRequirement, row.source_extraction_id)
                if row.source_extraction_id
                else None
            )
            if source_row and source_row.document_id == document.id:
                snapshot["page_number"] = source_row.page_number
    from app.services.requirement_quality import POLICY_VERSION

    run = RequirementQualityRun(
        question_policy_version=POLICY_VERSION,
        document_id=document.id,
        extraction_run_id=extraction_run_id,
        version_id=version_id,
        requested_by=user.id,
        mode=mode,
        model=config.model,
        settings_revision=revision,
        status="waiting_extraction" if mode == "import" else "pending",
        source_sha256=await asyncio.to_thread(source_sha, document.file_path),
        snapshot={"rows": snapshots},
    )
    db.add(run)
    await db.flush()
    from app.services.audit import log_action

    await log_action(
        db,
        user,
        "create",
        "requirement_quality_run",
        str(run.id),
        new_value={
            "document_id": str(document.id),
            "mode": mode,
            "model": run.model,
            "settings_revision": revision,
            "extraction_run_id": str(extraction_run_id) if extraction_run_id else None,
            "version_id": str(version_id) if version_id else None,
            "external_processing_confirmed": True,
        },
    )
    return run


async def complete_import_quality(db, extraction, pages):
    await db.scalar(
        select(Document)
        .where(Document.id == extraction.document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    runs = list(
        (
            await db.scalars(
                select(RequirementQualityRun)
                .where(
                    RequirementQualityRun.extraction_run_id == extraction.id,
                    RequirementQualityRun.status == "waiting_extraction",
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    rows = list(
        (
            await db.scalars(
                select(ExtractedRequirement).where(
                    ExtractedRequirement.extraction_run_id == extraction.id,
                    ExtractedRequirement.status != "rejected",
                )
            )
        ).all()
    )
    for run in runs:
        run.snapshot = {
            "rows": [row_snapshot(row) for row in rows],
            "pages": [{"page_number": p["page_number"], "text": p.get("text", "")} for p in pages],
        }
        run.status = "pending"
    await db.commit()
    for run in runs:
        await dispatch_quality_run(db, run.id)


async def dispatch_quality_run(db, run_id):
    run = await db.scalar(
        select(RequirementQualityRun)
        .where(RequirementQualityRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = utcnow()
    if (
        not run
        or run.status not in {"pending", "running"}
        or (run.dispatch_after and _as_utc(run.dispatch_after) > now)
    ):
        await db.rollback()
        return False
    run.dispatch_after = now + timedelta(seconds=240)
    await db.commit()
    from app.tasks.requirement_quality import check_requirement_quality_task

    try:
        await asyncio.to_thread(check_requirement_quality_task.delay, str(run_id))
        return True
    except Exception:
        # Never persist provider or broker exception bodies.
        return False


async def reconcile_quality_jobs(factory):
    now = utcnow()
    async with factory() as db:
        candidates = list(
            (
                await db.execute(
                    select(RequirementQualityRun.id, RequirementQualityRun.document_id)
                    .where(
                        or_(
                            RequirementQualityRun.status == "waiting_extraction",
                            and_(
                                RequirementQualityRun.status.in_(["pending", "running"]),
                                or_(
                                    RequirementQualityRun.dispatch_after.is_(None),
                                    RequirementQualityRun.dispatch_after <= now,
                                ),
                            ),
                        )
                    )
                    .order_by(
                        RequirementQualityRun.status == "waiting_extraction",
                        RequirementQualityRun.dispatch_after.is_not(None),
                        RequirementQualityRun.dispatch_after,
                        RequirementQualityRun.created_at,
                    )
                    .limit(100)
                )
            ).all()
        )
    for run_id, document_id in candidates:
        async with factory() as db:
            await db.scalar(select(Document).where(Document.id == document_id).with_for_update())
            run = await db.scalar(
                select(RequirementQualityRun)
                .where(RequirementQualityRun.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not run or run.status not in {"waiting_extraction", "pending", "running"}:
                continue
            if run.status == "waiting_extraction":
                extraction = await db.get(ExtractionRun, run.extraction_run_id)
                if not extraction or extraction.status in {"failed", "cancelled"}:
                    run.status = "skipped"
                    run.warnings = ["Baseline extraction did not complete."]
                    run.completed_at = utcnow()
                elif extraction.status == "completed":
                    rows = list(
                        (
                            await db.scalars(
                                select(ExtractedRequirement).where(
                                    ExtractedRequirement.extraction_run_id == extraction.id,
                                    ExtractedRequirement.status != "rejected",
                                )
                            )
                        ).all()
                    )
                    run.snapshot = {"rows": [row_snapshot(row) for row in rows]}
                    run.status = "pending"
            await db.commit()
            if run.status in {"pending", "running"}:
                await dispatch_quality_run(db, run.id)
