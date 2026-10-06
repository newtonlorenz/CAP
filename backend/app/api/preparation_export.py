"""Read-only exports preserve the case's actual review and readiness state."""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.api.tenant import apply_org_scope
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.preparation import (
    PreparationCase,
    PreparationEvidence,
    PreparationResponse,
    PreparationResponseEvidence,
)
from app.models.user import User
from app.services.access import require_access
from app.services.audit import log_action
from app.services.preparation import build_case_response
from app.services.preparation_export import build_preparation_archive

router = APIRouter(prefix="/api/v1/preparation/cases", tags=["preparation"])


@router.get("/{case_id}/export")
async def export_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = apply_org_scope(
        select(PreparationCase).where(PreparationCase.id == case_id), PreparationCase, user
    ).with_for_update()
    case = (await db.scalars(query)).one_or_none()
    if case is None:
        raise HTTPException(404, "Form not found")
    await require_access(db, PreparationCase, case.id, user, "export")
    evidence_ids = (
        select(PreparationResponseEvidence.evidence_id)
        .join(
            PreparationResponse, PreparationResponse.id == PreparationResponseEvidence.response_id
        )
        .where(PreparationResponse.case_id == case.id)
    )
    expected_ids = set((await db.scalars(evidence_ids)).all()) | {
        uuid.UUID(value) for value in json.loads(case.original_evidence_ids_json or "[]")
    }
    evidence_query = (
        apply_org_scope(
            select(PreparationEvidence).where(PreparationEvidence.id.in_(expected_ids)),
            PreparationEvidence,
            user,
        )
        .order_by(PreparationEvidence.id)
        .with_for_update()
    )
    evidence = list((await db.scalars(evidence_query)).all())
    # Reject broken cross-tenant associations rather than silently producing an incomplete pack.
    if expected_ids != {item.id for item in evidence}:
        raise HTTPException(
            409, "A linked evidence item is unavailable. Review the case before exporting."
        )
    for item in evidence:
        await require_access(db, PreparationEvidence, item.id, user, "export")
    payload = (await build_case_response(db, case)).model_dump(mode="json")
    jurisdiction = await db.get(Jurisdiction, case.jurisdiction_id)
    owner = await db.get(User, case.owner_id) if case.owner_id else None
    stream = await run_in_threadpool(
        build_preparation_archive,
        payload,
        evidence,
        jurisdiction=jurisdiction.name,
        owner=owner.full_name if owner else None,
    )
    try:
        await log_action(
            db,
            user,
            "export",
            "preparation_case",
            str(case.id),
            new_value={
                "revision": case.revision,
                "ready": payload["readiness"]["ready"],
                "evidence_count": len(evidence),
            },
        )
        await db.commit()
    except BaseException:
        stream.close()
        raise

    def chunks():
        try:
            while chunk := stream.read(1024 * 1024):
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="cap-preparation-{case.id}.zip"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stream.close),
    )
