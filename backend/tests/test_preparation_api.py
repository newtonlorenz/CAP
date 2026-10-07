import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import AuditLog, Organization, PreparationEvidence, User
from app.services.auth import create_access_token
from app.services.preparation_files import checked_evidence_path
from app.models.program import CertificationProject
from app.services.access import initialize_access

BASE = "/api/v1/preparation"


async def test_project_forms_filter_before_pagination_and_require_project_access(
    client, db_session, actors, default_jurisdiction
):
    manager = actors["manager"]
    projects = []
    for name, owner, visibility in [
        ("First project", manager, "organisation"),
        ("Second project", manager, "organisation"),
        ("Private project", actors["contributor"], "secret"),
        ("Foreign project", actors["other"], "organisation"),
    ]:
        project = CertificationProject(
            organization_id=owner.organization_id, jurisdiction_id=default_jurisdiction.id,
            name=name, created_by=owner.id,
        )
        db_session.add(project)
        await db_session.flush()
        await initialize_access(db_session, "certification_project", project.id, owner, visibility)
        projects.append(project)
    await db_session.commit()
    form = await make_template(client, manager)
    for name, project in [("First A", projects[0]), ("First B", projects[0]), ("Second", projects[1])]:
        response = await client.post(f"{BASE}/cases", headers=headers(manager), json={
            "template_id": form["id"], "name": name,
            "jurisdiction_id": str(default_jurisdiction.id), "project_id": str(project.id),
            "visibility": "organisation",
        })
        assert response.status_code == 201, response.text
    response = await client.get(
        f"{BASE}/cases?project_id={projects[0].id}&limit=1", headers=headers(manager)
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["project_id"] == str(projects[0].id)
    for project in projects[2:]:
        denied = await client.get(f"{BASE}/cases?project_id={project.id}", headers=headers(manager))
        assert denied.status_code == 404, denied.text


@pytest.fixture
async def actors(db_session):
    first = Organization(code="first", name="First")
    second = Organization(code="second", name="Second")
    db_session.add_all([first, second])
    await db_session.flush()
    users = {}
    for label, org, role in [
        ("manager", first, "manager"),
        ("contributor", first, "contributor"),
        ("reader", first, "reader"),
        ("other", second, "manager"),
        ("null_manager", None, "manager"),
    ]:
        user = User(
            email=f"{label}@example.com",
            password_hash="unused",
            full_name=label,
            role=role,
            organization_id=org.id if org else None,
            active=True,
        )
        db_session.add(user)
        users[label] = user
    await db_session.commit()
    return users


def headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


def template(fields=None):
    return {
        "name": "Draft application",
        "kind": "licence_application",
        "fields": fields
        or [
            {"key": "answer", "label": "Answer", "type": "text", "reuse_key": "shared_answer"},
            {"key": "proof", "label": "Proof", "type": "evidence", "required": False},
        ],
    }


async def make_template(client, user, fields=None):
    response = await client.post(f"{BASE}/templates", json=template(fields), headers=headers(user))
    assert response.status_code == 201, response.text
    return response.json()


async def make_case(client, user, template_id, jurisdiction_id, name="Case"):
    response = await client.post(
        f"{BASE}/cases",
        json={"template_id": template_id, "jurisdiction_id": str(jurisdiction_id), "name": name, "visibility": "organisation"},
        headers=headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_field_validation_and_strict_response_types(client, actors, default_jurisdiction):
    manager = actors["manager"]
    for fields in [
        [{"key": "bad key", "label": "Answer", "type": "text"}],
        [{"key": "a", "label": "   ", "type": "text"}],
        [{"key": "a", "label": "A", "type": "choice", "options": ["same", "same"]}],
        [{"key": "a", "label": "A", "type": "choice", "options": ["x" * 256]}],
        [{"key": "a", "label": "A", "type": "text", "options": ["invalid"]}],
        [{"key": "a", "label": "A", "type": "text"}] * 2,
    ]:
        result = await client.post(
            f"{BASE}/templates", json=template(fields), headers=headers(manager)
        )
        assert result.status_code == 422
    fields = [
        {"key": "number", "label": "Number", "type": "number"},
        {"key": "yes", "label": "Yes", "type": "yes_no"},
        {"key": "when", "label": "When", "type": "date"},
    ]
    form = await make_template(client, manager, fields)
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    for key, value in [("number", "12"), ("number", True), ("yes", "true"), ("when", "2026-13-01")]:
        result = await client.put(
            f"{BASE}/cases/{case['id']}/responses/{key}",
            json={"expected_revision": 1, "value": value},
            headers=headers(manager),
        )
        assert result.status_code == 422, result.text
    result = await client.put(
        f"{BASE}/cases/{case['id']}/responses/number",
        json={"expected_revision": 1, "value": 0},
        headers=headers(manager),
    )
    assert result.status_code == 200
    assert result.json()["readiness"]["answered_count"] == 1
    result = await client.put(
        f"{BASE}/cases/{case['id']}/responses/yes",
        json={"expected_revision": 2, "value": False},
        headers=headers(manager),
    )
    assert result.status_code == 200
    assert result.json()["readiness"]["answered_count"] == 2


async def test_snapshot_stale_revision_and_roles(client, actors, default_jurisdiction):
    manager, contributor, reader = (actors[key] for key in ("manager", "contributor", "reader"))
    forbidden = await client.post(
        f"{BASE}/templates", json=template(), headers=headers(contributor)
    )
    assert forbidden.status_code == 403
    form = await make_template(client, manager)
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    change = await client.patch(
        f"{BASE}/templates/{form['id']}",
        json={
            "expected_revision": 1,
            "name": "Revised",
            "fields": [{"key": "new", "label": "New", "type": "text"}],
        },
        headers=headers(manager),
    )
    assert change.status_code == 200
    read = await client.get(f"{BASE}/cases/{case['id']}", headers=headers(reader))
    assert read.status_code == 200
    assert read.json()["template_name"] == "Draft application"
    assert [field["key"] for field in read.json()["fields"]] == ["answer", "proof"]
    denied = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 1, "value": "yes"},
        headers=headers(reader),
    )
    assert denied.status_code == 403
    edit = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 1, "value": "yes"},
        headers=headers(contributor),
    )
    assert edit.status_code == 200
    stale = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 1, "value": "no"},
        headers=headers(contributor),
    )
    assert stale.status_code == 409
    assert (
        await client.post(
            f"{BASE}/cases/{case['id']}/responses/answer/accept",
            json={"expected_revision": 2},
            headers=headers(contributor),
        )
    ).status_code == 403
    accepted = await client.post(
        f"{BASE}/cases/{case['id']}/responses/answer/accept",
        json={"expected_revision": 2},
        headers=headers(manager),
    )
    assert accepted.status_code == 200
    assert accepted.json()["readiness"]["ready"] is True
    assert accepted.json()["readiness"]["accepted_count"] == 1


async def test_long_multiline_question_survives_template_and_case_snapshot(
    client, actors, default_jurisdiction
):
    question = (
        "Describe the applicant’s governance arrangements and responsibility for compliance.\n\n"
        "Include the responsible person, reporting lines, review frequency and escalation process.\n"
        "Explain how the arrangements apply to outsourced services and describe the records retained.\n"
        "☐ Confirm that the description includes each jurisdiction covered by this application."
    )
    field = {"key": "governance", "label": question, "type": "multiline"}
    form = await make_template(client, actors["manager"], [field])
    assert form["fields"][0]["label"] == question
    case = await make_case(client, actors["manager"], form["id"], default_jurisdiction.id)
    read = await client.get(f"{BASE}/cases/{case['id']}", headers=headers(actors["manager"]))
    assert read.status_code == 200
    assert read.json()["fields"][0]["label"] == question


async def test_org_denials_and_null_org_equality(client, actors, default_jurisdiction):
    form = await make_template(client, actors["manager"])
    case = await make_case(client, actors["manager"], form["id"], default_jurisdiction.id)
    other = actors["other"]
    assert (
        await client.get(f"{BASE}/cases/{case['id']}", headers=headers(other))
    ).status_code == 404
    assert (
        await client.patch(
            f"{BASE}/templates/{form['id']}",
            json={"expected_revision": 1, "name": "hijacked"},
            headers=headers(other),
        )
    ).status_code == 404
    assert (
        await client.post(
            f"{BASE}/cases",
            json={
                "template_id": form["id"],
                "jurisdiction_id": str(default_jurisdiction.id),
                "name": "Foreign",
            },
            headers=headers(other),
        )
    ).status_code == 404
    assert (await client.get(f"{BASE}/cases", headers=headers(other))).json()["total"] == 0
    null_manager = actors["null_manager"]
    assert (await client.get(f"{BASE}/cases", headers=headers(null_manager))).json()["total"] == 0
    null_form = await make_template(client, null_manager)
    null_case = await make_case(client, null_manager, null_form["id"], default_jurisdiction.id)
    assert (
        await client.get(f"{BASE}/cases/{null_case['id']}", headers=headers(other))
    ).status_code == 404


async def test_reuse_resets_acceptance_and_archive_guards(client, actors, default_jurisdiction):
    manager = actors["manager"]
    form = await make_template(client, manager)
    source = await make_case(client, manager, form["id"], default_jurisdiction.id, "Source")
    target = await make_case(client, manager, form["id"], default_jurisdiction.id, "Target")
    source = (
        await client.put(
            f"{BASE}/cases/{source['id']}/responses/answer",
            json={"expected_revision": 1, "value": "Reusable"},
            headers=headers(manager),
        )
    ).json()
    source = (
        await client.post(
            f"{BASE}/cases/{source['id']}/responses/answer/accept",
            json={"expected_revision": 2},
            headers=headers(manager),
        )
    ).json()
    suggestions = (
        await client.get(
            f"{BASE}/cases/{target['id']}/reuse?field_key=answer", headers=headers(manager)
        )
    ).json()["items"]
    assert len(suggestions) == 1
    target = (
        await client.post(
            f"{BASE}/cases/{target['id']}/responses/answer/reuse",
            json={
                "expected_revision": 1,
                "source_case_id": source["id"],
                "source_field_key": "answer",
            },
            headers=headers(manager),
        )
    ).json()
    assert target["responses"][0]["accepted_by"] is None
    assert target["responses"][0]["reused_from_case_id"] == source["id"]
    assert target["readiness"]["ready"] is False
    target = (
        await client.put(
            f"{BASE}/cases/{target['id']}/responses/answer",
            json={"expected_revision": 2, "value": "Edited"},
            headers=headers(manager),
        )
    ).json()
    assert target["responses"][0]["reused_from_case_id"] is None
    archived = await client.patch(
        f"{BASE}/cases/{target['id']}",
        json={"expected_revision": 3, "status": "archived"},
        headers=headers(manager),
    )
    assert archived.status_code == 200
    assert archived.json()["readiness"]["ready"] is False
    assert (
        await client.put(
            f"{BASE}/cases/{target['id']}/responses/answer",
            json={"expected_revision": 4, "value": "again"},
            headers=headers(manager),
        )
    ).status_code == 409
    assert (
        await client.patch(
            f"{BASE}/cases/{target['id']}",
            json={"expected_revision": 4, "status": "active", "name": "Not allowed"},
            headers=headers(manager),
        )
    ).status_code == 409
    reactivated = await client.patch(
        f"{BASE}/cases/{target['id']}",
        json={"expected_revision": 4, "status": "active"},
        headers=headers(manager),
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"


async def test_evidence_expiry_and_inactive_jurisdiction(
    client, db_session, actors, default_jurisdiction
):
    manager = actors["manager"]
    form = await make_template(
        client, manager, [{"key": "proof", "label": "Proof", "type": "evidence"}]
    )
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    expired = PreparationEvidence(
        organization_id=manager.organization_id,
        title="Expired",
        kind="note",
        body="Old",
        valid_until=datetime.now(timezone.utc).date() - timedelta(days=1),
        created_by=manager.id,
    )
    db_session.add(expired)
    await db_session.commit()
    result = await client.put(
        f"{BASE}/cases/{case['id']}/responses/proof",
        json={"expected_revision": 1, "value": None, "evidence_ids": [str(expired.id)]},
        headers=headers(manager),
    )
    assert result.status_code == 200
    assert result.json()["responses"][0]["evidence_ids"] == [str(expired.id)]
    assert result.json()["readiness"]["blockers"][0]["code"] == "expired_evidence"
    assert (
        await client.post(
            f"{BASE}/cases/{case['id']}/responses/proof/accept",
            json={"expected_revision": 2},
            headers=headers(manager),
        )
    ).status_code == 422
    default_jurisdiction.active = False
    await db_session.commit()
    assert (
        await client.post(
            f"{BASE}/cases",
            json={
                "template_id": form["id"],
                "jurisdiction_id": str(default_jurisdiction.id),
                "name": "Inactive",
            },
            headers=headers(manager),
        )
    ).status_code == 422


async def test_optional_invalid_evidence_blocks_ready_case(
    client, db_session, actors, default_jurisdiction
):
    manager = actors["manager"]
    form = await make_template(client, manager)
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    case = (
        await client.put(
            f"{BASE}/cases/{case['id']}/responses/answer",
            json={"expected_revision": 1, "value": "Done"},
            headers=headers(manager),
        )
    ).json()
    case = (
        await client.post(
            f"{BASE}/cases/{case['id']}/responses/answer/accept",
            json={"expected_revision": 2},
            headers=headers(manager),
        )
    ).json()
    assert case["readiness"]["ready"] is True
    expired = PreparationEvidence(
        organization_id=manager.organization_id,
        title="Old",
        kind="note",
        body="Old",
        valid_until=datetime.now(timezone.utc).date() - timedelta(days=1),
        created_by=manager.id,
    )
    db_session.add(expired)
    await db_session.commit()
    case = (
        await client.put(
            f"{BASE}/cases/{case['id']}/responses/proof",
            json={"expected_revision": 3, "evidence_ids": [str(expired.id)]},
            headers=headers(manager),
        )
    ).json()
    assert any(str(expired.id) in response["evidence_ids"] for response in case["responses"])
    assert case["readiness"]["required_count"] == 1
    assert case["readiness"]["accepted_count"] == 1
    assert case["readiness"]["ready"] is False
    assert any(
        item["field_key"] == "proof" and item["code"] == "expired_evidence"
        for item in case["readiness"]["blockers"]
    )


async def test_not_applicable_needs_acceptance_and_audit_records_answer(
    client, db_session, actors, default_jurisdiction
):
    manager = actors["manager"]
    form = await make_template(client, manager)
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    updated = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 1, "not_applicable_reason": "Outside this scope"},
        headers=headers(manager),
    )
    assert updated.status_code == 200
    assert updated.json()["readiness"]["answered_count"] == 1
    assert updated.json()["readiness"]["ready"] is False
    accepted = await client.post(
        f"{BASE}/cases/{case['id']}/responses/answer/accept",
        json={"expected_revision": 2},
        headers=headers(manager),
    )
    assert accepted.status_code == 200
    assert accepted.json()["readiness"]["ready"] is True
    logs = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.entity_type == "preparation_response")
                .order_by(AuditLog.timestamp)
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 2
    assert "Outside this scope" in logs[0].new_value
    assert "value_sha256" in logs[1].new_value
    assert "accepted_by" in logs[1].new_value
    # An identical autosave retry is not a new compliance decision or edit.
    unchanged = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 3, "not_applicable_reason": "  Outside this scope  "},
        headers=headers(manager),
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["revision"] == 3
    assert unchanged.json()["readiness"]["accepted_count"] == 1
    stale = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 2, "not_applicable_reason": "Outside this scope"},
        headers=headers(manager),
    )
    assert stale.status_code == 409
    edited = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        json={"expected_revision": 3, "value": "Now in scope"},
        headers=headers(manager),
    )
    assert edited.status_code == 200
    assert edited.json()["revision"] == 4
    assert edited.json()["readiness"]["accepted_count"] == 0
    logs = (await db_session.execute(select(AuditLog).where(
        AuditLog.entity_type == "preparation_response"
    ).order_by(AuditLog.timestamp))).scalars().all()
    assert len(logs) == 3
    assert logs[-1].user_id == manager.id
    assert "Outside this scope" in logs[-1].old_value
    assert "value_sha256" in logs[-1].new_value


async def test_case_evidence_reference_cap(client, db_session, actors, default_jurisdiction):
    manager = actors["manager"]
    fields = [{"key": "answer", "label": "Answer", "type": "text"}]
    fields += [
        {"key": key, "label": key, "type": "evidence", "required": False}
        for key in ("first", "second", "third")
    ]
    form = await make_template(client, manager, fields)
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    evidence = [
        PreparationEvidence(
            organization_id=manager.organization_id,
            title=f"Item {i}",
            kind="note",
            body="Evidence",
            created_by=manager.id,
        )
        for i in range(201)
    ]
    db_session.add_all(evidence)
    await db_session.commit()
    for revision, key, items in [(1, "first", evidence[:100]), (2, "second", evidence[100:200])]:
        result = await client.put(
            f"{BASE}/cases/{case['id']}/responses/{key}",
            json={"expected_revision": revision, "evidence_ids": [str(item.id) for item in items]},
            headers=headers(manager),
        )
        assert result.status_code == 200, result.text
    excess = await client.put(
        f"{BASE}/cases/{case['id']}/responses/third",
        json={"expected_revision": 3, "evidence_ids": [str(evidence[200].id)]},
        headers=headers(manager),
    )
    assert excess.status_code == 422
    current = await client.get(f"{BASE}/cases/{case['id']}", headers=headers(manager))
    assert current.json()["revision"] == 3


async def test_changed_file_bytes_block_readiness_and_list_hashes_shared_file_once(
    client, db_session, actors, default_jurisdiction, monkeypatch
):
    manager = actors["manager"]
    original_bytes = b"original evidence bytes"
    uploaded = await client.post(
        f"{BASE}/evidence/upload",
        data={"title": "Shared file", "visibility": "organisation"},
        files={"file": ("evidence.txt", original_bytes, "text/plain")},
        headers=headers(manager),
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence_id = uploaded.json()["id"]
    form = await make_template(
        client, manager, [{"key": "proof", "label": "Proof", "type": "evidence"}]
    )
    cases = []
    for name in ("First", "Second"):
        case = await make_case(client, manager, form["id"], default_jurisdiction.id, name)
        case = (
            await client.put(
                f"{BASE}/cases/{case['id']}/responses/proof",
                json={"expected_revision": 1, "evidence_ids": [evidence_id]},
                headers=headers(manager),
            )
        ).json()
        accepted = await client.post(
            f"{BASE}/cases/{case['id']}/responses/proof/accept",
            json={"expected_revision": 2},
            headers=headers(manager),
        )
        assert accepted.status_code == 200
        assert accepted.json()["readiness"]["ready"] is True
        cases.append(case)

    from app.services import preparation as preparation_service

    verify = preparation_service.verify_evidence_file
    checked = []

    def count_verification(item):
        checked.append(item.id)
        return verify(item)

    monkeypatch.setattr(preparation_service, "verify_evidence_file", count_verification)
    listed = await client.get(f"{BASE}/cases", headers=headers(manager))
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert all(item["readiness"]["ready"] for item in listed.json()["items"])
    assert checked == [uuid.UUID(evidence_id)]

    item = await db_session.get(PreparationEvidence, uuid.UUID(evidence_id))
    checked_evidence_path(item).write_bytes(b"X" * len(original_bytes))
    read = await client.get(f"{BASE}/cases/{cases[0]['id']}", headers=headers(manager))
    assert read.status_code == 200
    assert read.json()["readiness"]["ready"] is False
    assert read.json()["readiness"]["accepted_count"] == 0
    assert read.json()["readiness"]["blockers"][0]["code"] == "invalid_evidence_file"


@pytest.mark.parametrize("length", [101, 1000])
async def test_bilingual_sections_survive_template_save_edit_and_case_creation(
    client, actors, default_jurisdiction, length
):
    manager = actors["manager"]
    section = ("Applicant details / Hakijan tiedot – " * 30)[:length]
    fields = [{"key": "name", "label": "Name / Nimi", "type": "text", "section": section}]
    form = await make_template(client, manager, fields)
    assert form["fields"][0]["section"] == section
    updated_section = section[:-1] + "ä"
    fields[0]["section"] = updated_section
    updated = await client.patch(
        f"{BASE}/templates/{form['id']}",
        headers=headers(manager),
        json={"expected_revision": form["revision"], "fields": fields},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["fields"][0]["section"] == updated_section
    case = await make_case(client, manager, form["id"], default_jurisdiction.id)
    assert case["fields"][0]["section"] == updated_section
    loaded = await client.get(f"{BASE}/cases/{case['id']}", headers=headers(manager))
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["fields"][0]["section"] == updated_section


async def test_sections_over_1000_characters_are_rejected_on_create_and_edit(client, actors):
    manager = actors["manager"]
    fields = [{"key": "name", "label": "Name / Nimi", "type": "text", "section": "ä" * 1001}]
    created = await client.post(f"{BASE}/templates", headers=headers(manager), json=template(fields))
    assert created.status_code == 422, created.text
    assert created.json()["detail"][0]["loc"] == ["body", "fields", 0, "section"]
    form = await make_template(client, manager)
    updated = await client.patch(
        f"{BASE}/templates/{form['id']}",
        headers=headers(manager),
        json={"expected_revision": form["revision"], "fields": fields},
    )
    assert updated.status_code == 422, updated.text
    assert updated.json()["detail"][0]["loc"] == ["body", "fields", 0, "section"]
