import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Requirement, ReviewCycle, ReviewItem, ReviewItemEvidenceFile, User
from app.models.organization import Organization
from app.services.auth import create_access_token, create_refresh_token, hash_password


@pytest.fixture
async def original_work(db_session, default_jurisdiction, tmp_path):
    org = Organization(code="review-owner", name="Review owner")
    other = Organization(code="other-company", name="Other company")
    db_session.add_all([org, other])
    await db_session.flush()
    owner = User(
        email="owner@example.test",
        full_name="Owner",
        role="admin",
        organization_id=org.id,
        password_hash=hash_password("fixture-password"),
    )
    outsider = User(
        email="outsider@example.test",
        full_name="Outsider",
        role="admin",
        organization_id=other.id,
        password_hash=hash_password("fixture-password"),
    )
    db_session.add_all([owner, outsider])
    await db_session.flush()
    requirement = Requirement(
        reference_id="3.1.1.1",
        text="Retain evidence",
        requirement_type="mandatory",
        organization_id=org.id,
        jurisdiction_id=default_jurisdiction.id,
    )
    cycle = ReviewCycle(
        name="Protected review",
        created_by=owner.id,
        organization_id=org.id,
        jurisdiction_id=default_jurisdiction.id,
    )
    db_session.add_all([requirement, cycle])
    await db_session.flush()
    item = ReviewItem(review_cycle_id=cycle.id, requirement_id=requirement.id)
    db_session.add(item)
    await db_session.flush()
    source = tmp_path / "original.png"
    source.write_bytes(b"retained fixture evidence")
    evidence = ReviewItemEvidenceFile(
        review_item_id=item.id, filename="original.png", file_path=str(source), uploaded_by=owner.id
    )
    db_session.add(evidence)
    await db_session.commit()
    return owner, outsider, cycle, item, evidence, source


def auth(user):
    return {"Authorization": "Bearer " + create_access_token({"sub": str(user.id)})}


@pytest.mark.parametrize(
    "role", ["admin", "manager", "approver", "contributor", "assigned_reviewer"]
)
async def test_evidence_checks_parent_organisation_for_every_role(
    client, db_session, original_work, role
):
    _, outsider, cycle, item, evidence, source = original_work
    outsider.role = role
    await db_session.commit()
    url = f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/files/{evidence.id}"
    for suffix in ("/download", "/preview"):
        response = await client.get(url + suffix, headers=auth(outsider))
        assert response.status_code == 404
    assert (await client.delete(url, headers=auth(outsider))).status_code == 404
    assert source.read_bytes() == b"retained fixture evidence"
    assert await db_session.get(ReviewItemEvidenceFile, evidence.id)


@pytest.mark.parametrize("state", ["closed", "archived"])
@pytest.mark.parametrize(
    "action", ["decision", "comment", "assign", "bulk", "jira", "upload", "delete_file"]
)
async def test_inactive_reviews_cannot_mutate_through_child_routes(
    client, db_session, original_work, state, action
):
    owner, _, cycle, item, evidence, source = original_work
    cycle.status = state
    await db_session.commit()
    base = f"/api/v1/review-cycles/{cycle.id}"
    url = f"{base}/items/{item.id}"
    requests = {
        "decision": (
            "PUT",
            url,
            {"json": {"review_status": "confirmed", "review_evidence": "Changed"}},
        ),
        "comment": ("POST", url + "/comments", {"json": {"body": "Changed"}}),
        "assign": ("PUT", url + "/assign", {"json": {"responsible_user_id": str(owner.id)}}),
        "bulk": (
            "PATCH",
            base + "/items/bulk",
            {"json": {"item_ids": [str(item.id)], "review_status": "confirmed"}},
        ),
        "jira": ("PUT", url + "/jira", {"json": {"jira_issue_key": "TEST-1"}}),
        "upload": (
            "POST",
            url + "/files",
            {"files": {"file": ("new.txt", b"new fixture", "text/plain")}},
        ),
        "delete_file": ("DELETE", url + f"/files/{evidence.id}", {}),
    }
    method, path, kwargs = requests[action]
    response = await client.request(method, path, headers=auth(owner), **kwargs)
    assert response.status_code == 409, response.text
    await db_session.refresh(item)
    assert item.review_status == "pending" and item.review_evidence is None
    assert source.exists()
    assert (
        await client.get(url + f"/files/{evidence.id}/download", headers=auth(owner))
    ).status_code == 200


async def test_uploaded_file_audit_identifies_the_created_file(
    client, db_session, original_work, monkeypatch, tmp_path
):
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    owner, _, cycle, item, _, _ = original_work
    response = await client.post(
        f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/files",
        headers=auth(owner),
        files={"file": ("proof.txt", b"proof", "text/plain")},
    )
    assert response.status_code == 201
    created_id = response.json()["id"]
    event = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.entity_type == "review_item_evidence_file")
        )
    ).scalar_one()
    assert event.entity_id == created_id and uuid.UUID(event.entity_id)


async def test_refresh_token_cannot_be_used_as_access_cookie_or_bearer(client, original_work):
    owner, *_ = original_work
    token = create_refresh_token({"sub": str(owner.id), "type": "access"})
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    client.cookies.set("access_token", token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_comment_attachment_upload_respects_tenant_and_assignment(
    client, db_session, original_work,
):
    owner, outsider, cycle, item, _, _ = original_work
    url = f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/comments/attachments"
    response = await client.post(url, headers=auth(outsider), data={"body": "Private"},
                                 files={"files": ("private.txt", b"private")})
    assert response.status_code == 404
    owner.role = "assigned_reviewer"
    await db_session.commit()
    response = await client.post(url, headers=auth(owner), data={"body": "Unassigned"},
                                 files={"files": ("private.txt", b"private")})
    assert response.status_code == 403
    item.assigned_reviewer_id = owner.id
    await db_session.commit()
    response = await client.post(url, headers=auth(owner), data={"body": "Assigned"},
                                 files={"files": ("private.txt", b"private")})
    assert response.status_code == 201, response.text
