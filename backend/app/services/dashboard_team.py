"""Manager coordination across real, accessible active work."""

from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlencode

from sqlalchemy import and_, exists, func, or_, select

from app.api.tenant import org_clause
from app.models.application import Application, ApplicationFollowup
from app.models.document import Document
from app.models.change_management import ChangeEntry, ComponentRegister
from app.services.change_readiness import readiness
from app.models.preparation import PreparationCase
from app.models.program import CertificationProject
from app.models.requirement import Requirement, RequirementStatus
from app.models.review import ReviewCycle, ReviewItem
from app.models.user import User
from app.services.preparation_review import (
    included_case_clause,
    review_queue_items,
    visible_case_projection,
)
from app.services.requirement_scope import current_requirement_condition
from app.services.review_progress import ACTIONABLE_REQUIREMENT_TYPES, COMPLETED_REVIEW_STATUSES

KINDS = ("requirement", "review", "form", "answer_review", "authority_query", "change")


async def team_work(
    db,
    user,
    *,
    jurisdiction_id=None,
    kind=None,
    owner_id=None,
    unassigned=False,
    overdue=False,
    q=None,
    context=None,
    sort_by="priority",
    skip=0,
    limit=50,
):
    today = datetime.now(UTC).date()
    users = {
        item.id: item.full_name
        for item in (await db.scalars(select(User).where(org_clause(User, user)))).all()
    }
    items = []

    def add(
        kind, identity, title, context, status, owner, due, href, jurisdiction, action, **extra
    ):
        due = due.date() if isinstance(due, datetime) else due
        items.append(
            dict(
                id=f"{kind}:{identity}",
                kind=kind,
                title=title,
                context=context,
                status=status,
                action_label=action,
                owner_id=owner,
                owner_name=users.get(owner),
                due_date=due,
                overdue=bool(due and due < today),
                href=href,
                jurisdiction_id=jurisdiction,
                **extra,
            )
        )

    latest = select(
        RequirementStatus.requirement_id,
        RequirementStatus.status,
        RequirementStatus.assigned_to,
        func.row_number()
        .over(
            partition_by=RequirementStatus.requirement_id,
            order_by=(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc()),
        )
        .label("rn"),
    ).subquery()
    query = (
        select(Requirement, Document.name, latest.c.status, latest.c.assigned_to)
        .outerjoin(Document, Document.id == Requirement.document_id)
        .outerjoin(latest, and_(latest.c.requirement_id == Requirement.id, latest.c.rn == 1))
        .where(
            org_clause(Requirement, user),
            Requirement.active.is_(True),
            current_requirement_condition(),
            Requirement.requirement_type.in_(ACTIONABLE_REQUIREMENT_TYPES),
            or_(
                Document.id.is_(None),
                and_(
                    org_clause(Document, user),
                    Document.status == "approved",
                    Document.archived_at.is_(None),
                ),
            ),
            func.coalesce(latest.c.status, "not_started").not_in(["evidenced", "not_applicable"]),
        )
    )
    if jurisdiction_id:
        query = query.where(Requirement.jurisdiction_id == jurisdiction_id)
    for req, document_name, status, owner in (await db.execute(query)).all():
        add(
            "requirement",
            req.id,
            f"{req.reference_id} · {req.title or 'Requirement'}",
            document_name or "Independent requirements",
            status or "not_started",
            owner,
            None,
            f"/requirements/{req.id}",
            req.jurisdiction_id,
            "Update assessment and evidence",
        )

    project_access = exists(
        select(CertificationProject.id).where(
            CertificationProject.id == ReviewCycle.certification_project_id,
            org_clause(CertificationProject, user),
        )
    )
    query = (
        select(ReviewItem, ReviewCycle, Requirement, latest.c.status)
        .join(ReviewCycle, ReviewCycle.id == ReviewItem.review_cycle_id)
        .join(Requirement, Requirement.id == ReviewItem.requirement_id)
        .outerjoin(latest, and_(latest.c.requirement_id == Requirement.id, latest.c.rn == 1))
        .where(
            org_clause(ReviewCycle, user),
            org_clause(Requirement, user),
            ReviewCycle.status == "active",
            ReviewItem.review_status.not_in(COMPLETED_REVIEW_STATUSES),
            or_(ReviewCycle.certification_project_id.is_(None), project_access),
        )
    )
    if jurisdiction_id:
        query = query.where(ReviewCycle.jurisdiction_id == jurisdiction_id)
    for review, cycle, req, legacy_status in (await db.execute(query)).all():
        # A responsible contributor supplies missing evidence; the reviewer owns decisions.
        needs_evidence = (review.assessment_status or legacy_status) not in {
            "evidenced",
            "not_applicable",
        } and review.responsible_user_id is not None
        owner = review.responsible_user_id if needs_evidence else review.assigned_reviewer_id
        add(
            "review",
            review.id,
            f"{req.reference_id} · {req.title or 'Review requirement'}",
            cycle.name,
            review.review_status,
            owner,
            cycle.deadline,
            f"/review-cycles/{cycle.id}?mode=focus&item={review.id}",
            cycle.jurisdiction_id,
            (
                "Supply assessment and evidence"
                if needs_evidence
                else "Review assessment and evidence"
            ),
        )

    query = select(PreparationCase).where(
        org_clause(PreparationCase, user),
        PreparationCase.status == "active",
        included_case_clause(user),
    )
    if jurisdiction_id:
        query = query.where(PreparationCase.jurisdiction_id == jurisdiction_id)
    for case in (await db.scalars(query)).all():
        projection = await visible_case_projection(db, case, user)
        if projection is None:
            continue
        # Forms only represent contributor work; pending acceptance is represented by answer tasks.
        missing = any(
            blocker.code not in {"pending_acceptance"} for blocker in projection.readiness.blockers
        )
        if missing:
            add(
                "form",
                case.id,
                case.name,
                case.template_name,
                "in_progress",
                case.owner_id,
                case.due_date,
                f"/preparation?case={case.id}",
                case.jurisdiction_id,
                "Complete form answers and evidence",
                case_id=case.id,
            )
    for answer in await review_queue_items(db, user, jurisdiction_id):
        returned = answer["review_status"] == "changes_requested"
        owner = answer["owner_id"] if returned else answer["reviewer_id"]
        add(
            "answer_review",
            f'{answer["case_id"]}:{answer["field_key"]}',
            answer["question"],
            answer["case_name"],
            answer["review_status"],
            owner,
            answer["due_date"],
            "/preparation?"
            + urlencode({"case": str(answer["case_id"]), "field": answer["field_key"]}),
            answer["jurisdiction_id"],
            "Address reviewer feedback" if returned else "Accept answer and evidence",
            case_id=answer["case_id"],
            field_key=answer["field_key"],
        )

    query = (
        select(ApplicationFollowup, Application)
        .join(Application, Application.id == ApplicationFollowup.application_id)
        .where(
            org_clause(Application, user),
            ApplicationFollowup.status == "open",
            Application.status != "completed",
        )
    )
    if jurisdiction_id:
        query = query.where(Application.jurisdiction_id == jurisdiction_id)
    for followup, application in (await db.execute(query)).all():
        add(
            "authority_query",
            followup.id,
            followup.question,
            application.name,
            followup.status,
            followup.owner_id,
            followup.due_date,
            f"/licence-applications?application={application.id}&tab=approval",
            application.jurisdiction_id,
            "Respond to authority query",
        )

    query = (
        select(ChangeEntry, ComponentRegister)
        .join(ComponentRegister, ComponentRegister.id == ChangeEntry.register_id)
        .where(
            org_clause(ComponentRegister, user),
            ComponentRegister.status == "active",
            ChangeEntry.status.in_(["draft", "rejected", "approved", "implemented"]),
        )
    )
    if jurisdiction_id:
        query = query.where(ComponentRegister.jurisdiction_id == jurisdiction_id)
    for change, register in (await db.execute(query)).all():
        phase = (
            "implementation"
            if change.status == "approved"
            else "verification" if change.status == "implemented" else "approval"
        )
        current = await readiness(db, change, register)
        reasons = current[phase]["reasons"] if current else []
        action = (
            reasons[0]["message"]
            if reasons
            else {
                "approval": "Review change for internal approval",
                "implementation": "Record implementation",
                "verification": "Verify implemented change",
            }[phase]
        )
        # Authorship and past decisions are not a next-action assignment.
        add(
            "change",
            change.id,
            change.title,
            register.name,
            change.status,
            None,
            change.planned_start_at if phase == "implementation" else change.planned_end_at,
            f"/change-management?change={change.id}",
            register.jurisdiction_id,
            action,
        )

    contexts = sorted({item["context"] for item in items})
    filtered = [
        item
        for item in items
        if (not kind or item["kind"] == kind)
        and (not owner_id or item["owner_id"] == owner_id)
        and (not unassigned or item["owner_id"] is None)
        and (not overdue or item["overdue"])
        and (not context or item["context"] == context)
        and (
            not q
            or q.casefold()
            in f'{item["title"]} {item["context"]} {item["owner_name"] or ""}'.casefold()
        )
    ]
    filtered.sort(
        key=lambda item: (
            item["due_date"] is None,
            item["due_date"] or today,
            item["kind"],
            item["id"],
        )
    )
    # Stable secondary ordering comes from the priority order above. Sort the entire
    # visible matching set before pagination so programme/owner order spans pages.
    if sort_by == "programme":
        filtered.sort(key=lambda item: item["context"].casefold())
    elif sort_by == "owner":
        filtered.sort(
            key=lambda item: (item["owner_id"] is None, (item["owner_name"] or "").casefold())
        )
    counts = Counter(item["kind"] for item in filtered)
    people = {}
    for item in filtered:
        owner = item["owner_id"]
        person = people.setdefault(
            owner, dict(id=owner, name=item["owner_name"] or "Unassigned", total=0, overdue=0)
        )
        person["total"] += 1
        person["overdue"] += int(item["overdue"])
    return dict(
        items=filtered[skip : skip + limit],
        total=len(filtered),
        skip=skip,
        limit=limit,
        contexts=contexts,
        counts=dict(
            total=len(filtered),
            overdue=sum(item["overdue"] for item in filtered),
            unassigned=sum(item["owner_id"] is None for item in filtered),
            by_kind={kind: counts[kind] for kind in KINDS},
        ),
        people=sorted(people.values(), key=lambda item: (-item["total"], item["name"])),
    )
