"""Explicit process pointers and live projections of canonical owner collections."""
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, exists, func, literal, or_, select

from app.models.document import Document
from app.models.user import User
from app.models.documentation import DocumentationExpectation, DocumentationProcessTarget, ExpectationRequirement
from app.models.preparation import PreparationCase
from app.models.program import CertificationProject, RequirementSetVersion, ReviewCycleRequirementBaseline
from app.models.requirement import Requirement
from app.models.review import ReviewCycle, ReviewItem
from app.services.access import access_clause, require_access, tenant_clause
from app.services.review_assessment import plain_text


def effective_process_register(register, expectation):
    """A row override selects its owner; the register remains a compatible default."""
    from types import SimpleNamespace
    values = {key: getattr(register, key) for key in (
        "id", "organization_id", "jurisdiction_id", "review_cycle_id", "application_id",
        "name", "description", "revision", "created_by", "created_at", "updated_at")}
    if getattr(expectation, "review_cycle_id", None) is not None:
        values.update(review_cycle_id=expectation.review_cycle_id, application_id=None)
    return SimpleNamespace(**values)


async def validate_row_review(db, register, review_cycle_id, project_id, user):
    if review_cycle_id is None:
        return None
    cycle = await get_review_process(db, review_cycle_id, register, user)
    if project_id is not None and cycle.certification_project_id != project_id:
        raise HTTPException(422, "Review and documentation project scope must match")
    return cycle


def actor_item_clause(user):
    return ReviewItem.assigned_reviewer_id == user.id if user.role == "assigned_reviewer" else True


async def get_review_process(db, cycle_id, register, user, action="view"):
    if action == "export":
        visible = await require_access(db, ReviewCycle, cycle_id, user, "view")
        if visible.certification_project_id:
            await require_access(db, CertificationProject, visible.certification_project_id, user, "export")
    cycle = await require_access(db, ReviewCycle, cycle_id, user, action)
    if cycle.jurisdiction_id != register.jurisdiction_id:
        raise HTTPException(422, "Process and register jurisdictions must match")
    return cycle


async def review_summary(db, cycle, register, user, action="view"):
    cycle = await get_review_process(db, cycle.id, register, user, action)
    project = await require_access(db, CertificationProject, cycle.certification_project_id, user, action) if cycle.certification_project_id else None
    return {"kind": "review", "id": cycle.id, "name": cycle.name,
        "href": f"/review-cycles/{cycle.id}", "project_id": project.id if project else None,
        "project_name": project.name if project else None, "available": True,
        "status": cycle.status, "readonly": cycle.status != "active" or bool(cycle.closed_at)}


async def register_process_summary(db, register, user, action="view"):
    try:
        if register.review_cycle_id:
            cycle = await get_review_process(db, register.review_cycle_id, register, user, action)
            return await review_summary(db, cycle, register, user, action)
        if register.application_id:
            from app.services.documentation_process_applications import application_summary
            return await application_summary(db, register.application_id, register, user, action)
        return None
    except HTTPException as error:
        if error.status_code in {403, 404} and action == "view":
            return {"available": False}
        raise


async def review_options(db, register, user, q="", skip=0, limit=100, project_id=None):
    query = select(ReviewCycle).where(tenant_clause(ReviewCycle, user), access_clause(ReviewCycle, user, "view"),
        ReviewCycle.jurisdiction_id == register.jurisdiction_id)
    if project_id is not None:
        query = query.where(ReviewCycle.certification_project_id == project_id)
    if user.role == "assigned_reviewer":
        query = query.where(exists(select(ReviewItem.id).where(ReviewItem.review_cycle_id == ReviewCycle.id, actor_item_clause(user))))
    if q:
        project_match = exists(select(CertificationProject.id).where(
            CertificationProject.id == ReviewCycle.certification_project_id,
            tenant_clause(CertificationProject, user), access_clause(CertificationProject, user, "view"),
            CertificationProject.name.icontains(q, autoescape=True)))
        query = query.where(or_(ReviewCycle.name.icontains(q, autoescape=True), project_match))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    cycles = (await db.scalars(query.order_by(ReviewCycle.created_at.desc(), ReviewCycle.id).offset(skip).limit(limit))).all()
    return {"items": [await review_summary(db, cycle, register, user) for cycle in cycles], "total": total}


async def process_options(db, register, user, q="", skip=0, limit=100):
    from app.services.documentation_process_applications import application_options
    return {"review_cycles": await review_options(db, register, user, q, skip, limit),
        "applications": await application_options(db, register, user, q, skip, limit)}


async def read_review_target(db, review_item_id, register, user, cycle_id=None, action="view", include_collection=True, evidence_cache=None):
    cycle_id = cycle_id or register.review_cycle_id
    if cycle_id is None:
        raise HTTPException(422, "Select an assessment process first")
    cycle = await get_review_process(db, cycle_id, register, user, action)
    item = await db.scalar(select(ReviewItem).where(ReviewItem.id == review_item_id,
        ReviewItem.review_cycle_id == cycle.id, actor_item_clause(user)))
    if item is None:
        raise HTTPException(404, "Assessment item not found")
    requirement = await db.scalar(select(Requirement).where(Requirement.id == item.requirement_id,
        tenant_clause(Requirement, user), Requirement.jurisdiction_id == register.jurisdiction_id))
    if requirement is None or requirement.requirement_set_version_id is None:
        raise HTTPException(422, "Choose an item with an explicit requirement version")
    version = await db.scalar(select(RequirementSetVersion).where(
        RequirementSetVersion.id == requirement.requirement_set_version_id, tenant_clause(RequirementSetVersion, user)))
    if version is None or version.document_id != requirement.document_id:
        raise HTTPException(404, "Requirement version not found")
    if version.status != "approved":
        raise HTTPException(422, "The process target no longer has an approved requirement version")
    pin = await db.scalar(select(ReviewCycleRequirementBaseline.requirement_set_version_id).where(
        ReviewCycleRequirementBaseline.review_cycle_id == cycle.id,
        ReviewCycleRequirementBaseline.document_id == requirement.document_id))
    if pin is not None and pin != version.id:
        raise HTTPException(422, "Assessment item does not match its pinned review baseline")
    document = await db.scalar(select(Document).where(Document.id == requirement.document_id, tenant_clause(Document, user)))
    owner_id = item.responsible_user_id or item.assigned_reviewer_id
    owner = await db.scalar(select(User).where(User.id == owner_id, tenant_clause(User, user))) if owner_id else None
    from app.services.documentation_review import review_evidence_collection
    target = review_target_metadata(item, requirement, version, document, owner, cycle)
    if include_collection:
        target["collection"] = await review_evidence_collection(db, cycle, item, user, action, evidence_cache=evidence_cache)
    return target


def review_target_metadata(item, requirement, version, document, owner, cycle):
    return {"kind": "review_item", "review_item_id": item.id, "review_cycle_id": cycle.id,
        "requirement_id": requirement.id, "requirement_set_version_id": version.id,
        "reference_id": requirement.reference_id, "title": requirement.title or requirement.reference_id,
        "project_id": cycle.certification_project_id, "version_number": version.version_number,
        "set_name": (document.name or document.filename) if document else None, "owner_name": owner.full_name if owner else None,
        "href": f"/review-cycles/{cycle.id}?mode=focus&item={item.id}", "available": True}


def review_target_query(cycle, register, user):
    return select(ReviewItem, Requirement, RequirementSetVersion, Document, User).join(Requirement, Requirement.id == ReviewItem.requirement_id).join(
        RequirementSetVersion, RequirementSetVersion.id == Requirement.requirement_set_version_id).join(
        Document, Document.id == Requirement.document_id).outerjoin(User,
        (User.id == func.coalesce(ReviewItem.responsible_user_id, ReviewItem.assigned_reviewer_id)) & tenant_clause(User, user)).where(
        ReviewItem.review_cycle_id == cycle.id, actor_item_clause(user), tenant_clause(Requirement, user),
        Requirement.jurisdiction_id == register.jurisdiction_id, Requirement.requirement_set_version_id.is_not(None),
        tenant_clause(RequirementSetVersion, user), RequirementSetVersion.status == "approved",
        RequirementSetVersion.document_id == Requirement.document_id,
        tenant_clause(Document, user),
        ~exists(select(ReviewCycleRequirementBaseline.document_id).where(
            ReviewCycleRequirementBaseline.review_cycle_id == cycle.id,
            ReviewCycleRequirementBaseline.document_id == Requirement.document_id,
            ReviewCycleRequirementBaseline.requirement_set_version_id != RequirementSetVersion.id)))


async def process_targets(db, register, user, q="", skip=0, limit=100):
    if register.application_id:
        from app.services.documentation_process_applications import application_targets
        return await application_targets(db, register.application_id, register, user, q, skip, limit)
    if register.review_cycle_id is None:
        return {"items": [], "total": 0}
    cycle = await get_review_process(db, register.review_cycle_id, register, user)
    query = review_target_query(cycle, register, user)
    ordered = query.order_by(Requirement.document_id, Requirement.sort_order,
        Requirement.reference_id, Requirement.id, ReviewItem.id)
    needle = " ".join(q.casefold().split())
    wordings = {}
    if needle:
        # Stream scalar source columns, not every ORM target or its evidence collection.
        # Requirement ordering keeps duplicate review items adjacent for one normalization.
        sources = await db.stream(ordered.with_only_columns(
            ReviewItem.id.label("review_item_id"), Requirement.id.label("requirement_id"),
            Requirement.reference_id, Requirement.title, Requirement.text,
            maintain_column_froms=True).execution_options(yield_per=100))
        total, selected_ids, previous_id, matches, wording = 0, [], None, False, ""
        try:
            async for batch in sources.partitions(100):
                for source in batch:
                    if source.requirement_id != previous_id:
                        previous_id = source.requirement_id
                        wording = requirement_picker_text(source.text)
                        matches = any(needle in " ".join(value.casefold().split()) for value in (
                            source.reference_id, source.title or "", wording))
                    if matches:
                        if skip <= total < skip + limit:
                            selected_ids.append(source.review_item_id)
                            wordings[source.requirement_id] = wording
                        total += 1
        finally:
            await sources.close()
        items = (await db.execute(ordered.where(ReviewItem.id.in_(selected_ids)))).all() if selected_ids else []
    else:
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        items = (await db.execute(ordered.offset(skip).limit(limit))).all()
    contexts = await review_picker_contexts(db, cycle, register, user, [row[1].id for row in items])
    targets = []
    for item, requirement, version, document, owner in items:
        if requirement.id not in wordings:
            wordings[requirement.id] = requirement_picker_text(requirement.text)
        wording = wordings[requirement.id]
        targets.append(dict(review_target_metadata(item, requirement, version, document, owner, cycle),
            process_name=cycle.name, requirement_text=wording[:1000],
            requirement_text_truncated=len(wording) > 1000,
            requirement_context=contexts.get(requirement.id, [])))
    return {"items": targets, "total": total}


def requirement_picker_text(value):
    """Keep paragraph/list boundaries and decode canonical rich text before shortening it."""
    separated = re.sub(r"<\s*(?:br\b[^>]*|/(?:p|div|li|ul|ol)\s*)>", "\n", value, flags=re.I)
    # Inline emphasis does not introduce spaces inside words or before punctuation.
    text = plain_text(re.sub(r"<[^>]*>", "", separated))
    return "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines())


async def review_picker_contexts(db, cycle, register, user, requirement_ids):
    """Read a bounded breadcrumb for the page, only through permitted pinned review items."""
    if not requirement_ids:
        return {}
    visible = review_target_query(cycle, register, user).with_only_columns(
        Requirement.id, Requirement.parent_id, Requirement.reference_id, Requirement.title,
        Requirement.text, Requirement.document_id,
        Requirement.requirement_set_version_id, maintain_column_froms=True).distinct().cte()
    ancestors = select(visible, literal(0).label("depth")).where(
        visible.c.id.in_(requirement_ids)).cte(recursive=True)
    ancestors = ancestors.union_all(select(visible, ancestors.c.depth + 1).join(
        ancestors, (visible.c.id == ancestors.c.parent_id)
        & (visible.c.document_id == ancestors.c.document_id)
        & (visible.c.requirement_set_version_id == ancestors.c.requirement_set_version_id)
    ).where(ancestors.c.depth < 12))
    rows = {row.id: row for row in (await db.execute(select(ancestors))).all()}
    result = {}
    for requirement_id in requirement_ids:
        path, seen = [], {requirement_id}
        current = rows.get(requirement_id)
        while current and current.parent_id in rows and len(path) < 12:
            parent = rows[current.parent_id]
            if parent.id in seen or (parent.document_id, parent.requirement_set_version_id) != (
                current.document_id, current.requirement_set_version_id):
                break
            seen.add(parent.id)
            title = (parent.title or "").strip()
            if not title or title == parent.reference_id:
                title = requirement_picker_text(parent.text)
            path.append({"reference_id": parent.reference_id,
                "title": title[:160] + ("…" if len(title) > 160 else "")})
            current = parent
        result[requirement_id] = list(reversed(path))
    return result


async def prefetch_review_targets(db, register, mappings, user, cache, evidence_cache):
    ids = {row.review_item_id for row in mappings if row.review_item_id}
    if not ids:
        return
    for item_id in ids:
        cache[(item_id, None, None, "view")] = None
    try:
        if register.review_cycle_id is None:
            return
        cycle = await get_review_process(db, register.review_cycle_id, register, user)
        rows = (await db.execute(review_target_query(cycle, register, user).where(ReviewItem.id.in_(ids)))).all()
        from app.services.documentation_review import review_evidence_collections
        collections = await review_evidence_collections(db, cycle, [row[0] for row in rows], user,
            evidence_cache=evidence_cache)
    except HTTPException as error:
        if error.status_code in {403, 404, 409, 422}:
            return
        raise
    for item, requirement, version, document, owner in rows:
        if item.id in collections:
            target = review_target_metadata(item, requirement, version, document, owner, cycle)
            target["collection"] = collections[item.id]
            cache[(item.id, None, None, "view")] = target


async def build_process_targets(db, expectation, register, user, action="view", rows=None, cache=None, evidence_cache=None):
    if rows is None:
        rows = (await db.scalars(select(DocumentationProcessTarget).where(
            DocumentationProcessTarget.expectation_id == expectation.id).order_by(DocumentationProcessTarget.created_at, DocumentationProcessTarget.id))).all()
    result = []
    for row in rows:
        try:
            key = (row.review_item_id, row.case_id, row.field_key, action)
            if cache is not None and key in cache:
                target = cache[key]
                if target is None:
                    raise HTTPException(404, "Assessment target unavailable")
            elif row.review_item_id:
                target = await read_review_target(db, row.review_item_id, register, user, action=action, evidence_cache=evidence_cache)
            else:
                from app.services.documentation_process_applications import read_application_target
                target = await read_application_target(db, row, register, user, action=action, evidence_cache=evidence_cache)
            if cache is not None:
                cache[key] = target
            if uuid.UUID(str(target["requirement_id"])) != row.requirement_id or uuid.UUID(str(target["requirement_set_version_id"])) != row.requirement_set_version_id:
                raise HTTPException(409, "The saved process target no longer matches its source")
            result.append(dict(target, id=row.id, available=True))
        except HTTPException as error:
            if error.status_code in {403, 404, 409, 422} and action == "view":
                result.append({"id": row.id, "available": False})
            else:
                raise
    return result


async def set_register_process(db, register, user, body):
    from app.services.documentation import advance_register, get_expectation, invalidate_review
    desired = (body.review_cycle_id, body.application_id)
    current = (register.review_cycle_id, register.application_id)
    if desired == current and not body.clear_targets:
        return register
    mappings = (await db.scalars(select(DocumentationProcessTarget).join(DocumentationExpectation,
        DocumentationExpectation.id == DocumentationProcessTarget.expectation_id).where(
            DocumentationExpectation.register_id == register.id,
            DocumentationExpectation.review_cycle_id.is_(None)))).all()
    if desired == current and not mappings:
        return register
    if mappings and not body.clear_targets:
        raise HTTPException(409, "Confirm removal of register matches before changing the process; process evidence will be kept")
    if body.review_cycle_id:
        await get_review_process(db, body.review_cycle_id, register, user)
    elif body.application_id:
        from app.services.documentation_process_applications import application_summary
        await application_summary(db, body.application_id, register, user)
    if mappings:
        # The actor changes register-owned pointers, never the canonical source.
        affected = []
        for expectation_id in sorted({row.expectation_id for row in mappings}, key=str):
            try:
                affected.append(await get_expectation(db, expectation_id, user, "edit"))
            except HTTPException as error:
                if error.status_code in {403, 404}:
                    raise HTTPException(404, "Not found") from error
                raise
        for item in affected:
            item.revision += 1
            invalidate_review(item)
        await db.execute(delete(DocumentationProcessTarget).where(DocumentationProcessTarget.id.in_([row.id for row in mappings])))
    register.review_cycle_id, register.application_id = desired
    await advance_register(db, register, user, "set_documentation_process", {"bound": bool(any(desired)), "matches_cleared": bool(mappings)})
    return register


async def set_row_review(db, expectation, register, user, body):
    from app.services.documentation import advance_expectation, invalidate_review
    if expectation.review_cycle_id == body.review_cycle_id and not body.clear_targets:
        return expectation
    await validate_row_review(db, register, body.review_cycle_id, expectation.project_id, user)
    mappings = (await db.scalars(select(DocumentationProcessTarget).where(
        DocumentationProcessTarget.expectation_id == expectation.id))).all()
    previous = effective_process_register(register, expectation)
    desired_cycle = body.review_cycle_id or register.review_cycle_id
    desired_application = None if body.review_cycle_id else register.application_id
    changes_owner = (previous.review_cycle_id, previous.application_id) != (desired_cycle, desired_application)
    if mappings and changes_owner and not body.clear_targets:
        raise HTTPException(409, "Confirm removal of this document's matches before changing its review; process evidence will be kept")
    if mappings and body.clear_targets:
        await db.execute(delete(DocumentationProcessTarget).where(DocumentationProcessTarget.expectation_id == expectation.id))
        invalidate_review(expectation)
    if expectation.review_cycle_id == body.review_cycle_id and not mappings:
        return expectation
    expectation.review_cycle_id = body.review_cycle_id
    await advance_expectation(db, expectation, user, "set_documentation_row_review")
    return expectation


async def replace_process_targets(db, expectation, register, user, body):
    from app.services.documentation import advance_expectation, invalidate_review
    register = effective_process_register(register, expectation)
    rows = (await db.scalars(select(DocumentationProcessTarget).where(DocumentationProcessTarget.expectation_id == expectation.id))).all()
    for row in rows:
        try:
            if row.review_item_id:
                await read_review_target(db, row.review_item_id, register, user, include_collection=False)
            else:
                if register.application_id is None:
                    raise HTTPException(404, "Process unavailable")
                from app.services.documentation_process_applications import resolve_application_target
                await resolve_application_target(db, register.application_id, row.case_id, row.field_key, register, user)
        except HTTPException as error:
            if error.status_code in {403, 404, 409, 422}:
                raise HTTPException(404, "An existing process target is unavailable; restore source access or explicitly disconnect the register process") from error
            raise
    desired = {}
    for selected in body.targets:
        if selected.review_item_id:
            if register.review_cycle_id is None:
                raise HTTPException(422, "Select an assessment process before matching an assessment item")
            target = await read_review_target(db, selected.review_item_id, register, user, include_collection=False)
            key = (selected.review_item_id, None, None)
            if expectation.project_id is not None and target.get("project_id") != expectation.project_id:
                raise HTTPException(422, "Assessment target and documentation project scope must match")
        else:
            if register.application_id is None:
                raise HTTPException(422, "Select a licence application before matching a form field")
            from app.services.documentation_process_applications import resolve_application_target
            target = await resolve_application_target(db, register.application_id, selected.case_id, selected.field_key, register, user)
            key = (None, selected.case_id, selected.field_key)
            if expectation.project_id is not None:
                case = await require_access(db, PreparationCase, selected.case_id, user)
                if case.project_id != expectation.project_id:
                    raise HTTPException(422, "Form target and documentation project scope must match")
        if (uuid.UUID(str(target["requirement_id"])) != selected.requirement_id
                or uuid.UUID(str(target["requirement_set_version_id"])) != selected.requirement_set_version_id):
            raise HTTPException(409, "The selected requirement source changed; refresh the targets and choose its exact version again")
        if key in desired:
            raise HTTPException(422, "Each process target can be selected only once")
        desired[key] = target
    current = {(row.review_item_id, row.case_id, row.field_key): row for row in rows}
    if set(current) == set(desired) and all(
        current[key].requirement_id == uuid.UUID(str(target["requirement_id"]))
        and current[key].requirement_set_version_id == uuid.UUID(str(target["requirement_set_version_id"]))
        for key, target in desired.items()):
        return expectation
    linked = {row.requirement_id: row.requirement_set_version_id for row in (await db.scalars(select(ExpectationRequirement).where(
        ExpectationRequirement.expectation_id == expectation.id))).all()}
    for key, target in desired.items():
        requirement_id = uuid.UUID(str(target["requirement_id"]))
        version_id = uuid.UUID(str(target["requirement_set_version_id"]))
        requirement = await db.scalar(select(Requirement).where(Requirement.id == requirement_id, tenant_clause(Requirement, user),
            Requirement.jurisdiction_id == register.jurisdiction_id, Requirement.requirement_set_version_id == version_id))
        version = await db.scalar(select(RequirementSetVersion).where(RequirementSetVersion.id == version_id,
            tenant_clause(RequirementSetVersion, user), RequirementSetVersion.status == "approved"))
        if requirement is None or version is None:
            raise HTTPException(422, "Choose a target with an approved, matching requirement version")
        if requirement_id in linked and linked[requirement_id] != version_id:
            raise HTTPException(409, "The existing versioned requirement link does not match this target")
        if requirement_id not in linked:
            db.add(ExpectationRequirement(expectation_id=expectation.id, requirement_id=requirement_id, requirement_set_version_id=version_id))
            linked[requirement_id] = version_id
        if key in current:
            current[key].requirement_id = requirement_id
            current[key].requirement_set_version_id = version_id
        else:
            db.add(DocumentationProcessTarget(expectation_id=expectation.id, review_item_id=key[0], case_id=key[1], field_key=key[2],
                requirement_id=requirement_id, requirement_set_version_id=version_id, created_by=user.id))
    removed = [row.id for key, row in current.items() if key not in desired]
    if removed:
        await db.execute(delete(DocumentationProcessTarget).where(DocumentationProcessTarget.id.in_(removed)))
    invalidate_review(expectation)
    await advance_expectation(db, expectation, user, "match_documentation_process_targets")
    return expectation



def process_content_present(target):
    if not target.get("available"):
        return False
    collection = target["collection"]
    value = collection.get("current_value")
    return bool(collection["items"] or collection.get("has_review_notes")) or (value is not None and value != "" and value != [])


def process_fingerprint(targets):
    import hashlib
    import json
    content = []
    for target in targets:
        content.append({key: target.get(key) for key in ("kind", "review_item_id", "case_id", "field_key", "requirement_id", "requirement_set_version_id", "available")})
        collection = target.get("collection", {})
        content[-1]["collection"] = {key: collection.get(key) for key in ("items", "evidence_changed_at", "has_review_notes", "review_notes_summary", "current_value", "not_applicable_reason")}
    from datetime import date, datetime
    def portable(value):
        return value.isoformat() if isinstance(value, (datetime, date)) else str(value)
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=portable, separators=(",", ":")).encode()).hexdigest()
