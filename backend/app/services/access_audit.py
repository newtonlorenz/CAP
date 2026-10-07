"""Filter audit records before pagination so hidden work leaves no activity trail."""

from functools import lru_cache

from sqlalchemy import String, and_, cast, exists, func, literal, or_, select
from sqlalchemy.orm import aliased

from app.models.access import ResourceAccess
from app.models.application import Application, ApplicationComponent
from app.models.audit import AuditLog
from app.models.preparation import (
    PreparationCase,
    PreparationEvidence,
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
from app.services.access import (
    MAX_DEPTH,
    access_clause,
    inherited_clause,
    resource_type,
    tenant_clause,
)


@lru_cache(maxsize=1)
def _policy_descendants():
    """Share one SQL expression, never permission results, across audit branches."""
    tree = select(
        ResourceAccess.id.label("root_id"),
        ResourceAccess.id.label("child_id"),
        literal(0).label("depth"),
    ).cte(recursive=True)
    child = aliased(ResourceAccess)
    tree = tree.union_all(
        select(tree.c.root_id, child.id, tree.c.depth + 1)
        .join(child, child.parent_id == tree.c.child_id)
        .where(tree.c.depth < MAX_DEPTH + 1)
    )
    return tree


class _VisibleSources:
    """Share SQL expressions within a query, never cache permission results.

    Each relationship refers to a CTE of visible IDs instead of nesting the
    complete parent predicate again. This bounds SQLite parser depth and lets
    PostgreSQL plan shared sources once across audit entity types.
    """

    def __init__(self, user):
        self.user = user
        self._visible = {}
        self._full = {}

    def clause(self, model, user, action):
        assert user is self.user and action == "view"
        return model.id.in_(select(self.visible(model).c.id))

    def visible(self, model):
        if model not in self._visible:
            permission = (
                access_clause(model, self.user, "view")
                if resource_type(model)
                else inherited_clause(model, self.user, "view", resolve=self.clause)
            )
            predicates = [permission]
            if hasattr(model, "organization_id"):
                predicates.append(tenant_clause(model, self.user))
            self._visible[model] = select(model.id).where(*predicates).cte()
        return self._visible[model]

    def full(self, model):
        if model not in self._full:
            self._full[model] = select(model.id).where(_full_content_clause(model, self)).cte()
        return self._full[model]


def full_content_access_clause(model, user):
    """Require view of all current and persistently linked historical sources."""
    return model.id.in_(select(_VisibleSources(user).full(model).c.id))


def _full_content_clause(model, sources):
    tree = _policy_descendants()
    root = aliased(ResourceAccess)
    descendant = aliased(ResourceAccess)
    source_models = {
        "application": Application,
        "preparation_case": PreparationCase,
        "preparation_evidence": PreparationEvidence,
    }
    accessible = or_(
        *(
            and_(
                descendant.resource_type == kind,
                descendant.resource_id.in_(select(sources.visible(source).c.id)),
            )
            for kind, source in source_models.items()
        )
    )
    kind = "application" if model is Application else "preparation_case"
    hidden_descendant = exists(
        select(descendant.id)
        .select_from(root)
        .join(tree, tree.c.root_id == root.id)
        .join(descendant, descendant.id == tree.c.child_id)
        .where(root.resource_type == kind, root.resource_id == model.id, ~accessible)
        .correlate(model)
    )
    predicates = [model.id.in_(select(sources.visible(model).c.id)), ~hidden_descendant]
    # Existing records may have associations that predate persistent inheritance.
    if model is PreparationCase:
        evidence = PreparationEvidence
        response = aliased(PreparationResponse)
        link = aliased(PreparationResponseEvidence)
        hidden_evidence = exists(
            select(link.evidence_id)
            .select_from(response)
            .join(link, link.response_id == response.id)
            .outerjoin(evidence, evidence.id == link.evidence_id)
            .where(
                response.case_id == model.id,
                or_(
                    evidence.id.is_(None),
                    evidence.id.not_in(select(sources.visible(evidence).c.id)),
                ),
            )
            .correlate(model)
        )
        predicates.append(~hidden_evidence)
    if model is Application:
        component = aliased(ApplicationComponent)
        case_visible = component.case_id.in_(select(sources.full(PreparationCase).c.id))
        evidence_visible = component.evidence_id.in_(
            select(sources.visible(PreparationEvidence).c.id)
        )
        hidden_component = exists(
            select(component.id)
            .where(
                component.application_id == model.id,
                or_(
                    and_(component.case_id.is_not(None), ~case_visible),
                    and_(component.evidence_id.is_not(None), ~evidence_visible),
                ),
            )
            .correlate(model)
        )
        predicates.append(~hidden_component)
    return and_(*predicates)


def audit_access_clause(user):
    sources = _VisibleSources(user)

    # Normalise UUIDs for PostgreSQL UUID and SQLite's UUID representation.
    def matches(column):
        return func.replace(cast(column, String), "-", "") == func.replace(
            AuditLog.entity_id, "-", ""
        )

    def visible(model):
        ids = (
            sources.full(model)
            if model in (Application, PreparationCase)
            else sources.visible(model)
        )
        return exists(select(ids.c.id).where(matches(ids.c.id)).correlate(AuditLog))

    models = {
        "evidence_item": EvidenceItem,
        "evidence_validation": EvidenceValidation,
        "application": Application,
        "preparation_case": PreparationCase,
        "preparation_evidence": PreparationEvidence,
        "certification_project": CertificationProject,
        "maintenance_plan": MaintenancePlan,
        "certification_project_stage_gate": CertificationProject,
        "certification_project_milestone": CertificationProjectMilestone,
        "review_cycle": ReviewCycle,
        "review_item": ReviewItem,
        "review_item_comment": ReviewItemComment,
        "review_item_evidence_file": ReviewItemEvidenceFile,
        "review_package": ReviewCycle,
        "submission_package": SubmissionPackage,
        "submission_package_artifact": SubmissionPackageArtifact,
        "baseline_migration": BaselineMigration,
        "snapshot": Snapshot,
        "export_manifest": ExportManifest,
    }
    case_ids = sources.full(PreparationCase)
    # Deleted protected entities fail closed; their historical payload may still
    # contain confidential text even though there is no current row to check.
    return or_(
        AuditLog.entity_type.not_in((*models, "preparation_response")),
        and_(
            AuditLog.entity_type == "preparation_response",
            exists(
                select(case_ids.c.id)
                .where(
                    func.replace(cast(case_ids.c.id, String), "-", "")
                    == func.replace(func.substr(AuditLog.entity_id, 1, 36), "-", ""),
                )
                .correlate(AuditLog)
            ),
        ),
        *(and_(AuditLog.entity_type == kind, visible(model)) for kind, model in models.items()),
    )
