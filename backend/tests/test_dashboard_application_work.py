"""Dashboard queues enforce ownership, contextual access and existing deadlines."""

from datetime import date

import pytest

from app.models.access import AccessGrant, ResourceAccess
from app.models.application import Application, ApplicationComponent, ApplicationFollowup
from app.models.audit import AuditLog
from app.models.preparation import PreparationCase, PreparationTemplate
from app.models.program import CertificationProject, MaintenancePlan
from app.models.user import User
from app.services.auth import create_access_token


@pytest.fixture
async def work(db_session, default_jurisdiction):
    admin = User(
        email="dashboard-admin@example.test",
        full_name="Admin",
        role="admin",
        password_hash="unused",
    )
    other = User(
        email="dashboard-owner@example.test",
        full_name="Owner",
        role="manager",
        password_hash="unused",
    )
    db_session.add_all([admin, other])
    await db_session.flush()
    template = PreparationTemplate(
        name="Licence questions", kind="licence_application", fields_json="[]", created_by=other.id
    )
    db_session.add(template)
    await db_session.flush()
    application = Application(
        name="Operating licence",
        scope="licence",
        jurisdiction_id=default_jurisdiction.id,
        created_by=other.id,
        status="draft",
    )
    case = PreparationCase(
        name="Assigned licence form",
        template_id=template.id,
        template_name=template.name,
        template_revision=1,
        fields_json="[]",
        kind="licence_application",
        jurisdiction_id=default_jurisdiction.id,
        created_by=other.id,
        owner_id=admin.id,
        due_date=date(2026, 10, 15),
        status="active",
    )
    db_session.add_all([application, case])
    await db_session.flush()
    component = ApplicationComponent(
        application_id=application.id,
        case_id=case.id,
        name="Main form",
        kind="form",
        included=True,
        required=True,
    )
    query = ApplicationFollowup(
        application_id=application.id,
        question="Provide director information",
        owner_id=admin.id,
        due_date=date(2026, 10, 20),
        status="open",
    )
    db_session.add_all([component, query])
    await db_session.commit()
    return admin, other, application, case, query


def headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def test_work_queue_preserves_assignment_deadlines_and_excludes_inactive_or_other_owned_work(
    client, db_session, work
):
    admin, other, application, case, query = work
    db_session.add(
        ApplicationFollowup(
            application_id=application.id,
            question="Not assigned to admin",
            owner_id=other.id,
            status="open",
        )
    )
    db_session.add(
        ApplicationFollowup(
            application_id=application.id,
            question="Already resolved",
            owner_id=admin.id,
            status="resolved",
        )
    )
    # Same form reused in another pack must appear once.
    db_session.add(
        ApplicationComponent(
            application_id=application.id,
            case_id=case.id,
            name="Reuse",
            kind="annex",
            included=True,
            required=False,
        )
    )
    await db_session.commit()
    result = await client.get("/api/v1/dashboard", headers=headers(admin))
    assert result.status_code == 200, result.text
    queues = result.json()["my_work"]
    assert queues["assigned_forms"]["total"] == 1
    form = queues["assigned_forms"]["items"][0]
    assert form["case_id"] == str(case.id) and form["due_date"] == "2026-10-15"
    assert form["owner_id"] == str(admin.id) and form["application_id"] == str(application.id)
    assert queues["authority_queries"]["total"] == 1
    authority = queues["authority_queries"]["items"][0]
    assert authority["query_id"] == str(query.id) and authority["due_date"] == "2026-10-20"
    case.status = "archived"
    query.status = "resolved"
    await db_session.commit()
    queues = (await client.get("/api/v1/dashboard", headers=headers(admin))).json()["my_work"]
    assert queues["assigned_forms"] == {"total": 0, "items": []}
    assert queues["authority_queries"] == {"total": 0, "items": []}


async def test_summary_only_admin_assignments_do_not_disclose_forms_queries_or_counts(
    client, db_session, work
):
    admin, other, application, case, query = work
    policies = [
        ResourceAccess(
            resource_type=kind, resource_id=resource.id, owner_id=other.id, visibility="secret"
        )
        for kind, resource in [("application", application), ("preparation_case", case)]
    ]
    db_session.add_all(policies)
    await db_session.flush()
    for policy in policies:
        db_session.add(
            AccessGrant(
                policy_id=policy.id, subject_type="user", subject_id=admin.id, permission="summary"
            )
        )
    await db_session.commit()
    result = await client.get("/api/v1/dashboard", headers=headers(admin))
    assert result.status_code == 200, result.text
    assert result.json()["my_work"]["assigned_forms"] == {"total": 0, "items": []}
    assert result.json()["my_work"]["authority_queries"] == {"total": 0, "items": []}
    assert case.name not in result.text and query.question not in result.text
    for policy in policies:
        db_session.add(
            AccessGrant(
                policy_id=policy.id, subject_type="user", subject_id=admin.id, permission="view"
            )
        )
    await db_session.commit()
    queues = (await client.get("/api/v1/dashboard", headers=headers(admin))).json()["my_work"]
    assert queues["assigned_forms"]["total"] == 1 and queues["authority_queries"]["total"] == 1


async def test_form_component_assignment_uses_its_deadline_without_exposing_hidden_project(
    client, db_session, work, default_jurisdiction
):
    admin, other, application, case, _query = work
    case.owner_id = other.id
    project = CertificationProject(
        name="Private project title", jurisdiction_id=default_jurisdiction.id, created_by=other.id
    )
    db_session.add(project)
    await db_session.flush()
    case.project_id = project.id
    db_session.add(
        ResourceAccess(
            resource_type="certification_project",
            resource_id=project.id,
            owner_id=other.id,
            visibility="secret",
        )
    )
    db_session.add(
        ApplicationComponent(
            application_id=application.id,
            case_id=case.id,
            name="Assigned component",
            kind="form",
            included=True,
            required=True,
            owner_id=admin.id,
            due_date=date(2026, 10, 5),
        )
    )
    await db_session.commit()
    result = await client.get("/api/v1/dashboard", headers=headers(admin))
    assert result.status_code == 200, result.text
    form = result.json()["my_work"]["assigned_forms"]["items"][0]
    assert form["owner_id"] == str(admin.id) and form["due_date"] == "2026-10-05"
    assert form["project_id"] is None and form["project_name"] is None
    assert "Private project title" not in result.text


async def test_maintenance_plan_activity_follows_project_view_access(
    client, db_session, work, default_jurisdiction
):
    admin, other, _application, _case, _query = work
    project = CertificationProject(
        name="Confidential certification",
        jurisdiction_id=default_jurisdiction.id,
        created_by=other.id,
    )
    db_session.add(project)
    await db_session.flush()
    policy = ResourceAccess(
        resource_type="certification_project",
        resource_id=project.id,
        owner_id=other.id,
        visibility="secret",
    )
    plan = MaintenancePlan(
        certification_project_id=project.id,
        jurisdiction_id=default_jurisdiction.id,
        name="Private cadence",
        cadence_days=30,
        created_by=other.id,
    )
    db_session.add_all([policy, plan])
    await db_session.flush()
    activity = AuditLog(
        user_id=other.id,
        user_name="Owner",
        action="update",
        entity_type="maintenance_plan",
        entity_id=str(plan.id),
    )
    db_session.add(activity)
    await db_session.commit()
    before = (await client.get("/api/v1/dashboard", headers=headers(admin))).json()[
        "recent_activity"
    ]
    assert str(activity.id) not in {event["id"] for event in before}
    db_session.add(
        AccessGrant(
            policy_id=policy.id, subject_type="user", subject_id=admin.id, permission="view"
        )
    )
    await db_session.commit()
    after = (await client.get("/api/v1/dashboard", headers=headers(admin))).json()[
        "recent_activity"
    ]
    assert str(activity.id) in {event["id"] for event in after}
