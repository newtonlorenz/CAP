"""Content permissions. Account administrators receive no confidential-content bypass."""

from fastapi import HTTPException
from sqlalchemy import and_, exists, literal, or_, select
from sqlalchemy.orm import aliased

from app.models.access import AccessGrant, AccessTeamMember, ResourceAccess

PERMISSIONS = ("summary", "view", "edit", "approve", "export", "manage_access")
MAX_DEPTH = 4


def resource_models():
    from app.models.application import Application
    from app.models.preparation import PreparationCase, PreparationEvidence
    from app.models.program import CertificationProject

    return {
        "application": Application,
        "certification_project": CertificationProject,
        "preparation_case": PreparationCase,
        "preparation_evidence": PreparationEvidence,
    }


def resource_type(model):
    return next((key for key, value in resource_models().items() if value is model), None)


def tenant_clause(model, user):
    return (
        model.organization_id == user.organization_id
        if user.organization_id
        else model.organization_id.is_(None)
    )


def legacy_permission(user, action):
    if action in ("summary", "view", "export"):
        return True
    if action == "edit":
        return user.role in ("contributor", "manager", "admin")
    if action == "approve":
        return user.role in ("manager", "approver", "admin")
    return False


def _own_permission(policy, user, action):
    grant = aliased(AccessGrant)
    membership = exists(
        select(AccessTeamMember.team_id).where(
            AccessTeamMember.team_id == grant.subject_id, AccessTeamMember.user_id == user.id
        )
    )
    actions = PERMISSIONS if action == "summary" else (action,)
    explicit = exists(
        select(grant.policy_id).where(
            grant.policy_id == policy.id,
            grant.permission.in_(actions),
            or_(
                and_(grant.subject_type == "user", grant.subject_id == user.id),
                and_(grant.subject_type == "team", policy.visibility != "secret", membership),
            ),
        )
    )
    return or_(
        policy.owner_id == user.id,
        explicit,
        and_(policy.visibility == "organisation", legacy_permission(user, action)),
    )


def _allowed_policy_ids(user, action):
    """One shared recursive SQL expression per request actor/action, never a result cache.

    Expanding a nested ancestor predicate for every audited resource makes the
    PostgreSQL planner duplicate hundreds of policy subqueries. A recursive CTE
    evaluates the permitted roots once and walks only permitted descendants.
    """
    identity = (user.id, user.organization_id, user.role, user.active)
    cached_identity, expressions = getattr(user, "_content_access_expressions", (None, {}))
    if cached_identity != identity:
        expressions = {}
        user._content_access_expressions = (identity, expressions)
    if action in expressions:
        return expressions[action]
    root = aliased(ResourceAccess)
    allowed = (
        select(root.id.label("id"), literal(0).label("depth"))
        .where(
            tenant_clause(root, user), root.parent_id.is_(None), _own_permission(root, user, action)
        )
        .cte(recursive=True)
    )
    child = aliased(ResourceAccess)
    allowed = allowed.union_all(
        select(child.id, allowed.c.depth + 1)
        .join(allowed, child.parent_id == allowed.c.id)
        .where(
            tenant_clause(child, user),
            allowed.c.depth < MAX_DEPTH,
            _own_permission(child, user, action),
        )
    )
    expressions[action] = allowed
    return allowed


def access_clause(model, user, action="view"):
    kind = resource_type(model)
    if not kind:
        return inherited_clause(model, user, action)
    if action not in PERMISSIONS:
        raise ValueError("Unknown permission")
    policy = aliased(ResourceAccess)
    match = and_(policy.resource_type == kind, policy.resource_id == model.id)
    absent = ~exists(select(policy.id).where(match))
    legacy = legacy_permission(user, action)
    if action == "manage_access":
        legacy = model.created_by == user.id
    permitted = or_(
        and_(absent, legacy),
        exists(
            select(policy.id).where(
                match,
                tenant_clause(policy, user),
                policy.id.in_(select(_allowed_policy_ids(user, action).c.id)),
            )
        ),
    )
    if action in ("edit", "approve", "export"):
        return and_(permitted, access_clause(model, user, "view"))
    return permitted


async def require_access(db, model_or_type, resource_id, user, action="view"):
    model = (
        resource_models().get(model_or_type) if isinstance(model_or_type, str) else model_or_type
    )
    if model is None:
        raise HTTPException(404, "Not found")
    if action in ("edit", "approve", "export", "manage_access"):
        # Lock first, then authorise in a separate statement. PostgreSQL READ
        # COMMITTED takes its snapshot before a lock wait; combining the grant
        # predicate with FOR UPDATE could accept a grant revoked while waiting.
        locked = await db.scalar(
            select(model.id)
            .where(model.id == resource_id, tenant_clause(model, user))
            .with_for_update()
        )
        if locked is None:
            raise HTTPException(404, "Not found")
    query = select(model).where(
        model.id == resource_id, tenant_clause(model, user), access_clause(model, user, action)
    )
    row = await db.scalar(query)
    if row is None or not user.active:
        raise HTTPException(404, "Not found")
    return row


async def get_policy(db, kind, resource_id):
    return await db.scalar(
        select(ResourceAccess).where(
            ResourceAccess.resource_type == kind, ResourceAccess.resource_id == resource_id
        )
    )


async def initialize_access(
    db, kind, resource_id, user, visibility="secret", parent_type=None, parent_id=None
):
    if visibility not in ("organisation", "restricted", "secret"):
        raise HTTPException(422, "Invalid visibility")
    existing = await get_policy(db, kind, resource_id)
    if existing:
        return existing
    model = resource_models().get(kind)
    if model is None:
        raise HTTPException(404, "Not found")
    resource = await db.scalar(
        select(model).where(model.id == resource_id, tenant_clause(model, user))
    )
    if resource is None or resource.created_by != user.id:
        raise HTTPException(403, "Only the resource creator can establish its access owner")
    policy = ResourceAccess(
        organization_id=user.organization_id,
        resource_type=kind,
        resource_id=resource_id,
        visibility=visibility,
        owner_id=user.id,
        revision=1,
    )
    db.add(policy)
    await db.flush()
    if parent_type and parent_id:
        await protect_child(db, parent_type, parent_id, kind, resource_id, user)
    return policy


async def effective_permissions(db, kind, resource_id, user):
    if not user.active:
        return []
    model = resource_models().get(kind)
    if model is None:
        return []
    predicates = [model.id == resource_id, tenant_clause(model, user)]
    row = (
        await db.execute(
            select(*(access_clause(model, user, p) for p in PERMISSIONS)).where(*predicates)
        )
    ).first()
    return [p for p, allowed in zip(PERMISSIONS, row or ()) if allowed]


async def access_details(db, kind, resource_id, user):
    resource = await require_access(db, kind, resource_id, user, "summary")
    permissions = await effective_permissions(db, kind, resource_id, user)
    policy = await get_policy(db, kind, resource_id)
    result = {
        "resource_type": kind,
        "resource_id": str(resource_id),
        "visibility": policy.visibility if policy else "organisation",
        "owner_id": str(policy.owner_id if policy else resource.created_by),
        "revision": policy.revision if policy else 0,
        "effective_permissions": permissions,
        "grants": [],
        "parent_type": None,
        "parent_id": None,
    }
    if policy and "manage_access" in permissions:
        grants = (
            await db.scalars(select(AccessGrant).where(AccessGrant.policy_id == policy.id))
        ).all()
        grouped = {}
        for g in grants:
            grouped.setdefault((g.subject_type, str(g.subject_id)), []).append(g.permission)
        result["grants"] = [
            {"subject_type": t, "subject_id": i, "permissions": ps}
            for (t, i), ps in grouped.items()
        ]
        if policy.parent_id:
            parent = await db.get(ResourceAccess, policy.parent_id)
            result.update(parent_type=parent.resource_type, parent_id=str(parent.resource_id))
    return result


async def protect_child(db, parent_type, parent_id, child_type, child_id, user, *, force=False):
    """A linked source keeps its parent restriction permanently, including after unlink."""
    await require_access(db, parent_type, parent_id, user, "edit")
    await require_access(db, child_type, child_id, user, "view")
    parent = await get_policy(db, parent_type, parent_id)
    if parent is None:
        parent = await initialize_access(db, parent_type, parent_id, user, "organisation")
    child = await get_policy(db, child_type, child_id)
    if child and child.parent_id and child.parent_id != parent.id:
        raise HTTPException(
            409, "This source is protected by another workspace. Create a private copy."
        )
    if not force and parent.visibility == "organisation" and parent.parent_id is None:
        return child
    if child and child.parent_id == parent.id:
        return child
    await require_access(db, child_type, child_id, user, "manage_access")
    if child is None:
        child = await initialize_access(db, child_type, child_id, user, "organisation")
    await db.execute(
        select(ResourceAccess.id)
        .where(ResourceAccess.id.in_([parent.id, child.id]))
        .order_by(ResourceAccess.id)
        .with_for_update()
    )
    await db.refresh(parent)
    await db.refresh(child)
    await require_access(db, parent_type, parent_id, user, "edit")
    await require_access(db, child_type, child_id, user, "manage_access")
    if child.parent_id and child.parent_id != parent.id:
        raise HTTPException(
            409, "This source is protected by another workspace. Create a private copy."
        )
    ancestor = parent
    depth = 0
    while ancestor:
        if ancestor.id == child.id:
            raise HTTPException(409, "Circular access inheritance is not allowed")
        depth += 1
        if depth > MAX_DEPTH:
            raise HTTPException(409, "Access inheritance is too deep")
        ancestor = await db.get(ResourceAccess, ancestor.parent_id) if ancestor.parent_id else None
    if child.parent_id is None:
        child.parent_id = parent.id
        child.revision += 1
        await db.flush()
    return child


async def has_confidential_access(db, user):
    """Account reset must not become a route into somebody else's private content."""
    from app.models.access import AccessTeam

    owned_teams = select(AccessTeam.id).where(AccessTeam.owner_id == user.id)
    memberships = select(AccessTeamMember.team_id).where(AccessTeamMember.user_id == user.id)
    grant = exists(
        select(AccessGrant.policy_id).where(
            AccessGrant.policy_id == ResourceAccess.id,
            or_(
                and_(AccessGrant.subject_type == "user", AccessGrant.subject_id == user.id),
                and_(
                    AccessGrant.subject_type == "team",
                    or_(
                        AccessGrant.subject_id.in_(memberships),
                        AccessGrant.subject_id.in_(owned_teams),
                    ),
                ),
            ),
        )
    )
    return bool(
        await db.scalar(
            select(
                exists(
                    select(ResourceAccess.id).where(
                        tenant_clause(ResourceAccess, user),
                        or_(
                            ResourceAccess.visibility != "organisation",
                            ResourceAccess.parent_id.is_not(None),
                        ),
                        or_(ResourceAccess.owner_id == user.id, grant),
                    )
                )
            )
        )
    )


def inherited_clause(model, user, action, *, resolve=None):
    resolve = resolve or access_clause
    from app.models.application import (
        Application,
        ApplicationComponent,
        ApplicationFollowup,
        ApplicationSnapshot,
    )
    from app.models.preparation import (
        PreparationCase,
        PreparationResponse,
        PreparationResponseEvidence,
    )
    from app.models.program import (
        BaselineMigration,
        CertificationProject,
        CertificationProjectMilestone,
        EvidenceItem,
        EvidenceValidation,
        ExportManifest,
        MaintenanceEvent,
        MaintenancePlan,
        SubmissionPackage,
        SubmissionPackageArtifact,
    )
    from app.models.review import (
        ReviewCycle,
        ReviewItem,
        ReviewItemComment,
        ReviewItemEvidenceFile,
        Snapshot,
    )

    mapping = {
        EvidenceValidation: (EvidenceItem, EvidenceValidation.evidence_item_id, False),
        ReviewCycle: (CertificationProject, ReviewCycle.certification_project_id, True),
        MaintenancePlan: (CertificationProject, MaintenancePlan.certification_project_id, True),
        MaintenanceEvent: (MaintenancePlan, MaintenanceEvent.maintenance_plan_id, False),
        ReviewItem: (ReviewCycle, ReviewItem.review_cycle_id, False),
        ReviewItemComment: (ReviewItem, ReviewItemComment.review_item_id, False),
        ReviewItemEvidenceFile: (ReviewItem, ReviewItemEvidenceFile.review_item_id, False),
        CertificationProjectMilestone: (
            CertificationProject,
            CertificationProjectMilestone.project_id,
            False,
        ),
        BaselineMigration: (CertificationProject, BaselineMigration.project_id, False),
        SubmissionPackage: (CertificationProject, SubmissionPackage.project_id, False),
        SubmissionPackageArtifact: (
            SubmissionPackage,
            SubmissionPackageArtifact.submission_package_id,
            False,
        ),
        ApplicationComponent: (Application, ApplicationComponent.application_id, False),
        ApplicationFollowup: (Application, ApplicationFollowup.application_id, False),
        ApplicationSnapshot: (Application, ApplicationSnapshot.application_id, False),
        PreparationResponse: (PreparationCase, PreparationResponse.case_id, False),
        PreparationResponseEvidence: (
            PreparationResponse,
            PreparationResponseEvidence.response_id,
            False,
        ),
    }
    if model is EvidenceItem:
        # Evidence is private to its creator, operational owner and reviewer.
        # Account roles never bypass this relationship check.
        author = or_(model.created_by == user.id, model.owner_id == user.id)
        participant = or_(author, model.reviewer_id == user.id)
        if action in ("summary", "view", "export"):
            return and_(user.active, participant)
        if action == "edit":
            return and_(user.active, author, legacy_permission(user, "edit"))
        if action == "approve":
            return and_(user.active, participant, user.role in ("approver", "admin"))
        return literal(False)
    if model is ExportManifest:
        return manifest_access_clause(user, action, resolve=resolve)
    if model is Snapshot:
        # Every referencing project must be visible; shared snapshots cannot widen an audience.
        clauses = []
        for target in (ReviewCycle, SubmissionPackage):
            clauses.append(
                ~exists(
                    select(target.id)
                    .where(target.snapshot_id == Snapshot.id, ~resolve(target, user, action))
                    .correlate_except(target)
                )
            )
        return and_(*clauses)
    if model not in mapping:
        return True
    parent, foreign_key, nullable = mapping[model]
    predicates = [parent.id == foreign_key, resolve(parent, user, action)]
    if hasattr(parent, "organization_id"):
        predicates.append(tenant_clause(parent, user))
    allowed = exists(select(parent.id).where(*predicates).correlate_except(parent))
    return or_(foreign_key.is_(None), allowed) if nullable else allowed


def manifest_access_clause(user, action="view", *, resolve=None):
    """Manifests retain the audience of the material they describe."""
    resolve = resolve or access_clause
    from sqlalchemy import String, cast, func

    from app.models.program import CertificationProject, ExportManifest, SubmissionPackage
    from app.models.review import ReviewCycle, Snapshot

    models = {
        "certification_project": CertificationProject,
        "submission_package": SubmissionPackage,
        "review_cycle": ReviewCycle,
        "review_package": ReviewCycle,
        "snapshot": Snapshot,
    }
    clauses = []
    for kind, model in models.items():
        match = func.replace(cast(model.id, String), "-", "") == func.replace(
            ExportManifest.scope_id, "-", ""
        )
        predicates = [match, resolve(model, user, action)]
        if hasattr(model, "organization_id"):
            predicates.append(tenant_clause(model, user))
        clauses.append(
            and_(
                ExportManifest.scope_type == kind,
                exists(select(model.id).where(*predicates).correlate_except(model)),
            )
        )
    return or_(ExportManifest.scope_type.not_in(tuple(models)), *clauses)
