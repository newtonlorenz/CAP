"""HTTP regressions for inherited project privacy and independent capabilities."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.access import AccessGrant, ResourceAccess
from app.models.audit import AuditLog
from app.models.program import CertificationProject, ExportManifest, SubmissionPackage
from app.models.requirement import Requirement, RequirementStatus
from app.models.review import ReviewCycle, ReviewItem, Snapshot
from app.models.user import User
from app.services.auth import create_access_token


@pytest.fixture
async def private_project(db_session, default_jurisdiction):
    owner = User(
        id=uuid.uuid4(),
        email="project-owner@example.test",
        password_hash="unused",
        full_name="Owner",
        role="manager",
        active=True,
    )
    admin = User(
        id=uuid.uuid4(),
        email="account-admin@example.test",
        password_hash="unused",
        full_name="Account admin",
        role="admin",
        active=True,
    )
    viewer = User(
        id=uuid.uuid4(),
        email="project-viewer@example.test",
        password_hash="unused",
        full_name="Viewer",
        role="manager",
        active=True,
    )
    db_session.add_all([owner, admin, viewer])
    await db_session.flush()
    project = CertificationProject(
        id=uuid.uuid4(),
        name="Confidential acquisition",
        jurisdiction_id=default_jurisdiction.id,
        created_by=owner.id,
        stage="intake",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    policy = ResourceAccess(
        id=uuid.uuid4(),
        resource_type="certification_project",
        resource_id=project.id,
        visibility="secret",
        owner_id=owner.id,
    )
    db_session.add(policy)
    await db_session.flush()
    db_session.add(
        AccessGrant(
            policy_id=policy.id, subject_type="user", subject_id=viewer.id, permission="view"
        )
    )
    cycle = ReviewCycle(
        id=uuid.uuid4(),
        name="Secret submission review",
        jurisdiction_id=default_jurisdiction.id,
        certification_project_id=project.id,
        created_by=owner.id,
        status="active",
        cycle_type="submission",
        scope="all",
    )
    snapshot = Snapshot(
        id=uuid.uuid4(),
        name="Secret frozen assessment",
        snapshot_type="review_cycle",
        data_json="{}",
        total_requirements=1,
        evidenced_requirements=0,
        created_by=owner.id,
    )
    db_session.add_all([cycle, snapshot])
    await db_session.flush()
    cycle.snapshot_id = snapshot.id
    package = SubmissionPackage(
        id=uuid.uuid4(),
        project_id=project.id,
        review_cycle_id=cycle.id,
        snapshot_id=snapshot.id,
        version=1,
        status="draft",
        created_by=owner.id,
    )
    requirement = Requirement(
        id=uuid.uuid4(),
        jurisdiction_id=default_jurisdiction.id,
        reference_id="PUBLIC-1",
        text="Public requirement",
        requirement_type="mandatory",
        active=True,
    )
    db_session.add_all([package, requirement])
    await db_session.flush()
    item = ReviewItem(
        id=uuid.uuid4(),
        review_cycle_id=cycle.id,
        requirement_id=requirement.id,
        assigned_reviewer_id=admin.id,
        review_status="pending",
    )
    manifest = ExportManifest(
        id=uuid.uuid4(),
        scope_type="submission_package",
        scope_id=str(package.id),
        payload_json=json.dumps({"name": "Confidential acquisition"}),
        hash_algo="sha256",
        signature="synthetic",
        signed_by=owner.id,
    )
    db_session.add_all([item, manifest])
    await db_session.flush()
    for entity, identifier in [
        ("certification_project", project.id),
        ("review_cycle", cycle.id),
        ("review_item", item.id),
        ("submission_package", package.id),
        ("export_manifest", manifest.id),
    ]:
        db_session.add(
            AuditLog(
                user_id=owner.id,
                user_name=owner.full_name,
                action="create",
                entity_type=entity,
                entity_id=str(identifier),
                new_value='{"name":"Confidential acquisition"}',
                timestamp=datetime.now(UTC),
            )
        )
    await db_session.commit()
    return {
        "owner": owner,
        "admin": admin,
        "viewer": viewer,
        "project": project,
        "policy": policy,
        "cycle": cycle,
        "snapshot": snapshot,
        "package": package,
        "item": item,
        "requirement": requirement,
        "manifest": manifest,
    }


def headers(user):
    return {"Authorization": f'Bearer {create_access_token({"sub": str(user.id)})}'}


async def test_admin_cannot_discover_secret_project_through_lists_dashboard_audit_or_direct_links(
    client, private_project
):
    p = private_project
    auth = headers(p["admin"])
    for path in [
        "/certification-projects",
        "/review-cycles",
        "/submission-packages",
        "/snapshots",
        "/export-manifests",
    ]:
        result = await client.get("/api/v1" + path, headers=auth)
        assert result.status_code == 200, result.text
        assert result.json()["total"] == 0, path
    for path in [
        f'/certification-projects/{p["project"].id}',
        f'/certification-projects/{p["project"].id}/milestones',
        f'/review-cycles/{p["cycle"].id}',
        f'/snapshots/{p["snapshot"].id}',
        f'/submission-packages/{p["package"].id}/gate-check',
        f'/export-manifests/{p["manifest"].id}/verify',
        f'/reports/gap-analysis?review_cycle_id={p["cycle"].id}',
    ]:
        result = await client.get("/api/v1" + path, headers=auth)
        assert result.status_code == 404, (path, result.text)
    dashboard = await client.get("/api/v1/dashboard", headers=auth)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["review_cycles"]["active"] == []
    assert dashboard.json()["recent_activity"] == []
    assert dashboard.json()["my_work"]["assigned_review_items"]["total"] == 0
    summary = await client.get("/api/v1/program-workspace/summary", headers=auth)
    assert summary.status_code == 200, summary.text
    assert summary.json()["items"] == []
    audit = await client.get("/api/v1/reports/audit-trail", headers=auth)
    assert audit.status_code == 200
    assert "Confidential acquisition" not in audit.text
    visible = await client.get(
        f'/api/v1/certification-projects/{p["project"].id}', headers=headers(p["owner"])
    )
    assert visible.status_code == 200, visible.text


async def test_view_grant_does_not_allow_project_review_mutations_or_exports(
    client, private_project, db_session
):
    p = private_project
    auth = headers(p["viewer"])
    visible = await client.get(f'/api/v1/review-cycles/{p["cycle"].id}', headers=auth)
    assert visible.status_code == 200, visible.text
    requests = [
        ("patch", f'/certification-projects/{p["project"].id}', {"name": "Changed"}),
        ("post", f'/certification-projects/{p["project"].id}/submission-cycle', {}),
        ("post", f'/review-cycles/{p["cycle"].id}/archive', {}),
        (
            "put",
            f'/review-cycles/{p["cycle"].id}/items/{p["item"].id}',
            {"review_evidence": "Changed"},
        ),
        ("patch", f'/submission-packages/{p["package"].id}', {"checklist_json": "{}"}),
        ("post", f'/submission-packages/{p["package"].id}/bundle-manifest', {}),
    ]
    for method, path, body in requests:
        result = await client.request(method, "/api/v1" + path, json=body, headers=auth)
        assert result.status_code == 404, (path, result.text)
    report = await client.get(
        f'/api/v1/reports/gap-analysis?review_cycle_id={p["cycle"].id}', headers=auth
    )
    assert report.status_code == 404
    db_session.add(
        AccessGrant(
            policy_id=p["policy"].id,
            subject_type="user",
            subject_id=p["viewer"].id,
            permission="export",
        )
    )
    await db_session.commit()
    report = await client.get(
        f'/api/v1/reports/gap-analysis?review_cycle_id={p["cycle"].id}', headers=auth
    )
    assert report.status_code == 200, report.text
    assert "PUBLIC-1" in report.text


async def test_secret_review_assessment_does_not_publish_evidence_to_shared_requirement_history(
    client, private_project, db_session
):
    p = private_project
    result = await client.put(
        f'/api/v1/review-cycles/{p["cycle"].id}/items/{p["item"].id}',
        headers=headers(p["owner"]),
        json={
            "requirement_status": "in_progress",
            "review_evidence": "Confidential negotiation information",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["review_evidence"] == "Confidential negotiation information"
    shared = (
        await db_session.scalars(
            select(RequirementStatus).where(RequirementStatus.requirement_id == p["requirement"].id)
        )
    ).all()
    assert shared == []


async def test_project_notifications_skip_mentioned_and_assigned_people_without_access(
    client, private_project, db_session, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    import app.api.reviews as reviews_api

    p = private_project
    p["item"].responsible_user_id = p["viewer"].id
    await db_session.commit()
    monkeypatch.setattr(
        reviews_api,
        "resolve_installation_settings",
        AsyncMock(return_value=SimpleNamespace(email_available=True)),
    )
    send = Mock()
    monkeypatch.setattr(reviews_api, "send_email", send)
    comment = await client.post(
        f'/api/v1/review-cycles/{p["cycle"].id}/items/{p["item"].id}/comments',
        headers=headers(p["owner"]),
        json={
            "body": "@account-admin@example.test @project-viewer@example.test Confidential discussion"
        },
    )
    assert comment.status_code == 201, comment.text
    assert [call.args[0] for call in send.call_args_list] == [[p["viewer"].email]]
    send.reset_mock()
    reminder = await client.post(
        f'/api/v1/review-cycles/{p["cycle"].id}/remind-assigned',
        headers=headers(p["owner"]),
        json={"review_statuses": ["pending"]},
    )
    assert reminder.status_code == 200, reminder.text
    assert reminder.json()["reviewers_emailed"] == 1
    assert [call.args[0] for call in send.call_args_list] == [[p["viewer"].email]]


async def test_private_project_jira_dispatch_requires_both_edit_and_export(
    client, private_project, db_session, monkeypatch
):
    from unittest.mock import AsyncMock

    from sqlalchemy import delete

    import app.api.reviews as reviews_api
    from app.services.jira import JiraSyncSummary

    p = private_project
    edit = AccessGrant(
        policy_id=p["policy"].id,
        subject_type="user",
        subject_id=p["viewer"].id,
        permission="edit",
    )
    db_session.add(edit)
    await db_session.commit()
    dispatch = AsyncMock(return_value=JiraSyncSummary())
    monkeypatch.setattr(reviews_api, "sync_review_cycle_jira_items", dispatch)
    endpoint = f'/api/v1/review-cycles/{p["cycle"].id}/jira-sync'
    denied = await client.post(endpoint, headers=headers(p["viewer"]), json={"force": True})
    assert denied.status_code == 404, denied.text
    dispatch.assert_not_awaited()

    db_session.add(
        AccessGrant(
            policy_id=p["policy"].id,
            subject_type="user",
            subject_id=p["viewer"].id,
            permission="export",
        )
    )
    await db_session.commit()
    allowed = await client.post(endpoint, headers=headers(p["viewer"]), json={"force": True})
    assert allowed.status_code == 200, allowed.text
    assert dispatch.await_count == 1

    await db_session.execute(
        delete(AccessGrant).where(
            AccessGrant.policy_id == p["policy"].id,
            AccessGrant.subject_id == p["viewer"].id,
            AccessGrant.permission == "edit",
        )
    )
    await db_session.commit()
    denied = await client.post(endpoint, headers=headers(p["viewer"]), json={"force": True})
    assert denied.status_code == 404, denied.text
    assert dispatch.await_count == 1
