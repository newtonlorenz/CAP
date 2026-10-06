import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models.audit import AuditLog
from app.models.change_management import (
    ChangeEntry,
    ChangeEntryComponent,
    ChangeEvent,
    Component,
    ComponentBaseline,
    ComponentBaselineItem,
    ComponentRegister,
    IntegrationCheck,
)
from app.models.user import User
from app.schemas.change_management import (
    BaselineDiffItem,
    BaselineDiffResponse,
    ChangeActivityItem,
    ChangeActivityResponse,
    ChangeEntityDeleteRequest,
    ChangeRequirementImpactsUpdate,
    ChangeAssessmentCreate,
    ChangeCompliance,
    ChangeEntryApproveRequest,
    ChangeRollbackRequest,
    HistoricalScopeAttestationRequest,
    ChangeEntryCreate,
    ChangeEntryImplementRequest,
    ChangeEntryRejectRequest,
    ChangeEntryResponse,
    ChangeEntryUpdate,
    ChangeEntryVerifyRequest,
    ChangeEventCreate,
    ChangeEventUpdate,
    ChangeEventResponse,
    ChangeEntryComponentResponse,
    ComponentBaselineCreate,
    ComponentBaselineResponse,
    ComponentCreate,
    ComponentRegisterCreate,
    ComponentRegisterResponse,
    ComponentRegisterUpdate,
    ComponentResponse,
    ComponentUpdate,
    IntegrationCheckCreate,
    IntegrationCheckUpdate,
    IntegrationCheckResponse,
)
from app.services.audit import log_action
from app.services.change_readiness import (
    readiness,
    programme_readiness,
    denmark_profile,
    dt,
    months,
)

router = APIRouter(prefix="/api/v1/change-management", tags=["change-management"])


def _org_filter(query, model, current_user: User):
    org_id = current_user.organization_id
    if org_id is None:
        return query.where(model.organization_id.is_(None))
    return query.where(model.organization_id == org_id)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_actual_date(value: Optional[datetime], label: str) -> None:
    if value is not None and value.replace(tzinfo=value.tzinfo or timezone.utc) > _utcnow():
        raise HTTPException(status_code=400, detail=f"{label} cannot be in the future")


def _derive_classification(values: dict) -> int:
    return max(
        int(values["confidentiality_code"]),
        int(values["integrity_code"]),
        int(values["availability_code"]),
        int(values["accountability_code"]),
    )


def _validate_component_payload(values: dict) -> int:
    for key in [
        "confidentiality_code",
        "integrity_code",
        "availability_code",
        "accountability_code",
    ]:
        code_value = values.get(key)
        if code_value is None:
            raise HTTPException(status_code=400, detail=f"{key} is required")
        code = int(code_value)
        if code not in {1, 2, 3}:
            raise HTTPException(status_code=400, detail=f"{key} must be one of 1, 2, 3")

    classification = _derive_classification(values)
    if classification == 3 and not values.get("checksum_hash"):
        raise HTTPException(
            status_code=400,
            detail="checksum_hash is required when component classification is 3",
        )

    public_cloud_exempt = (
        values.get("hosting_model") == "public_cloud"
        and settings.cloud_location_exemption_standard.strip()
        and (values.get("public_cloud_certification") or "").strip().casefold()
        == settings.cloud_location_exemption_standard.strip().casefold()
        and values.get("public_cloud_independent")
        and values.get("public_cloud_redundancy")
    )
    if (
        values.get("is_hardware")
        and not values.get("geographic_location")
        and not public_cloud_exempt
    ):
        raise HTTPException(
            status_code=400,
            detail="geographic_location is required for hardware components unless public cloud exemption criteria is met",
        )

    return classification


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _component_snapshot(component: Component) -> dict[str, Any]:
    return {
        "regulatory_scope": component.regulatory_scope,
        "component_uid": component.component_uid,
        "definition": component.definition,
        "version": component.version,
        "identifying_characteristics": component.identifying_characteristics,
        "change_owner_id": str(component.change_owner_id) if component.change_owner_id else None,
        "change_owner_name": component.change_owner_name,
        "confidentiality_code": component.confidentiality_code,
        "integrity_code": component.integrity_code,
        "availability_code": component.availability_code,
        "accountability_code": component.accountability_code,
        "classification_code": component.classification_code,
        "checksum_hash": component.checksum_hash,
        "is_hardware": component.is_hardware,
        "geographic_location": component.geographic_location,
        "hosting_model": component.hosting_model,
        "virtualized": component.virtualized,
        "public_cloud_provider": component.public_cloud_provider,
        "public_cloud_certification": component.public_cloud_certification,
        "public_cloud_iso27001": component.public_cloud_iso27001,
        "public_cloud_independent": component.public_cloud_independent,
        "public_cloud_redundancy": component.public_cloud_redundancy,
        "status": component.status,
        "updated_at": component.updated_at.isoformat() if component.updated_at else None,
    }


def _normalize_snapshot_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def _snapshot_differences(
    baseline: dict[str, Any], current: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    diffs: dict[str, dict[str, Any]] = {}
    keys = sorted(set(baseline.keys()) | set(current.keys()))
    for key in keys:
        baseline_value = _normalize_snapshot_value(baseline.get(key))
        current_value = _normalize_snapshot_value(current.get(key))
        if baseline_value != current_value:
            diffs[key] = {
                "baseline": baseline.get(key),
                "current": current.get(key),
            }
    return diffs


async def _get_register_for_user(
    db: AsyncSession,
    current_user: User,
    register_id: uuid.UUID,
) -> ComponentRegister:
    result = await db.execute(
        _org_filter(
            select(ComponentRegister).where(ComponentRegister.id == register_id),
            ComponentRegister,
            current_user,
        )
    )
    register = result.scalar_one_or_none()
    if register is None:
        raise HTTPException(status_code=404, detail="Component register not found")
    return register


async def _get_component_for_user(
    db: AsyncSession,
    current_user: User,
    component_id: uuid.UUID,
) -> tuple[Component, ComponentRegister]:
    result = await db.execute(
        _org_filter(
            select(Component, ComponentRegister)
            .join(ComponentRegister, Component.register_id == ComponentRegister.id)
            .where(Component.id == component_id),
            ComponentRegister,
            current_user,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return row[0], row[1]


async def _get_change_entry_for_user(
    db: AsyncSession,
    current_user: User,
    change_id: uuid.UUID,
    *,
    lock: bool = False,
) -> tuple[ChangeEntry, ComponentRegister]:
    query = _org_filter(
        select(ChangeEntry, ComponentRegister)
        .join(ComponentRegister, ChangeEntry.register_id == ComponentRegister.id)
        .where(ChangeEntry.id == change_id),
        ComponentRegister,
        current_user,
    )
    if lock:
        query = query.with_for_update(of=ChangeEntry).execution_options(populate_existing=True)
    result = await db.execute(query)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Change entry not found")
    return row[0], row[1]


async def _load_change_components(
    db: AsyncSession,
    change_id: uuid.UUID,
) -> list[ChangeEntryComponent]:
    result = await db.execute(
        select(ChangeEntryComponent)
        .where(ChangeEntryComponent.change_entry_id == change_id)
        .order_by(ChangeEntryComponent.created_at.asc())
    )
    return list(result.scalars().all())


async def _load_change_events(
    db: AsyncSession,
    change_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> list[ChangeEvent]:
    query = select(ChangeEvent).where(ChangeEvent.change_entry_id == change_id)
    if not include_deleted:
        query = query.where(ChangeEvent.deleted_at.is_(None))
    result = await db.execute(query.order_by(ChangeEvent.created_at.asc(), ChangeEvent.id.asc()))
    return list(result.scalars().all())


async def _load_integration_checks(
    db: AsyncSession,
    change_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> list[IntegrationCheck]:
    query = select(IntegrationCheck).where(IntegrationCheck.change_entry_id == change_id)
    if not include_deleted:
        query = query.where(IntegrationCheck.deleted_at.is_(None))
    result = await db.execute(
        query.order_by(IntegrationCheck.created_at.asc(), IntegrationCheck.id.asc())
    )
    return list(result.scalars().all())


async def _get_change_event_for_change(
    db: AsyncSession,
    change_id: uuid.UUID,
    event_id: uuid.UUID,
) -> ChangeEvent:
    result = await db.execute(
        select(ChangeEvent).where(
            and_(
                ChangeEvent.id == event_id,
                ChangeEvent.change_entry_id == change_id,
            )
        )
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Change event not found")
    return event


async def _get_integration_check_for_change(
    db: AsyncSession,
    change_id: uuid.UUID,
    check_id: uuid.UUID,
) -> IntegrationCheck:
    result = await db.execute(
        select(IntegrationCheck).where(
            and_(
                IntegrationCheck.id == check_id,
                IntegrationCheck.change_entry_id == change_id,
            )
        )
    )
    check = result.scalar_one_or_none()
    if check is None:
        raise HTTPException(status_code=404, detail="Integration check not found")
    return check


async def _build_change_response(
    db: AsyncSession,
    change_entry: ChangeEntry,
    current_user: User,
) -> ChangeEntryResponse:
    links = await _load_change_components(db, change_entry.id)
    events = await _load_change_events(db, change_entry.id)
    checks = await _load_integration_checks(db, change_entry.id)

    payload = ChangeEntryResponse.model_validate(change_entry).model_dump()
    register = await db.get(ComponentRegister, change_entry.register_id)
    payload["jurisdiction_id"] = register.jurisdiction_id if register else None
    payload["components"] = [
        ChangeEntryComponentResponse.model_validate(item).model_dump() for item in links
    ]
    payload["events"] = [ChangeEventResponse.model_validate(item).model_dump() for item in events]
    payload["integration_checks"] = [
        IntegrationCheckResponse.model_validate(item).model_dump() for item in checks
    ]
    from app.services.change_assessments import list_assessments

    assessment_list = await list_assessments(db, current_user, change_entry.id)
    payload["assessments"] = [item.model_dump() for item in assessment_list["items"]]
    visible_ids = {str(item.id) for item in assessment_list["items"]}
    payload["blocking_assessment_ids"] = [
        ident for ident in payload["blocking_assessment_ids"] if ident in visible_ids
    ]
    if payload.get("approved_scope"):
        payload["approved_scope"] = {
            **payload["approved_scope"],
            "blocking_assessment_ids": [
                ident
                for ident in payload["approved_scope"].get("blocking_assessment_ids", [])
                if ident in visible_ids
            ],
        }
    payload["readiness"] = await readiness(db, change_entry, register) if register else None
    return ChangeEntryResponse(**payload)


async def _replace_change_components(
    db: AsyncSession,
    register_id: uuid.UUID,
    change_id: uuid.UUID,
    component_inputs,
) -> None:
    unique_ids: set[uuid.UUID] = set()

    def _component_id(component_input) -> uuid.UUID:
        if isinstance(component_input, dict):
            return uuid.UUID(str(component_input["component_id"]))
        return component_input.component_id

    def _component_value(component_input, key: str):
        if isinstance(component_input, dict):
            return component_input.get(key)
        return getattr(component_input, key, None)

    for component_input in component_inputs:
        component_id = _component_id(component_input)
        if component_id in unique_ids:
            raise HTTPException(
                status_code=400, detail="Duplicate component_id in change components"
            )
        unique_ids.add(component_id)

    if unique_ids:
        result = await db.execute(
            select(Component.id).where(
                and_(
                    Component.id.in_(list(unique_ids)),
                    Component.register_id == register_id,
                )
            )
        )
        found = {row[0] for row in result.all()}
        missing = [str(component_id) for component_id in unique_ids if component_id not in found]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"One or more components are not in this register: {', '.join(missing)}",
            )

    await db.execute(
        delete(ChangeEntryComponent).where(ChangeEntryComponent.change_entry_id == change_id)
    )
    for item in component_inputs:
        component = await db.get(Component, _component_id(item))
        baseline_id = _component_value(item, "baseline_id")
        if baseline_id:
            baseline = await db.get(ComponentBaseline, baseline_id)
            if not baseline or baseline.register_id != register_id:
                raise HTTPException(400, "Baseline must belong to this register")
        supplied_version = _component_value(item, "version_at_proposal")
        if supplied_version and supplied_version != component.version:
            raise HTTPException(409, "Proposal version differs from the current component")
        if _component_value(item, "implemented_version"):
            raise HTTPException(
                400, "Implemented versions are recorded by the implementation action"
            )
        db.add(
            ChangeEntryComponent(
                change_entry_id=change_id,
                component_id=_component_id(item),
                version_at_proposal=component.version,
                planned_checksum_hash=_component_value(item, "planned_checksum_hash"),
                baseline_id=baseline_id,
                baseline_scope_assessment=_component_value(item, "baseline_scope_assessment"),
                planned_version=_component_value(item, "planned_version"),
                implemented_version=_component_value(item, "implemented_version"),
            )
        )


async def _record_status_event(
    db: AsyncSession,
    change_entry: ChangeEntry,
    current_user: User,
    status_from: Optional[str],
    status_to: str,
    note: Optional[str] = None,
):
    db.add(
        ChangeEvent(
            change_entry_id=change_entry.id,
            event_type="status_change",
            status_from=status_from,
            status_to=status_to,
            note=note,
            created_by=current_user.id,
            created_at=_utcnow(),
        )
    )


async def _validate_change_for_approval(db: AsyncSession, change_entry: ChangeEntry) -> None:
    required_fields = [
        "description",
        "change_type",
        "complexity_classification",
        "resource_assessment",
        "scheduling_assessment",
        "planned_start_at",
        "planned_end_at",
        "justification",
        "evaluation_effect",
        "evaluation_risk",
        "evaluation_regulatory_impact",
        "evaluation_ciaa_impact",
    ]
    missing = [field for field in required_fields if not getattr(change_entry, field)]

    components = await _load_change_components(db, change_entry.id)
    if not components:
        missing.append("components")
    if change_entry.testing_org_required:
        for field in ["testing_org_status", "testing_org_cycle"]:
            if not getattr(change_entry, field):
                missing.append(field)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Change entry is incomplete for approval. Missing: {', '.join(missing)}",
        )


async def _linked_component_uids(db: AsyncSession, change_id: uuid.UUID) -> list[str]:
    result = await db.execute(
        select(Component.component_uid)
        .join(ChangeEntryComponent, ChangeEntryComponent.component_id == Component.id)
        .where(ChangeEntryComponent.change_entry_id == change_id)
        .order_by(Component.component_uid.asc())
    )
    return [row[0] for row in result.all()]


def _validate_change_window_fields(change_entry: ChangeEntry) -> None:
    _validate_actual_date(
        change_entry.testing_org_approved_at, "Testing organisation approval date"
    )
    _validate_actual_date(change_entry.implemented_start_at, "Actual implementation start")
    _validate_actual_date(change_entry.implemented_end_at, "Actual implementation end")
    if (
        change_entry.planned_start_at
        and change_entry.planned_end_at
        and change_entry.planned_end_at < change_entry.planned_start_at
    ):
        raise HTTPException(status_code=400, detail="planned_end_at must be after planned_start_at")
    if (
        change_entry.implemented_start_at
        and change_entry.implemented_end_at
        and change_entry.implemented_end_at < change_entry.implemented_start_at
    ):
        raise HTTPException(
            status_code=400,
            detail="implemented_end_at must be after implemented_start_at",
        )


async def _validate_integration_checks_for_verification(
    db: AsyncSession,
    change_entry: ChangeEntry,
) -> None:
    checks = await _load_integration_checks(db, change_entry.id)
    if not checks:
        raise HTTPException(
            status_code=400,
            detail=(
                "Integration-related changes require at least one integration check before verification"
            ),
        )
    if not any(check.completed_at is not None for check in checks):
        raise HTTPException(
            status_code=400,
            detail=(
                "Integration-related changes require at least one completed integration check "
                "before verification"
            ),
        )
    invalid_checks = [
        check.action
        for check in checks
        if (
            check.result != "pass"
            or check.completed_at is None
            or check.completed_at.replace(tzinfo=check.completed_at.tzinfo or timezone.utc)
            > _utcnow()
            or not _normalize_optional_text(check.action_reference)
            or not _normalize_optional_text(check.evidence_notes)
        )
    ]
    if invalid_checks:
        raise HTTPException(
            status_code=400,
            detail=(
                "All integration checks must pass, have a completion date, action_reference "
                "and evidence_notes before verification. Resolve: " + ", ".join(invalid_checks)
            ),
        )


def _validate_testing_org_for_verification(change_entry: ChangeEntry, max_relevance: int) -> None:
    if max_relevance == 3:
        if change_entry.testing_org_status not in {"approved", "certified"}:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Relevance code 3 changes require testing_org_status approved or certified "
                    "before verification"
                ),
            )
        if change_entry.testing_org_cycle != "immediate":
            raise HTTPException(
                status_code=400,
                detail="Relevance code 3 changes require testing_org_cycle set to immediate",
            )
        if change_entry.testing_org_approved_at is None:
            raise HTTPException(
                status_code=400,
                detail="Relevance code 3 changes require testing_org_approved_at before verification",
            )
    elif max_relevance == 2:
        if not _normalize_optional_text(change_entry.testing_org_status):
            raise HTTPException(
                status_code=400,
                detail="Relevance code 2 changes require testing_org_status before verification",
            )
        if change_entry.testing_org_status == "rejected":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Relevance code 2 changes cannot be verified with testing_org_status rejected"
                ),
            )
        if change_entry.testing_org_cycle != "annual":
            raise HTTPException(
                status_code=400,
                detail="Relevance code 2 changes require testing_org_cycle set to annual",
            )
        if change_entry.testing_org_next_due_at is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Relevance code 2 changes require testing_org_next_due_at to track annual cadence"
                ),
            )


async def _highest_linked_component_relevance(
    db: AsyncSession,
    change_id: uuid.UUID,
) -> int:
    result = await db.execute(
        select(Component.classification_code)
        .join(ChangeEntryComponent, ChangeEntryComponent.component_id == Component.id)
        .where(ChangeEntryComponent.change_entry_id == change_id)
    )
    values = [row[0] for row in result.all()]
    return max(values) if values else 1


def _assurance_payload(incoming, previous=None):
    if incoming is None:
        return None
    incoming = jsonable_encoder(incoming)
    for key in [
        "latest_certification_at",
        "report_submitted_at",
        "postponement_notified_at",
        "change_plan_approved_at",
        "integration_procedure_approved_at",
    ]:
        _validate_actual_date(dt(incoming.get(key)), key.replace("_", " "))
    old = previous or {}
    latest, old_latest = (
        dt(incoming.get("latest_certification_at")),
        dt(old.get("latest_certification_at")),
    )
    if latest and old_latest and latest < old_latest:
        raise HTTPException(409, "Programme certification history cannot be moved backwards")
    if latest and old_latest and latest > old_latest:
        old_due = dt(old.get("renewal_due_at")) or months(old_latest, 12)
        anchor = dt(old.get("cadence_anchor_at")) or old_due
        incoming["cadence_anchor_at"] = anchor.isoformat()
        if latest > old_due:
            postponed = dt(old.get("postponed_until"))
            if (
                not postponed
                or postponed > months(old_due, 2)
                or postponed > months(old_latest, 14)
                or not old.get("postponement_notified_at")
                or dt(old.get("postponement_notified_at")) >= old_due
                or latest > postponed
                or not old.get("postponement_reference")
            ):
                raise HTTPException(
                    409,
                    "Late programme renewal requires previously recorded valid postponement and DGA notice",
                )
            incoming["renewal_report_due_at"] = min(postponed, months(old_latest, 14)).isoformat()
        incoming["postponed_until"] = None
        incoming["postponement_notified_at"] = None
        incoming["postponement_reference"] = None
    elif old.get("cadence_anchor_at"):
        incoming["cadence_anchor_at"] = old["cadence_anchor_at"]
    if old.get("renewal_report_due_at") and latest == old_latest:
        incoming["renewal_report_due_at"] = old["renewal_report_due_at"]
    return incoming


async def _validate_certification_record(db, change):
    cert = (change.compliance or {}).get("certification") or {}
    if cert.get("status") != "certified":
        return
    if not all(cert.get(k) for k in ["provider", "reference", "evidence", "certified_at"]):
        raise HTTPException(
            400,
            "An ATO certification attestation requires provider, report reference, evidence and actual date",
        )
    _validate_actual_date(dt(cert["certified_at"]), "ATO certification date")
    links = await _load_change_components(db, change.id)
    for link in links:
        component = await db.get(Component, link.component_id)
        snapshot = link.frozen_snapshot or _component_snapshot(component)
        if snapshot["classification_code"] in {2, 3}:
            version = link.implemented_version or link.planned_version
            if (cert.get("component_versions") or {}).get(str(link.component_id)) != version:
                raise HTTPException(
                    400, "ATO certification must identify each regulated component version"
                )
            if snapshot["classification_code"] == 3 and (cert.get("component_checksums") or {}).get(
                str(link.component_id)
            ) != (link.implemented_checksum_hash or link.planned_checksum_hash):
                raise HTTPException(
                    400, "ATO certification must identify each relevance code 3 checksum"
                )


async def _register_response(db, item):
    payload = ComponentRegisterResponse.model_validate(item).model_dump()
    if await denmark_profile(db, item):
        payload["programme_readiness"] = programme_readiness(item)
    return ComponentRegisterResponse(**payload)


async def _require_readiness(
    db, change, register, phase, *, implementation_at=None, implementation_end_at=None
):
    result = await readiness(
        db,
        change,
        register,
        implementation_at=implementation_at,
        implementation_end_at=implementation_end_at,
    )
    if result and not result[phase]["ready"]:
        raise HTTPException(400, "; ".join(r["message"] for r in result[phase]["reasons"]))


async def _validate_blocking_assessments(db, user, change, identifiers):
    from app.models.review import ReviewCycle
    from app.services.access import require_access

    for identifier in identifiers or []:
        cycle = await require_access(db, ReviewCycle, uuid.UUID(str(identifier)), user, "edit")
        if cycle.change_entry_id != change.id:
            raise HTTPException(400, "Blocking assessments must belong to this change")


@router.get("/registers", response_model=dict)
async def list_registers(
    jurisdiction_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(max(limit, 1), 1000)
    query = _org_filter(select(ComponentRegister), ComponentRegister, current_user)
    if jurisdiction_id is not None:
        query = query.where(ComponentRegister.jurisdiction_id == jurisdiction_id)

    result = await db.execute(query.order_by(ComponentRegister.created_at.desc()))
    rows = result.scalars().all()
    return {
        "items": [await _register_response(db, item) for item in rows[skip : skip + limit]],
        "total": len(rows),
    }


@router.post("/registers", response_model=ComponentRegisterResponse, status_code=201)
async def create_register(
    body: ComponentRegisterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    if body.status == "active":
        active_result = await db.execute(
            _org_filter(
                select(ComponentRegister).where(
                    and_(
                        ComponentRegister.jurisdiction_id == body.jurisdiction_id,
                        ComponentRegister.status == "active",
                    )
                ),
                ComponentRegister,
                current_user,
            )
        )
        if active_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail="An active component register already exists for this jurisdiction",
            )

    item = ComponentRegister(
        id=uuid.uuid4(),
        organization_id=current_user.organization_id,
        jurisdiction_id=body.jurisdiction_id,
        responsibility_role=body.responsibility_role,
        programme_assurance=_assurance_payload(body.programme_assurance),
        name=body.name.strip(),
        status=body.status,
        created_by=current_user.id,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "component_register",
        str(item.id),
        new_value={
            "jurisdiction_id": str(item.jurisdiction_id),
            "responsibility_role": item.responsibility_role,
            "programme_assurance": item.programme_assurance,
            "name": item.name,
            "status": item.status,
        },
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An active component register already exists for this jurisdiction",
        ) from exc
    await db.refresh(item)
    return await _register_response(db, item)


@router.patch("/registers/{register_id}", response_model=ComponentRegisterResponse)
async def update_register(
    register_id: uuid.UUID,
    body: ComponentRegisterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    register = await _get_register_for_user(db, current_user, register_id)
    updates = body.model_dump(mode="json", exclude_unset=True)

    if "programme_assurance" in updates:
        updates["programme_assurance"] = _assurance_payload(
            updates["programme_assurance"], register.programme_assurance
        )
    target_status = updates.get("status", register.status)
    if target_status == "active" and register.status != "active":
        active_result = await db.execute(
            _org_filter(
                select(ComponentRegister).where(
                    and_(
                        ComponentRegister.jurisdiction_id == register.jurisdiction_id,
                        ComponentRegister.status == "active",
                        ComponentRegister.id != register.id,
                    )
                ),
                ComponentRegister,
                current_user,
            )
        )
        if active_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail="An active component register already exists for this jurisdiction",
            )

    old_value = jsonable_encoder({field: getattr(register, field) for field in updates})
    for field, value in updates.items():
        if field == "name" and isinstance(value, str):
            value = value.strip()
        setattr(register, field, value)

    await log_action(
        db,
        current_user,
        "update",
        "component_register",
        str(register.id),
        old_value=old_value,
        new_value=updates,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An active component register already exists for this jurisdiction",
        ) from exc
    await db.refresh(register)
    return await _register_response(db, register)


@router.get("/registers/{register_id}/components", response_model=dict)
async def list_components(
    register_id: uuid.UUID,
    status: Optional[str] = None,
    classification_code: Optional[int] = None,
    hosting_model: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = await _get_register_for_user(db, current_user, register_id)
    limit = min(max(limit, 1), 1000)

    query = select(Component).where(Component.register_id == register_id)
    if status:
        query = query.where(Component.status == status)
    if classification_code is not None:
        query = query.where(Component.classification_code == classification_code)
    if hosting_model:
        query = query.where(Component.hosting_model == hosting_model)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Component.component_uid.ilike(like),
                Component.definition.ilike(like),
                Component.identifying_characteristics.ilike(like),
            )
        )

    result = await db.execute(
        query.order_by(Component.component_uid.asc(), Component.created_at.asc())
    )
    rows = result.scalars().all()
    return {
        "items": [ComponentResponse.model_validate(item) for item in rows[skip : skip + limit]],
        "total": len(rows),
    }


@router.post(
    "/registers/{register_id}/components", response_model=ComponentResponse, status_code=201
)
async def create_component(
    register_id: uuid.UUID,
    body: ComponentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    _ = await _get_register_for_user(db, current_user, register_id)
    values = body.model_dump()
    values["component_uid"] = values["component_uid"].strip()
    classification_code = _validate_component_payload(values)

    duplicate_result = await db.execute(
        select(Component).where(
            and_(
                Component.register_id == register_id,
                Component.component_uid == values["component_uid"],
            )
        )
    )
    if duplicate_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="component_uid already exists in this register")

    item = Component(
        id=uuid.uuid4(),
        register_id=register_id,
        component_uid=values["component_uid"],
        regulatory_scope=values["regulatory_scope"],
        definition=values["definition"],
        version=values["version"],
        identifying_characteristics=values["identifying_characteristics"],
        change_owner_id=values.get("change_owner_id"),
        change_owner_name=values.get("change_owner_name"),
        confidentiality_code=values["confidentiality_code"],
        integrity_code=values["integrity_code"],
        availability_code=values["availability_code"],
        accountability_code=values["accountability_code"],
        classification_code=classification_code,
        checksum_hash=values.get("checksum_hash"),
        is_hardware=values["is_hardware"],
        geographic_location=values.get("geographic_location"),
        hosting_model=values["hosting_model"],
        virtualized=values["virtualized"],
        public_cloud_provider=values.get("public_cloud_provider"),
        public_cloud_certification=values.get("public_cloud_certification"),
        public_cloud_iso27001=values["public_cloud_iso27001"],
        public_cloud_independent=values["public_cloud_independent"],
        public_cloud_redundancy=values["public_cloud_redundancy"],
        status=values["status"],
        created_by=current_user.id,
    )
    db.add(item)

    await log_action(
        db,
        current_user,
        "create",
        "component",
        str(item.id),
        new_value={"register_id": str(item.register_id), **_component_snapshot(item)},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="component_uid already exists in this register"
        ) from exc
    await db.refresh(item)
    return item


@router.patch("/components/{component_id}", response_model=ComponentResponse)
async def update_component(
    component_id: uuid.UUID,
    body: ComponentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    component, _ = await _get_component_for_user(db, current_user, component_id)
    updates = body.model_dump(exclude_unset=True)

    merged = _component_snapshot(component)
    merged.pop("classification_code")
    merged.pop("updated_at")
    merged["change_owner_id"] = component.change_owner_id
    merged.update(updates)
    for key in [
        "confidentiality_code",
        "integrity_code",
        "availability_code",
        "accountability_code",
        "is_hardware",
        "hosting_model",
        "virtualized",
        "public_cloud_iso27001",
        "public_cloud_independent",
        "public_cloud_redundancy",
        "status",
    ]:
        if merged.get(key) is None:
            merged[key] = getattr(component, key)
    if isinstance(merged.get("component_uid"), str):
        merged["component_uid"] = merged["component_uid"].strip()

    classification_code = _validate_component_payload(merged)

    if merged["component_uid"] != component.component_uid:
        duplicate_result = await db.execute(
            select(Component).where(
                and_(
                    Component.register_id == component.register_id,
                    Component.component_uid == merged["component_uid"],
                    Component.id != component.id,
                )
            )
        )
        if duplicate_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409, detail="component_uid already exists in this register"
            )

    old_value = _component_snapshot(component)
    for field, value in merged.items():
        setattr(component, field, value)
    component.classification_code = classification_code

    await log_action(
        db,
        current_user,
        "update",
        "component",
        str(component.id),
        old_value=old_value,
        new_value=_component_snapshot(component),
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="component_uid already exists in this register"
        ) from exc
    await db.refresh(component)
    return component


@router.delete("/components/{component_id}", status_code=204)
async def delete_component(
    component_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    component, _ = await _get_component_for_user(db, current_user, component_id)

    linked_result = await db.execute(
        select(ChangeEntryComponent.id)
        .where(ChangeEntryComponent.component_id == component.id)
        .limit(1)
    )
    if linked_result.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Component cannot be deleted because it is linked to change records. "
                "Set status to retired instead."
            ),
        )

    old_value = {
        "component_uid": component.component_uid,
        "version": component.version,
        "classification_code": component.classification_code,
        "status": component.status,
    }

    await db.delete(component)
    await log_action(
        db,
        current_user,
        "delete",
        "component",
        str(component.id),
        old_value=old_value,
        new_value={"deleted": True},
    )
    await db.commit()
    return None


@router.get("/registers/{register_id}/changes", response_model=dict)
async def list_changes(
    register_id: uuid.UUID,
    status: Optional[str] = None,
    change_type: Optional[str] = None,
    integration_related: Optional[bool] = None,
    component_id: Optional[uuid.UUID] = None,
    q: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = await _get_register_for_user(db, current_user, register_id)
    limit = min(max(limit, 1), 1000)

    query = select(ChangeEntry).where(ChangeEntry.register_id == register_id)
    if status:
        query = query.where(ChangeEntry.status == status)
    if change_type:
        query = query.where(ChangeEntry.change_type == change_type)
    if integration_related is not None:
        query = query.where(ChangeEntry.integration_related == integration_related)
    if component_id is not None:
        query = query.where(
            select(ChangeEntryComponent.id)
            .where(
                ChangeEntryComponent.change_entry_id == ChangeEntry.id,
                ChangeEntryComponent.component_id == component_id,
            )
            .exists()
        )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                ChangeEntry.title.ilike(like),
                ChangeEntry.description.ilike(like),
                ChangeEntry.justification.ilike(like),
            )
        )
    if from_date:
        query = query.where(ChangeEntry.created_at >= from_date)
    if to_date:
        query = query.where(ChangeEntry.created_at <= to_date)

    # A correlated existence filter avoids duplicates without comparing JSON rows.
    total = await db.scalar(query.with_only_columns(func.count()).order_by(None))
    result = await db.execute(
        query.order_by(ChangeEntry.created_at.desc(), ChangeEntry.id)
        .offset(max(skip, 0))
        .limit(limit)
    )
    page_rows = result.scalars().all()

    items = []
    for row in page_rows:
        items.append(await _build_change_response(db, row, current_user))

    return {"items": items, "total": total or 0}


@router.post(
    "/registers/{register_id}/changes", response_model=ChangeEntryResponse, status_code=201
)
async def create_change(
    register_id: uuid.UUID,
    body: ChangeEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    _ = await _get_register_for_user(db, current_user, register_id)

    item = ChangeEntry(
        register_id=register_id,
        title=body.title.strip(),
        description=_normalize_optional_text(body.description),
        category=_normalize_optional_text(body.category),
        change_type=body.change_type,
        proposed_by_name_snapshot=current_user.full_name or current_user.email,
        complexity_classification=body.complexity_classification,
        resource_assessment=_normalize_optional_text(body.resource_assessment),
        scheduling_assessment=_normalize_optional_text(body.scheduling_assessment),
        affected_components_summary=_normalize_optional_text(body.affected_components_summary),
        affected_docs_summary=_normalize_optional_text(body.affected_docs_summary),
        planned_start_at=body.planned_start_at,
        planned_end_at=body.planned_end_at,
        justification=_normalize_optional_text(body.justification),
        affected_documentation=_normalize_optional_text(body.affected_documentation),
        evaluation_effect=_normalize_optional_text(body.evaluation_effect),
        evaluation_risk=_normalize_optional_text(body.evaluation_risk),
        evaluation_regulatory_impact=_normalize_optional_text(body.evaluation_regulatory_impact),
        evaluation_ciaa_impact=_normalize_optional_text(body.evaluation_ciaa_impact),
        testing_org_required=body.testing_org_required,
        testing_org_status=_normalize_optional_text(body.testing_org_status),
        testing_org_due_at=body.testing_org_due_at,
        testing_org_cycle=body.testing_org_cycle,
        testing_org_next_due_at=body.testing_org_next_due_at,
        testing_org_approved_at=body.testing_org_approved_at,
        integration_related=body.integration_related,
        status="draft",
        proposed_by=current_user.id,
    )
    item.compliance = body.compliance.model_dump(mode="json")
    item.blocking_assessment_ids = [str(x) for x in body.blocking_assessment_ids]
    _validate_change_window_fields(item)
    db.add(item)
    await db.flush()

    await _validate_blocking_assessments(db, current_user, item, item.blocking_assessment_ids)
    await _replace_change_components(db, register_id, item.id, body.components)
    if not item.affected_components_summary:
        linked_uids = await _linked_component_uids(db, item.id)
        item.affected_components_summary = ", ".join(linked_uids) if linked_uids else None
    await _record_status_event(db, item, current_user, None, "draft", "Change proposal created")

    await log_action(
        db,
        current_user,
        "create",
        "change_entry",
        str(item.id),
        new_value={
            "register_id": str(item.register_id),
            "title": item.title,
            "status": item.status,
            "change_type": item.change_type,
        },
    )
    await db.commit()
    await db.refresh(item)
    return await _build_change_response(db, item, current_user)


@router.patch("/changes/{change_id}", response_model=ChangeEntryResponse)
async def update_change(
    change_id: uuid.UUID,
    body: ChangeEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    change_entry, register = await _get_change_entry_for_user(
        db, current_user, change_id, lock=True
    )
    updates = body.model_dump(exclude_unset=True)
    if change_entry.status == "rolled_back":
        raise HTTPException(status_code=409, detail="Rolled back changes are immutable")
    if change_entry.status == "verified":
        if current_user.role not in {"manager", "admin"}:
            raise HTTPException(
                403, "Only managers can record supplementary certification after verification"
            )
        if set(updates) != {"compliance"} or not updates["compliance"]:
            raise HTTPException(
                status_code=409,
                detail="Verified proposals are immutable; supplementary ATO certification can be recorded",
            )
        old = ChangeCompliance.model_validate(change_entry.compliance or {}).model_dump(mode="json")
        new = ChangeCompliance.model_validate(updates["compliance"]).model_dump(mode="json")
        if (
            any(new.get(k) != v for k, v in old.items() if k != "certification")
            or new.get("certification", {}).get("status") != "certified"
        ):
            raise HTTPException(
                409, "Only an evidenced supplementary certification may update a verified record"
            )
        if (old.get("certification") or {}).get("status") == "certified":
            raise HTTPException(409, "Recorded certification is immutable")
    if change_entry.status in {"approved", "implemented"}:
        testing_fields = {
            "testing_org_status",
            "testing_org_cycle",
            "testing_org_due_at",
            "testing_org_next_due_at",
            "testing_org_approved_at",
            "compliance",
        }
        if set(updates) - testing_fields:
            raise HTTPException(
                status_code=409,
                detail="The approved proposal is read-only. Reject an approved change before revising its proposal, or create a new change after implementation. Testing results can still be recorded until verification.",
            )
    if "compliance" in updates:
        if updates["compliance"] is None:
            raise HTTPException(400, "Compliance metadata cannot be cleared")
        updates["compliance"] = ChangeCompliance.model_validate(updates["compliance"]).model_dump(
            mode="json"
        )
        scope = (
            change_entry.approved_scope or {}
            if change_entry.status in {"approved", "implemented", "verified"}
            else {}
        )
        approved_evaluation = scope.get("evaluation_attestation")
        if approved_evaluation:
            approved_evaluation = ChangeCompliance.model_validate(
                {"evaluation": approved_evaluation}
            ).model_dump(mode="json")["evaluation"]
        if approved_evaluation and updates["compliance"].get("evaluation") != approved_evaluation:
            raise HTTPException(409, "The ATO evaluation approved with this proposal is immutable")
        previous_cert = ChangeCompliance.model_validate(change_entry.compliance or {}).model_dump(
            mode="json"
        )["certification"]
        if (
            change_entry.status in {"approved", "implemented", "verified"}
            and previous_cert.get("status") == "certified"
            and updates["compliance"].get("certification") != previous_cert
        ):
            raise HTTPException(409, "Recorded ATO certification is immutable")
        frozen = scope.get("compliance_triggers", {})
        for group, fields in frozen.items():
            for field, value in fields.items():
                previous = ((change_entry.compliance or {}).get(group) or {}).get(field)
                protected = previous if previous is not None else value
                incoming = updates["compliance"].get(group, {}).get(field)
                if (
                    protected is not None
                    and incoming != protected
                    and not (
                        field == "game_approval_required"
                        and protected is False
                        and incoming is True
                    )
                ):
                    raise HTTPException(
                        409,
                        "Approved regulatory and supplier applicability cannot be narrowed; reject and revise the proposal",
                    )
    if "blocking_assessment_ids" in updates:
        await _validate_blocking_assessments(
            db, current_user, change_entry, updates["blocking_assessment_ids"]
        )
        updates["blocking_assessment_ids"] = [
            str(x) for x in updates["blocking_assessment_ids"] or []
        ]
    component_updates = updates.pop("components", None)
    if "title" in updates and isinstance(updates["title"], str):
        updates["title"] = updates["title"].strip()
    for field in [
        "description",
        "category",
        "resource_assessment",
        "scheduling_assessment",
        "affected_components_summary",
        "affected_docs_summary",
        "justification",
        "affected_documentation",
        "evaluation_effect",
        "evaluation_risk",
        "evaluation_regulatory_impact",
        "evaluation_ciaa_impact",
        "testing_org_status",
    ]:
        if field in updates:
            updates[field] = _normalize_optional_text(updates[field])

    old_value = jsonable_encoder(
        {
            field: getattr(change_entry, field)
            for field in updates
            if field != "blocking_assessment_ids"
        }
    )
    audit_updates = {
        field: value for field, value in updates.items() if field != "blocking_assessment_ids"
    }
    if "blocking_assessment_ids" in updates:
        audit_updates["blocking_assessment_count"] = len(updates["blocking_assessment_ids"])
    if component_updates is not None:
        old_value["components"] = [
            jsonable_encoder(
                {
                    "component_id": link.component_id,
                    "version_at_proposal": link.version_at_proposal,
                    "planned_version": link.planned_version,
                    "implemented_version": link.implemented_version,
                }
            )
            for link in await _load_change_components(db, change_entry.id)
        ]
    for field, value in updates.items():
        setattr(change_entry, field, value)
    _validate_change_window_fields(change_entry)

    if component_updates is not None:
        await _replace_change_components(db, register.id, change_entry.id, component_updates)
    if component_updates is not None and not change_entry.affected_components_summary:
        linked_uids = await _linked_component_uids(db, change_entry.id)
        change_entry.affected_components_summary = ", ".join(linked_uids) if linked_uids else None

    if change_entry.status == "verified":
        await _validate_certification_record(db, change_entry)
    await log_action(
        db,
        current_user,
        "update",
        "change_entry",
        str(change_entry.id),
        old_value=old_value,
        new_value=jsonable_encoder(
            {
                **audit_updates,
                **({"components": component_updates} if component_updates is not None else {}),
            }
        ),
    )
    await db.commit()
    await db.refresh(change_entry)
    return await _build_change_response(db, change_entry, current_user)


@router.post("/changes/{change_id}/approve", response_model=ChangeEntryResponse)
async def approve_change(
    change_id: uuid.UUID,
    body: ChangeEntryApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change_entry, register = await _get_change_entry_for_user(
        db, current_user, change_id, lock=True
    )
    if change_entry.status not in {"draft", "rejected"}:
        raise HTTPException(
            status_code=409, detail="Only draft or rejected changes can be approved"
        )

    if await denmark_profile(db, register):
        await _require_readiness(db, change_entry, register, "approval")
    else:
        await _validate_change_for_approval(db, change_entry)
    latest_baseline = await db.scalar(
        select(ComponentBaseline)
        .where(
            ComponentBaseline.register_id == register.id,
            ComponentBaseline.certification_scope == "whole_platform",
            ComponentBaseline.certification_reference.is_not(None),
            ComponentBaseline.certification_at.is_not(None),
            ComponentBaseline.certification_at <= _utcnow(),
            ComponentBaseline.certification_evidence.is_not(None),
            ComponentBaseline.certification_ato.is_not(None),
        )
        .order_by(
            ComponentBaseline.certification_at.desc(), ComponentBaseline.established_at.desc()
        )
        .limit(1)
    )
    if latest_baseline and months(latest_baseline.certification_at, 12) < _utcnow():
        latest_baseline = None
    prior_bindings = {
        binding["component_id"]: binding.get("baseline_id")
        for binding in (change_entry.approved_scope or {}).get("baseline_bindings", [])
    }
    baseline_bindings = []
    for link in await _load_change_components(db, change_entry.id):
        component = await db.get(Component, link.component_id)
        prior_binding_retained = change_entry.status == "rejected" and str(
            link.baseline_id
        ) == prior_bindings.get(str(link.component_id))
        # A fresh approval binds current certification. An explicitly revised
        # baseline choice differs from the previous binding and is preserved.
        if latest_baseline and (not link.baseline_id or prior_binding_retained):
            link.baseline_id = latest_baseline.id
        baseline = await db.get(ComponentBaseline, link.baseline_id) if link.baseline_id else None
        baseline_item = (
            await db.scalar(
                select(ComponentBaselineItem).where(
                    ComponentBaselineItem.baseline_id == link.baseline_id,
                    ComponentBaselineItem.component_id == link.component_id,
                )
            )
            if baseline
            else None
        )
        old_snapshot = json.loads(baseline_item.snapshot_json) if baseline_item else {}
        baseline_bindings.append(
            {
                "component_id": str(link.component_id),
                "baseline_id": str(baseline.id) if baseline else None,
                "certification_reference": baseline.certification_reference if baseline else None,
                "certification_at": (
                    dt(baseline.certification_at).isoformat()
                    if baseline and baseline.certification_at
                    else None
                ),
                "certification_scope": baseline.certification_scope if baseline else "unresolved",
                "new_component": baseline_item is None,
                "scope_assessment": link.baseline_scope_assessment,
                "differences": _snapshot_differences(
                    {k: v for k, v in old_snapshot.items() if k != "updated_at"},
                    {k: v for k, v in _component_snapshot(component).items() if k != "updated_at"},
                ),
            }
        )
        link.frozen_snapshot = _component_snapshot(component)
        link.version_at_proposal = component.version
    c = change_entry.compliance or {}
    change_entry.approved_scope = {
        "responsibility_role": register.responsibility_role,
        "evaluation_attestation": (c.get("evaluation") or {}).copy(),
        "baseline_bindings": baseline_bindings,
        "proposal_compliance": c.copy(),
        "blocking_assessment_ids": change_entry.blocking_assessment_ids or [],
        "compliance_triggers": {
            "regulator": {
                k: (c.get("regulator") or {}).get(k)
                for k in ["game_approval_required", "error_identified_at"]
            },
            "supplier": {"recommended_at": (c.get("supplier") or {}).get("recommended_at")},
        },
    }
    previous_status = change_entry.status
    change_entry.status = "approved"
    change_entry.approval_decision = body.approval_decision.strip()
    change_entry.approved_by = current_user.id
    change_entry.approved_at = _utcnow()
    change_entry.rejection_reason = None
    change_entry.rejected_by = None
    change_entry.rejected_at = None

    await _record_status_event(
        db,
        change_entry,
        current_user,
        previous_status,
        "approved",
        change_entry.approval_decision,
    )

    await log_action(
        db,
        current_user,
        "approve",
        "change_entry",
        str(change_entry.id),
        old_value={"status": previous_status},
        new_value={
            "status": change_entry.status,
            "approved_scope": {
                k: v
                for k, v in change_entry.approved_scope.items()
                if k != "blocking_assessment_ids"
            },
            "blocking_assessment_count": len(change_entry.blocking_assessment_ids or []),
            "components": [
                jsonable_encoder(
                    {"component_id": x.component_id, "frozen_snapshot": x.frozen_snapshot}
                )
                for x in await _load_change_components(db, change_entry.id)
            ],
        },
    )
    await db.commit()
    await db.refresh(change_entry)
    return await _build_change_response(db, change_entry, current_user)


@router.post("/changes/{change_id}/reject", response_model=ChangeEntryResponse)
async def reject_change(
    change_id: uuid.UUID,
    body: ChangeEntryRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change_entry, register = await _get_change_entry_for_user(
        db, current_user, change_id, lock=True
    )
    if change_entry.status not in {"draft", "approved"}:
        raise HTTPException(
            status_code=409, detail="Only draft or approved changes can be rejected"
        )

    supplier = (change_entry.compliance or {}).get("supplier") or {}
    role = (change_entry.approved_scope or {}).get(
        "responsibility_role", register.responsibility_role
    )
    base_scope = False
    for link in await _load_change_components(db, change_entry.id):
        component = await db.get(Component, link.component_id)
        snapshot = link.frozen_snapshot or _component_snapshot(component)
        base_scope = base_scope or snapshot.get("regulatory_scope") == "base_platform"
    applies = await denmark_profile(db, register) and role == "licensed_operator" and base_scope
    if (
        applies
        and supplier.get("recommended_at")
        and not all(
            supplier.get(k)
            for k in ["rejection_attestation", "rejection_ato", "rejection_evidence"]
        )
    ):
        raise HTTPException(
            400,
            "Dismissing a supplier recommendation requires an evidenced ATO attestation of the individual justification",
        )
    previous_status = change_entry.status
    change_entry.status = "rejected"
    change_entry.rejection_reason = body.rejection_reason.strip()
    change_entry.rejected_by = current_user.id
    change_entry.rejected_at = _utcnow()

    await _record_status_event(
        db,
        change_entry,
        current_user,
        previous_status,
        "rejected",
        change_entry.rejection_reason,
    )

    await log_action(
        db,
        current_user,
        "reject",
        "change_entry",
        str(change_entry.id),
        old_value={"status": previous_status},
        new_value={"status": change_entry.status},
    )
    await db.commit()
    await db.refresh(change_entry)
    return await _build_change_response(db, change_entry, current_user)


@router.post("/changes/{change_id}/implement", response_model=ChangeEntryResponse)
async def implement_change(
    change_id: uuid.UUID,
    body: ChangeEntryImplementRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    change_entry, register = await _get_change_entry_for_user(
        db, current_user, change_id, lock=True
    )
    if change_entry.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved changes can be implemented")

    _validate_actual_date(body.implemented_start_at, "Actual implementation start")
    _validate_actual_date(body.implemented_end_at, "Actual implementation end")
    if (
        body.implemented_start_at
        and change_entry.approved_at
        and dt(body.implemented_start_at) < dt(change_entry.approved_at)
    ):
        raise HTTPException(400, "Implementation cannot precede recorded approval")
    await _require_readiness(
        db,
        change_entry,
        register,
        "implementation",
        implementation_at=body.implemented_start_at,
        implementation_end_at=body.implemented_end_at or _utcnow(),
    )
    links = await _load_change_components(db, change_entry.id)
    actual = {str(x.component_id): x for x in body.components}
    if await denmark_profile(db, register) and not body.components:
        raise HTTPException(
            400, "Record actual implemented versions and checksums for each linked component"
        )
    if body.components and (
        len(actual) != len(body.components) or set(actual) != {str(x.component_id) for x in links}
    ):
        raise HTTPException(400, "Implementation must identify each linked component exactly once")
    for link in links:
        item = actual.get(str(link.component_id))
        version = item.implemented_version if item else link.planned_version
        checksum = item.implemented_checksum_hash if item else link.planned_checksum_hash
        if version != link.planned_version or checksum != link.planned_checksum_hash:
            raise HTTPException(
                409,
                "Implemented version and checksum must match the approved proposal; revise and reapprove deviations",
            )
        if version is None and not await denmark_profile(db, register):
            continue
        component = await db.get(Component, link.component_id, with_for_update=True)
        before = _component_snapshot(component)
        if link.frozen_snapshot and _snapshot_differences(
            {k: v for k, v in link.frozen_snapshot.items() if k != "updated_at"},
            {k: v for k, v in before.items() if k != "updated_at"},
        ):
            raise HTTPException(409, "Component changed since approval; revise and reapprove")
        link.implemented_version = version
        link.implemented_checksum_hash = checksum
        component.version = version
        if checksum:
            component.checksum_hash = checksum
        await log_action(
            db,
            current_user,
            "implement",
            "component",
            str(component.id),
            old_value=before,
            new_value={**_component_snapshot(component), "change_id": str(change_entry.id)},
        )
    change_entry.approved_scope = {
        **(change_entry.approved_scope or {}),
        "implementation_compliance": (change_entry.compliance or {}).copy(),
        "implementation_recorded_by": str(current_user.id),
        "implementation_recorded_at": _utcnow().isoformat(),
    }
    previous_status = change_entry.status
    change_entry.status = "implemented"
    change_entry.implementation_notes = body.implementation_notes.strip()
    change_entry.implemented_by = current_user.id
    change_entry.implemented_start_at = body.implemented_start_at or _utcnow()
    change_entry.implemented_end_at = body.implemented_end_at or _utcnow()
    _validate_change_window_fields(change_entry)
    change_entry.implemented_at = change_entry.implemented_end_at

    await _record_status_event(
        db,
        change_entry,
        current_user,
        previous_status,
        "implemented",
        change_entry.implementation_notes,
    )

    await log_action(
        db,
        current_user,
        "implement",
        "change_entry",
        str(change_entry.id),
        old_value={"status": previous_status},
        new_value={"status": change_entry.status},
    )
    await db.commit()
    await db.refresh(change_entry)
    return await _build_change_response(db, change_entry, current_user)


@router.post("/changes/{change_id}/verify", response_model=ChangeEntryResponse)
async def verify_change(
    change_id: uuid.UUID,
    body: ChangeEntryVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change_entry, register = await _get_change_entry_for_user(
        db, current_user, change_id, lock=True
    )
    if change_entry.status != "implemented":
        raise HTTPException(status_code=409, detail="Only implemented changes can be verified")
    _validate_change_window_fields(change_entry)

    if change_entry.integration_related:
        await _validate_integration_checks_for_verification(db, change_entry)

    if await denmark_profile(db, register):
        await _require_readiness(db, change_entry, register, "verification")
    else:
        max_relevance = await _highest_linked_component_relevance(db, change_entry.id)
        _validate_testing_org_for_verification(change_entry, max_relevance)

    previous_status = change_entry.status
    change_entry.status = "verified"
    change_entry.verification_notes = body.verification_notes.strip()
    change_entry.verified_by = current_user.id
    change_entry.verified_at = _utcnow()

    await _record_status_event(
        db,
        change_entry,
        current_user,
        previous_status,
        "verified",
        change_entry.verification_notes,
    )

    await log_action(
        db,
        current_user,
        "verify",
        "change_entry",
        str(change_entry.id),
        old_value={"status": previous_status},
        new_value={"status": change_entry.status},
    )
    await db.commit()
    await db.refresh(change_entry)
    return await _build_change_response(db, change_entry, current_user)


@router.post(
    "/changes/{change_id}/historical-scope-attestation", response_model=ChangeEntryResponse
)
async def attest_historical_scope(
    change_id: uuid.UUID,
    body: HistoricalScopeAttestationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change, register = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    if change.status not in {"implemented", "verified"}:
        raise HTTPException(409, "Historical scope attestation is for implemented legacy records")
    links = await _load_change_components(db, change.id)
    attested = {x.component_id: x for x in body.components}
    if len(attested) != len(body.components) or set(attested) != {x.component_id for x in links}:
        raise HTTPException(400, "Attest each linked historical component exactly once")
    if any(x.frozen_snapshot for x in links):
        raise HTTPException(409, "Existing historical snapshots cannot be overwritten")
    if body.responsibility_role == "unknown" or any(
        x.regulatory_scope == "unknown" for x in body.components
    ):
        raise HTTPException(400, "Attested historical scope must be resolved from evidence")
    for link in links:
        item = attested[link.component_id]
        snapshot = item.model_dump(
            mode="json",
            exclude={"component_id", "planned_checksum_hash", "implemented_checksum_hash"},
        )
        snapshot["classification_code"] = _derive_classification(snapshot)
        if link.version_at_proposal and snapshot["version"] != link.version_at_proposal:
            raise HTTPException(
                409, "Historical attestation cannot rewrite the recorded proposal version"
            )
        if snapshot["classification_code"] == 3 and not snapshot["checksum_hash"]:
            raise HTTPException(
                400, "Historical relevance code 3 scope needs an evidenced checksum"
            )
        for field in ["planned_checksum_hash", "implemented_checksum_hash"]:
            recorded = getattr(link, field)
            incoming = getattr(item, field)
            if recorded and incoming and recorded != incoming:
                raise HTTPException(409, "Historical attestation cannot replace recorded checksums")
            if snapshot["classification_code"] == 3 and not (recorded or incoming):
                raise HTTPException(
                    400,
                    "Historical relevance code 3 needs evidenced planned and implemented checksums",
                )
            if not recorded and incoming:
                setattr(link, field, incoming)
        link.frozen_snapshot = snapshot
    change.approved_scope = {
        "responsibility_role": body.responsibility_role,
        "blocking_assessment_ids": change.blocking_assessment_ids or [],
        "historical_attestation": {
            "recorded_by": str(current_user.id),
            "recorded_at": _utcnow().isoformat(),
            "evidence_reference": body.evidence_reference,
            "evidence": body.evidence,
        },
    }
    await log_action(
        db,
        current_user,
        "historical_scope_attestation",
        "change_entry",
        str(change.id),
        new_value={
            "approved_scope": change.approved_scope,
            "components": [
                {
                    "component_id": str(x.component_id),
                    "frozen_snapshot": x.frozen_snapshot,
                    "planned_checksum_hash": x.planned_checksum_hash,
                    "implemented_checksum_hash": x.implemented_checksum_hash,
                }
                for x in links
            ],
        },
    )
    await db.commit()
    await db.refresh(change)
    return await _build_change_response(db, change, current_user)


@router.post("/changes/{change_id}/rollback", response_model=ChangeEntryResponse)
async def rollback_change(
    change_id: uuid.UUID,
    body: ChangeRollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change, register = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    if change.status not in {"implemented", "verified"}:
        raise HTTPException(409, "Only implemented or verified changes can be rolled back")
    links = await _load_change_components(db, change.id)
    restored = {x.component_id: x for x in body.components}
    if len(restored) != len(body.components) or set(restored) != {x.component_id for x in links}:
        raise HTTPException(400, "Record every restored component exactly once")
    # A rollback is a new regulated change. Record observed recovery; CAP does not
    # authorise or actuate an uncertified release, nor pretend the rollback was certified.
    observations = []
    for link in links:
        component = await db.get(Component, link.component_id, with_for_update=True)
        item = restored[link.component_id]
        if (
            component.version != item.implemented_version
            or component.checksum_hash != item.implemented_checksum_hash
        ):
            raise HTTPException(
                409,
                "Record the rollback through a separately approved and implemented change first; observed versions must match the current register",
            )
        observations.append(item.model_dump(mode="json"))
    recovery_query = select(ChangeEntry).where(
        ChangeEntry.register_id == register.id,
        ChangeEntry.id != change.id,
        ChangeEntry.status.in_(["implemented", "verified"]),
        ChangeEntry.implemented_at >= change.implemented_at,
    )
    recovery_query = recovery_query.where(ChangeEntry.id == body.recovery_change_id)
    candidates = list(
        (
            await db.scalars(
                recovery_query.order_by(ChangeEntry.implemented_at.desc(), ChangeEntry.id)
            )
        ).all()
    )
    recovery = None
    for candidate in candidates:
        recovery_links = {
            x.component_id: x for x in await _load_change_components(db, candidate.id)
        }
        if set(restored).issubset(recovery_links) and all(
            recovery_links[ident].implemented_version == item.implemented_version
            and recovery_links[ident].implemented_checksum_hash == item.implemented_checksum_hash
            for ident, item in restored.items()
        ):
            recovery = candidate
            break
    if recovery is None:
        raise HTTPException(
            409,
            "A separately approved and implemented recovery change must record these restored versions and checksums",
        )
    old_status = change.status
    change.status = "rolled_back"
    note = json.dumps(
        {
            "reason": body.reason,
            "outcome": body.outcome,
            "follow_up": body.follow_up,
            "components": observations,
            "recovery_change_id": str(recovery.id),
        }
    )
    await _record_status_event(db, change, current_user, old_status, "rolled_back", note)
    await log_action(
        db,
        current_user,
        "rollback",
        "change_entry",
        str(change.id),
        old_value={"status": old_status},
        new_value={"status": change.status, "observations": json.loads(note)},
    )
    await db.commit()
    await db.refresh(change)
    return await _build_change_response(db, change, current_user)


@router.post("/changes/{change_id}/events", response_model=ChangeEventResponse, status_code=201)
async def add_change_event(
    change_id: uuid.UUID,
    body: ChangeEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    change_entry, _ = await _get_change_entry_for_user(db, current_user, change_id, lock=True)

    event = ChangeEvent(
        id=uuid.uuid4(),
        change_entry_id=change_entry.id,
        event_type=body.event_type,
        note=_normalize_optional_text(body.note),
        created_by=current_user.id,
    )
    db.add(event)

    await log_action(
        db,
        current_user,
        "create",
        "change_event",
        str(event.id),
        new_value={
            "change_entry_id": str(change_entry.id),
            "event_type": event.event_type,
            "note": event.note,
        },
    )
    await db.commit()
    await db.refresh(event)
    return event


@router.patch("/changes/{change_id}/events/{event_id}", response_model=ChangeEventResponse)
async def update_change_event(
    change_id: uuid.UUID,
    event_id: uuid.UUID,
    body: ChangeEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    _, _ = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    event = await _get_change_event_for_change(db, change_id, event_id)
    if event.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Deleted events cannot be modified")
    if event.event_type == "status_change":
        raise HTTPException(status_code=409, detail="Status transition events are immutable")

    updates = body.model_dump(exclude_unset=True)
    if "note" in updates:
        updates["note"] = _normalize_optional_text(updates["note"])
    old_value = {"event_type": event.event_type, "note": event.note}
    for field, value in updates.items():
        setattr(event, field, value)
    event.updated_by = current_user.id
    event.updated_at = _utcnow()

    await log_action(
        db,
        current_user,
        "update",
        "change_event",
        str(event.id),
        old_value=old_value,
        new_value={"event_type": event.event_type, "note": event.note},
    )
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/changes/{change_id}/events/{event_id}", response_model=ChangeEventResponse)
async def delete_change_event(
    change_id: uuid.UUID,
    event_id: uuid.UUID,
    body: ChangeEntityDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    _, _ = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    event = await _get_change_event_for_change(db, change_id, event_id)
    if event.event_type == "status_change":
        raise HTTPException(status_code=409, detail="Status transition events cannot be deleted")
    if event.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Event already deleted")

    event.deleted_at = _utcnow()
    event.deleted_by = current_user.id
    event.deletion_reason = body.reason.strip()

    await log_action(
        db,
        current_user,
        "delete",
        "change_event",
        str(event.id),
        old_value={"event_type": event.event_type, "note": event.note},
        new_value={"deleted_at": event.deleted_at.isoformat(), "reason": event.deletion_reason},
    )
    await db.commit()
    await db.refresh(event)
    return event


@router.post(
    "/changes/{change_id}/integration-checks",
    response_model=IntegrationCheckResponse,
    status_code=201,
)
async def add_integration_check(
    change_id: uuid.UUID,
    body: IntegrationCheckCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    change_entry, _ = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    if change_entry.status in {"verified", "rolled_back"}:
        raise HTTPException(
            status_code=409,
            detail="Verified change checks are read-only. Create a new change for further work.",
        )
    _validate_actual_date(body.completed_at, "Integration check completion date")

    check = IntegrationCheck(
        id=uuid.uuid4(),
        change_entry_id=change_entry.id,
        action=body.action.strip(),
        action_reference=_normalize_optional_text(body.action_reference),
        result=body.result,
        completed_by=current_user.id if body.completed_at else None,
        completed_at=body.completed_at,
        notes=_normalize_optional_text(body.notes),
        evidence_notes=_normalize_optional_text(body.evidence_notes),
    )
    db.add(check)

    await log_action(
        db,
        current_user,
        "create",
        "integration_check",
        str(check.id),
        new_value={
            "change_entry_id": str(change_entry.id),
            "action": check.action,
            "action_reference": check.action_reference,
            "result": check.result,
            "completed_at": check.completed_at.isoformat() if check.completed_at else None,
            "notes": check.notes,
            "evidence_notes": check.evidence_notes,
        },
    )
    await db.commit()
    await db.refresh(check)
    return check


@router.patch(
    "/changes/{change_id}/integration-checks/{check_id}",
    response_model=IntegrationCheckResponse,
)
async def update_integration_check(
    change_id: uuid.UUID,
    check_id: uuid.UUID,
    body: IntegrationCheckUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    change_entry, _ = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    if change_entry.status in {"verified", "rolled_back"}:
        raise HTTPException(
            status_code=409,
            detail="Verified change checks are read-only. Create a new change for further work.",
        )
    _validate_actual_date(body.completed_at, "Integration check completion date")
    check = await _get_integration_check_for_change(db, change_id, check_id)
    if check.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Deleted integration checks cannot be modified")

    updates = body.model_dump(exclude_unset=True)
    for field in ["action_reference", "notes", "evidence_notes"]:
        if field in updates:
            updates[field] = _normalize_optional_text(updates[field])
    if "action" in updates and isinstance(updates["action"], str):
        updates["action"] = updates["action"].strip()
    if "completed_at" in updates:
        updates["completed_by"] = current_user.id if updates["completed_at"] else None

    old_value = {
        "action": check.action,
        "action_reference": check.action_reference,
        "result": check.result,
        "completed_at": check.completed_at.isoformat() if check.completed_at else None,
        "notes": check.notes,
        "evidence_notes": check.evidence_notes,
    }
    for field, value in updates.items():
        setattr(check, field, value)
    check.updated_by = current_user.id
    check.updated_at = _utcnow()

    await log_action(
        db,
        current_user,
        "update",
        "integration_check",
        str(check.id),
        old_value=old_value,
        new_value={
            "action": check.action,
            "action_reference": check.action_reference,
            "result": check.result,
            "completed_at": check.completed_at.isoformat() if check.completed_at else None,
            "notes": check.notes,
            "evidence_notes": check.evidence_notes,
        },
    )
    await db.commit()
    await db.refresh(check)
    return check


@router.delete(
    "/changes/{change_id}/integration-checks/{check_id}",
    response_model=IntegrationCheckResponse,
)
async def delete_integration_check(
    change_id: uuid.UUID,
    check_id: uuid.UUID,
    body: ChangeEntityDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("contributor", "manager", "admin")),
):
    change_entry, _ = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    if change_entry.status in {"verified", "rolled_back"}:
        raise HTTPException(
            status_code=409,
            detail="Verified change checks are read-only. Create a new change for further work.",
        )
    check = await _get_integration_check_for_change(db, change_id, check_id)
    if check.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Integration check already deleted")

    check.deleted_at = _utcnow()
    check.deleted_by = current_user.id
    check.deletion_reason = body.reason.strip()

    await log_action(
        db,
        current_user,
        "delete",
        "integration_check",
        str(check.id),
        old_value={
            "action": check.action,
            "result": check.result,
            "completed_at": check.completed_at.isoformat() if check.completed_at else None,
        },
        new_value={
            "deleted_at": check.deleted_at.isoformat(),
            "reason": check.deletion_reason,
        },
    )
    await db.commit()
    await db.refresh(check)
    return check


@router.get("/changes/{change_id}/activity", response_model=ChangeActivityResponse)
async def get_change_activity(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, _ = await _get_change_entry_for_user(db, current_user, change_id)
    events = await _load_change_events(db, change_id, include_deleted=True)
    checks = await _load_integration_checks(db, change_id, include_deleted=True)
    tracked_entity_ids = [str(change_id)]
    tracked_entity_ids.extend([str(event.id) for event in events])
    tracked_entity_ids.extend([str(check.id) for check in checks])

    audit_query = _org_filter(
        select(AuditLog)
        .where(
            and_(
                AuditLog.entity_type.in_(
                    [
                        "change_entry",
                        "change_event",
                        "integration_check",
                    ]
                ),
                AuditLog.entity_id.in_(tracked_entity_ids),
            )
        )
        .order_by(AuditLog.timestamp.asc()),
        AuditLog,
        current_user,
    )
    audit_result = await db.execute(audit_query)
    audit_rows = audit_result.scalars().all()

    items: list[ChangeActivityItem] = []
    for event in events:
        items.append(
            ChangeActivityItem(
                id=str(event.id),
                activity_type="status_event" if event.event_type == "status_change" else "event",
                action=event.event_type,
                occurred_at=event.deleted_at or event.updated_at or event.created_at,
                actor_id=event.deleted_by or event.updated_by or event.created_by,
                detail=event.deletion_reason or event.note,
                metadata={
                    "status_from": event.status_from,
                    "status_to": event.status_to,
                    "deleted_at": event.deleted_at.isoformat() if event.deleted_at else None,
                },
            )
        )

    for check in checks:
        items.append(
            ChangeActivityItem(
                id=str(check.id),
                activity_type="integration_check",
                action="integration_check_deleted" if check.deleted_at else "integration_check",
                occurred_at=check.deleted_at or check.updated_at or check.created_at,
                actor_id=check.deleted_by or check.updated_by or check.completed_by,
                detail=check.deletion_reason or check.notes,
                metadata={
                    "result": check.result,
                    "action": check.action,
                    "completed_at": check.completed_at.isoformat() if check.completed_at else None,
                },
            )
        )

    for audit in audit_rows:
        items.append(
            ChangeActivityItem(
                id=str(audit.id),
                activity_type="audit_log",
                action=f"{audit.action}:{audit.entity_type}",
                occurred_at=audit.timestamp,
                actor_id=audit.user_id,
                detail=None,
                metadata={},
            )
        )

    items.sort(key=lambda item: (item.occurred_at, item.id))
    return ChangeActivityResponse(items=items)


@router.post(
    "/registers/{register_id}/baselines",
    response_model=ComponentBaselineResponse,
    status_code=201,
)
async def create_baseline(
    register_id: uuid.UUID,
    body: ComponentBaselineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    _ = await _get_register_for_user(db, current_user, register_id)

    _validate_actual_date(body.certification_at, "Whole-platform baseline certification date")
    if body.certification_scope == "whole_platform" and not all(
        [
            body.certification_reference,
            body.certification_at,
            body.certification_evidence,
            body.certification_ato,
        ]
    ):
        raise HTTPException(
            400,
            "Whole-platform baseline attestation requires certification date, report reference, ATO and evidence",
        )
    baseline = ComponentBaseline(
        register_id=register_id,
        certification_scope=body.certification_scope,
        certification_at=body.certification_at,
        certification_evidence=body.certification_evidence,
        certification_ato=body.certification_ato,
        certification_reference=body.certification_reference,
        label=body.label.strip(),
        established_by=current_user.id,
    )
    db.add(baseline)
    await db.flush()

    component_result = await db.execute(
        select(Component)
        .where(Component.register_id == register_id)
        .order_by(Component.component_uid.asc())
    )
    components = component_result.scalars().all()

    for component in components:
        snapshot = _component_snapshot(component)
        db.add(
            ComponentBaselineItem(
                baseline_id=baseline.id,
                component_id=component.id,
                component_uid=component.component_uid,
                definition=component.definition,
                version=component.version,
                classification_code=component.classification_code,
                checksum_hash=component.checksum_hash,
                snapshot_json=json.dumps(snapshot, sort_keys=True),
            )
        )

    await log_action(
        db,
        current_user,
        "create",
        "component_baseline",
        str(baseline.id),
        new_value={
            "register_id": str(register_id),
            "label": baseline.label,
            "item_count": len(components),
        },
    )
    await db.commit()
    await db.refresh(baseline)
    return baseline


@router.get("/registers/{register_id}/baselines", response_model=dict)
async def list_baselines(
    register_id: uuid.UUID,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = await _get_register_for_user(db, current_user, register_id)
    limit = min(max(limit, 1), 1000)

    result = await db.execute(
        select(ComponentBaseline)
        .where(ComponentBaseline.register_id == register_id)
        .order_by(ComponentBaseline.established_at.desc())
    )
    rows = result.scalars().all()
    return {
        "items": [
            ComponentBaselineResponse.model_validate(item) for item in rows[skip : skip + limit]
        ],
        "total": len(rows),
    }


@router.get(
    "/registers/{register_id}/baselines/{baseline_id}/diff",
    response_model=BaselineDiffResponse,
)
async def baseline_diff(
    register_id: uuid.UUID,
    baseline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = await _get_register_for_user(db, current_user, register_id)

    baseline_result = await db.execute(
        select(ComponentBaseline).where(
            and_(
                ComponentBaseline.id == baseline_id,
                ComponentBaseline.register_id == register_id,
            )
        )
    )
    baseline = baseline_result.scalar_one_or_none()
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline not found")

    baseline_items_result = await db.execute(
        select(ComponentBaselineItem)
        .where(ComponentBaselineItem.baseline_id == baseline.id)
        .order_by(ComponentBaselineItem.component_uid.asc())
    )
    current_components_result = await db.execute(
        select(Component)
        .where(Component.register_id == register_id)
        .order_by(Component.component_uid.asc())
    )

    baseline_items = baseline_items_result.scalars().all()
    current_components = current_components_result.scalars().all()

    baseline_by_uid = {item.component_uid: item for item in baseline_items}
    current_by_uid = {item.component_uid: item for item in current_components}

    items: list[BaselineDiffItem] = []

    for uid, current in current_by_uid.items():
        baseline_item = baseline_by_uid.get(uid)
        current_snapshot = _component_snapshot(current)
        if baseline_item is None:
            diff_map = {
                key: {"baseline": None, "current": value} for key, value in current_snapshot.items()
            }
            items.append(
                BaselineDiffItem(
                    component_uid=uid,
                    change_type="added",
                    baseline_version=None,
                    current_version=current.version,
                    baseline_classification_code=None,
                    current_classification_code=current.classification_code,
                    changed_fields=sorted(diff_map.keys()),
                    field_differences=diff_map,
                )
            )
            continue
        baseline_snapshot = json.loads(baseline_item.snapshot_json)
        diffs = _snapshot_differences(baseline_snapshot, current_snapshot)
        if diffs:
            items.append(
                BaselineDiffItem(
                    component_uid=uid,
                    change_type="changed",
                    baseline_version=baseline_item.version,
                    current_version=current.version,
                    baseline_classification_code=baseline_item.classification_code,
                    current_classification_code=current.classification_code,
                    changed_fields=sorted(diffs.keys()),
                    field_differences=diffs,
                )
            )

    for uid, baseline_item in baseline_by_uid.items():
        if uid not in current_by_uid:
            baseline_snapshot = json.loads(baseline_item.snapshot_json)
            diff_map = {
                key: {"baseline": value, "current": None}
                for key, value in baseline_snapshot.items()
            }
            items.append(
                BaselineDiffItem(
                    component_uid=uid,
                    change_type="removed",
                    baseline_version=baseline_item.version,
                    current_version=None,
                    baseline_classification_code=baseline_item.classification_code,
                    current_classification_code=None,
                    changed_fields=sorted(diff_map.keys()),
                    field_differences=diff_map,
                )
            )

    items.sort(key=lambda item: (item.component_uid, item.change_type))

    summary = {
        "added": len([item for item in items if item.change_type == "added"]),
        "removed": len([item for item in items if item.change_type == "removed"]),
        "changed": len([item for item in items if item.change_type == "changed"]),
        "total": len(items),
        "generated_at": _utcnow().isoformat(),
    }

    return BaselineDiffResponse(
        baseline_id=baseline.id,
        register_id=register_id,
        summary=summary,
        items=items,
    )


@router.get("/changes/{change_id}/impacts")
async def get_change_impacts(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_change_entry_for_user(db, current_user, change_id)
    from app.services.change_assessments import visible_impacts

    return {"items": await visible_impacts(db, current_user, change_id)}


@router.put("/changes/{change_id}/impacts")
async def put_change_impacts(
    change_id: uuid.UUID,
    body: ChangeRequirementImpactsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change, register = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    from app.services.change_assessments import replace_impacts

    return await replace_impacts(db, current_user, change, register, body)


@router.get("/changes/{change_id}/assessments")
async def get_change_assessments(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_change_entry_for_user(db, current_user, change_id)
    from app.services.change_assessments import list_assessments

    return await list_assessments(db, current_user, change_id)


@router.post("/changes/{change_id}/assessments", status_code=201)
async def post_change_assessments(
    change_id: uuid.UUID,
    body: ChangeAssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("manager", "admin")),
):
    change, register = await _get_change_entry_for_user(db, current_user, change_id, lock=True)
    from app.services.change_assessments import create_assessments

    return await create_assessments(db, current_user, change, register, body)


@router.get("/changes/{change_id}", response_model=ChangeEntryResponse)
async def get_change(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change, _ = await _get_change_entry_for_user(db, current_user, change_id)
    return await _build_change_response(db, change, current_user)
