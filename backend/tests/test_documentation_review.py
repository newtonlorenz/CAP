"""Shared-library review bridge keeps decisions, concurrency and frozen-source access distinct."""
import io
import uuid
import zipfile

from app.models import User
from app.services.auth import create_access_token
from app.services.preparation_files import checked_evidence_path
from app.models.preparation import PreparationEvidence
from tests.test_review_assurance import assessment, finish  # noqa: F401


async def test_shared_review_evidence_preserves_decisions_fences_edits_and_freezes_bytes(
    client, db_session, assessment
):
    owner, cycle, items, headers, _ = assessment
    base = f"/api/v1/review-cycles/{cycle.id}"
    item_path = f"{base}/items/{items[0].id}"
    original_bytes = b"Original assessment upload remains independent"
    original = await client.post(f"{item_path}/files", headers=headers,
        files={"file": ("original.txt", original_bytes, "text/plain")})
    assert original.status_code == 201, original.text
    assessed = await client.put(item_path, headers=headers, json={
        "review_status": "confirmed", "requirement_status": "evidenced",
        "review_evidence": "Assessment rationale remains unchanged."})
    assert assessed.status_code == 200, assessed.text
    shared_bytes = b"Shared policy version one: board oversight"
    uploaded = await client.post("/api/v1/preparation/evidence/upload", headers=headers,
        data={"title": "Shared oversight policy", "visibility": "secret"},
        files={"file": ("policy.txt", shared_bytes, "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    evidence_id = uploaded.json()["id"]
    shared_path = f"{item_path}/shared-evidence"
    before = await client.get(shared_path, headers=headers)
    assert before.status_code == 200, before.text
    changed = await client.put(shared_path, headers=headers, json={
        "expected_evidence_changed_at": before.json()["evidence_changed_at"],
        "links": [{"evidence_id": evidence_id, "locator": "Section 2",
                   "rationale": "Oversight scope is described in this version."}]})
    assert changed.status_code == 200, changed.text
    assert changed.json()["items"][0]["evidence_id"] == evidence_id
    assert changed.json()["evidence_changed_at"] != before.json()["evidence_changed_at"]
    stale = await client.put(shared_path, headers=headers, json={
        "expected_evidence_changed_at": before.json()["evidence_changed_at"], "links": []})
    assert stale.status_code == 409, stale.text
    await db_session.refresh(items[0])
    assert items[0].review_status == "confirmed"
    assert items[0].assessment_status == "evidenced"
    assert items[0].review_evidence == "Assessment rationale remains unchanged."
    original_download = await client.get(f"{item_path}/files/{original.json()['id']}/download", headers=headers)
    assert original_download.content == original_bytes
    assert (await finish(client, assessment)).status_code == 200
    frozen = await client.get(shared_path, headers=headers)
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["items"][0]["evidence_id"] == evidence_id
    evidence = await db_session.get(PreparationEvidence, uuid.UUID(evidence_id))
    checked_evidence_path(evidence).write_bytes(b"Changed live source after review closure")
    report = await client.get("/api/v1/reports/review-package", headers=headers,
                              params={"review_cycle_id": str(cycle.id)})
    assert report.status_code == 200, report.text
    with zipfile.ZipFile(io.BytesIO(report.content)) as archive:
        contents = [archive.read(name) for name in archive.namelist() if not name.endswith("/")]
        assert shared_bytes in contents
        assert original_bytes in contents
    readonly = await client.put(shared_path, headers=headers, json={
        "expected_evidence_changed_at": frozen.json()["evidence_changed_at"], "links": []})
    assert readonly.status_code == 409, readonly.text
    peer = User(email="shared-review-peer@example.test", full_name="Review peer", password_hash="unused",
                role="admin", organization_id=owner.organization_id, active=True)
    db_session.add(peer)
    await db_session.commit()
    peer_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(peer.id)})}"}
    redacted = await client.get(shared_path, headers=peer_headers)
    assert redacted.status_code == 200, redacted.text
    assert redacted.json()["items"] == []
    assert redacted.json()["warning"]
    assert (await client.get("/api/v1/reports/review-package", headers=peer_headers,
                            params={"review_cycle_id": str(cycle.id)})).status_code == 404
