"""Explicit change impact scopes and assessments; links never widen project access."""

import uuid
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from app.api.tenant import get_active_user_in_org_or_404, get_org_owned_or_404
from app.models.change_management import ChangeRequirementImpact
from app.models.document import Document
from app.models.program import (
    CertificationProject,
    CertificationProjectRequirementBaseline,
    RequirementSetVersion,
    ReviewCycleRequirementBaseline,
)
from app.models.requirement import Requirement
from app.models.review import ReviewCycle, ReviewItem
from app.services.access import access_clause, require_access
from app.services.audit import log_action


async def project_access(db, user, project_id, action="view"):
    if project_id is None:
        return True
    return bool(
        await db.scalar(
            select(CertificationProject.id).where(
                CertificationProject.id == project_id,
                CertificationProject.organization_id == user.organization_id,
                access_clause(CertificationProject, user, action),
            )
        )
    )


async def visible_impacts(db, user, change_id):
    rows = list(
        (
            await db.scalars(
                select(ChangeRequirementImpact)
                .where(
                    ChangeRequirementImpact.change_entry_id == change_id,
                )
                .order_by(ChangeRequirementImpact.id)
            )
        ).all()
    )
    result = []
    for row in rows:
        if not await project_access(db, user, row.certification_project_id):
            continue
        version = await db.get(RequirementSetVersion, row.requirement_set_version_id)
        document = await db.get(Document, version.document_id) if version else None
        if not document or document.organization_id != user.organization_id:
            continue
        project = (
            await db.get(CertificationProject, row.certification_project_id)
            if row.certification_project_id
            else None
        )
        requirement = await db.get(Requirement, row.requirement_id) if row.requirement_id else None
        result.append(
            {
                "id": row.id,
                "requirement_set_version_id": row.requirement_set_version_id,
                "requirement_id": row.requirement_id,
                "requirement_reference_id": requirement.reference_id if requirement else None,
                "requirement_title": requirement.title if requirement else None,
                "certification_project_id": row.certification_project_id,
                "rationale": row.rationale,
                "set_name": document.name or document.filename,
                "version_number": version.version_number,
                "project_name": project.name if project else None,
            }
        )
    return result


async def validate_impact(db, user, register, value):
    version = await get_org_owned_or_404(
        db, RequirementSetVersion, value.requirement_set_version_id, user
    )
    if version.status != "approved":
        raise HTTPException(409, "Select an approved requirement-set version")
    document = await get_org_owned_or_404(db, Document, version.document_id, user)
    if document.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(400, "Impacted requirements must match the change jurisdiction")
    if value.certification_project_id:
        project = await require_access(
            db, CertificationProject, value.certification_project_id, user, "edit"
        )
        if project.jurisdiction_id != register.jurisdiction_id:
            raise HTTPException(400, "Project must match the change jurisdiction")
        baseline = await db.scalar(
            select(CertificationProjectRequirementBaseline.project_id).where(
                CertificationProjectRequirementBaseline.project_id == project.id,
                CertificationProjectRequirementBaseline.requirement_set_version_id == version.id,
            )
        )
        if not baseline:
            raise HTTPException(409, "Select a version pinned to this project's baseline")
    if value.requirement_id:
        row = await get_org_owned_or_404(db, Requirement, value.requirement_id, user)
        if row.requirement_set_version_id != version.id or not row.active:
            raise HTTPException(
                400, "Requirement must belong to the selected version and be active"
            )
    return version


def impact_key(value):
    return (value.requirement_set_version_id, value.requirement_id, value.certification_project_id)


async def replace_impacts(db, user, change, register, body):
    if change.status in {"approved", "implemented", "verified", "rolled_back"}:
        raise HTTPException(409, "Approved changes preserve their recorded impact scope")
    keys = [impact_key(value) for value in body.items]
    if len(keys) != len(set(keys)):
        raise HTTPException(400, "Duplicate requirement impact")
    for value in body.items:
        await validate_impact(db, user, register, value)
    existing = list(
        (
            await db.scalars(
                select(ChangeRequirementImpact).where(
                    ChangeRequirementImpact.change_entry_id == change.id,
                )
            )
        ).all()
    )
    editable = {
        impact_key(row): row
        for row in existing
        if await project_access(db, user, row.certification_project_id, "edit")
    }
    for key, row in editable.items():
        if key not in keys:
            await db.delete(row)
    for value in body.items:
        row = editable.get(impact_key(value))
        if row is None:
            row = ChangeRequirementImpact(change_entry_id=change.id, **value.model_dump())
            db.add(row)
        else:
            row.rationale = value.rationale
    # Broad change activity must not disclose protected scope identifiers or wording.
    await log_action(db, user, "update_impacts", "change_entry", str(change.id))
    await db.commit()
    return {"items": await visible_impacts(db, user, change.id)}


async def list_assessments(db, user, change_id):
    from app.api.reviews import _cycle_response

    cycles = list(
        (
            await db.scalars(
                select(ReviewCycle)
                .where(
                    ReviewCycle.change_entry_id == change_id,
                    ReviewCycle.organization_id == user.organization_id,
                    access_clause(ReviewCycle, user, "view"),
                )
                .order_by(ReviewCycle.created_at.desc(), ReviewCycle.id)
            )
        ).all()
    )
    return {"items": [await _cycle_response(db, cycle) for cycle in cycles]}


async def create_assessments(db, user, change, register, body):
    from app.api.reviews import _cycle_response
    from app.schemas.change_management import ChangeRequirementImpactCreate

    if len(set(body.impact_ids)) != len(body.impact_ids):
        raise HTTPException(400, "Duplicate impact selection")
    impacts = list(
        (
            await db.scalars(
                select(ChangeRequirementImpact).where(
                    ChangeRequirementImpact.change_entry_id == change.id,
                    ChangeRequirementImpact.id.in_(body.impact_ids),
                )
            )
        ).all()
    )
    if len(impacts) != len(body.impact_ids):
        raise HTTPException(404, "Requirement impact not found")
    for impact in impacts:
        await validate_impact(
            db,
            user,
            register,
            ChangeRequirementImpactCreate.model_validate(
                {
                    key: getattr(impact, key)
                    for key in (
                        "requirement_set_version_id",
                        "requirement_id",
                        "certification_project_id",
                        "rationale",
                    )
                }
            ),
        )
    for user_id in (body.default_assigned_reviewer_id, body.default_responsible_user_id):
        await get_active_user_in_org_or_404(
            db, user_id, user, detail="Assignee not found or inactive"
        )
    groups = defaultdict(list)
    for impact in impacts:
        groups[impact.certification_project_id].append(impact)
    cycles = []
    for project_id, selected in groups.items():
        version_ids = {impact.requirement_set_version_id for impact in selected}
        versions = list(
            (
                await db.scalars(
                    select(RequirementSetVersion).where(
                        RequirementSetVersion.id.in_(version_ids),
                    )
                )
            ).all()
        )
        if len({version.document_id for version in versions}) != len(versions):
            raise HTTPException(
                400, "One assessment can select only one version of each requirement set"
            )
        whole_versions = {
            impact.requirement_set_version_id
            for impact in selected
            if impact.requirement_id is None
        }
        requirement_ids = {impact.requirement_id for impact in selected if impact.requirement_id}
        requirements = list(
            (
                await db.scalars(
                    select(Requirement)
                    .where(
                        Requirement.organization_id == user.organization_id,
                        Requirement.requirement_set_version_id.in_(version_ids),
                        Requirement.active.is_(True),
                    )
                    .order_by(Requirement.document_id, Requirement.sort_order)
                )
            ).all()
        )
        requirements = [
            r
            for r in requirements
            if r.requirement_set_version_id in whole_versions or r.id in requirement_ids
        ]
        if not requirements:
            raise HTTPException(409, "Selected impacts have no active requirements to assess")
        cycle = ReviewCycle(
            id=uuid.uuid4(),
            organization_id=user.organization_id,
            jurisdiction_id=register.jurisdiction_id,
            certification_project_id=project_id,
            change_entry_id=change.id,
            cycle_type="change",
            name=body.name.strip(),
            deadline=body.deadline,
            scope="documents",
            created_by=user.id,
        )
        if not cycle.name:
            raise HTTPException(400, "Assessment name cannot be empty")
        import json

        cycle.scope_filter = json.dumps([str(version.document_id) for version in versions])
        db.add(cycle)
        await db.flush()
        for version in versions:
            db.add(
                ReviewCycleRequirementBaseline(
                    review_cycle_id=cycle.id,
                    document_id=version.document_id,
                    requirement_set_version_id=version.id,
                )
            )
        for req in requirements:
            non_actionable = req.requirement_type in {"informational", "not_applicable"}
            db.add(
                ReviewItem(
                    review_cycle_id=cycle.id,
                    requirement_id=req.id,
                    review_status="confirmed" if non_actionable else "pending",
                    assessment_status=(
                        "not_applicable"
                        if req.requirement_type == "not_applicable"
                        else "not_started"
                    ),
                    review_comment=(
                        "Informational requirement - no action required"
                        if req.requirement_type == "informational"
                        else (
                            "Not applicable requirement - no action required"
                            if req.requirement_type == "not_applicable"
                            else None
                        )
                    ),
                    assigned_reviewer_id=body.default_assigned_reviewer_id,
                    responsible_user_id=body.default_responsible_user_id,
                )
            )
        await log_action(db, user, "create", "review_cycle", str(cycle.id))
        cycles.append(cycle)
    await db.commit()
    return {"items": [await _cycle_response(db, cycle) for cycle in cycles]}
