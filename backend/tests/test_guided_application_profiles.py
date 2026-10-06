# ruff: noqa: F811 - imported pytest fixture reused in test signatures
"""Public API contracts for versioned pack guidance and private working forms."""

import io
import zipfile

from tests.test_preparation_api import actors, headers, make_template  # noqa: F401

BASE = "/api/v1/applications"
PREP = "/api/v1/preparation"


async def test_profile_version_is_frozen_and_stale_guided_creation_conflicts(
    client, actors, default_jurisdiction
):
    manager = actors["manager"]
    url = f"{BASE}/market-profile?jurisdiction_id={default_jurisdiction.id}"
    profile = (await client.get(url, headers=headers(manager))).json()
    assert profile["revision"] == 0
    assert profile["status"] == "published"
    assert {item["key"] for item in profile["items"]} >= {
        "dk-2-01",
        "dk-2-02",
        "dk-2-03",
        "dk-2-04",
    }
    payload = {
        "visibility": "secret",
        "name": "Danish licence",
        "scope": "full_pack",
        "jurisdiction_id": str(default_jurisdiction.id),
        "profile_version": profile["version"],
        "setup_answers": {
            "foreign_applicant": True,
            "representative_used": False,
            "people": ["Alex"],
        },
        "items": [
            {
                "name": "Application 2-01",
                "kind": "form",
                "required": True,
                "included": True,
                "profile_item_key": "dk-2-01",
            }
        ],
    }
    created = await client.post(f"{BASE}/guided", headers=headers(manager), json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["profile_snapshot"]["version"] == profile["version"]
    assert created.json()["setup_answers"]["people"] == ["Alex"]
    patched = await client.patch(
        f"{BASE}/market-profile",
        headers=headers(manager),
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "expected_revision": 0,
            **{
                key: profile[key]
                for key in (
                    "status",
                    "label",
                    "authority",
                    "setup_questions",
                    "items",
                    "guidance",
                    "source_urls",
                    "checked_at",
                )
            },
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["version"] != profile["version"]
    stale = await client.post(f"{BASE}/guided", headers=headers(manager), json=payload)
    assert stale.status_code == 409
    read = await client.get(f"{BASE}/{created.json()['id']}", headers=headers(manager))
    assert read.json()["profile_snapshot"]["version"] == profile["version"]


async def test_private_form_duplicate_copies_blank_fields_but_not_answers(
    client, actors, default_jurisdiction
):
    manager = actors["manager"]
    upload = await client.post(
        f"{PREP}/evidence/upload",
        headers=headers(manager),
        data={"visibility": "organisation", "title": "Original signed form"},
        files={"file": ("original.pdf", b"%PDF-source", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    original_evidence_id = upload.json()["id"]
    pack = await client.post(
        BASE,
        headers=headers(manager),
        json={
            "name": "Private pack",
            "scope": "licence",
            "jurisdiction_id": str(default_jurisdiction.id),
        },
    )
    assert pack.status_code == 201, pack.text
    pack = pack.json()
    form = await client.post(
        f"{BASE}/{pack['id']}/components",
        headers=headers(manager),
        json={
            "expected_revision": pack["revision"],
            "name": "My form",
            "kind": "form",
            "form_fields": [
                {
                    "key": "applicant",
                    "label": "Applicant",
                    "section": "Identity",
                    "type": "text",
                    "required": True,
                }
            ],
            "original_evidence_ids": [original_evidence_id],
        },
    )
    assert form.status_code == 201, form.text
    pack = form.json()
    original = pack["components"][0]
    case = (
        await client.get(f"{PREP}/cases/{original['case_id']}", headers=headers(manager))
    ).json()
    assert case["template_id"] is None and not case["readiness"]["ready"]
    assert case["original_evidence_ids"] == [original_evidence_id]
    exported = await client.get(f"{PREP}/cases/{case['id']}/export", headers=headers(manager))
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.read(f"evidence/{original_evidence_id}/original.pdf") == b"%PDF-source"
    answered = await client.put(
        f"{PREP}/cases/{case['id']}/responses/applicant",
        headers=headers(manager),
        json={
            "expected_revision": case["revision"],
            "value": "Company Ltd",
        },
    )
    assert answered.status_code == 200, answered.text
    copied = await client.post(
        f"{BASE}/{pack['id']}/components/{original['id']}/duplicate",
        headers=headers(manager),
        json={"expected_revision": pack["revision"], "name": "Second person"},
    )
    assert copied.status_code == 201, copied.text
    duplicate = next(item for item in copied.json()["components"] if item["id"] != original["id"])
    duplicate_case = (
        await client.get(f"{PREP}/cases/{duplicate['case_id']}", headers=headers(manager))
    ).json()
    assert duplicate_case["responses"] == []
    assert duplicate_case["fields"] == case["fields"]
    assert duplicate_case["original_evidence_ids"] == []
    assert not duplicate_case["readiness"]["ready"]
    stale = await client.patch(
        f"{BASE}/{pack['id']}/components/{original['id']}",
        headers=headers(manager),
        json={
            "expected_revision": copied.json()["revision"],
            "expected_case_revision": case["revision"],
            "form_fields": [{"key": "applicant", "label": "New wording", "type": "text"}],
        },
    )
    assert stale.status_code == 409
    edited = await client.patch(
        f"{PREP}/cases/{case['id']}",
        headers=headers(manager),
        json={
            "expected_revision": answered.json()["revision"],
            "fields": [
                {
                    "key": "applicant",
                    "label": "Applicant name",
                    "section": "Identity",
                    "type": "text",
                    "required": True,
                },
                {
                    "key": "address",
                    "label": "Address",
                    "section": "Identity",
                    "type": "text",
                    "required": True,
                },
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["responses"][0]["value"] == "Company Ltd"
    lost = await client.patch(
        f"{PREP}/cases/{case['id']}",
        headers=headers(manager),
        json={
            "expected_revision": edited.json()["revision"],
            "fields": [],
        },
    )
    assert lost.status_code == 422


async def test_standalone_private_case_uses_its_own_definition(
    client, actors, default_jurisdiction
):
    manager = actors["manager"]
    created = await client.post(
        f"{PREP}/cases",
        headers=headers(manager),
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Working form",
            "fields": [{"key": "question", "label": "Working question", "type": "text"}],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["template_id"] is None
    assert created.json()["fields"][0]["key"] == "question"
    assert created.json()["readiness"]["ready"] is False
    invalid = await client.post(
        f"{PREP}/cases",
        headers=headers(manager),
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Ambiguous form",
            "template_id": str(default_jurisdiction.id),
            "fields": [],
        },
    )
    assert invalid.status_code == 422


async def test_saved_blank_form_can_retain_original_per_case_without_changing_source(
    client, actors, default_jurisdiction
):
    manager = actors["manager"]
    saved = await make_template(client, manager)
    upload = await client.post(
        f"{PREP}/evidence/upload",
        headers=headers(manager),
        data={"visibility": "organisation", "title": "Authority original"},
        files={"file": ("original.pdf", b"%PDF-authority", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    original_id = upload.json()["id"]
    pack = await client.post(
        BASE,
        headers=headers(manager),
        json={
            "name": "Saved blank form pack",
            "scope": "licence",
            "jurisdiction_id": str(default_jurisdiction.id),
        },
    )
    assert pack.status_code == 201, pack.text
    pack = pack.json()
    added = await client.post(
        f"{BASE}/{pack['id']}/components",
        headers=headers(manager),
        json={
            "expected_revision": pack["revision"],
            "name": "Main form",
            "kind": "form",
            "template_id": saved["id"],
            "original_evidence_ids": [original_id],
        },
    )
    assert added.status_code == 201, added.text
    case_id = added.json()["components"][0]["case_id"]
    case = (await client.get(f"{PREP}/cases/{case_id}", headers=headers(manager))).json()
    assert case["template_id"] == saved["id"]
    assert case["original_evidence_ids"] == [original_id]
    templates = (await client.get(f"{PREP}/templates", headers=headers(manager))).json()["items"]
    assert (
        next(item for item in templates if item["id"] == saved["id"])["fields"] == saved["fields"]
    )
    exported = await client.get(f"{PREP}/cases/{case_id}/export", headers=headers(manager))
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.read(f"evidence/{original_id}/original.pdf") == b"%PDF-authority"

    second_upload = await client.post(
        f"{PREP}/evidence/upload",
        headers=headers(manager),
        data={"visibility": "organisation", "title": "Another original"},
        files={"file": ("second.pdf", b"%PDF-second", "application/pdf")},
    )
    assert second_upload.status_code == 201, second_upload.text
    changed = await client.patch(
        f"{BASE}/{pack['id']}/components/{added.json()['components'][0]['id']}",
        headers=headers(manager),
        json={
            "expected_revision": added.json()["revision"],
            "expected_case_revision": case["revision"],
            "original_evidence_ids": [original_id, second_upload.json()["id"]],
        },
    )
    assert changed.status_code == 200, changed.text
    case = (await client.get(f"{PREP}/cases/{case_id}", headers=headers(manager))).json()
    assert set(case["original_evidence_ids"]) == {original_id, second_upload.json()["id"]}

    direct_upload = await client.post(
        f"{PREP}/evidence/upload",
        headers=headers(manager),
        data={"visibility": "organisation", "title": "Project form original"},
        files={"file": ("direct.pdf", b"%PDF-direct", "application/pdf")},
    )
    assert direct_upload.status_code == 201, direct_upload.text
    direct = await client.post(
        f"{PREP}/cases",
        headers=headers(manager),
        json={
            "name": "Direct saved form",
            "jurisdiction_id": str(default_jurisdiction.id),
            "template_id": saved["id"],
            "original_evidence_ids": [direct_upload.json()["id"]],
        },
    )
    assert direct.status_code == 201, direct.text
    assert direct.json()["original_evidence_ids"] == [direct_upload.json()["id"]]
