# ruff: noqa: F811 - imported pytest fixture reused across application scenarios
"""API contracts for flexible packs, tenant boundaries and retained approval bytes.

These scenarios own the application lifecycle contract: existing preparation tests
cover individual answer types; this suite exercises their composition into packs.
"""

import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, PreparationEvidence, User
from app.services.preparation_files import checked_evidence_path
from tests.test_preparation_api import actors, headers, make_template  # noqa: F401

BASE = "/api/v1/applications"
PREP = "/api/v1/preparation"


@pytest.fixture
async def approver(db_session, actors):
    user = User(
        email="approver@example.test",
        full_name="Approver",
        password_hash="unused",
        role="approver",
        organization_id=actors["manager"].organization_id,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def create(client, user, jurisdiction, scope="annex_only"):
    response = await client.post(
        BASE,
        headers=headers(user),
        json={
            "visibility": "organisation",
            "name": "Annex A and B",
            "scope": scope,
            "jurisdiction_id": str(jurisdiction.id),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def action(client, user, pack, operation, expected=200, **body):
    result = await client.post(
        f"{BASE}/{pack['id']}/{operation}",
        headers=headers(user),
        json={"expected_revision": pack["revision"], **body},
    )
    assert result.status_code == expected, result.text
    return result.json()


async def component(client, user, pack, **body):
    result = await client.post(
        f"{BASE}/{pack['id']}/components",
        headers=headers(user),
        json={"expected_revision": pack["revision"], "name": "Annex A", "kind": "annex", **body},
    )
    assert result.status_code == 201, result.text
    return result.json()


async def answer(client, user, case_id, value="Company Ltd"):
    case = (await client.get(f"{PREP}/cases/{case_id}", headers=headers(user))).json()
    result = await client.put(
        f"{PREP}/cases/{case_id}/responses/answer",
        headers=headers(user),
        json={"expected_revision": case["revision"], "value": value},
    )
    assert result.status_code == 200, result.text
    result = await client.post(
        f"{PREP}/cases/{case_id}/responses/answer/accept",
        headers=headers(user),
        json={"expected_revision": result.json()["revision"]},
    )
    assert result.status_code == 200, result.text


async def ready_pack(client, manager, jurisdiction, scope="annex_only"):
    form = await make_template(client, manager)
    pack = await create(client, manager, jurisdiction, scope)
    pack = await component(client, manager, pack, template_id=form["id"])
    case_id = pack["components"][0]["case_id"]
    await answer(client, manager, case_id)
    return pack, case_id


@pytest.mark.parametrize("scope", ["annex_only", "licence", "full_pack"])
async def test_scope_does_not_impose_a_main_form_or_annex(
    client, actors, approver, default_jurisdiction, scope
):
    manager = actors["manager"]
    pack, _ = await ready_pack(client, manager, default_jurisdiction, scope)
    pack = await action(client, manager, pack, "request-review")
    pack = await action(client, approver, pack, "approve")
    assert pack["status"] == "approved"
    assert pack["snapshots"][0]["version"] == 1
    # Download is a read, never evidence of submission.
    snapshot = pack["snapshots"][0]
    exported = await client.get(
        f"{BASE}/{pack['id']}/snapshots/{snapshot['id']}/export", headers=headers(actors["reader"])
    )
    assert hashlib.sha256(exported.content).hexdigest() == snapshot["sha256"]
    assert (await client.get(f"{BASE}/{pack['id']}", headers=headers(manager))).json()[
        "status"
    ] == "approved"
    pack = await action(
        client,
        manager,
        pack,
        "record-submission",
        submitted_at=datetime.now(UTC).isoformat(),
        reference="AUTH-42",
    )
    pack = await action(client, manager, pack, "complete", outcome="Accepted by authority")
    assert pack["status"] == "completed"
    assert pack["outcome"] == "Accepted by authority"


async def test_readiness_empty_unfinished_excluded_and_stale_review(
    client, actors, approver, default_jurisdiction
):
    manager = actors["manager"]
    pack = await create(client, manager, default_jurisdiction)
    await action(client, manager, pack, "request-review", expected=422)
    form = await make_template(client, manager)
    pack = await component(client, manager, pack, template_id=form["id"])
    await action(client, manager, pack, "request-review", expected=422)
    cid = pack["components"][0]["id"]
    case_id = pack["components"][0]["case_id"]
    patch = await client.patch(
        f"{BASE}/{pack['id']}/components/{cid}",
        headers=headers(manager),
        json={"expected_revision": pack["revision"], "included": False},
    )
    pack = patch.json()
    assert any(item["code"] == "excluded_required" for item in pack["readiness"]["blockers"])
    pack = (
        await client.patch(
            f"{BASE}/{pack['id']}/components/{cid}",
            headers=headers(manager),
            json={"expected_revision": pack["revision"], "included": True},
        )
    ).json()
    await answer(client, manager, case_id)
    pack = await action(client, manager, pack, "request-review")
    await answer(client, manager, case_id, "Changed during review")
    await action(client, approver, pack, "approve", expected=409)
    pack = await action(client, approver, pack, "return-to-draft", reason="Review updated response")
    pack = await action(client, manager, pack, "request-review")
    pack = await action(client, approver, pack, "approve")
    await answer(client, manager, case_id, "Changed after approval")
    detail = (await client.get(f"{BASE}/{pack['id']}", headers=headers(manager))).json()
    assert any(item["code"] == "approval_stale" for item in detail["readiness"]["blockers"])
    await action(
        client,
        manager,
        pack,
        "record-submission",
        expected=409,
        reference="X",
        submitted_at=datetime.now(UTC).isoformat(),
    )


async def test_immutable_document_archive_and_invalid_evidence(
    client, actors, approver, default_jurisdiction, db_session
):
    manager = actors["manager"]
    upload = await client.post(
        f"{PREP}/evidence/upload",
        headers=headers(manager),
        data={"visibility": "organisation", "title": "Signed annex"},
        files={"file": ("annex.pdf", b"%PDF-synthetic signed annex", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    evidence_id = upload.json()["id"]
    pack = await create(client, manager, default_jurisdiction)
    pack = await component(client, manager, pack, kind="document", evidence_id=evidence_id)
    pack = await action(client, manager, pack, "request-review")
    pack = await action(client, approver, pack, "approve")
    snapshot = pack["snapshots"][0]
    url = f"{BASE}/{pack['id']}/snapshots/{snapshot['id']}/export"
    original = (await client.get(url, headers=headers(manager))).content
    archive = zipfile.ZipFile(io.BytesIO(original))
    assert archive.read(f"evidence/{evidence_id}/annex.pdf") == b"%PDF-synthetic signed annex"
    evidence = await db_session.get(PreparationEvidence, uuid.UUID(evidence_id))
    checked_evidence_path(evidence).write_bytes(b"tampered")
    await action(
        client,
        manager,
        pack,
        "record-submission",
        expected=422,
        reference="X",
        submitted_at=datetime.now(UTC).isoformat(),
    )
    assert (await client.get(url, headers=headers(manager))).content == original
    # Missing live evidence must not prevent historical pack retrieval either.
    checked_evidence_path(evidence).unlink()
    assert (await client.get(url, headers=headers(manager))).content == original


async def test_followup_resolution_resubmission_and_retained_versions(
    client, actors, approver, default_jurisdiction, db_session
):
    manager = actors["manager"]
    pack, case_id = await ready_pack(client, manager, default_jurisdiction)
    for op, actor in [("request-review", manager), ("approve", approver)]:
        pack = await action(client, actor, pack, op)
    first = pack["snapshots"][0]
    url = f"{BASE}/{pack['id']}/snapshots/{first['id']}/export"
    original = (await client.get(url, headers=headers(manager))).content
    pack = await action(
        client,
        manager,
        pack,
        "record-submission",
        reference="AUTH-1",
        submitted_at=datetime.now(UTC).isoformat(),
    )
    pack = await action(client, manager, pack, "start-follow-up")
    pack = await action(
        client,
        manager,
        pack,
        "followups",
        expected=201,
        question="Provide updated ownership",
        owner_id=str(actors["contributor"].id),
    )
    fid = pack["followups"][0]["id"]
    await action(client, manager, pack, "complete", expected=422, outcome="Accepted")
    result = await client.patch(
        f"{BASE}/{pack['id']}/followups/{fid}",
        headers=headers(manager),
        json={"expected_revision": pack["revision"], "status": "resolved"},
    )
    assert result.status_code == 422
    pack = (
        await client.patch(
            f"{BASE}/{pack['id']}/followups/{fid}",
            headers=headers(actors["contributor"]),
            json={"expected_revision": pack["revision"], "response": "Ownership confirmed"},
        )
    ).json()
    pack = (
        await client.patch(
            f"{BASE}/{pack['id']}/followups/{fid}",
            headers=headers(manager),
            json={"expected_revision": pack["revision"], "status": "resolved"},
        )
    ).json()
    assert pack["followups"][0]["resolved_at"]
    # Editing a resolved response reopens the query and requires fresh manager resolution.
    pack = (
        await client.patch(
            f"{BASE}/{pack['id']}/followups/{fid}",
            headers=headers(actors["contributor"]),
            json={"expected_revision": pack["revision"], "response": "Confirmed final ownership"},
        )
    ).json()
    assert pack["followups"][0]["status"] == "open"
    pack = (
        await client.patch(
            f"{BASE}/{pack['id']}/followups/{fid}",
            headers=headers(manager),
            json={"expected_revision": pack["revision"], "status": "resolved"},
        )
    ).json()
    pack = await action(client, manager, pack, "return-to-draft", reason="Prepare supplement")
    await answer(client, manager, case_id, "Revised company")
    for op, actor in [("request-review", manager), ("approve", approver)]:
        pack = await action(client, actor, pack, op)
    assert [s["version"] for s in pack["snapshots"]] == [2, 1]
    second = pack["snapshots"][0]
    new_archive = zipfile.ZipFile(
        io.BytesIO(
            (
                await client.get(
                    f"{BASE}/{pack['id']}/snapshots/{second['id']}/export", headers=headers(manager)
                )
            ).content
        )
    )
    assert (
        json.loads(new_archive.read("application.json"))["followups"][0]["response"]
        == "Confirmed final ownership"
    )
    pack = await action(
        client,
        manager,
        pack,
        "record-submission",
        reference="AUTH-2",
        submitted_at=datetime.now(UTC).isoformat(),
    )
    assert pack["snapshots"][1]["reference"] == "AUTH-1"
    assert (await client.get(url, headers=headers(manager))).content == original
    audit = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "application", AuditLog.entity_id == pack["id"]
            )
        )
    ).all()
    assert len(audit) == pack["revision"]


async def test_tenant_roles_revision_and_linking_boundaries(
    client, actors, approver, default_jurisdiction
):
    manager = actors["manager"]
    pack, case_id = await ready_pack(client, manager, default_jurisdiction)
    for actor in [actors["other"], actors["null_manager"]]:
        assert (await client.get(f"{BASE}/{pack['id']}", headers=headers(actor))).status_code == 404
        assert (await client.get(BASE, headers=headers(actor))).json()["total"] == 0
        foreign = await create(client, actor, default_jurisdiction)
        result = await client.post(
            f"{BASE}/{foreign['id']}/components",
            headers=headers(actor),
            json={
                "expected_revision": foreign["revision"],
                "name": "Leak",
                "kind": "annex",
                "case_id": case_id,
            },
        )
        assert result.status_code == 404
    for actor in [actors["reader"], actors["contributor"], approver]:
        result = await client.post(
            BASE,
            headers=headers(actor),
            json={
                "name": "Denied",
                "scope": "licence",
                "jurisdiction_id": str(default_jurisdiction.id),
            },
        )
        assert result.status_code == 403
    stale = await client.patch(
        f"{BASE}/{pack['id']}",
        headers=headers(manager),
        json={"expected_revision": 1, "name": "Stale"},
    )
    assert stale.status_code == 409
    pack = await action(client, manager, pack, "request-review")
    await action(client, manager, pack, "approve", expected=403)
    pack = await action(client, approver, pack, "approve")
    for actor in [actors["other"], actors["null_manager"]]:
        assert (
            await client.get(
                f"{BASE}/{pack['id']}/snapshots/{pack['snapshots'][0]['id']}/export",
                headers=headers(actor),
            )
        ).status_code == 404
    await action(
        client,
        manager,
        pack,
        "record-submission",
        expected=422,
        reference="X",
        submitted_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
    )
    assert (
        await client.patch(
            f"{BASE}/{pack['id']}",
            headers=headers(manager),
            json={"expected_revision": pack["revision"], "name": "Frozen"},
        )
    ).status_code == 409


async def test_existing_forms_jurisdiction_and_document_validity(
    client, actors, approver, default_jurisdiction, db_session
):
    from app.models import Jurisdiction
    from tests.test_preparation_api import make_case

    manager = actors["manager"]
    pack = await create(client, manager, default_jurisdiction, "full_pack")
    form = await make_template(client, manager)
    other_jurisdiction = Jurisdiction(code="other", name="Other jurisdiction", active=True)
    db_session.add(other_jurisdiction)
    await db_session.commit()
    other_case = await make_case(client, manager, form["id"], other_jurisdiction.id)
    result = await client.post(
        f"{BASE}/{pack['id']}/components",
        headers=headers(manager),
        json={
            "expected_revision": pack["revision"],
            "name": "Wrong market",
            "kind": "annex",
            "case_id": other_case["id"],
        },
    )
    assert result.status_code == 422
    existing = await make_case(client, manager, form["id"], default_jurisdiction.id)
    await answer(client, manager, existing["id"])
    pack = await component(client, manager, pack, case_id=existing["id"])
    # Optional excluded placeholders never force a full-pack template structure.
    pack = await component(
        client,
        manager,
        pack,
        name="Unused main application",
        kind="form",
        required=False,
        included=False,
    )
    pack = await action(client, manager, pack, "request-review")
    pack = await action(client, approver, pack, "approve")
    pack = await action(client, manager, pack, "return-to-draft", reason="Add supporting note")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    evidence = await client.post(
        f"{PREP}/evidence",
        headers=headers(manager),
        json={
            "title": "Expired supporting note",
            "kind": "note",
            "body": "Synthetic",
            "valid_until": yesterday,
        },
    )
    assert evidence.status_code == 201
    pack = await component(
        client,
        manager,
        pack,
        name="Supporting note",
        kind="document",
        evidence_id=evidence.json()["id"],
    )
    assert not pack["readiness"]["ready"]
    await action(client, manager, pack, "request-review", expected=422)


async def test_checklist_placeholder_creates_scoped_form_from_template(
    client, actors, default_jurisdiction
):
    manager = actors["manager"]
    template = await make_template(client, manager)
    pack = await create(client, manager, default_jurisdiction)
    pack = await component(
        client,
        manager,
        pack,
        name="Annex B checklist",
        owner_id=str(actors["contributor"].id),
        due_date="2026-12-01",
    )
    item = pack["components"][0]
    assert item["case_id"] is None and not item["ready"]
    foreign_template = await make_template(client, actors["other"])
    result = await client.patch(
        f"{BASE}/{pack['id']}/components/{item['id']}",
        headers=headers(manager),
        json={"expected_revision": pack["revision"], "template_id": foreign_template["id"]},
    )
    assert result.status_code == 404
    result = await client.patch(
        f"{BASE}/{pack['id']}/components/{item['id']}",
        headers=headers(manager),
        json={"expected_revision": pack["revision"], "template_id": template["id"]},
    )
    assert result.status_code == 200, result.text
    linked = result.json()["components"][0]
    assert linked["id"] == item["id"] and linked["case_id"]
    case = (await client.get(f"{PREP}/cases/{linked['case_id']}", headers=headers(manager))).json()
    assert case["jurisdiction_id"] == str(default_jurisdiction.id)
    assert case["owner_id"] == str(actors["contributor"].id)
    assert case["name"] == "Annex B checklist" and case["due_date"] == "2026-12-01"
    assert case["template_revision"] == template["revision"]
    assert case["fields"] == template["fields"]
    assert (
        await client.get(f"{PREP}/cases/{case['id']}", headers=headers(actors["other"]))
    ).status_code == 404


async def test_readiness_field_targets_preserve_source_rules(client, actors, default_jurisdiction):
    manager = actors["manager"]
    template = await make_template(client, manager, fields=[
        {"key": "answer", "label": "Company name", "section": "Applicant", "type": "text", "required": True},
        {"key": "proof", "label": "Supporting proof", "section": "Evidence", "type": "evidence", "required": True},
    ])
    pack = await create(client, manager, default_jurisdiction)
    pack = await component(client, manager, pack, template_id=template["id"])
    attached = pack["components"][0]
    case_id = attached["case_id"]
    blockers = pack["readiness"]["blockers"]
    assert [(item["field_key"], item["code"]) for item in blockers] == [("answer", "missing"), ("proof", "missing")]
    assert blockers[0] == {
        "component_id": attached["id"], "case_id": case_id, "field_key": "answer",
        "field_label": "Company name", "field_type": "text", "section": "Applicant",
        "code": "missing", "message": "Annex A: Response required",
    }
    await action(client, manager, pack, "request-review", expected=422)
    case = (await client.get(f"{PREP}/cases/{case_id}", headers=headers(manager))).json()
    saved = await client.put(f"{PREP}/cases/{case_id}/responses/answer", headers=headers(manager), json={"expected_revision": case["revision"], "value": "Example Ltd"})
    assert saved.status_code == 200
    detail = (await client.get(f"{BASE}/{pack['id']}", headers=headers(manager))).json()
    assert [(item["field_key"], item["code"]) for item in detail["readiness"]["blockers"]] == [("answer", "pending_acceptance"), ("proof", "missing")]
    assert detail["readiness"]["ready"] is False
    assert detail["readiness"]["ready_count"] == 0
    await action(client, manager, detail, "request-review", expected=422)
