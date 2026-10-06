import uuid

import pytest

from app.models import Requirement, RequirementStatus, ReviewCycle, ReviewItem, User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def test_user(db_session):
    user = User(
        email="test@example.com",
        password_hash=hash_password("testpass"),
        full_name="Test User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_requirements(db_session, test_user, default_jurisdiction):
    doc_id = uuid.uuid4()
    reqs = []
    for i in range(5):
        req = Requirement(
            jurisdiction_id=default_jurisdiction.id,
            document_id=doc_id,
            reference_id=f"REQ-00{i + 1}",
            text=f"Test requirement {i + 1}",
            requirement_type="mandatory",
            active=True,
            version=1,
            sort_order=i,
        )
        db_session.add(req)
        reqs.append(req)
    await db_session.commit()

    # Add status to some requirements
    for i, req in enumerate(reqs):
        await db_session.refresh(req)
        if i < 2:
            status = RequirementStatus(
                requirement_id=req.id,
                status="evidenced",
                comment="Completed",
                changed_by=test_user.id,
            )
            db_session.add(status)
    await db_session.commit()

    return reqs


@pytest.fixture
def auth_headers(test_user):
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_get_dashboard(client, auth_headers, test_requirements):
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert "kpis" in data
    assert "breakdowns" in data
    assert "recent_activity" in data
    assert "review_cycles" in data
    assert "snapshots" in data
    assert "my_work" in data

    assert data["kpis"]["overall"]["total"] == 5
    assert data["kpis"]["overall"]["evidenced"] == 2
    assert data["kpis"]["overall"]["percentage"] == 40.0

    assert data["kpis"]["mandatory"]["total"] == 5
    assert data["kpis"]["mandatory"]["evidenced"] == 2
    assert data["kpis"]["mandatory"]["percentage"] == 40.0

    status_totals = {row["status"]: row["total"] for row in data["kpis"]["by_status"]}
    assert status_totals["evidenced"] == 2
    assert status_totals["not_started"] == 3


async def test_dashboard_unauthorized(client):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 401


@pytest.fixture
async def assigned_reviewer_user(db_session):
    user = User(
        email="reviewer@example.com",
        password_hash=hash_password("testpass"),
        full_name="Assigned Reviewer",
        role="assigned_reviewer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def assigned_reviewer_headers(assigned_reviewer_user):
    token = create_access_token({"sub": str(assigned_reviewer_user.id)})
    return {"Authorization": f"Bearer {token}"}


async def test_assigned_reviewer_dashboard_scoped(
    client, db_session, assigned_reviewer_user, assigned_reviewer_headers, default_jurisdiction
):
    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        reference_id="REQ-AR-001",
        text="Assigned reviewer requirement",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)

    cycle = ReviewCycle(
        name="Active Cycle",
        jurisdiction_id=default_jurisdiction.id,
        scope="all",
        status="active",
        created_by=assigned_reviewer_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=req.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.get("/api/v1/dashboard", headers=assigned_reviewer_headers)
    assert response.status_code == 200
    data = response.json()

    # Assigned reviewers should not receive admin queues / data quality panels.
    assert data.get("queues") is None
    assert data.get("data_quality") is None

    assert data["my_work"]["assigned_review_items"]["total"] == 1
    assert data["review_cycles"]["active"][0]["my_pending_count"] == 1


async def test_dashboard_active_cycle_progress_excludes_not_applicable_requirement_status(
    client, db_session, assigned_reviewer_user, assigned_reviewer_headers, default_jurisdiction
):
    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        reference_id="REQ-AR-NA-001",
        text="Excluded from progress when not applicable",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)

    cycle = ReviewCycle(
        name="Not Applicable Cycle",
        jurisdiction_id=default_jurisdiction.id,
        scope="all",
        status="active",
        created_by=assigned_reviewer_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=req.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
    )
    db_session.add(item)
    await db_session.commit()

    initial_response = await client.get("/api/v1/dashboard", headers=assigned_reviewer_headers)
    assert initial_response.status_code == 200
    initial_cycle = initial_response.json()["review_cycles"]["active"][0]
    assert initial_cycle["progress"] == {"total": 1, "completed": 0, "pending": 1}
    assert initial_cycle["my_pending_count"] == 1

    db_session.add(
        RequirementStatus(
            requirement_id=req.id,
            status="not_applicable",
            comment="No longer applicable for this cycle",
            changed_by=assigned_reviewer_user.id,
        )
    )
    await db_session.commit()

    excluded_response = await client.get("/api/v1/dashboard", headers=assigned_reviewer_headers)
    assert excluded_response.status_code == 200
    excluded_cycle = excluded_response.json()["review_cycles"]["active"][0]
    assert excluded_cycle["progress"] == {"total": 0, "completed": 0, "pending": 0}
    assert excluded_cycle["my_pending_count"] == 0

    db_session.add(
        RequirementStatus(
            requirement_id=req.id,
            status="in_progress",
            comment="Back in scope",
            changed_by=assigned_reviewer_user.id,
        )
    )
    await db_session.commit()

    restored_response = await client.get("/api/v1/dashboard", headers=assigned_reviewer_headers)
    assert restored_response.status_code == 200
    restored_cycle = restored_response.json()["review_cycles"]["active"][0]
    assert restored_cycle["progress"] == {"total": 1, "completed": 0, "pending": 1}
    assert restored_cycle["my_pending_count"] == 1


async def test_dashboard_excludes_historical_draft_and_duplicate_legacy_requirements(
    client, db_session, test_user, auth_headers, default_jurisdiction
):
    from app.models.document import Document
    from app.models.program import RequirementSetVersion

    source = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="versioned.pdf",
        file_path="/fixtures/versioned.pdf",
        name="Versioned set",
        document_type="standard",
        status="approved",
        uploaded_by=test_user.id,
    )
    legacy = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="legacy.pdf",
        file_path="/fixtures/legacy.pdf",
        name="Legacy set",
        document_type="annex_b",
        status="approved",
        uploaded_by=test_user.id,
    )
    db_session.add_all([source, legacy])
    await db_session.flush()
    versions = []
    for number, status, current in [
        (1, "approved", False),
        (2, "approved", True),
        (3, "draft", False),
    ]:
        version = RequirementSetVersion(
            document_id=source.id,
            version_number=number,
            status=status,
            is_current=current,
            created_by=test_user.id,
        )
        db_session.add(version)
        versions.append(version)
    await db_session.flush()
    rows = []
    for number, (document_id, version_id) in enumerate(
        [
            (source.id, versions[0].id),
            (source.id, versions[1].id),
            (source.id, versions[2].id),
            (source.id, None),
            (legacy.id, None),
            (None, None),
        ]
    ):
        requirement = Requirement(
            jurisdiction_id=default_jurisdiction.id,
            document_id=document_id,
            requirement_set_version_id=version_id,
            reference_id=f"CONTROL-{number}",
            text="A source control",
            requirement_type="mandatory",
            active=True,
        )
        db_session.add(requirement)
        rows.append(requirement)
    await db_session.flush()
    for requirement in [rows[0], rows[3], rows[4]]:
        db_session.add(
            RequirementStatus(
                requirement_id=requirement.id, status="evidenced", comment="Test evidence", changed_by=test_user.id
            )
        )
    await db_session.commit()
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["kpis"]["overall"]["total"] == 3
    assert data["kpis"]["overall"]["evidenced"] == 1
    assert data["kpis"]["mandatory"]["total"] == 3
    assert sum(row["total"] for row in data["kpis"]["by_status"]) == 3
    assert sum(row["total"] for row in data["breakdowns"]["by_document"]) == 3


async def test_dashboard_trend_does_not_mix_review_scopes_with_manual_snapshots(client, db_session, test_user, auth_headers):
    from app.models import Snapshot
    manual = Snapshot(name="Organisation baseline", snapshot_type="manual", data_json="{}", total_requirements=100, evidenced_requirements=30, created_by=test_user.id)
    review = Snapshot(name="Small review", snapshot_type="review_close", data_json="{}", total_requirements=2, evidenced_requirements=2, created_by=test_user.id)
    db_session.add_all([manual, review])
    await db_session.commit()
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    assert [row["name"] for row in response.json()["snapshots"]] == ["Organisation baseline"]


async def test_dashboard_coverage_excludes_informational_and_non_applicable_controls(client, db_session, test_user, auth_headers, default_jurisdiction):
    for index, (kind, status) in enumerate([("mandatory", "evidenced"), ("recommended", "not_started"), ("informational", "evidenced"), ("mandatory", "not_applicable"), ("not_applicable", "not_started")]):
        row = Requirement(jurisdiction_id=default_jurisdiction.id, reference_id=str(index), text="Synthetic control", requirement_type=kind, active=True)
        db_session.add(row); await db_session.flush()
        db_session.add(RequirementStatus(requirement_id=row.id, status=status, comment="Synthetic assessment rationale", changed_by=test_user.id))
    await db_session.commit()
    result = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()
    assert result["kpis"]["overall"] == {"total": 2, "evidenced": 1, "percentage": 50.0}
    assert result["kpis"]["mandatory"] == {"total": 1, "evidenced": 1, "percentage": 100.0}
    assert sum(row["total"] for row in result["kpis"]["by_status"]) == 2
    assert sum(row["total"] for row in result["breakdowns"]["by_document"]) == 2


async def test_dashboard_attention_uses_completion_gaps_before_counting_and_paging(
    client, db_session, test_user, auth_headers, default_jurisdiction
):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    cycle = ReviewCycle(name="Due review", jurisdiction_id=default_jurisdiction.id, scope="all", status="active", created_by=test_user.id, deadline=now - timedelta(days=2))
    db_session.add(cycle)
    await db_session.flush()
    # More than one old page of completed work must never hide outstanding work.
    for index in range(24):
        req = Requirement(jurisdiction_id=default_jurisdiction.id, reference_id=f"DONE-{index}", text="Complete control", requirement_type="mandatory", active=True)
        db_session.add(req)
        await db_session.flush()
        db_session.add(ReviewItem(review_cycle_id=cycle.id, requirement_id=req.id, assigned_reviewer_id=test_user.id, review_status="confirmed", assessment_status="evidenced", review_evidence="Evidence recorded"))
    expected = {}
    for reference, status, decision, kind, evidence in [
        ("MISSING-EVIDENCE", "in_progress", "confirmed", "mandatory", ""),
        ("ESCALATED", "evidenced", "escalated", "mandatory", "Evidence"),
        ("MISSING-REASON", "not_applicable", "confirmed", "mandatory", ""),
        ("EXCLUDED-COMPLETE", "not_applicable", "confirmed", "mandatory", "Outside scope"),
        ("INFORMATIONAL", "not_started", "pending", "informational", ""),
    ]:
        req = Requirement(jurisdiction_id=default_jurisdiction.id, reference_id=reference, text="Synthetic control", requirement_type=kind, active=True)
        db_session.add(req)
        await db_session.flush()
        item = ReviewItem(review_cycle_id=cycle.id, requirement_id=req.id, assigned_reviewer_id=test_user.id, review_status=decision, assessment_status=status, review_evidence=evidence)
        db_session.add(item)
        await db_session.flush()
        expected[reference] = str(item.id)
    await db_session.commit()

    result = (await client.get("/api/v1/dashboard?work_scope=unresolved&work_page_size=2", headers=auth_headers)).json()["my_work"]["assigned_review_items"]
    assert result["total"] == 3
    assert sum(row["total"] for row in result["by_status"]) == 3
    assert result["items"][0]["review_item_id"] == expected["ESCALATED"]
    page2 = (await client.get("/api/v1/dashboard?work_scope=unresolved&work_page_size=2&work_page=2", headers=auth_headers)).json()["my_work"]["assigned_review_items"]
    rows = {row["requirement_reference_id"]: row for row in result["items"] + page2["items"]}
    assert rows["MISSING-EVIDENCE"]["action_reasons"] == ["Evidence is not complete"]
    assert rows["MISSING-REASON"]["action_reasons"] == ["Record the reason this requirement does not apply"]
    assert rows["ESCALATED"]["action_reasons"] == ["Resolve escalation"]
    all_work = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()["my_work"]["assigned_review_items"]
    assert all_work["total"] == 29
    assert len(all_work["items"]) == 20


async def test_dashboard_attention_preserves_role_tenant_and_cycle_visibility(
    client, db_session, assigned_reviewer_user, assigned_reviewer_headers, default_jurisdiction
):
    from app.models.access import ResourceAccess
    from app.models.program import CertificationProject
    from app.models.organization import Organization

    organization = Organization(name="Other organization", code="other-dashboard")
    other = User(email="other-dashboard@example.test", full_name="Other", role="manager", password_hash="unused")
    db_session.add_all([organization, other])
    await db_session.flush()
    for label in ["visible", "responsible-only", "hidden", "foreign", "closed"]:
        foreign = organization.id if label == "foreign" else None
        req = Requirement(organization_id=foreign, jurisdiction_id=default_jurisdiction.id, reference_id=label, text="Scoped control", requirement_type="mandatory", active=True)
        cycle = ReviewCycle(organization_id=foreign, jurisdiction_id=default_jurisdiction.id, name=label, scope="all", status="closed" if label == "closed" else "active", created_by=other.id)
        db_session.add_all([req, cycle])
        await db_session.flush()
        item = ReviewItem(review_cycle_id=cycle.id, requirement_id=req.id, assigned_reviewer_id=other.id if label == "responsible-only" else assigned_reviewer_user.id, responsible_user_id=assigned_reviewer_user.id, assessment_status="not_started", review_status="pending")
        db_session.add(item)
        if label == "hidden":
            project = CertificationProject(name="Private project", jurisdiction_id=default_jurisdiction.id, created_by=other.id)
            db_session.add(project)
            await db_session.flush()
            cycle.certification_project_id = project.id
            db_session.add(ResourceAccess(resource_type="certification_project", resource_id=project.id, visibility="secret", owner_id=other.id))
    await db_session.commit()
    result = (await client.get("/api/v1/dashboard?work_scope=unresolved", headers=assigned_reviewer_headers)).json()
    assert [row["cycle_name"] for row in result["my_work"]["assigned_review_items"]["items"]] == ["visible"]


async def test_dashboard_activity_filters_auth_before_limit_and_links_visible_comments(
    client, db_session, test_user, auth_headers, default_jurisdiction
):
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import func, select
    from app.models.audit import AuditLog
    from app.models.review import ReviewItemComment
    from app.models.access import ResourceAccess

    now = datetime.now(UTC)
    req = Requirement(jurisdiction_id=default_jurisdiction.id, reference_id="CTRL-7", title="Player records", text="Synthetic control", requirement_type="mandatory", active=True)
    cycle = ReviewCycle(jurisdiction_id=default_jurisdiction.id, name="Quarterly review", scope="all", status="active", created_by=test_user.id)
    hidden_owner = User(email="hidden-feed@example.test", full_name="Other", role="manager", password_hash="unused")
    db_session.add_all([req, cycle, hidden_owner])
    await db_session.flush()
    item = ReviewItem(review_cycle_id=cycle.id, requirement_id=req.id, assigned_reviewer_id=test_user.id)
    db_session.add(item)
    await db_session.flush()
    comment = ReviewItemComment(review_item_id=item.id, author_id=test_user.id, body="Check the evidence")
    db_session.add(comment)
    await db_session.flush()
    for index in range(25):
        db_session.add(AuditLog(user_id=test_user.id, user_name="Contributor", action="login", entity_type="user", entity_id=str(test_user.id), timestamp=now + timedelta(seconds=index)))
    db_session.add(AuditLog(user_id=test_user.id, user_name="Contributor", action="create", entity_type="review_item_comment", entity_id=str(comment.id), timestamp=now - timedelta(seconds=1)))
    await db_session.commit()
    response = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()
    assert len(response["recent_activity"]) == 1
    activity = response["recent_activity"][0]
    assert activity["title"] == "CTRL-7 · Player records"
    assert activity["destination"] == f"/review-cycles/{cycle.id}?mode=focus&item={item.id}"
    assert await db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "login")) == 25
    from app.models.program import CertificationProject
    project = CertificationProject(name="Private project", jurisdiction_id=default_jurisdiction.id, created_by=hidden_owner.id)
    db_session.add(project)
    await db_session.flush()
    cycle.certification_project_id = project.id
    db_session.add(ResourceAccess(resource_type="certification_project", resource_id=project.id, visibility="secret", owner_id=hidden_owner.id))
    await db_session.commit()
    hidden_response = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()
    assert hidden_response["recent_activity"] == []


@pytest.mark.parametrize(
    "legacy_status,legacy_comment,assessment_status,review_evidence,expected_reasons",
    [
        ("evidenced", "Evidence complete", None, None, []),
        ("not_applicable", "Outside the licensed activity", None, None, []),
        ("not_applicable", "", None, None, ["Record the reason this requirement does not apply"]),
        ("in_progress", "Evidence incomplete", None, None, ["Evidence is not complete"]),
        ("evidenced", "Previously complete", "in_progress", "", ["Evidence is not complete"]),
        ("not_applicable", "Old exclusion reason", "not_applicable", "", ["Record the reason this requirement does not apply"]),
    ],
)
async def test_dashboard_legacy_assessment_status_and_rationale_fallback(
    client, db_session, test_user, auth_headers, default_jurisdiction,
    legacy_status, legacy_comment, assessment_status, review_evidence, expected_reasons,
):
    from datetime import UTC, datetime, timedelta

    req = Requirement(
        jurisdiction_id=default_jurisdiction.id, reference_id="LEGACY-1",
        text="Legacy control", requirement_type="mandatory", active=True,
    )
    cycle = ReviewCycle(
        jurisdiction_id=default_jurisdiction.id, name="Legacy review", scope="all",
        status="active", created_by=test_user.id,
    )
    db_session.add_all([req, cycle])
    await db_session.flush()
    item = ReviewItem(
        review_cycle_id=cycle.id, requirement_id=req.id,
        assigned_reviewer_id=test_user.id, review_status="confirmed",
        assessment_status=assessment_status, review_evidence=review_evidence,
    )
    now = datetime.now(UTC)
    db_session.add_all([
        item,
        RequirementStatus(
            requirement_id=req.id, status="blocked", comment="Superseded status",
            changed_by=test_user.id, changed_at=now - timedelta(days=1),
        ),
        RequirementStatus(
            requirement_id=req.id, status=legacy_status, comment=legacy_comment,
            changed_by=test_user.id, changed_at=now,
        ),
    ])
    await db_session.commit()
    response = await client.get("/api/v1/dashboard?work_scope=unresolved", headers=auth_headers)
    assert response.status_code == 200
    work = response.json()["my_work"]["assigned_review_items"]
    assert work["total"] == int(bool(expected_reasons))
    if expected_reasons:
        assert work["items"][0]["action_reasons"] == expected_reasons
    else:
        assert work["items"] == []
    all_work = (await client.get("/api/v1/dashboard?work_scope=all", headers=auth_headers)).json()["my_work"]["assigned_review_items"]
    assert all_work["total"] == 1
    assert all_work["items"][0]["action_reasons"] == expected_reasons
