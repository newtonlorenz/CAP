"""Public API contracts for explicit process bindings and canonical evidence reuse.

The register is a view of authoritative process collections, not a second store
whose evidence is synchronised by copying. Fixtures deliberately distinguish the
review's pinned source from its project's subsequently advanced baseline.
"""

# ruff: noqa: F811 - imported pytest fixture reused by this owning API suite
import hashlib
import io
import uuid
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select

from app.models import PreparationEvidence, Requirement, ReviewCycle, ReviewItem, ReviewItemEvidenceFile, User
from app.models.documentation import DocumentationAssessmentEvidence, DocumentationCoverage
from app.models.program import CertificationProjectRequirementBaseline, RequirementSetVersion
from app.config import settings
from app.services.auth import create_access_token
from tests.test_documentation_register import (  # noqa: F401
    BASE, create_evidence, create_expectation, create_register, documentation_actors,
)
from tests.test_preparation_requirements import make_source


async def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


async def register_current(client, actor, register):
    return await checked(await client.get(f"{BASE}/registers/{register['id']}", headers=actor["headers"]))


async def expectation_current(client, actor, expectation):
    return await checked(await client.get(f"{BASE}/expectations/{expectation['id']}", headers=actor["headers"]))


async def bind_process(client, actor, register, **process):
    current = await register_current(client, actor, register)
    return await checked(await client.put(f"{BASE}/registers/{register['id']}/process",
        headers=actor["headers"], json={"revision": current["revision"],
            "review_cycle_id": None, "application_id": None, **process}))


async def bind_targets(client, actor, expectation, targets):
    current = await expectation_current(client, actor, expectation)
    return await checked(await client.put(f"{BASE}/expectations/{expectation['id']}/process-targets",
        headers=actor["headers"], json={"revision": current["revision"], "targets": targets}))


async def shared_current(client, actor, process):
    return await checked(await client.get(process["shared_path"], headers=actor["headers"]))


async def shared_replace(client, actor, process, evidence_ids):
    current = await shared_current(client, actor, process)
    return await checked(await client.put(process["shared_path"], headers=actor["headers"], json={
        "expected_evidence_changed_at": current["evidence_changed_at"],
        "links": [{"evidence_id": evidence_id, "locator": "Section 2",
                   "rationale": "Synthetic accountable oversight"} for evidence_id in evidence_ids],
    }))


@pytest.fixture
async def review_process(client, db_session, documentation_actors, default_jurisdiction):
    owner = documentation_actors["owner"]
    user = owner["user"]
    document, pinned, requirements = await make_source(db_session, user, default_jurisdiction.id)
    source = Path(settings.upload_dir) / "synthetic-process-source.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    pdf = Canvas(str(source))
    pdf.drawString(40, 700, "Synthetic process source: retain accountable oversight evidence.")
    pdf.save()
    document.file_path = str(source)
    document.status = "approved"
    pinned.status = "approved"
    pinned.is_current = True
    project = await checked(await client.post("/api/v1/certification-projects", headers=owner["headers"],
        json={"name": "Synthetic process project", "jurisdiction_id": str(default_jurisdiction.id)}), 201)
    db_session.add(CertificationProjectRequirementBaseline(project_id=uuid.UUID(project["id"]),
        document_id=document.id, requirement_set_version_id=pinned.id))
    await db_session.commit()
    cycles = []
    for name in ("Pinned process review", "Other process with the same SCP references"):
        cycles.append(await checked(await client.post("/api/v1/review-cycles", headers=owner["headers"], json={
            "name": name, "jurisdiction_id": str(default_jurisdiction.id),
            "certification_project_id": project["id"], "scope": "all",
        }), 201))
    items = list((await db_session.scalars(select(ReviewItem).where(
        ReviewItem.review_cycle_id == uuid.UUID(cycles[0]["id"])).order_by(ReviewItem.id))).all())
    item = next(row for row in items if row.requirement_id == requirements[1].id)
    other_item = await db_session.scalar(select(ReviewItem).where(
        ReviewItem.review_cycle_id == uuid.UUID(cycles[1]["id"]),
        ReviewItem.requirement_id == requirements[1].id))
    # A later project pin must never change the exact target of an existing review.
    latest = RequirementSetVersion(organization_id=user.organization_id, document_id=document.id,
        version_number=2, status="approved", is_current=True, created_by=user.id)
    pinned.is_current = False
    db_session.add(latest)
    await db_session.flush()
    replacement = Requirement(organization_id=user.organization_id, document_id=document.id,
        jurisdiction_id=default_jurisdiction.id, requirement_set_version_id=latest.id,
        reference_id=requirements[1].reference_id, title="New wording for the same printed SCP reference",
        text="Later requirements must not replace the pinned process target", requirement_type="mandatory")
    db_session.add(replacement)
    baseline = await db_session.get(CertificationProjectRequirementBaseline,
        (uuid.UUID(project["id"]), document.id))
    baseline.requirement_set_version_id = latest.id
    await db_session.commit()
    return {"owner": owner, "document": document, "version": pinned,
        "requirement": requirements[1], "replacement": replacement, "project": project,
        "cycle": cycles[0], "other_cycle": cycles[1], "item": item, "other_item": other_item,
        "items": items, "source_identity": {"requirement_id": str(requirements[1].id), "requirement_set_version_id": str(pinned.id)},
        "target": {"review_item_id": str(item.id), "requirement_id": str(requirements[1].id), "requirement_set_version_id": str(pinned.id)},
        "shared_path": f"/api/v1/review-cycles/{cycles[0]['id']}/items/{item.id}/shared-evidence"}


async def sourced_application(client, actor, jurisdiction, process):
    requirement = process["requirement"]
    document = process["document"]
    version = process["version"]
    source = {"kind": "requirement", "document_id": str(document.id), "document_name": document.name,
        "document_status": "approved", "jurisdiction_id": str(jurisdiction.id),
        "requirement_id": str(requirement.id), "requirement_set_version_id": str(version.id),
        "version_number": version.version_number, "version_status": "approved",
        "reference_id": requirement.reference_id,
        "text_sha256": hashlib.sha256(requirement.text.encode()).hexdigest()}
    fields = [{"key": "proof", "label": "Oversight evidence", "type": "evidence",
               "required": True, "source": source},
              {"key": "proof_alias", "label": "Second question for the same exact requirement", "type": "evidence",
               "required": False, "source": source},
              {"key": "unsourced", "label": "Unrelated manually authored evidence", "type": "evidence", "required": False}]
    application = await checked(await client.post("/api/v1/applications", headers=actor["headers"], json={
        "name": "Synthetic process licence application", "scope": "annex_only",
        "jurisdiction_id": str(jurisdiction.id), "visibility": "organisation",
    }), 201)
    application = await checked(await client.post(f"/api/v1/applications/{application['id']}/components",
        headers=actor["headers"], json={"expected_revision": application["revision"], "name": "Source form",
            "kind": "annex", "form_fields": fields}), 201)
    case_id = application["components"][0]["case_id"]
    return application, case_id


async def test_optional_process_uses_exact_pinned_item_and_never_guesses_printed_references(
    client, db_session, documentation_actors, review_process, default_jurisdiction
):
    process = review_process
    owner = process["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register,
        source_reference=process["requirement"].reference_id)
    assert row["requirements"] == [], "A printed SCP reference is not an explicit process target"
    attached = await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    assert attached["process"]["id"] == process["cycle"]["id"]
    candidates = await checked(await client.get(f"{BASE}/registers/{register['id']}/process-targets",
        headers=owner["headers"], params={"q": process["requirement"].reference_id}))
    assert candidates["total"] == 1
    assert str(candidates["items"][0]["review_item_id"]) == str(process["item"].id)
    row = await bind_targets(client, owner, row, [process["target"]])
    assert [(link["requirement_id"], link["requirement_set_version_id"]) for link in row["requirements"]] == [
        (str(process["requirement"].id), str(process["version"].id))]
    assert str(process["replacement"].id) not in str(row["requirements"])
    stale = await client.put(f"{BASE}/registers/{register['id']}/process", headers=owner["headers"],
        json={"revision": register["revision"], "review_cycle_id": process["other_cycle"]["id"], "application_id": None})
    assert stale.status_code == 409, stale.text
    # Keep each unrelated guard satisfied: current row revision, visible peer item,
    # same organisation/jurisdiction, but the wrong explicitly selected process.
    wrong_process = await client.put(f"{BASE}/expectations/{row['id']}/process-targets", headers=owner["headers"],
        json={"revision": row["revision"], "targets": [{**process["target"], "review_item_id": str(process["other_item"].id)}]})
    assert wrong_process.status_code in (404, 422), wrong_process.text
    missing_version = await client.put(f"{BASE}/expectations/{row['id']}/process-targets", headers=owner["headers"],
        json={"revision": row["revision"], "targets": [{"requirement_id": str(process["replacement"].id)}]})
    assert missing_version.status_code == 422, missing_version.text
    unchanged = await expectation_current(client, owner, row)
    assert unchanged["requirements"] == row["requirements"]
    foreign = documentation_actors["foreign"]["user"]
    hidden = ReviewCycle(organization_id=foreign.organization_id, jurisdiction_id=default_jurisdiction.id,
        name="Confidential foreign process", created_by=foreign.id)
    db_session.add(hidden)
    await db_session.commit()
    standalone = await create_register(client, owner, default_jurisdiction, name="Standalone remains optional")
    denied = await client.put(f"{BASE}/registers/{standalone['id']}/process", headers=owner["headers"], json={
        "revision": standalone["revision"], "review_cycle_id": str(hidden.id), "application_id": None})
    assert denied.status_code == 404, denied.text
    assert hidden.name not in denied.text
    options = await checked(await client.get(f"{BASE}/registers/{standalone['id']}/process-options",
        headers=owner["headers"], params={"q": hidden.name}))
    assert options["review_cycles"] == {"items": [], "total": 0}


async def grant(client, actor, resource_type, resource_id, subject, permissions):
    path = f"/api/v1/access/{resource_type}/{resource_id}"
    policy = await checked(await client.get(path, headers=actor["headers"]))
    return await checked(await client.put(path, headers=actor["headers"], json={
        "visibility": policy["visibility"], "expected_revision": policy["revision"],
        "reason": "Synthetic process contract access grant",
        "grants": [{"subject_type": "user", "subject_id": str(subject.id), "permissions": permissions}],
    }))


def collection(row):
    assert len(row["process_targets"]) == 1
    target = row["process_targets"][0]
    assert target["available"] is True
    return target["collection"]


async def test_two_register_rows_reflect_one_review_collection_without_copying_or_sync_loops(
    client, db_session, review_process, default_jurisdiction
):
    process = review_process
    owner = process["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    rows = [await create_expectation(client, owner, register, title=title)
        for title in ("Board policy reference", "Supplier policy reference")]
    target = process["target"]
    rows = [await bind_targets(client, owner, row, [target]) for row in rows]
    source_bytes = b"Synthetic canonical file: no per-row byte copies"
    uploaded = await checked(await client.post("/api/v1/preparation/evidence/upload", headers=owner["headers"],
        data={"title": "One canonical oversight file", "visibility": "organisation"},
        files={"file": ("canonical.txt", source_bytes, "text/plain")}), 201)
    evidence = [uploaded, await create_evidence(client, owner, title="Replacement canonical oversight note")]
    original_files = {path.relative_to(settings.upload_dir) for path in Path(settings.upload_dir).rglob("*") if path.is_file()}
    before_count = await db_session.scalar(select(func.count()).select_from(PreparationEvidence))
    from_register = collection(await expectation_current(client, owner, rows[0]))
    assert from_register["shared_evidence_uri"] == process["shared_path"].removeprefix("/api/v1")
    changed = await checked(await client.put(f"/api/v1{from_register['shared_evidence_uri']}",
        headers=owner["headers"], json={"expected_evidence_changed_at": from_register["evidence_changed_at"],
            "links": [{"evidence_id": evidence[0]["id"], "rationale": "Register context edited the authoritative collection"}]}))
    assert [item["evidence_id"] for item in (await shared_current(client, owner, process))["items"]] == [evidence[0]["id"]]
    for row in rows:
        current = await expectation_current(client, owner, row)
        assert [item["evidence_id"] for item in collection(current)["items"]] == [evidence[0]["id"]]
        assert current["coverage"] == [], "Process reuse must not manufacture a second coverage store"
    replaced = await shared_replace(client, owner, process, [evidence[1]["id"]])
    repeated = await shared_replace(client, owner, process, [evidence[1]["id"]])
    assert [entry["evidence_id"] for entry in repeated["items"]] == [evidence[1]["id"]]
    assert repeated["evidence_changed_at"] == replaced["evidence_changed_at"]
    # A row opened before the process edit cannot silently overwrite that edit.
    stale = await client.put(f"/api/v1{from_register['shared_evidence_uri']}", headers=owner["headers"], json={
        "expected_evidence_changed_at": changed["evidence_changed_at"], "links": []})
    assert stale.status_code == 409, stale.text
    for row in rows:
        assert [item["evidence_id"] for item in collection(await expectation_current(client, owner, row))["items"]] == [evidence[1]["id"]]
    retried = await bind_targets(client, owner, rows[1], [target])
    assert len(retried["process_targets"]) == 1
    unbound = await bind_targets(client, owner, rows[0], [])
    assert unbound["process_targets"] == []
    assert [item["evidence_id"] for item in collection(await expectation_current(client, owner, rows[1]))["items"]] == [evidence[1]["id"]]
    assert (await client.get(f"/api/v1/preparation/evidence/{evidence[0]['id']}", headers=owner["headers"])).status_code == 200
    assert (await client.get(f"/api/v1/preparation/evidence/{evidence[1]['id']}", headers=owner["headers"])).status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(PreparationEvidence)) == before_count
    assert await db_session.scalar(select(func.count()).select_from(DocumentationAssessmentEvidence).where(
        DocumentationAssessmentEvidence.review_item_id == process["item"].id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(DocumentationCoverage).where(
        DocumentationCoverage.expectation_id.in_([uuid.UUID(row["id"]) for row in rows]))) == 0
    assert {path.relative_to(settings.upload_dir) for path in Path(settings.upload_dir).rglob("*") if path.is_file()} == original_files
    assert (await client.get(f"/api/v1/preparation/evidence/{uploaded['id']}/download", headers=owner["headers"])).content == source_bytes


async def test_process_source_access_and_assignment_cannot_be_bypassed_through_register(
    client, db_session, documentation_actors, review_process, default_jurisdiction
):
    process = review_process
    owner, peer = process["owner"], documentation_actors["peer"]
    register = await create_register(client, owner, default_jurisdiction)
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    row = await create_expectation(client, owner, register)
    row = await bind_targets(client, owner, row, [process["target"]])
    evidence = await create_evidence(client, owner, title="Confidential process note", body="Confidential process contents", visibility="secret")
    await shared_replace(client, owner, process, [evidence["id"]])
    assert (await client.get(f"{BASE}/expectations/{row['id']}", headers=peer["headers"])).status_code == 404
    await grant(client, owner, "documentation_register", register["id"], peer["user"], ["view", "edit", "export"])
    redacted = await expectation_current(client, peer, row)
    assert evidence["id"] not in str(redacted)
    assert evidence["title"] not in str(redacted)
    assert evidence["body"] not in str(redacted)
    assert collection(redacted)["items"] == []
    assert collection(redacted).get("warning") or collection(redacted).get("unavailable")
    before = await shared_current(client, peer, process)
    deletion = await client.put(process["shared_path"], headers=peer["headers"], json={
        "expected_evidence_changed_at": before["evidence_changed_at"], "links": []})
    assert deletion.status_code == 404, deletion.text
    assert [item["evidence_id"] for item in (await shared_current(client, owner, process))["items"]] == [evidence["id"]]
    scoped = await create_expectation(client, owner, register, title="Project-scoped mapping", project_id=process["project"]["id"])
    scoped = await bind_targets(client, owner, scoped, [process["target"]])
    await grant(client, owner, "preparation_evidence", evidence["id"], peer["user"], ["view"])
    project_policy_path = f"/api/v1/access/certification_project/{process['project']['id']}"
    policy = await checked(await client.get(project_policy_path, headers=owner["headers"]))
    await checked(await client.put(project_policy_path, headers=owner["headers"], json={
        "expected_revision": policy["revision"], "visibility": "secret", "grants": [],
        "reason": "Only the original process permission is revoked"}))
    hidden = await expectation_current(client, peer, row)
    assert all(not target["available"] for target in hidden["process_targets"])
    denied_clear = await client.put(f"{BASE}/expectations/{row['id']}/process-targets", headers=peer["headers"], json={
        "revision": hidden["revision"], "targets": []})
    assert denied_clear.status_code == 404, denied_clear.text
    preserved = await expectation_current(client, owner, row)
    assert preserved["revision"] == hidden["revision"]
    assert len(preserved["process_targets"]) == 1
    assert preserved["process_targets"][0]["review_item_id"] == str(process["item"].id)
    view_only = await grant(client, owner, "certification_project", process["project"]["id"], peer["user"], ["view"])
    current_register = await register_current(client, peer, register)
    denied_bulk_clear = await client.put(f"{BASE}/registers/{register['id']}/process", headers=peer["headers"], json={
        "revision": current_register["revision"], "review_cycle_id": None, "application_id": None, "clear_targets": True})
    assert denied_bulk_clear.status_code == 404, denied_bulk_clear.text
    retained_register = await register_current(client, owner, register)
    assert retained_register["revision"] == current_register["revision"]
    assert retained_register["process"]["id"] == process["cycle"]["id"]
    retained_scoped = await expectation_current(client, owner, scoped)
    assert retained_scoped["revision"] == scoped["revision"]
    assert retained_scoped["coverage_status"] == scoped["coverage_status"]
    assert [target["id"] for target in retained_scoped["process_targets"]] == [target["id"] for target in scoped["process_targets"]]
    await checked(await client.put(project_policy_path, headers=owner["headers"], json={
        "expected_revision": view_only["revision"], "visibility": "organisation", "grants": [],
        "reason": "Restore the synthetic organisation-visible process"}))
    reviewer = User(email="process-assigned-reviewer@example.test", full_name="Assigned reviewer",
        password_hash="unused", organization_id=owner["user"].organization_id, role="assigned_reviewer", active=True)
    db_session.add(reviewer)
    await db_session.commit()
    reviewer_actor = {"user": reviewer, "headers": {"Authorization": f"Bearer {create_access_token({'sub': str(reviewer.id)})}"}}
    await grant(client, owner, "documentation_register", register["id"], reviewer, ["view", "edit"])
    # Organisation-visible process and source access are satisfied; assignment is not.
    await grant(client, owner, "preparation_evidence", evidence["id"], reviewer, ["view"])
    unassigned = await expectation_current(client, reviewer_actor, row)
    assert evidence["id"] not in str(unassigned)
    options = await checked(await client.get(f"{BASE}/registers/{register['id']}/process-targets",
        headers=reviewer_actor["headers"]))
    assert options == {"items": [], "total": 0}
    process["item"].assigned_reviewer_id = reviewer.id
    await db_session.commit()
    assigned = await expectation_current(client, reviewer_actor, row)
    assert [item["evidence_id"] for item in collection(assigned)["items"]] == [evidence["id"]]


async def test_licence_collection_reuses_the_included_approved_source_and_preserves_approved_archive(
    client, db_session, documentation_actors, review_process, default_jurisdiction
):
    process = review_process
    owner = process["owner"]
    application, case_id = await sourced_application(client, owner, default_jurisdiction, process)
    register = await create_register(client, owner, default_jurisdiction)
    await bind_process(client, owner, register, application_id=application["id"])
    row = await create_expectation(client, owner, register)
    target = {"case_id": case_id, "field_key": "proof", **process["source_identity"]}
    row = await bind_targets(client, owner, row, [target])
    initial = collection(row)
    assert initial["response_uri"] == f"/preparation/cases/{case_id}/responses/proof"
    assert row["requirements"][0]["requirement_id"] == str(process["requirement"].id)
    assert row["requirements"][0]["requirement_set_version_id"] == str(process["version"].id)
    unsourced = await client.put(f"{BASE}/expectations/{row['id']}/process-targets", headers=owner["headers"], json={
        "revision": row["revision"], "targets": [{**target, "field_key": "unsourced"}]})
    assert unsourced.status_code == 422, unsourced.text
    evidence = [await create_evidence(client, owner, title=title)
        for title in ("First licence source note", "Later licence source note")]
    from_register = await checked(await client.put(f"/api/v1{initial['response_uri']}", headers=owner["headers"], json={
        "expected_revision": initial["case_revision"], "evidence_ids": [evidence[0]["id"]]}))
    saved = next(answer for answer in from_register["responses"] if answer["field_key"] == "proof")
    assert saved["evidence_ids"] == [evidence[0]["id"]]
    current = await expectation_current(client, owner, row)
    assert [item["evidence_id"] for item in collection(current)["items"]] == [evidence[0]["id"]]
    stale = await client.put(f"/api/v1{initial['response_uri']}", headers=owner["headers"], json={
        "expected_revision": initial["case_revision"], "evidence_ids": []})
    assert stale.status_code == 409, stale.text
    accepted = await checked(await client.post(f"/api/v1/preparation/cases/{case_id}/responses/proof/accept",
        headers=owner["headers"], json={"expected_revision": from_register["revision"]}))
    requested = await checked(await client.post(f"/api/v1/applications/{application['id']}/request-review",
        headers=owner["headers"], json={"expected_revision": application["revision"]}))
    await grant(client, owner, "preparation_case", case_id, documentation_actors["peer"]["user"], ["view", "export"])
    approved = await checked(await client.post(f"/api/v1/applications/{application['id']}/approve",
        headers=documentation_actors["peer"]["headers"], json={"expected_revision": requested["revision"]}))
    snapshot_path = f"/api/v1/applications/{application['id']}/snapshots/{approved['snapshots'][0]['id']}/export"
    original = await client.get(snapshot_path, headers=owner["headers"])
    assert original.status_code == 200, original.text
    # The reusable live form remains editable; its already approved archive does not.
    changed = await checked(await client.put(f"/api/v1{initial['response_uri']}", headers=owner["headers"], json={
        "expected_revision": accepted["revision"], "evidence_ids": [evidence[1]["id"]]}))
    assert changed["revision"] > accepted["revision"]
    current = await expectation_current(client, owner, row)
    assert [item["evidence_id"] for item in collection(current)["items"]] == [evidence[1]["id"]]
    assert (await client.get(snapshot_path, headers=owner["headers"])).content == original.content
    await bind_targets(client, owner, row, [])
    case = await checked(await client.get(f"/api/v1/preparation/cases/{case_id}", headers=owner["headers"]))
    assert next(answer for answer in case["responses"] if answer["field_key"] == "proof")["evidence_ids"] == [evidence[1]["id"]]
    alias = await create_expectation(client, owner, register, title="A second row for the same licence collection")
    alias = await bind_targets(client, owner, alias, [target])
    assert [item["evidence_id"] for item in collection(alias)["items"]] == [evidence[1]["id"]]
    multiple = await create_expectation(client, owner, register, title="Fresh row with two questions for one versioned requirement")
    assert multiple["requirements"] == []
    matched = await bind_targets(client, owner, multiple, [target, {**target, "field_key": "proof_alias"}])
    assert {item["field_key"] for item in matched["process_targets"]} == {"proof", "proof_alias"}
    assert [(item["requirement_id"], item["requirement_set_version_id"]) for item in matched["requirements"]] == [
        (str(process["requirement"].id), str(process["version"].id))]
    case = await checked(await client.get(f"/api/v1/preparation/cases/{case_id}", headers=owner["headers"]))
    fields = case["fields"]
    source = next(field for field in fields if field["key"] == "proof")["source"]
    source.update(requirement_id=str(process["replacement"].id),
        requirement_set_version_id=str(process["replacement"].requirement_set_version_id),
        version_number=2, text_sha256=hashlib.sha256(process["replacement"].text.encode()).hexdigest())
    retargeted = await checked(await client.patch(f"/api/v1/preparation/cases/{case_id}", headers=owner["headers"],
        json={"expected_revision": case["revision"], "fields": fields}))
    unavailable = await expectation_current(client, owner, matched)
    assert any(item["available"] is False for item in unavailable["process_targets"])
    assert unavailable["requirements"] == matched["requirements"]
    same_id_remap = await client.put(f"{BASE}/expectations/{matched['id']}/process-targets", headers=owner["headers"], json={
        "revision": unavailable["revision"], "targets": [target, {**target, "field_key": "proof_alias"}]})
    assert same_id_remap.status_code == 409, same_id_remap.text
    archived = await checked(await client.patch(f"/api/v1/preparation/cases/{case_id}", headers=owner["headers"],
        json={"expected_revision": retargeted["revision"], "status": "archived"}))
    current = await expectation_current(client, owner, matched)
    still_pinned = next(item for item in current["process_targets"] if item.get("field_key") == "proof_alias")
    assert still_pinned["collection"]["readonly"] is True
    readonly = await client.put(f"/api/v1/preparation/cases/{case_id}/responses/proof_alias", headers=owner["headers"],
        json={"expected_revision": archived["revision"], "evidence_ids": []})
    assert readonly.status_code == 409, readonly.text


async def test_snapshot_retains_original_process_audience_after_all_live_mappings_are_removed(
    client, review_process, documentation_actors, default_jurisdiction
):
    process = review_process
    owner, peer = process["owner"], documentation_actors["peer"]
    register = await create_register(client, owner, default_jurisdiction)
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    row = await create_expectation(client, owner, register)
    await bind_targets(client, owner, row, [process["target"]])
    original_bytes = b"Synthetic canonical process file frozen once"
    evidence = await checked(await client.post("/api/v1/preparation/evidence/upload", headers=owner["headers"],
        data={"title": "Shared process file", "visibility": "organisation"},
        files={"file": ("shared.txt", original_bytes, "text/plain")}), 201)
    await shared_replace(client, owner, process, [evidence["id"]])
    current = await register_current(client, owner, register)
    snapshot = await checked(await client.post(f"{BASE}/registers/{register['id']}/snapshots",
        headers=owner["headers"], json={"revision": current["revision"]}), 201)
    download = f"{BASE}/snapshots/{snapshot['id']}/download"
    await grant(client, owner, "documentation_register", register["id"], peer["user"], ["view", "export"])
    frozen = await client.get(download, headers=peer["headers"])
    assert frozen.status_code == 200, frozen.text
    with zipfile.ZipFile(io.BytesIO(frozen.content)) as archive:
        assert sum(archive.read(name) == original_bytes for name in archive.namelist() if not name.endswith("/")) == 1
    await bind_targets(client, owner, row, [])
    await bind_process(client, owner, register)
    policy_path = f"/api/v1/access/certification_project/{process['project']['id']}"
    policy = await checked(await client.get(policy_path, headers=owner["headers"]))
    await checked(await client.put(policy_path, headers=owner["headers"], json={
        "expected_revision": policy["revision"], "visibility": "secret", "grants": [],
        "reason": "Retain the original process audience after unlinking"}))
    # Register and evidence are still visible. The revoked original process is the
    # only missing permission, and the immutable snapshot must continue to require it.
    assert (await client.get(f"{BASE}/registers/{register['id']}", headers=peer["headers"])).status_code == 200
    assert (await client.get(f"/api/v1/preparation/evidence/{evidence['id']}", headers=peer["headers"])).status_code == 200
    assert (await client.get(download, headers=peer["headers"])).status_code == 404
    assert (await client.get(download, headers=owner["headers"])).content == frozen.content


async def test_register_projects_closed_review_evidence_from_frozen_bytes_without_reopening_decisions(
    client, db_session, review_process, default_jurisdiction
):
    from app.services.preparation_files import checked_evidence_path

    process = review_process
    owner = process["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    row = await create_expectation(client, owner, register)
    row = await bind_targets(client, owner, row, [process["target"]])
    original_bytes = b"Synthetic policy bytes at review closure"
    evidence = await checked(await client.post("/api/v1/preparation/evidence/upload", headers=owner["headers"],
        data={"title": "Policy retained at closure", "visibility": "organisation"},
        files={"file": ("closed.txt", original_bytes, "text/plain")}), 201)
    shared = await shared_replace(client, owner, process, [evidence["id"]])
    item_path = process["shared_path"].removesuffix("/shared-evidence")
    legacy_bytes = b"Independent legacy assessment upload retained by the process snapshot"
    legacy = await checked(await client.post(f"{item_path}/files", headers=owner["headers"],
        files={"file": ("legacy.txt", legacy_bytes, "text/plain")}), 201)
    legacy_record = await db_session.get(ReviewItemEvidenceFile, uuid.UUID(legacy["id"]))
    legacy_path = Path(legacy_record.file_path)
    before_missing = await expectation_current(client, owner, row)
    reviewed = await checked(await client.post(f"{BASE}/expectations/{row['id']}/review", headers=owner["headers"], json={
        "revision": before_missing["revision"], "status": "sufficient",
        "rationale": "Review the valid canonical collection before its native bytes become unavailable"}))
    assert reviewed["effective_coverage_status"] == "sufficient"
    legacy_path.unlink()
    current_row = await expectation_current(client, owner, row)
    unavailable_file = next(item for item in collection(current_row)["items"] if item.get("file_id") == legacy["id"])
    assert "invalid_evidence_file" in unavailable_file["problems"]
    assert current_row["effective_coverage_status"] == "unreviewed"
    assert "invalid_file" in current_row["derived_reasons"]
    blocked = await client.post(f"{BASE}/expectations/{row['id']}/review", headers=owner["headers"], json={
        "revision": current_row["revision"], "status": "sufficient",
        "rationale": "Fresh revision and explicit applicability cannot override unavailable bytes"})
    assert blocked.status_code == 422, blocked.text
    legacy_path.write_bytes(legacy_bytes)
    await checked(await client.put(item_path, headers=owner["headers"], json={
        "review_status": "confirmed", "requirement_status": "evidenced",
        "review_evidence": "Synthetic explicit assessment decision before closure"}))
    await checked(await client.post(f"/api/v1/review-cycles/{process['cycle']['id']}/close", headers=owner["headers"]))
    current_register = await register_current(client, owner, register)
    snapshot = await checked(await client.post(f"{BASE}/registers/{register['id']}/snapshots", headers=owner["headers"],
        json={"revision": current_register["revision"]}), 201)
    snapshot_path = f"{BASE}/snapshots/{snapshot['id']}/download"
    frozen_snapshot = await client.get(snapshot_path, headers=owner["headers"])
    assert frozen_snapshot.status_code == 200, frozen_snapshot.text
    with zipfile.ZipFile(io.BytesIO(frozen_snapshot.content)) as archive:
        contents = [archive.read(name) for name in archive.namelist() if not name.endswith("/")]
        assert contents.count(original_bytes) == 1
        assert contents.count(legacy_bytes) == 1
    stored = await db_session.get(PreparationEvidence, uuid.UUID(evidence["id"]))
    checked_evidence_path(stored).write_bytes(b"Live source bytes changed after closure")
    legacy_path.unlink()
    projected = await expectation_current(client, owner, row)
    frozen = collection(projected)
    assert frozen["readonly"] is True
    entry = next(item for item in frozen["items"] if item.get("evidence_id") == evidence["id"])
    assert (await client.get(f"/api/v1{entry['download_href']}", headers=owner["headers"])).content == original_bytes
    assert (await client.get(snapshot_path, headers=owner["headers"])).content == frozen_snapshot.content
    denied = await client.put(process["shared_path"], headers=owner["headers"], json={
        "expected_evidence_changed_at": shared["evidence_changed_at"], "links": []})
    assert denied.status_code == 409, denied.text
    current = await checked(await client.get(f"/api/v1/review-cycles/{process['cycle']['id']}", headers=owner["headers"]))
    assessed = next(item for item in current["items"] if item["id"] == str(process["item"].id))
    assert assessed["review_status"] == "confirmed"
    assert assessed["requirement_current_status"] == "evidenced"


async def test_documentation_references_block_review_deletion_before_attachment_bytes_are_removed(
    client, db_session, review_process, default_jurisdiction
):
    process = review_process
    owner = process["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    row = await create_expectation(client, owner, register)
    await bind_targets(client, owner, row, [process["target"]])
    original = b"Synthetic assessment attachment retained while documentation refers to it"
    item_path = process["shared_path"].removesuffix("/shared-evidence")
    legacy = await checked(await client.post(f"{item_path}/files", headers=owner["headers"],
        files={"file": ("retained.txt", original, "text/plain")}), 201)
    stored = await db_session.get(ReviewItemEvidenceFile, uuid.UUID(legacy["id"]))
    path = Path(stored.file_path)
    deletion_path = f"/api/v1/review-cycles/{process['cycle']['id']}"
    denied = await client.delete(deletion_path, headers=owner["headers"])
    assert denied.status_code == 409, denied.text
    assert path.read_bytes() == original
    assert (await client.get(deletion_path, headers=owner["headers"])).status_code == 200
    current = await register_current(client, owner, register)
    snapshot = await checked(await client.post(f"{BASE}/registers/{register['id']}/snapshots",
        headers=owner["headers"], json={"revision": current["revision"]}), 201)
    await bind_process(client, owner, register, clear_targets=True)
    retained_history = await client.delete(deletion_path, headers=owner["headers"])
    assert retained_history.status_code == 409, retained_history.text
    assert path.read_bytes() == original
    assert (await client.get(f"{BASE}/snapshots/{snapshot['id']}/download", headers=owner["headers"])).status_code == 200


async def test_retained_standalone_diagnostics_do_not_invalidate_a_current_canonical_review(
    client, review_process, default_jurisdiction
):
    process = review_process
    owner = process["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    expired = await create_evidence(client, owner, valid_until=(date.today() - timedelta(days=1)).isoformat())
    row = await checked(await client.put(f"{BASE}/expectations/{row['id']}/coverage", headers=owner["headers"],
        json={"revision": row["revision"], "links": [{"evidence_id": expired["id"], "rationale": "Historical standalone context"}]}))
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    row = await bind_targets(client, owner, row, [process["target"]])
    current = await create_evidence(client, owner, title="Current canonical oversight record")
    await shared_replace(client, owner, process, [current["id"]])
    row = await expectation_current(client, owner, row)
    reviewed = await checked(await client.post(f"{BASE}/expectations/{row['id']}/review", headers=owner["headers"],
        json={"revision": row["revision"], "status": "sufficient", "rationale": "Explicitly reviewed the current matched collection"}))
    assert reviewed["coverage_status"] == reviewed["effective_coverage_status"] == "sufficient"
    assert reviewed["coverage_warning"] is None
    assert "expired" not in reviewed["derived_reasons"]
    assert reviewed["standalone_coverage_warning"]
    assert reviewed["coverage"][0]["evidence_id"] == expired["id"]
    assert "expired_evidence" in reviewed["coverage"][0]["problems"]


async def test_each_document_selects_its_review_and_register_default_changes_preserve_overrides(
    client, review_process, default_jurisdiction
):
    process = review_process
    owner = process["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    first = await create_expectation(client, owner, register, source_reference="SCP original first cell")
    second = await create_expectation(client, owner, register, source_reference="SCP original second cell")
    for row, cycle in ((first, process["cycle"]), (second, process["other_cycle"])):
        options = await checked(await client.get(f"{BASE}/expectations/{row['id']}/review-options", headers=owner["headers"]))
        assert cycle["id"] in {option["id"] for option in options["items"]}
        selected = await checked(await client.put(f"{BASE}/expectations/{row['id']}/review-process", headers=owner["headers"],
            json={"revision": row["revision"], "review_cycle_id": cycle["id"]}))
        assert selected["review_cycle_id"] == cycle["id"]
        assert selected["process"]["id"] == cycle["id"]
        assert selected["process_inherited"] is False
    wrong_cycle = await client.put(f"{BASE}/expectations/{first['id']}/process-targets", headers=owner["headers"], json={
        "revision": (await expectation_current(client, owner, first))["revision"],
        "targets": [{"review_item_id": str(process["other_item"].id), **process["source_identity"]}]})
    assert wrong_cycle.status_code == 404, wrong_cycle.text
    first = await bind_targets(client, owner, first, [process["target"]])
    second = await bind_targets(client, owner, second, [{"review_item_id": str(process["other_item"].id), **process["source_identity"]}])
    first_evidence = await create_evidence(client, owner, title="First review canonical record")
    second_evidence = await create_evidence(client, owner, title="Second review canonical record")
    await shared_replace(client, owner, process, [first_evidence["id"]])
    other_process = {**process, "shared_path": f"/api/v1/review-cycles/{process['other_cycle']['id']}/items/{process['other_item'].id}/shared-evidence"}
    await shared_replace(client, owner, other_process, [second_evidence["id"]])
    listed = await checked(await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"]))
    mapped = {row["id"]: row for row in listed["items"]}
    assert [entry["evidence_id"] for entry in collection(mapped[first["id"]])["items"]] == [first_evidence["id"]]
    assert [entry["evidence_id"] for entry in collection(mapped[second["id"]])["items"]] == [second_evidence["id"]]
    assert mapped[first["id"]]["source_reference"] == "SCP original first cell"
    assert mapped[second["id"]]["source_reference"] == "SCP original second cell"
    await bind_process(client, owner, register, review_cycle_id=process["cycle"]["id"])
    inherited = await create_expectation(client, owner, register, title="Existing default-compatible document")
    inherited = await bind_targets(client, owner, inherited, [process["target"]])
    await bind_process(client, owner, register, clear_targets=True)
    assert (await expectation_current(client, owner, inherited))["process_targets"] == []
    for row, cycle in ((first, process["cycle"]), (second, process["other_cycle"])):
        current = await expectation_current(client, owner, row)
        assert current["revision"] == row["revision"]
        assert current["process"]["id"] == cycle["id"]
        assert len(current["process_targets"]) == 1
    denied = await client.put(f"{BASE}/expectations/{second['id']}/review-process", headers=owner["headers"], json={
        "revision": second["revision"], "review_cycle_id": process["cycle"]["id"]})
    assert denied.status_code == 409, denied.text
    cleared = await checked(await client.put(f"{BASE}/expectations/{second['id']}/review-process", headers=owner["headers"], json={
        "revision": second["revision"], "review_cycle_id": None, "clear_targets": True}))
    assert cleared["process"] is None
    assert cleared["process_targets"] == []
    assert cleared["requirements"][0]["requirement_id"] == process["source_identity"]["requirement_id"]
    assert [entry["evidence_id"] for entry in (await shared_current(client, owner, other_process))["items"]] == [second_evidence["id"]]


async def test_row_review_selection_rejects_foreign_and_wrong_project_scope_without_mutation(
    client, db_session, review_process, documentation_actors, default_jurisdiction
):
    process = review_process
    owner, foreign = process["owner"], documentation_actors["foreign"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    foreign_document, foreign_version, _ = await make_source(db_session, foreign["user"], default_jurisdiction.id)
    foreign_document.status = "approved"
    foreign_version.status = "approved"
    foreign_version.is_current = True
    await db_session.commit()
    foreign_cycle = await checked(await client.post("/api/v1/review-cycles", headers=foreign["headers"], json={
        "name": "Foreign confidential review", "jurisdiction_id": str(default_jurisdiction.id), "scope": "all"}), 201)
    denied = await client.put(f"{BASE}/expectations/{row['id']}/review-process", headers=owner["headers"], json={
        "revision": row["revision"], "review_cycle_id": foreign_cycle["id"]})
    assert denied.status_code == 404, denied.text
    assert foreign_cycle["name"] not in denied.text
    other_project = await checked(await client.post("/api/v1/certification-projects", headers=owner["headers"], json={
        "name": "Different documentation project", "jurisdiction_id": str(default_jurisdiction.id)}), 201)
    scoped = await create_expectation(client, owner, register, project_id=other_project["id"])
    options = await checked(await client.get(f"{BASE}/expectations/{scoped['id']}/review-options", headers=owner["headers"]))
    assert process["cycle"]["id"] not in {option["id"] for option in options["items"]}
    mismatch = await client.put(f"{BASE}/expectations/{scoped['id']}/review-process", headers=owner["headers"], json={
        "revision": scoped["revision"], "review_cycle_id": process["cycle"]["id"]})
    assert mismatch.status_code == 422, mismatch.text
    for existing in (row, scoped):
        current = await expectation_current(client, owner, existing)
        assert current["revision"] == existing["revision"]
        assert current["review_cycle_id"] is None
        assert current["process_targets"] == []
