"""Personal form and authority-query queues, requiring full resource view access."""

from sqlalchemy import and_, case, func, or_, select

from app.api.tenant import org_clause
from app.models.application import Application, ApplicationComponent, ApplicationFollowup
from app.models.preparation import PreparationCase
from app.models.program import CertificationProject
from app.schemas.dashboard import (
    AssignedFormItem,
    AssignedForms,
    AuthorityQueries,
    AuthorityQueryItem,
)


async def application_work(db, user, jurisdiction_id=None, *, offset=0, limit=20):
    filters = [org_clause(PreparationCase, user), PreparationCase.status == "active"]
    if jurisdiction_id:
        filters.append(PreparationCase.jurisdiction_id == jurisdiction_id)
    component_assigned = and_(Application.id.is_not(None), ApplicationComponent.owner_id == user.id)
    effective_due = case(
        (
            component_assigned,
            func.coalesce(ApplicationComponent.due_date, PreparationCase.due_date),
        ),
        else_=PreparationCase.due_date,
    )
    ranked = (
        select(
            PreparationCase.id.label("case_id"),
            PreparationCase.name.label("name"),
            PreparationCase.kind.label("kind"),
            PreparationCase.status.label("status"),
            case(
                (component_assigned, ApplicationComponent.owner_id), else_=PreparationCase.owner_id
            ).label("owner_id"),
            effective_due.label("due_date"),
            Application.id.label("application_id"),
            Application.name.label("application_name"),
            CertificationProject.id.label("project_id"),
            CertificationProject.name.label("project_name"),
            func.row_number()
            .over(
                partition_by=PreparationCase.id,
                order_by=(
                    case((component_assigned, 0), (Application.id.is_not(None), 1), else_=2),
                    effective_due.asc().nullslast(),
                    Application.id,
                ),
            )
            .label("rank"),
        )
        .select_from(PreparationCase)
        .outerjoin(
            ApplicationComponent,
            and_(
                ApplicationComponent.case_id == PreparationCase.id,
                ApplicationComponent.included.is_(True),
            ),
        )
        .outerjoin(
            Application,
            and_(
                Application.id == ApplicationComponent.application_id,
                Application.status != "completed",
                org_clause(Application, user),
            ),
        )
        .outerjoin(
            CertificationProject,
            and_(
                CertificationProject.id == PreparationCase.project_id,
                org_clause(CertificationProject, user),
            ),
        )
        .where(*filters, or_(PreparationCase.owner_id == user.id, component_assigned))
        .subquery()
    )
    # Count and page after deduplication; keep a bounded queue ordered by its actual deadline.
    total = await db.scalar(select(func.count()).select_from(ranked).where(ranked.c.rank == 1))
    records = (
        (
            await db.execute(
                select(ranked)
                .where(ranked.c.rank == 1)
                .order_by(ranked.c.due_date.asc().nullslast(), ranked.c.case_id)
                .offset(offset)
                .limit(limit)
            )
        )
        .mappings()
        .all()
    )
    forms = [
        AssignedFormItem(
            **{
                key: str(value) if key.endswith("_id") and value is not None else value
                for key, value in record.items()
                if key != "rank"
            }
        )
        for record in records
    ]
    query_filters = [
        org_clause(Application, user),
        ApplicationFollowup.status == "open",
        ApplicationFollowup.owner_id == user.id,
        Application.status != "completed",
    ]
    if jurisdiction_id:
        query_filters.append(Application.jurisdiction_id == jurisdiction_id)
    queries = (
        select(ApplicationFollowup, Application.id, Application.name)
        .join(Application, Application.id == ApplicationFollowup.application_id)
        .where(*query_filters)
    )
    query_total = await db.scalar(select(func.count()).select_from(queries.subquery()))
    records = (
        await db.execute(
            queries.order_by(
                ApplicationFollowup.due_date.asc().nullslast(),
                ApplicationFollowup.created_at,
                ApplicationFollowup.id,
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [
        AuthorityQueryItem(
            query_id=str(followup.id),
            application_id=str(application_id),
            application_name=application_name,
            question=followup.question,
            status=followup.status,
            owner_id=str(followup.owner_id),
            due_date=followup.due_date,
        )
        for followup, application_id, application_name in records
    ]
    return AssignedForms(total=int(total or 0), items=forms), AuthorityQueries(
        total=int(query_total or 0), items=items
    )
