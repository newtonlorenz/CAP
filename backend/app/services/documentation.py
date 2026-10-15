"""Authoritative documentation coverage rules. Callers own commit/rollback."""
import json
import uuid
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, exists, or_, select

from app.api.tenant import get_active_user_in_org_or_404
from app.models.change_management import ChangeEntry, Component, ComponentRegister
from app.models.document import Document
from app.models.documentation import (
    AuditorRequestEvidence, AuditorRequestExpectation, AuditorRequestMapping,
    DocumentationCoverage, DocumentationExpectation, DocumentationReference,
    DocumentationRegister, DocumentationSection, DocumentationProcessTarget, EvidenceGroup, EvidenceGroupVersion, ExpectationRequirement,
)
from app.models.jurisdiction import Jurisdiction
from app.models.preparation import PreparationCase, PreparationEvidence
from app.models.program import CertificationProject, CertificationProjectRequirementBaseline, RequirementSetVersion
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.documentation import AuditorRequestCreate, ExpectationCreate, SectionCreate, SectionPatch
from app.services.access import access_clause, access_details, initialize_access, require_access, tenant_clause
from app.services.audit import log_action
from app.services.preparation import checked_evidence_problem, field_for


EDITOR_ROLES = {"contributor", "manager", "admin"}
REVIEWER_ROLES = {"approver", "manager", "admin"}


def check_role(user, action):
    roles = REVIEWER_ROLES if action == "approve" else EDITOR_ROLES
    if action in {"edit", "approve"} and user.role not in roles:
        raise HTTPException(403, "This role cannot perform this documentation action")


def check_revision(item, revision):
    if item.revision != revision:
        raise HTTPException(409, "This record has changed. Reload before saving.")


def expectation_clause(user, action="view"):
    register = exists(select(DocumentationRegister.id).where(
        DocumentationRegister.id == DocumentationExpectation.register_id,
        tenant_clause(DocumentationRegister, user), access_clause(DocumentationRegister, user, action),
    ))
    project = exists(select(CertificationProject.id).where(
        CertificationProject.id == DocumentationExpectation.project_id,
        tenant_clause(CertificationProject, user), access_clause(CertificationProject, user, action),
    ))
    return register & or_(DocumentationExpectation.project_id.is_(None), project)


def request_clause(user, action="view"):
    return exists(select(DocumentationRegister.id).where(
        DocumentationRegister.id == AuditorRequestMapping.register_id,
        tenant_clause(DocumentationRegister, user), access_clause(DocumentationRegister, user, action),
    )) & exists(select(PreparationCase.id).where(
        PreparationCase.id == AuditorRequestMapping.case_id,
        tenant_clause(PreparationCase, user), access_clause(PreparationCase, user, action),
    )) & exists(select(CertificationProject.id).where(
        CertificationProject.id == AuditorRequestMapping.project_id,
        tenant_clause(CertificationProject, user), access_clause(CertificationProject, user, action),
    ))


async def get_register(db, register_id, user, action="view", revision=None):
    check_role(user, action)
    item = await require_access(db, DocumentationRegister, register_id, user, action)
    if action in {"edit", "approve", "export", "manage_access"}:
        await db.refresh(item)
    if revision is not None:
        check_revision(item, revision)
    return item


async def get_expectation(db, expectation_id, user, action="view", revision=None):
    # Resolve only through the permitted parent; assignment is never an access grant.
    candidate = await db.scalar(select(DocumentationExpectation).where(
        DocumentationExpectation.id == expectation_id, expectation_clause(user, action),
    ))
    if candidate is None:
        raise HTTPException(404, "Not found")
    await get_register(db, candidate.register_id, user, action)
    if action in {"edit", "approve", "export"}:
        await db.execute(select(DocumentationExpectation.id).where(
            DocumentationExpectation.id == expectation_id).with_for_update())
        await db.refresh(candidate)
        # A project audience or register policy may have changed while waiting.
        if not await db.scalar(select(DocumentationExpectation.id).where(
            DocumentationExpectation.id == expectation_id, expectation_clause(user, action))):
            raise HTTPException(404, "Not found")
    if candidate.project_id is not None:
        await require_access(db, CertificationProject, candidate.project_id, user, action)
    if revision is not None:
        check_revision(candidate, revision)
    return candidate


async def validate_project(db, project_id, register, user, action="view"):
    if project_id is None:
        return None
    project = await require_access(db, CertificationProject, project_id, user, action)
    if project.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(422, "Project and register jurisdictions must match")
    return project


async def validate_section(db, section_id, register, user):
    if section_id is None:
        return None
    # Validate the parent audience before resolving a section supplied by a caller.
    await get_register(db, register.id, user)
    section = await db.scalar(select(DocumentationSection).where(
        DocumentationSection.id == section_id, DocumentationSection.register_id == register.id))
    if section is None:
        raise HTTPException(404, "Section not found in this register")
    return section


async def get_section(db, section_id, user, action="view"):
    section = await db.scalar(select(DocumentationSection).join(DocumentationRegister,
        DocumentationRegister.id == DocumentationSection.register_id).where(
            DocumentationSection.id == section_id, tenant_clause(DocumentationRegister, user),
            access_clause(DocumentationRegister, user, action)))
    if section is None:
        raise HTTPException(404, "Section not found")
    await get_register(db, section.register_id, user, action)
    return section


def section_name_key(name):
    return unicodedata.normalize("NFC", name.strip()).casefold()


async def section_response(db, section, register):
    await db.refresh(section)
    await db.refresh(register)
    return {"id": section.id, "register_id": section.register_id, "name": section.name,
        "position": section.position, "register_revision": register.revision}


async def ordered_sections(db, register_id):
    return list((await db.scalars(select(DocumentationSection).where(
        DocumentationSection.register_id == register_id).order_by(
            DocumentationSection.position, DocumentationSection.name_key, DocumentationSection.id))).all())


async def create_section(db, register, user, body):
    body = SectionCreate.model_validate(body)
    # require_access takes the register FOR UPDATE, reauthorises after waiting,
    # and get_register refreshes its revision before this structural mutation.
    register = await get_register(db, register.id, user, "edit", body.revision)
    name = body.name.strip()
    key = section_name_key(name)
    if await db.scalar(select(DocumentationSection.id).where(
        DocumentationSection.register_id == register.id, DocumentationSection.name_key == key)):
        raise HTTPException(409, "A section with this name already exists in this register")
    sections = await ordered_sections(db, register.id)
    position = len(sections) if body.position is None else min(body.position, len(sections))
    section = DocumentationSection(id=uuid.uuid4(), register_id=register.id, name=name,
        name_key=key, position=position, created_by=user.id)
    db.add(section)
    sections.insert(position, section)
    for index, entry in enumerate(sections):
        entry.position = index
    await advance_register(db, register, user, "create_documentation_section",
        {"section_id": str(section.id), "name": section.name, "position": section.position})
    return section


async def patch_section(db, section, user, body):
    body = SectionPatch.model_validate(body)
    register = await get_register(db, section.register_id, user, "edit", body.revision)
    await db.refresh(section)
    changes = body.model_dump(exclude={"revision"}, exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Section name and position cannot be null")
    new_name = changes.get("name", section.name).strip()
    new_key = section_name_key(new_name)
    if await db.scalar(select(DocumentationSection.id).where(
        DocumentationSection.register_id == register.id, DocumentationSection.name_key == new_key,
        DocumentationSection.id != section.id)):
        raise HTTPException(409, "A section with this name already exists in this register")
    changed = new_name != section.name
    section.name = new_name
    section.name_key = new_key
    if "position" in changes:
        sections = await ordered_sections(db, register.id)
        sections = [entry for entry in sections if entry.id != section.id]
        position = min(changes["position"], len(sections))
        changed |= position != section.position
        sections.insert(position, section)
        for index, entry in enumerate(sections):
            entry.position = index
    if changed:
        await advance_register(db, register, user, "update_documentation_section",
            {"section_id": str(section.id), "name": section.name, "position": section.position})
    return section


async def register_response(db, register, user):
    await db.refresh(register)
    result = {column.name: getattr(register, column.name) for column in register.__table__.columns}
    jurisdiction = await db.get(Jurisdiction, register.jurisdiction_id)
    result["jurisdiction_name"] = jurisdiction.name if jurisdiction else None
    policy = await access_details(db, "documentation_register", register.id, user)
    result["access"] = {"visibility": policy["visibility"], "permissions": policy["effective_permissions"], "revision": policy["revision"]}
    from app.services.documentation_processes import register_process_summary
    result["process"] = await register_process_summary(db, register, user)
    if result["process"] is not None and not result["process"].get("available"):
        result["review_cycle_id"] = None
        result["application_id"] = None
    return result


async def create_register(db, user, body):
    check_role(user, "edit")
    if await db.get(Jurisdiction, body.jurisdiction_id) is None:
        raise HTTPException(404, "Jurisdiction not found")
    row = DocumentationRegister(id=uuid.uuid4(), organization_id=user.organization_id,
        created_by=user.id, revision=1, **body.model_dump(exclude={"visibility"}))
    db.add(row)
    await db.flush()
    await initialize_access(db, "documentation_register", row.id, user, body.visibility)
    await log_action(db, user, "create", "documentation_register", str(row.id), new_value={"name": row.name})
    return row


async def advance_register(db, register, user, action, details=None):
    register.revision += 1
    await log_action(db, user, action, "documentation_register", str(register.id), new_value={"revision": register.revision, **(details or {})})
    await db.flush()


def invalidate_review(item):
    item.coverage_status = "unreviewed"
    item.review_rationale = None
    item.process_review_fingerprint = None
    item.reviewed_by = None
    item.reviewed_at = None


async def advance_expectation(db, item, user, action, old=None):
    item.revision += 1
    register = await get_register(db, item.register_id, user, "edit" if action != "review_coverage" else "approve")
    register.revision += 1
    await log_action(db, user, action, "documentation_expectation", str(item.id), old_value=old,
        new_value={"revision": item.revision, "coverage_status": item.coverage_status})
    await db.flush()


async def create_expectation(db, register, user, body):
    check_role(user, "edit")
    register = await get_register(db, register.id, user, "edit")
    body = ExpectationCreate.model_validate(body)
    await validate_section(db, body.section_id, register, user)
    await validate_project(db, body.project_id, register, user, "edit")
    from app.services.documentation_processes import validate_row_review
    await validate_row_review(db, register, body.review_cycle_id, body.project_id, user)
    await get_active_user_in_org_or_404(db, body.owner_id, user)
    row = DocumentationExpectation(id=uuid.uuid4(), register_id=register.id, created_by=user.id,
        revision=1, coverage_status="unreviewed", **body.model_dump())
    db.add(row)
    register.revision += 1
    await db.flush()
    await log_action(db, user, "create", "documentation_expectation", str(row.id), new_value={"title": row.title})
    return row


async def patch_expectation(db, item, user, body):
    changes = body.model_dump(exclude={"revision"}, exclude_unset=True)
    if any(changes.get(key, getattr(item, key)) is None for key in ("title", "description", "applicability")):
        raise HTTPException(422, "Title, description and applicability cannot be empty")
    if "section_id" in changes:
        register = await get_register(db, item.register_id, user, "edit")
        await validate_section(db, changes["section_id"], register, user)
    if changes.get("required_documentation") and "title" not in changes:
        changes["title"] = " ".join(changes["required_documentation"].split())[:500]
    if "owner_id" in changes:
        await get_active_user_in_org_or_404(db, changes["owner_id"], user)
    if "project_id" in changes and changes["project_id"] != item.project_id:
        if await db.scalar(select(DocumentationProcessTarget.id).where(DocumentationProcessTarget.expectation_id == item.id).limit(1)):
            raise HTTPException(409, "Clear process matches before changing the documentation project scope")
    if "project_id" in changes:
        register = await get_register(db, item.register_id, user, "edit")
        await validate_project(db, changes["project_id"], register, user, "edit")
        from app.services.documentation_processes import effective_process_register, validate_row_review
        await validate_row_review(db, register, item.review_cycle_id, changes["project_id"], user)
        await validate_requirement_links(db, effective_process_register(register, item), user, await requirement_link_values(db, item.id), changes["project_id"])
    applicability = changes.get("applicability", item.applicability)
    reason = changes.get("not_applicable_reason", item.not_applicable_reason)
    if applicability == "not_applicable" and not reason:
        raise HTTPException(422, "Explain why this expectation is not applicable")
    changed = {key: value for key, value in changes.items() if getattr(item, key) != value}
    if changed:
        for key, value in changed.items():
            setattr(item, key, value)
        if set(changed) - {"section_id", "owner_id"}:
            invalidate_review(item)
        await advance_expectation(db, item, user, "update", old={"changed_fields": sorted(changed)})
    return item


async def requirement_link_values(db, expectation_id):
    return [{"requirement_id": row.requirement_id, "requirement_set_version_id": row.requirement_set_version_id}
        for row in (await db.scalars(select(ExpectationRequirement).where(ExpectationRequirement.expectation_id == expectation_id))).all()]


async def validate_requirement_links(db, register, user, links, project_id=None):
    seen = set()
    for raw in links:
        data = raw.model_dump() if hasattr(raw, "model_dump") else raw
        requirement_id, version_id = data["requirement_id"], data["requirement_set_version_id"]
        if requirement_id in seen:
            raise HTTPException(422, "A requirement can be linked only once")
        seen.add(requirement_id)
        requirement = await db.scalar(select(Requirement).where(Requirement.id == requirement_id,
            tenant_clause(Requirement, user), Requirement.jurisdiction_id == register.jurisdiction_id))
        version = await db.scalar(select(RequirementSetVersion).where(RequirementSetVersion.id == version_id,
            tenant_clause(RequirementSetVersion, user)))
        if requirement is None or version is None:
            raise HTTPException(404, "Requirement or version not found")
        document = await db.scalar(select(Document).where(Document.id == version.document_id, tenant_clause(Document, user)))
        if document is None:
            raise HTTPException(404, "Requirement set not found")
        if requirement.requirement_set_version_id != version.id or requirement.document_id != version.document_id:
            raise HTTPException(422, "Requirement must belong to the selected version")
        if version.status != "approved":
            raise HTTPException(422, "Select an approved requirement version")
        if register.review_cycle_id:
            from app.models.program import ReviewCycleRequirementBaseline
            from app.models.review import ReviewItem
            from app.services.documentation_processes import get_review_process
            await get_review_process(db, register.review_cycle_id, register, user)
            pin = await db.scalar(select(ReviewCycleRequirementBaseline.requirement_set_version_id).where(
                ReviewCycleRequirementBaseline.review_cycle_id == register.review_cycle_id,
                ReviewCycleRequirementBaseline.document_id == version.document_id))
            member = await db.scalar(select(ReviewItem.id).where(ReviewItem.review_cycle_id == register.review_cycle_id, ReviewItem.requirement_id == requirement.id).limit(1))
            if member is None or (pin is not None and pin != version.id):
                raise HTTPException(422, "Requirement version must match the selected review scope")
        elif project_id:
            pin = await db.scalar(select(CertificationProjectRequirementBaseline.requirement_set_version_id).where(
                CertificationProjectRequirementBaseline.project_id == project_id,
                CertificationProjectRequirementBaseline.document_id == version.document_id))
            if pin != version.id:
                raise HTTPException(422, "Requirement version must match the project's pinned baseline")


async def replace_requirements(db, item, user, body):
    register = await get_register(db, item.register_id, user, "edit")
    from app.services.documentation_processes import effective_process_register
    register = effective_process_register(register, item)
    await validate_requirement_links(db, register, user, body.links, item.project_id)
    desired = {(link.requirement_id, link.requirement_set_version_id) for link in body.links}
    mapped = {(row.requirement_id, row.requirement_set_version_id) for row in (await db.scalars(select(DocumentationProcessTarget).where(DocumentationProcessTarget.expectation_id == item.id))).all()}
    if not mapped.issubset(desired):
        raise HTTPException(409, "Clear the corresponding process matches before removing these requirement links")
    current = {(link["requirement_id"], link["requirement_set_version_id"]) for link in await requirement_link_values(db, item.id)}
    if desired != current:
        await db.execute(delete(ExpectationRequirement).where(ExpectationRequirement.expectation_id == item.id))
        for requirement_id, version_id in desired:
            db.add(ExpectationRequirement(expectation_id=item.id, requirement_id=requirement_id, requirement_set_version_id=version_id))
        invalidate_review(item)
        await advance_expectation(db, item, user, "link_requirements")
    return item


async def evidence_currentness(db, evidence_id, user):
    group = await db.scalar(select(EvidenceGroup).join(EvidenceGroupVersion, EvidenceGroupVersion.group_id == EvidenceGroup.id)
        .where(EvidenceGroupVersion.evidence_id == evidence_id))
    if group is None:
        return True
    visible = await db.scalar(select(DocumentationRegister.id).where(DocumentationRegister.id == group.register_id,
        tenant_clause(DocumentationRegister, user), access_clause(DocumentationRegister, user, "view")))
    return bool(visible and group.current_evidence_id == evidence_id)


async def evidence_problems(db, evidence, user):
    problems = []
    if not await evidence_currentness(db, evidence.id, user):
        problems.append("superseded_or_unavailable_version")
    problem = await checked_evidence_problem(evidence, date.today())
    if problem:
        problems.append(problem)
    return problems


async def checked_evidence(db, evidence_id, user, action="view", current=False, lock=False):
    if current or lock:
        await db.execute(select(PreparationEvidence.id).where(PreparationEvidence.id == evidence_id,
            tenant_clause(PreparationEvidence, user)).with_for_update())
    evidence = await require_access(db, PreparationEvidence, evidence_id, user, action)
    if current or lock:
        await db.refresh(evidence)
    if current and await evidence_problems(db, evidence, user):
        raise HTTPException(422, "Evidence must be accessible, current and valid")
    return evidence


async def lock_evidence(db, evidence_ids, user):
    """Every parent locks reusable evidence in the same global order."""
    for evidence_id in sorted(set(evidence_ids), key=str):
        await db.execute(select(PreparationEvidence.id).where(
            PreparationEvidence.id == evidence_id, tenant_clause(PreparationEvidence, user)).with_for_update())


async def replace_coverage(db, item, user, body):
    if await db.scalar(select(DocumentationProcessTarget.id).where(DocumentationProcessTarget.expectation_id == item.id).limit(1)):
        raise HTTPException(409, "Manage evidence in the matched process collection; existing standalone links are retained separately")
    existing = (await db.scalars(select(DocumentationCoverage).where(DocumentationCoverage.expectation_id == item.id))).all()
    await lock_evidence(db, {link.evidence_id for link in existing} | {link.evidence_id for link in body.links}, user)
    seen = set()
    for link in body.links:
        if link.evidence_id in seen:
            raise HTTPException(422, "Evidence can be linked only once per expectation")
        seen.add(link.evidence_id)
        # Old versions can remain attached for traceability; sufficient review is stricter.
        await checked_evidence(db, link.evidence_id, user, lock=True)
    for link in existing:
        await checked_evidence(db, link.evidence_id, user, lock=True)
    keys = ("evidence_id", "locator", "scope", "period", "rationale")
    desired = {tuple(getattr(link, key) for key in keys) for link in body.links}
    if desired != {tuple(getattr(link, key) for key in keys) for link in existing}:
        await db.execute(delete(DocumentationCoverage).where(DocumentationCoverage.expectation_id == item.id))
        for link in body.links:
            db.add(DocumentationCoverage(expectation_id=item.id, **link.model_dump()))
        invalidate_review(item)
        await advance_expectation(db, item, user, "link_evidence")
    return item


async def review_coverage(db, item, user, body):
    check_role(user, "approve")
    from app.services.documentation_processes import build_process_targets, get_review_process, process_content_present, process_fingerprint
    register = await get_register(db, item.register_id, user, "approve")
    from app.services.documentation_processes import effective_process_register
    register = effective_process_register(register, item)
    mappings = (await db.scalars(select(DocumentationProcessTarget).where(DocumentationProcessTarget.expectation_id == item.id))).all()
    if mappings:
        if register.review_cycle_id:
            from app.models.review import ReviewCycle
            cycle = await get_review_process(db, register.review_cycle_id, register, user)
            if cycle.certification_project_id:
                await db.execute(select(CertificationProject.id).where(CertificationProject.id == cycle.certification_project_id).with_for_update())
            await db.execute(select(ReviewCycle.id).where(ReviewCycle.id == cycle.id).with_for_update())
        for case_id in sorted({mapping.case_id for mapping in mappings if mapping.case_id}, key=str):
            await db.execute(select(PreparationCase.id).where(PreparationCase.id == case_id, tenant_clause(PreparationCase, user)).with_for_update())
    targets = await build_process_targets(db, item, register, user)
    fingerprint = process_fingerprint(targets) if targets else None
    if body.status == "sufficient":
        if item.applicability != "applicable":
            raise HTTPException(422, "Confirm applicability before recording sufficient coverage")
        if targets:
            if any(not target.get("available") or target["collection"].get("warning") or target["collection"].get("unavailable") for target in targets):
                raise HTTPException(422, "Review every accessible process source before recording sufficient coverage")
            if not any(process_content_present(target) for target in targets):
                raise HTTPException(422, "Sufficient coverage requires supporting evidence")
            await lock_evidence(db, {uuid.UUID(str(entry["evidence_id"])) for target in targets
                for entry in target["collection"]["items"] if entry.get("kind") == "shared_evidence"}, user)
            for target in targets:
                for entry in target["collection"]["items"]:
                    if entry.get("problems"):
                        raise HTTPException(422, "Process evidence must be current and valid")
                    if entry.get("kind") == "shared_evidence":
                        await checked_evidence(db, uuid.UUID(str(entry["evidence_id"])), user, current=True)
        else:
            links = (await db.scalars(select(DocumentationCoverage).where(DocumentationCoverage.expectation_id == item.id))).all()
            if not links:
                raise HTTPException(422, "Sufficient coverage requires supporting evidence")
            await lock_evidence(db, {link.evidence_id for link in links}, user)
            for link in links:
                await checked_evidence(db, link.evidence_id, user, current=True)
    if (item.coverage_status, item.review_rationale, item.process_review_fingerprint) != (body.status, body.rationale, fingerprint):
        item.coverage_status = body.status
        item.review_rationale = body.rationale
        item.process_review_fingerprint = fingerprint
        item.reviewed_by = user.id
        item.reviewed_at = datetime.now(timezone.utc)
        await advance_expectation(db, item, user, "review_coverage")
    return item


async def checked_native(db, kind, native_id, register, user):
    model = Component if kind == "component" else ChangeEntry
    row = await db.scalar(select(model).join(ComponentRegister, ComponentRegister.id == model.register_id)
        .where(model.id == native_id, tenant_clause(ComponentRegister, user), ComponentRegister.jurisdiction_id == register.jurisdiction_id))
    if row is None:
        raise HTTPException(404, "Native CAP reference not found")
    return row


async def replace_references(db, item, user, body):
    register = await get_register(db, item.register_id, user, "edit")
    values = []
    for kind, ids in (("component", body.component_ids), ("change", body.change_ids)):
        for native_id in set(ids):
            await checked_native(db, kind, native_id, register, user)
            values.append({"kind": kind, f"{kind}_id": native_id})
    for link in body.jira_references:
        values.append({"kind": "jira", "jira_key": link.key, "jira_url": str(link.url) if link.url else None})
    keys = ("kind", "component_id", "change_id", "jira_key", "jira_url")
    desired = {tuple(value.get(key) for key in keys) for value in values}
    existing = (await db.scalars(select(DocumentationReference).where(DocumentationReference.expectation_id == item.id))).all()
    if desired != {tuple(getattr(value, key) for key in keys) for value in existing}:
        await db.execute(delete(DocumentationReference).where(DocumentationReference.expectation_id == item.id))
        for value in desired:
            db.add(DocumentationReference(expectation_id=item.id, **dict(zip(keys, value))))
        invalidate_review(item)
        await advance_expectation(db, item, user, "link_references")
    return item


async def build_expectation_responses(db, items, user, register):
    """Batch read-only projections for one actor and register in one request."""
    if not items:
        return []
    register = await get_register(db, register.id, user)
    ids = {item.id for item in items}
    allowed = set((await db.scalars(select(DocumentationExpectation.id).where(
        DocumentationExpectation.id.in_(ids), DocumentationExpectation.register_id == register.id,
        expectation_clause(user)))).all())
    if allowed != ids:
        raise HTTPException(404, "Not found")
    policy = await access_details(db, "documentation_register", register.id, user)
    context = {"register": register, "access": {"visibility": policy["visibility"],
        "permissions": policy["effective_permissions"], "revision": policy["revision"]},
        "targets": {}, "evidence_cache": {}, "process_summaries": {}}
    context["sections"] = {row.id: row for row in (await db.scalars(select(DocumentationSection).where(
        DocumentationSection.register_id == register.id, DocumentationSection.id.in_({item.section_id for item in items if item.section_id})))).all()}
    context["owners"] = {row.id: row for row in (await db.scalars(select(User).where(
        User.id.in_({item.owner_id for item in items if item.owner_id}), tenant_clause(User, user)))).all()}
    project_ids = {item.project_id for item in items if item.project_id}
    context["projects"] = {row.id: row for row in (await db.scalars(select(CertificationProject).where(
        CertificationProject.id.in_(project_ids), tenant_clause(CertificationProject, user), access_clause(CertificationProject, user, "view")))).all()}
    if set(context["projects"]) != project_ids:
        raise HTTPException(404, "Not found")
    for key, model in (("mappings", DocumentationProcessTarget), ("coverage", DocumentationCoverage),
                       ("references", DocumentationReference)):
        grouped = defaultdict(list)
        query = select(model).where(model.expectation_id.in_(ids))
        query = query.order_by(model.created_at, model.id) if model is DocumentationProcessTarget else query.order_by(model.id)
        for row in (await db.scalars(query)).all():
            grouped[row.expectation_id].append(row)
        context[key] = grouped
    from app.models.documentation_integrations import DocumentationImportRow
    context["provenance"] = defaultdict(list)
    for row in (await db.scalars(select(DocumentationImportRow).where(
        DocumentationImportRow.expectation_id.in_(ids), DocumentationImportRow.register_id == register.id).order_by(
            DocumentationImportRow.sheet, DocumentationImportRow.row_number, DocumentationImportRow.id))).all():
        context["provenance"][row.expectation_id].append(row)
    context["requirements"] = defaultdict(list)
    for link, requirement, version, document in (await db.execute(select(
        ExpectationRequirement, Requirement, RequirementSetVersion, Document).join(
            Requirement, Requirement.id == ExpectationRequirement.requirement_id).join(
            RequirementSetVersion, RequirementSetVersion.id == ExpectationRequirement.requirement_set_version_id).join(
            Document, Document.id == RequirementSetVersion.document_id).where(
                ExpectationRequirement.expectation_id.in_(ids), tenant_clause(Requirement, user),
                tenant_clause(RequirementSetVersion, user), tenant_clause(Document, user)))).all():
        context["requirements"][link.expectation_id].append((link, requirement, version, document))
    evidence_ids = {link.evidence_id for links in context["coverage"].values() for link in links}
    context["evidence"] = {row.id: row for row in (await db.scalars(select(PreparationEvidence).where(
        PreparationEvidence.id.in_(evidence_ids), tenant_clause(PreparationEvidence, user), access_clause(PreparationEvidence, user, "view")))).all()}
    groups = {evidence_id: (current_id, register_id) for evidence_id, current_id, register_id in (await db.execute(
        select(EvidenceGroupVersion.evidence_id, EvidenceGroup.current_evidence_id, EvidenceGroup.register_id).join(
            EvidenceGroup, EvidenceGroup.id == EvidenceGroupVersion.group_id).where(EvidenceGroupVersion.evidence_id.in_(evidence_ids)))).all()}
    group_registers = {value[1] for value in groups.values()}
    visible_registers = set((await db.scalars(select(DocumentationRegister.id).where(
        DocumentationRegister.id.in_(group_registers), tenant_clause(DocumentationRegister, user),
        access_clause(DocumentationRegister, user, "view")))).all()) if group_registers else set()
    context["evidence_state"] = {}
    for evidence in context["evidence"].values():
        group = groups.get(evidence.id)
        current = group is None or (group[0] == evidence.id and group[1] in visible_registers)
        problems = [] if current else ["superseded_or_unavailable_version"]
        problem = await checked_evidence_problem(evidence, date.today(), context["evidence_cache"])
        if problem:
            problems.append(problem)
        context["evidence_state"][evidence.id] = (current, problems)
    context["native"] = {}
    for kind, model in (("component", Component), ("change", ChangeEntry)):
        native_ids = {getattr(link, f"{kind}_id") for links in context["references"].values() for link in links if link.kind == kind}
        for native in (await db.scalars(select(model).join(ComponentRegister, ComponentRegister.id == model.register_id).where(
            model.id.in_(native_ids), tenant_clause(ComponentRegister, user), ComponentRegister.jurisdiction_id == register.jurisdiction_id))).all():
            context["native"][(kind, native.id)] = native
    from app.services.documentation_processes import effective_process_register, prefetch_review_targets
    scopes = {}
    for item in items:
        scoped = effective_process_register(register, item)
        key = (scoped.review_cycle_id, scoped.application_id)
        if key not in scopes:
            scopes[key] = (scoped, [])
        scopes[key][1].extend(context["mappings"][item.id])
    for scoped, mappings in scopes.values():
        await prefetch_review_targets(db, scoped, mappings, user, context["targets"], context["evidence_cache"])
        if scoped.application_id:
            from app.services.documentation_process_applications import prefetch_application_targets
            await prefetch_application_targets(db, scoped, mappings, user, context["targets"], context["evidence_cache"])
    return [await build_expectation_response(db, item, user, context=context) for item in items]


async def build_expectation_response(db, item, user, process_targets=None, context=None):
    if context is None:
        await db.refresh(item)
    result = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    register = context["register"] if context else await get_register(db, item.register_id, user)
    result["register_name"] = register.name
    section = context["sections"].get(item.section_id) if context else await validate_section(db, item.section_id, register, user)
    result["section_name"] = section.name if section else None
    result["access"] = context["access"] if context else (await register_response(db, register, user))["access"]
    from app.services.documentation_processes import effective_process_register, register_process_summary
    register = effective_process_register(register, item)
    key = (register.review_cycle_id, register.application_id)
    if context is not None and key in context["process_summaries"]:
        result["process"] = context["process_summaries"][key]
    else:
        result["process"] = await register_process_summary(db, register, user)
        if context is not None:
            context["process_summaries"][key] = result["process"]
    result["process_inherited"] = item.review_cycle_id is None
    if result["process"] is not None and not result["process"].get("available"):
        result["review_cycle_id"] = None
    owner = context["owners"].get(item.owner_id) if context else await db.scalar(select(User).where(User.id == item.owner_id, tenant_clause(User, user))) if item.owner_id else None
    result["owner_name"] = owner.full_name if owner else None
    project = context["projects"].get(item.project_id) if context else await validate_project(db, item.project_id, register, user)
    result["project_name"] = project.name if project else None
    from app.services.documentation_processes import build_process_targets
    if process_targets is not None:
        result["process_targets"] = process_targets
    elif context:
        result["process_targets"] = await build_process_targets(db, item, register, user,
            rows=context["mappings"][item.id], cache=context["targets"], evidence_cache=context["evidence_cache"])
    else:
        result["process_targets"] = await build_process_targets(db, item, register, user)
    result["coverage_mode"] = "process" if result["process_targets"] else "standalone"
    result["process_mapping_status"] = ("unavailable" if any(not target.get("available") for target in result["process_targets"])
        else "mapped" if result["process_targets"] else "unmapped")
    target_rows = context["mappings"][item.id] if context else (await db.scalars(select(DocumentationProcessTarget).where(DocumentationProcessTarget.expectation_id == item.id))).all()
    visible_pairs = {(uuid.UUID(str(target["requirement_id"])), uuid.UUID(str(target["requirement_set_version_id"])))
        for target in result["process_targets"] if target.get("available")}
    hidden_pairs = {(target.requirement_id, target.requirement_set_version_id) for target in target_rows} - visible_pairs
    result.pop("process_review_fingerprint", None)
    result["source_rows"] = []
    from app.models.documentation_integrations import DocumentationImportRow
    provenance = context["provenance"][item.id] if context else (await db.scalars(select(DocumentationImportRow).where(
        DocumentationImportRow.expectation_id == item.id,
        DocumentationImportRow.register_id == register.id).order_by(
            DocumentationImportRow.sheet, DocumentationImportRow.row_number, DocumentationImportRow.id))).all()
    for source in provenance:
        original = json.loads(source.original_json)
        result["source_rows"].append({"sheet": source.sheet, "row_number": source.row_number,
            "metadata": original.get("metadata", {}),
            "original_headers": original.get("original_headers", []),
            "original_values": original.get("original_values", [])})
    result["requirements"] = []
    links = [entry[0] for entry in context["requirements"][item.id]] if context else (await db.scalars(select(ExpectationRequirement).where(ExpectationRequirement.expectation_id == item.id))).all()
    requirement_details = {entry[0].requirement_id: entry[1:] for entry in context["requirements"][item.id]} if context else {}
    for link in links:
        if (link.requirement_id, link.requirement_set_version_id) in hidden_pairs:
            continue
        requirement = requirement_details[link.requirement_id][0] if context else await db.scalar(select(Requirement).where(Requirement.id == link.requirement_id, tenant_clause(Requirement, user)))
        version = requirement_details[link.requirement_id][1] if context else await db.scalar(select(RequirementSetVersion).where(RequirementSetVersion.id == link.requirement_set_version_id, tenant_clause(RequirementSetVersion, user)))
        if requirement is not None and version is not None:
            document = requirement_details[link.requirement_id][2] if context else await db.scalar(select(Document).where(Document.id == version.document_id, tenant_clause(Document, user)))
            if document is None:
                continue
            result["requirements"].append({"requirement_id": requirement.id, "requirement_set_version_id": version.id,
                "reference_id": requirement.reference_id, "title": requirement.title, "text": requirement.text,
                "document_id": version.document_id, "is_current": version.is_current,
                "version_number": version.version_number, "set_name": document.name or document.filename})
    result["coverage"] = []
    coverage = context["coverage"][item.id] if context else (await db.scalars(select(DocumentationCoverage).where(DocumentationCoverage.expectation_id == item.id))).all()
    unsuitable = False
    for link in coverage:
        evidence = context["evidence"].get(link.evidence_id) if context else await db.scalar(select(PreparationEvidence).where(PreparationEvidence.id == link.evidence_id,
            tenant_clause(PreparationEvidence, user), access_clause(PreparationEvidence, user, "view")))
        if evidence is None:
            unsuitable = True
            continue
        current, problems = context["evidence_state"][evidence.id] if context else (await evidence_currentness(db, evidence.id, user), await evidence_problems(db, evidence, user))
        unsuitable |= bool(problems)
        result["coverage"].append({**{key: getattr(link, key) for key in ("id", "evidence_id", "locator", "scope", "period", "rationale")},
            "title": evidence.title, "kind": evidence.kind, "is_current": current, "problems": problems})
    from app.services.documentation_processes import process_content_present, process_fingerprint
    process_targets = result["process_targets"]
    process_unavailable = any(not target.get("available") or target.get("collection", {}).get("unavailable") or target.get("collection", {}).get("warning") for target in process_targets)
    canonical_problems = [problem for target in process_targets if target.get("available")
        for entry in target["collection"]["items"] for problem in entry.get("problems", [])]
    process_stale = bool(process_targets and item.coverage_status != "unreviewed" and item.process_review_fingerprint != process_fingerprint(process_targets))
    standalone_unsuitable = unsuitable
    unsuitable = (process_unavailable or bool(canonical_problems) or process_stale) if process_targets else standalone_unsuitable
    result["effective_coverage_status"] = "unreviewed" if unsuitable else item.coverage_status
    result["standalone_coverage_label"] = "Additional standalone register evidence" if process_targets and result["coverage"] else None
    reasons = set()
    if process_unavailable:
        reasons.add("unavailable")
    if process_stale:
        reasons.add("stale")
    result["standalone_coverage_warning"] = "Some additional standalone evidence is unavailable or no longer valid" if process_targets and standalone_unsuitable else None
    if not process_targets and unsuitable and len(result["coverage"]) < len(coverage):
        reasons.add("unavailable")
    if (not process_targets and not coverage) or (process_targets and not process_unavailable and not any(process_content_present(target) for target in process_targets)):
        reasons.add("missing")
    problem_lists = [canonical_problems] if process_targets else [link["problems"] for link in result["coverage"]]
    for problems in problem_lists:
        for problem in problems:
            reasons.add({"superseded_or_unavailable_version": "stale", "superseded_evidence": "stale", "expired_evidence": "expired",
                "archived_evidence": "archived", "future_evidence": "future", "invalid_evidence_file": "invalid_file"}.get(problem, problem))
    if result["effective_coverage_status"] == "partial":
        reasons.add("partial")
    if result["effective_coverage_status"] == "unreviewed":
        reasons.add("unreviewed")
    result["derived_reasons"] = sorted(reasons)
    result["coverage_warning"] = "Coverage needs a fresh review of accessible, current evidence" if unsuitable else None
    # An inaccessible association does not reveal its identity, title or count.
    result["references"] = []
    references = context["references"][item.id] if context else (await db.scalars(select(DocumentationReference).where(DocumentationReference.expectation_id == item.id))).all()
    for link in references:
        value = {key: getattr(link, key) for key in ("id", "kind", "component_id", "change_id", "jira_key", "jira_url")}
        if link.kind == "jira":
            value["label"] = link.jira_key
        else:
            try:
                native = context["native"].get((link.kind, link.component_id or link.change_id)) if context else await checked_native(db, link.kind, link.component_id or link.change_id, register, user)
            except HTTPException as error:
                if error.status_code == 404:
                    continue
                raise
            if native is None:
                continue
            value["label"] = native.component_uid if link.kind == "component" else native.title
        result["references"].append(value)
    return result


async def build_group_response(db, group, user):
    await db.refresh(group)
    result = {column.name: getattr(group, column.name) for column in group.__table__.columns}
    result["versions"] = []
    rows = (await db.execute(select(EvidenceGroupVersion, PreparationEvidence)
        .join(PreparationEvidence, PreparationEvidence.id == EvidenceGroupVersion.evidence_id)
        .where(EvidenceGroupVersion.group_id == group.id, tenant_clause(PreparationEvidence, user),
            access_clause(PreparationEvidence, user, "view")).order_by(EvidenceGroupVersion.version.desc()))).all()
    for version, evidence in rows:
        result["versions"].append({"evidence_id": evidence.id, "version": version.version, "title": evidence.title,
            "kind": evidence.kind, "is_current": evidence.id == group.current_evidence_id, "problems": await evidence_problems(db, evidence, user)})
    # A caller must be able to view the current version before the group is listed.
    await checked_evidence(db, group.current_evidence_id, user)
    return result


async def add_group_version(db, group, user, evidence_id):
    await lock_evidence(db, {group.current_evidence_id, evidence_id}, user)
    await checked_evidence(db, group.current_evidence_id, user, lock=True)
    await checked_evidence(db, evidence_id, user, current=True)
    existing = await db.scalar(select(EvidenceGroupVersion).where(EvidenceGroupVersion.evidence_id == evidence_id))
    if existing:
        raise HTTPException(409, "This evidence version already has a stable evidence identity")
    group.revision += 1
    group.current_evidence_id = evidence_id
    db.add(EvidenceGroupVersion(group_id=group.id, evidence_id=evidence_id, version=group.revision))
    register = await get_register(db, group.register_id, user, "edit")
    await advance_register(db, register, user, "version_evidence", {"evidence_group_id": str(group.id)})
    # Past reviews and snapshots are retained; read-time validity reports supersession.
    return group


async def validate_request_links(db, register, request, user, expectation_ids, evidence_ids):
    for expectation_id in set(expectation_ids):
        expectation = await get_expectation(db, expectation_id, user)
        if expectation.register_id != register.id or expectation.project_id not in (None, request.project_id):
            raise HTTPException(422, "Requested expectations must belong to this register and project scope")
        # Global expectations may be reused only where their requirement versions match project pins.
        from app.services.documentation_processes import effective_process_register
        await validate_requirement_links(db, effective_process_register(register, expectation), user, await requirement_link_values(db, expectation.id), request.project_id)
    await lock_evidence(db, evidence_ids, user)
    for evidence_id in sorted(set(evidence_ids), key=str):
        await checked_evidence(db, evidence_id, user, lock=True)


async def create_auditor_request(db, register, user, body):
    register = await get_register(db, register.id, user, "edit")
    body = AuditorRequestCreate.model_validate(body)
    await validate_project(db, body.project_id, register, user, "edit")
    case = await require_access(db, PreparationCase, body.case_id, user, "edit")
    if case.kind != "audit" or case.project_id != body.project_id or case.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(422, "Use an audit form linked to the same project and jurisdiction")
    field_for(case, body.field_key)
    duplicate = await db.scalar(select(AuditorRequestMapping.id).where(AuditorRequestMapping.register_id == register.id,
        AuditorRequestMapping.case_id == body.case_id, AuditorRequestMapping.field_key == body.field_key,
        AuditorRequestMapping.list_revision == body.list_revision))
    if duplicate:
        raise HTTPException(409, "This request-list revision is already mapped")
    row = AuditorRequestMapping(id=uuid.uuid4(), register_id=register.id, created_by=user.id, revision=1,
        **body.model_dump(exclude={"expectation_ids", "evidence_ids"}))
    await validate_request_links(db, register, row, user, body.expectation_ids, body.evidence_ids)
    db.add(row)
    await db.flush()
    for expectation_id in set(body.expectation_ids):
        db.add(AuditorRequestExpectation(request_id=row.id, expectation_id=expectation_id))
    for evidence_id in set(body.evidence_ids):
        db.add(AuditorRequestEvidence(request_id=row.id, evidence_id=evidence_id))
    await advance_register(db, register, user, "map_auditor_request")
    await log_action(db, user, "create", "documentation_auditor_request", str(row.id), new_value={"request_id": row.request_id})
    return row


async def get_request(db, request_id, user, action="view", revision=None):
    row = await db.scalar(select(AuditorRequestMapping).where(AuditorRequestMapping.id == request_id, request_clause(user, action)))
    if row is None:
        raise HTTPException(404, "Not found")
    await get_register(db, row.register_id, user, action)
    if action in {"edit", "export"}:
        await db.execute(select(AuditorRequestMapping.id).where(AuditorRequestMapping.id == row.id).with_for_update())
        await db.refresh(row)
    await require_access(db, CertificationProject, row.project_id, user, action)
    await require_access(db, PreparationCase, row.case_id, user, action)
    if revision is not None:
        check_revision(row, revision)
    return row


async def patch_auditor_request(db, row, user, body):
    register = await get_register(db, row.register_id, user, "edit")
    current_expectations = list((await db.scalars(select(AuditorRequestExpectation.expectation_id).where(AuditorRequestExpectation.request_id == row.id))).all())
    current_evidence = list((await db.scalars(select(AuditorRequestEvidence.evidence_id).where(AuditorRequestEvidence.request_id == row.id))).all())
    await lock_evidence(db, set(current_evidence) | set(body.evidence_ids or []), user)
    for evidence_id in current_evidence:
        await checked_evidence(db, evidence_id, user, lock=True)
    for expectation_id in current_expectations:
        await get_expectation(db, expectation_id, user)
    changes = body.model_dump(exclude={"revision"}, exclude_unset=True)
    expectation_ids = changes.pop("expectation_ids", current_expectations)
    evidence_ids = changes.pop("evidence_ids", current_evidence)
    if expectation_ids is None or evidence_ids is None or changes.get("direction", row.direction) is None:
        raise HTTPException(422, "Direction and associations cannot be null")
    await validate_request_links(db, register, row, user, expectation_ids, evidence_ids)
    dirty = any(getattr(row, key) != value for key, value in changes.items()) or set(expectation_ids) != set(current_expectations) or set(evidence_ids) != set(current_evidence)
    if not dirty:
        return row
    for key, value in changes.items():
        setattr(row, key, value)
    await db.execute(delete(AuditorRequestExpectation).where(AuditorRequestExpectation.request_id == row.id))
    await db.execute(delete(AuditorRequestEvidence).where(AuditorRequestEvidence.request_id == row.id))
    for value in set(expectation_ids):
        db.add(AuditorRequestExpectation(request_id=row.id, expectation_id=value))
    for value in set(evidence_ids):
        db.add(AuditorRequestEvidence(request_id=row.id, evidence_id=value))
    row.revision += 1
    await advance_register(db, register, user, "update_auditor_mapping")
    await log_action(db, user, "update", "documentation_auditor_request", str(row.id), new_value={"revision": row.revision})
    return row


async def build_request_response(db, row, user):
    await db.refresh(row)
    await get_request(db, row.id, user)
    result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    case = await require_access(db, PreparationCase, row.case_id, user)
    project = await require_access(db, CertificationProject, row.project_id, user)
    result.update(case_name=case.name, project_name=project.name, expectations=[], evidence=[])
    expectations = (await db.scalars(select(DocumentationExpectation).join(AuditorRequestExpectation,
        AuditorRequestExpectation.expectation_id == DocumentationExpectation.id).where(
            AuditorRequestExpectation.request_id == row.id, expectation_clause(user)))).all()
    result["expectations"] = [{"id": item.id, "title": item.title} for item in expectations]
    evidence = (await db.scalars(select(PreparationEvidence).join(AuditorRequestEvidence,
        AuditorRequestEvidence.evidence_id == PreparationEvidence.id).where(AuditorRequestEvidence.request_id == row.id,
            tenant_clause(PreparationEvidence, user), access_clause(PreparationEvidence, user, "view")))).all()
    result["evidence"] = [{"id": item.id, "title": item.title, "kind": item.kind, "problems": await evidence_problems(db, item, user)} for item in evidence]
    result["unmatched"] = not result["expectations"]
    return result


async def reconciliation(db, register, user, project_id, list_revision=None):
    await validate_project(db, project_id, register, user)
    query = select(AuditorRequestMapping).where(AuditorRequestMapping.register_id == register.id,
        AuditorRequestMapping.project_id == project_id, request_clause(user))
    if list_revision is not None:
        query = query.where(AuditorRequestMapping.list_revision == list_revision)
    requests = [await build_request_response(db, row, user) for row in (await db.scalars(query)).all()]
    expectation_rows = (await db.scalars(select(DocumentationExpectation).where(
        DocumentationExpectation.register_id == register.id, DocumentationExpectation.applicability == "applicable",
        or_(DocumentationExpectation.project_id.is_(None), DocumentationExpectation.project_id == project_id), expectation_clause(user)))).all()
    selected = []
    matched = {value["id"] for request in requests for value in request["expectations"]}
    links_by_expectation = defaultdict(list)
    for link in (await db.scalars(select(ExpectationRequirement).where(
        ExpectationRequirement.expectation_id.in_([item.id for item in expectation_rows])))).all():
        links_by_expectation[link.expectation_id].append({
            "requirement_id": link.requirement_id,
            "requirement_set_version_id": link.requirement_set_version_id,
        })
    validated_scopes = {}
    from app.services.documentation_processes import effective_process_register
    for item in expectation_rows:
        # Requirement-linked global expectations must lie entirely in the project baseline.
        links = links_by_expectation[item.id]
        if item.project_id is None and not links and item.id not in matched:
            continue
        scoped = effective_process_register(register, item)
        key = (scoped.review_cycle_id, scoped.application_id, tuple(sorted(
            (link["requirement_id"], link["requirement_set_version_id"]) for link in links)))
        if key not in validated_scopes:
            try:
                await validate_requirement_links(db, scoped, user, links, project_id)
            except HTTPException as error:
                if error.status_code not in {404, 422}:
                    raise
                validated_scopes[key] = False
            else:
                validated_scopes[key] = True
        if validated_scopes[key]:
            selected.append(item)
    expectations = await build_expectation_responses(db, selected, user, register)
    matched = {value["id"] for request in requests for value in request["expectations"]}
    return {
        "requests_without_matches": [request for request in requests if request["unmatched"]],
        "missing_evidence": [item for item in expectations if "missing" in item["derived_reasons"]],
        "partial_coverage": [item for item in expectations if item["effective_coverage_status"] == "partial"],
        "unreviewed_coverage": [item for item in expectations if item["effective_coverage_status"] == "unreviewed"],
        "requests_with_unsuitable_evidence": [request for request in requests if any(item["problems"] for item in request["evidence"])],
        "unsuitable_evidence": [item for item in expectations if item["coverage_warning"] or any(link["problems"] for link in item["coverage"])],
        "expectations_absent_from_requests": [item for item in expectations if item["id"] not in matched],
        "notice": "Audit-list omissions describe documentation gaps in this project scope; they are not compliance decisions.",
    }
