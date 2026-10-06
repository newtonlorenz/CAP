from datetime import date, datetime, time, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask
from app.services.review_package import build_review_package
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.tenant import get_org_owned_or_404
from app.database import get_db
from app.models.review import ReviewCycle
from app.models.program import CertificationProject
from app.services.access import require_access
from app.models.user import User
from app.services.reports import (
    generate_change_management_component_history_csv,
    generate_change_management_components_csv,
    generate_change_management_hardware_locations_csv,
    generate_change_management_integration_changes_csv,
    generate_change_management_verified_changes_csv,
    generate_audit_trail_csv,
    generate_compliance_summary_pdf,
    generate_detailed_report_pdf,
    generate_gap_analysis_csv,
    generate_gap_analysis_pdf,
    generate_gap_analysis_xlsx,
    generate_review_cycle_report_pdf,
    generate_statement_of_applicability_pdf,
    generate_statement_of_applicability_xlsx,
    get_statement_of_applicability_fields,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


async def _get_review_cycle_or_404(
    db: AsyncSession,
    current_user: User,
    review_cycle_id: uuid.UUID,
) -> ReviewCycle:
    cycle = await get_org_owned_or_404(
        db,
        ReviewCycle,
        review_cycle_id,
        current_user,
        detail="Review cycle not found",
    )
    if cycle.certification_project_id:
        await require_access(
            db, CertificationProject, cycle.certification_project_id, current_user, "export"
        )
    return cycle


@router.get("/review-package")
async def get_review_package(
    review_cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    cycle = await _get_review_cycle_or_404(db, current_user, review_cycle_id)
    content = await build_review_package(db, cycle, current_user)
    try:
        from app.services.audit import log_action

        await log_action(
            db,
            current_user,
            "export",
            "review_package",
            str(cycle.id),
            new_value={"snapshot_id": str(cycle.snapshot_id)},
        )
        await db.commit()
    except BaseException:
        content.close()
        raise

    def chunks():
        while chunk := content.read(1024 * 1024):
            yield chunk

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=review-{cycle.id}-evidence.zip"},
        background=BackgroundTask(content.close),
    )


@router.get("/compliance-summary")
async def get_compliance_summary(
    format: str = Query("pdf", description="Output format: pdf"),
    review_cycle_id: Optional[uuid.UUID] = Query(
        None, description="Optional review cycle ID for cycle-scoped report"
    ),
    jurisdiction_id: Optional[uuid.UUID] = Query(
        None,
        description="Jurisdiction ID for jurisdiction-scoped report (required when review_cycle_id is not provided)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if review_cycle_id:
        await _get_review_cycle_or_404(db, current_user, review_cycle_id)
    elif jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    pdf_content = await generate_compliance_summary_pdf(
        db, review_cycle_id, jurisdiction_id, current_user.organization_id
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=compliance-summary.pdf"},
    )


@router.get("/detailed")
async def get_detailed_report(
    format: str = Query("pdf", description="Output format: pdf"),
    review_cycle_id: Optional[uuid.UUID] = Query(
        None, description="Optional review cycle ID for cycle-scoped report"
    ),
    jurisdiction_id: Optional[uuid.UUID] = Query(
        None,
        description="Jurisdiction ID for jurisdiction-scoped report (required when review_cycle_id is not provided)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if review_cycle_id:
        await _get_review_cycle_or_404(db, current_user, review_cycle_id)
    elif jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    pdf_content = await generate_detailed_report_pdf(
        db, review_cycle_id, jurisdiction_id, current_user.organization_id
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=detailed-compliance-report.pdf"},
    )


@router.get("/gap-analysis")
async def get_gap_analysis(
    format: str = Query("csv", description="Output format: csv, xlsx, or pdf"),
    review_cycle_id: Optional[uuid.UUID] = Query(
        None, description="Optional review cycle ID for cycle-scoped report"
    ),
    jurisdiction_id: Optional[uuid.UUID] = Query(
        None,
        description="Jurisdiction ID for jurisdiction-scoped report (required when review_cycle_id is not provided)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if review_cycle_id:
        await _get_review_cycle_or_404(db, current_user, review_cycle_id)
    elif jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    elif current_user.role not in {"manager", "approver", "admin"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    if format not in {"csv", "xlsx", "pdf"}:
        raise HTTPException(status_code=400, detail="format must be csv, xlsx, or pdf")

    if format == "xlsx":
        content = await generate_gap_analysis_xlsx(
            db, current_user, review_cycle_id, jurisdiction_id
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "gap-analysis.xlsx"
    elif format == "pdf":
        content = await generate_gap_analysis_pdf(
            db, current_user, review_cycle_id, jurisdiction_id
        )
        media_type = "application/pdf"
        filename = "gap-analysis.pdf"
    else:
        content = await generate_gap_analysis_csv(
            db, current_user, review_cycle_id, jurisdiction_id
        )
        media_type = "text/csv"
        filename = "gap-analysis.csv"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/statement-of-applicability")
async def get_statement_of_applicability(
    format: str = Query("xlsx", description="Output format: xlsx or pdf"),
    review_cycle_id: Optional[uuid.UUID] = Query(None, description="Review cycle ID (required)"),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to include"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if review_cycle_id is None:
        raise HTTPException(status_code=400, detail="review_cycle_id is required")

    cycle = await _get_review_cycle_or_404(db, current_user, review_cycle_id)

    field_keys: Optional[list[str]]
    if fields is None:
        field_keys = None
    else:
        trimmed = [key.strip() for key in fields.split(",") if key.strip()]
        if not trimmed:
            raise HTTPException(status_code=400, detail="fields cannot be empty")
        field_keys = trimmed

    try:
        selected_fields = get_statement_of_applicability_fields(field_keys)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        allowed = ", ".join(field.key for field in get_statement_of_applicability_fields(None))
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fields: {exc}. Allowed fields: {allowed}",
        ) from exc

    if format not in {"xlsx", "pdf"}:
        raise HTTPException(status_code=400, detail="format must be xlsx or pdf")

    if format == "pdf":
        content = await generate_statement_of_applicability_pdf(db, cycle, selected_fields)
        media_type = "application/pdf"
        filename = "statement-of-applicability.pdf"
    else:
        content = await generate_statement_of_applicability_xlsx(db, cycle, selected_fields)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "statement-of-applicability.xlsx"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/review-cycle-report")
async def get_review_cycle_report(
    review_cycle_id: Optional[uuid.UUID] = Query(None, description="Review cycle ID (required)"),
    reviewer_display: str = Query("both", description="Reviewer display: names, emails, both, ids"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if review_cycle_id is None:
        raise HTTPException(status_code=400, detail="review_cycle_id is required")
    if reviewer_display not in {"names", "emails", "both", "ids"}:
        raise HTTPException(
            status_code=400,
            detail="reviewer_display must be names, emails, both, or ids",
        )

    cycle = await _get_review_cycle_or_404(db, current_user, review_cycle_id)
    pdf_content = await generate_review_cycle_report_pdf(db, cycle, reviewer_display)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=review-cycle-report.pdf"},
    )


@router.get("/audit-trail")
async def get_audit_trail(
    format: str = Query("csv", description="Output format: csv"),
    from_date: Optional[str] = Query(
        None, description="Inclusive start date or ISO timestamp (UTC)"
    ),
    to_date: Optional[str] = Query(None, description="Inclusive end date or ISO timestamp (UTC)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    # Calendar dates include the entire selected day. Explicit timestamps retain their precision.
    def boundary(value: str | None, end_of_day: bool = False) -> datetime | None:
        if value is None:
            return None
        try:
            if len(value) == 10:
                return datetime.combine(
                    date.fromisoformat(value), time.max if end_of_day else time.min, timezone.utc
                )
            parsed = datetime.fromisoformat(value)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Use a valid calendar date or ISO timestamp."
            )

    start = boundary(from_date)
    end = boundary(to_date, end_of_day=True)
    if start and end and start > end:
        raise HTTPException(
            status_code=422, detail="The start date must be on or before the end date."
        )
    csv_content = await generate_audit_trail_csv(
        db, start, end, current_user.organization_id, current_user=current_user
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-trail.csv"},
    )


def _validate_period_days(period_days: Optional[int]) -> Optional[int]:
    if period_days is None:
        return None
    if period_days not in {90, 180, 365}:
        raise HTTPException(status_code=400, detail="period_days must be one of 90, 180, or 365")
    return period_days


@router.get("/change-management/components")
async def get_change_management_components_report(
    jurisdiction_id: Optional[uuid.UUID] = Query(None, description="Jurisdiction ID (required)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    csv_content = await generate_change_management_components_csv(
        db,
        jurisdiction_id,
        current_user.organization_id,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=change-management-components.csv"},
    )


@router.get("/change-management/component-history")
async def get_change_management_component_history_report(
    component_id: Optional[uuid.UUID] = Query(None, description="Component ID (required)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if component_id is None:
        raise HTTPException(status_code=400, detail="component_id is required")
    csv_content = await generate_change_management_component_history_csv(
        db,
        component_id,
        current_user.organization_id,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=change-management-component-history.csv"
        },
    )


@router.get("/change-management/hardware-locations")
async def get_change_management_hardware_locations_report(
    jurisdiction_id: Optional[uuid.UUID] = Query(None, description="Jurisdiction ID (required)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    csv_content = await generate_change_management_hardware_locations_csv(
        db,
        jurisdiction_id,
        current_user.organization_id,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=change-management-hardware-locations.csv"
        },
    )


@router.get("/change-management/verified-changes")
async def get_change_management_verified_changes_report(
    jurisdiction_id: Optional[uuid.UUID] = Query(None, description="Jurisdiction ID (required)"),
    period_days: Optional[int] = Query(
        None,
        description="Optional period filter (90, 180, 365)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    period_days = _validate_period_days(period_days)
    csv_content = await generate_change_management_verified_changes_csv(
        db,
        jurisdiction_id,
        current_user.organization_id,
        period_days,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=change-management-verified-changes.csv"
        },
    )


@router.get("/change-management/integration-changes")
async def get_change_management_integration_changes_report(
    jurisdiction_id: Optional[uuid.UUID] = Query(None, description="Jurisdiction ID (required)"),
    period_days: Optional[int] = Query(
        None,
        description="Optional period filter (90, 180, 365)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    if jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="jurisdiction_id is required")
    period_days = _validate_period_days(period_days)
    csv_content = await generate_change_management_integration_changes_csv(
        db,
        jurisdiction_id,
        current_user.organization_id,
        period_days,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=change-management-integration-changes.csv"
        },
    )


@router.get("/change-management/programme-assurance")
async def get_change_management_programme_assurance_report(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "approver", "admin")),
):
    from app.services.reports import generate_change_management_programme_assurance_csv

    csv_content = await generate_change_management_programme_assurance_csv(
        db, jurisdiction_id, current_user.organization_id
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=change-management-programme-assurance.csv"
        },
    )
