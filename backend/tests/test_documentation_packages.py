"""Typed handovers retain their project, immutable source and original audience."""
from tests.test_documentation_register import (  # noqa: F401
    BASE, documentation_actors, create_register, create_expectation,
)


async def test_package_snapshot_keeps_immutable_source_and_filters_confidential_artifacts(
    client, documentation_actors, default_jurisdiction
):
    owner = documentation_actors["owner"]
    project = await client.post("/api/v1/certification-projects", headers=owner["headers"], json={
        "name": "Synthetic handover project", "jurisdiction_id": str(default_jurisdiction.id)})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    package = await client.post("/api/v1/submission-packages", headers=owner["headers"], json={
        "project_id": project_id, "version": "synthetic-v1"})
    assert package.status_code == 201, package.text
    package_id = package.json()["id"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register, project_id=project_id)
    current = await client.get(f"{BASE}/registers/{register['id']}", headers=owner["headers"])
    snapshot = await client.post(f"{BASE}/registers/{register['id']}/snapshots", headers=owner["headers"],
        json={"revision": current.json()["revision"], "project_id": project_id})
    assert snapshot.status_code == 201, snapshot.text
    attach_path = f"{BASE}/snapshots/{snapshot.json()['id']}/packages/{package_id}"
    attached = await client.post(attach_path, headers=owner["headers"], json={})
    assert attached.status_code == 201, attached.text
    artifact = attached.json()
    assert artifact["documentation_snapshot_id"] == snapshot.json()["id"]
    assert artifact["artifact_type"] == "documentation_register_snapshot"
    assert (await client.post(attach_path, headers=owner["headers"], json={})).status_code == 409
    download_path = f"{BASE}/package-artifacts/{artifact['id']}/download"
    before = await client.get(download_path, headers=owner["headers"])
    assert before.status_code == 200, before.text
    changed = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"],
        json={"revision": row["revision"], "title": "Later source title"})
    assert changed.status_code == 200, changed.text
    assert (await client.get(download_path, headers=owner["headers"])).content == before.content
    replacement = await client.patch(f"/api/v1/submission-packages/{package_id}/artifacts/{artifact['id']}",
        headers=owner["headers"], json={"link_url": "https://example.test/replacement"})
    assert replacement.status_code in (409, 422), replacement.text
    listing_path = f"/api/v1/submission-packages/{package_id}/artifacts"
    own_listing = await client.get(listing_path, headers=owner["headers"])
    assert own_listing.json()["total"] == 1
    # The project remains organisation-visible, while the register source is secret.
    peer = documentation_actors["peer"]
    hidden = await client.get(listing_path, headers=peer["headers"])
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["items"] == []
    assert hidden.json()["total"] == 0
    assert (await client.get(download_path, headers=peer["headers"])).status_code == 404
    artifact_path = f"/api/v1/submission-packages/{package_id}/artifacts/{artifact['id']}"
    excluded = await client.patch(artifact_path, headers=owner["headers"], json={"included": False})
    assert excluded.status_code == 200, excluded.text
    manifest = await client.post(f"/api/v1/submission-packages/{package_id}/bundle-manifest", headers=peer["headers"])
    if manifest.status_code not in (403, 404):
        assert manifest.status_code == 201, manifest.text
        for confidential in (artifact["name"], artifact["documentation_snapshot_id"], artifact["link_url"]):
            assert confidential not in manifest.text, "Excluded confidential artifact metadata leaked through bundle manifest"
    for body in ({}, {"included": True}):
        hidden_patch = await client.patch(artifact_path, headers=peer["headers"], json=body)
        assert hidden_patch.status_code in (403, 404), "Project edit permission exposed or changed an inaccessible source artifact"
    retained = await client.get(listing_path, headers=owner["headers"])
    assert retained.json()["items"][0]["included"] is False
    other_project = await client.post("/api/v1/certification-projects", headers=owner["headers"], json={
        "name": "Another synthetic handover project", "jurisdiction_id": str(default_jurisdiction.id)})
    assert other_project.status_code == 201, other_project.text
    other_package = await client.post("/api/v1/submission-packages", headers=owner["headers"], json={
        "project_id": other_project.json()["id"], "version": "other-v1"})
    assert other_package.status_code == 201, other_package.text
    wrong_project = await client.post(f"{BASE}/snapshots/{snapshot.json()['id']}/packages/{other_package.json()['id']}",
        headers=owner["headers"], json={})
    assert wrong_project.status_code == 422, wrong_project.text
