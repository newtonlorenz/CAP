"""Synthetic API contracts for the manual documentation workflow and confidentiality."""

from datetime import date, timedelta

import pytest

from app.models import Organization, User
from app.services.auth import create_access_token

BASE = "/api/v1/documentation"


@pytest.fixture
async def documentation_actors(db_session):
    first = Organization(code="documentation-first", name="Documentation example")
    foreign = Organization(code="documentation-foreign", name="Another example")
    db_session.add_all([first, foreign])
    await db_session.flush()
    actors = {}
    for name, organisation, role in [
        ("owner", first, "manager"), ("peer", first, "admin"),
        ("contributor", first, "contributor"), ("foreign", foreign, "manager"),
    ]:
        user = User(email=f"documentation-{name}@example.test", full_name=name,
                    password_hash="unused", organization_id=organisation.id, role=role, active=True)
        db_session.add(user)
        await db_session.flush()
        actors[name] = {"user": user, "headers": {
            "Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}}
    await db_session.commit()
    return actors


async def create_register(client, actor, jurisdiction, **changes):
    response = await client.post(f"{BASE}/registers", headers=actor["headers"], json={
        "name": "Synthetic documentation", "jurisdiction_id": str(jurisdiction.id), **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


async def create_expectation(client, actor, register, **changes):
    response = await client.post(f"{BASE}/registers/{register['id']}/expectations",
                                headers=actor["headers"], json={
        "title": "Governance evidence", "description": "Describe the governance arrangements and accountable decision maker.",
        "applicability": "applicable", **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


async def create_evidence(client, actor, **changes):
    response = await client.post("/api/v1/preparation/evidence", headers=actor["headers"], json={
        "title": "Synthetic governance policy", "kind": "note",
        "body": "Section 2 records board oversight. Section 3 records escalation.",
        "visibility": "organisation", **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


async def link_evidence(client, actor, expectation, evidence, **changes):
    response = await client.put(f"{BASE}/expectations/{expectation['id']}/coverage",
                               headers=actor["headers"], json={
        "revision": expectation["revision"], "links": [{
            "evidence_id": evidence["id"], "locator": "Section 2", "scope": "Board oversight",
            "period": "Current policy", "rationale": "Records the accountable body", **changes,
        }],
    })
    assert response.status_code == 200, response.text
    return response.json()


async def review(client, actor, expectation, status="sufficient"):
    return await client.post(f"{BASE}/expectations/{expectation['id']}/review",
                             headers=actor["headers"], json={
        "revision": expectation["revision"], "status": status,
        "rationale": "Reviewed the specified scope and current evidence.",
    })


async def test_shared_evidence_keeps_each_expectation_scope_and_decision_independent(
    client, documentation_actors, default_jurisdiction, monkeypatch
):
    from app.config import settings
    monkeypatch.setattr(settings, "jev_enabled", False)
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    first = await create_expectation(client, owner, register, title="Board oversight")
    second = await create_expectation(client, owner, register, title="Escalation arrangements")
    evidence = await create_evidence(client, owner)
    first = await link_evidence(client, owner, first, evidence)
    second = await link_evidence(client, owner, second, evidence,
                                 locator="Section 3", scope="Incident escalation")
    accepted = await review(client, owner, first)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["coverage_status"] == "sufficient"
    rows = await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"])
    by_id = {item["id"]: item for item in rows.json()["items"]}
    assert by_id[second["id"]]["coverage_status"] == "unreviewed"
    assert by_id[first["id"]]["coverage"][0]["scope"] == "Board oversight"
    assert by_id[second["id"]]["coverage"][0]["scope"] == "Incident escalation"
    assert {row["coverage"][0]["evidence_id"] for row in by_id.values()} == {evidence["id"]}
    section = await create_section(client, owner, register, "Governance")
    moved = await client.patch(f"{BASE}/expectations/{first['id']}", headers=owner["headers"],
        json={"revision": accepted.json()["revision"], "section_id": section["id"]})
    assert moved.status_code == 200, moved.text
    assert moved.json()["coverage_status"] == "sufficient"
    updated = await client.patch(f"{BASE}/expectations/{first['id']}", headers=owner["headers"],
                                 json={"revision": moved.json()["revision"], "description": "Changed scope"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["coverage_status"] == "unreviewed"


async def test_private_register_cannot_be_enumerated_or_referenced_by_other_admins(
    client, db_session, documentation_actors, default_jurisdiction, monkeypatch
):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    expectation = await create_expectation(client, owner, register,
        owner_id=str(documentation_actors["peer"]["user"].id))
    for name in ("peer", "foreign"):
        actor = documentation_actors[name]
        listing = await client.get(f"{BASE}/registers", headers=actor["headers"])
        assert listing.status_code == 200, listing.text
        assert listing.json()["total"] == 0
        assert listing.json()["items"] == []
        for path in (f"/registers/{register['id']}",
                     f"/registers/{register['id']}/expectations",
                     f"/registers/{register['id']}/evidence-groups"):
            denied = await client.get(f"{BASE}{path}", headers=actor["headers"])
            assert denied.status_code == 404, denied.text
        mutation = await client.patch(f"{BASE}/expectations/{expectation['id']}",
            headers=actor["headers"], json={"revision": expectation["revision"], "title": "Tampered"})
        assert mutation.status_code == 404, mutation.text
    async def unexpected_provider(*args, **kwargs):
        pytest.fail("Inaccessible documentation must not reach an external provider")
    monkeypatch.setattr("app.services.documentation_suggestions.RemoteParser.complete", unexpected_provider)
    monkeypatch.setattr("app.services.documentation_suggestions.JevClient.evaluate", unexpected_provider)
    current = (await client.get(f"{BASE}/registers/{register['id']}", headers=owner["headers"])).json()
    for name in ("peer", "foreign"):
        other = documentation_actors[name]
        hidden_register = await create_register(client, other, default_jurisdiction, name=f"Confidential {name} register")
        hidden_row = await create_expectation(client, other, hidden_register, title=f"Confidential {name} expectation")
        hidden_evidence = await create_evidence(client, other, title=f"Confidential {name} evidence", visibility="secret")
        for suffix in ("suggestions/preview", "suggestions"):
            body = {"revision": current["revision"], "mode": "ai", "external_processing_confirmed": True,
                    "input_fingerprint": "0" * 64, "expectation_ids": [hidden_row["id"]]}
            denied_row = await client.post(f"{BASE}/registers/{register['id']}/{suffix}", headers=owner["headers"], json=body)
            assert denied_row.status_code == 422, denied_row.text
            assert "Choose accessible expectations" in denied_row.text
            assert hidden_row["title"] not in denied_row.text
            body.update(expectation_ids=[expectation["id"]], evidence_ids=[hidden_evidence["id"]])
            denied_evidence = await client.post(f"{BASE}/registers/{register['id']}/{suffix}", headers=owner["headers"], json=body)
            assert denied_evidence.status_code == 404, denied_evidence.text
            assert hidden_evidence["title"] not in denied_evidence.text
            denied_register = await client.post(f"{BASE}/registers/{hidden_register['id']}/{suffix}", headers=owner["headers"], json=body)
            assert denied_register.status_code == 404, denied_register.text
    documentation_actors["peer"]["user"].active = False
    await db_session.commit()
    still_visible = await client.get(f"{BASE}/expectations/{expectation['id']}", headers=owner["headers"])
    assert still_visible.status_code == 200, still_visible.text
    assert still_visible.json()["owner_id"] == str(documentation_actors["peer"]["user"].id)
    owner_listing = await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"])
    assert owner_listing.json()["total"] == 1


async def test_optimistic_revision_rejects_old_draft_without_overwriting_saved_content(
    client, documentation_actors, default_jurisdiction
):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    first = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"],
        json={"revision": row["revision"], "description": "First committed description"})
    assert first.status_code == 200, first.text
    stale = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"],
        json={"revision": row["revision"], "description": "Old draft must not overwrite"})
    assert stale.status_code == 409, stale.text
    listing = await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"])
    assert listing.json()["items"][0]["description"] == "First committed description"


@pytest.mark.parametrize("applicability", ["unknown", "not_applicable"])
async def test_sufficient_requires_explicit_applicability_and_current_evidence(
    client, documentation_actors, default_jurisdiction, applicability
):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register, applicability=applicability,
                                   not_applicable_reason="Conditional activity is absent" if applicability == "not_applicable" else None)
    evidence = await create_evidence(client, owner)
    row = await link_evidence(client, owner, row, evidence)
    denied = await review(client, owner, row)
    assert denied.status_code in (409, 422), denied.text
    applicable = await create_expectation(client, owner, register, title="Different applicable activity")
    assert applicable["applicability"] == "applicable"
    no_evidence = await review(client, owner, applicable)
    assert no_evidence.status_code in (409, 422), no_evidence.text


async def test_expired_evidence_does_not_satisfy_coverage(client, documentation_actors, default_jurisdiction):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    evidence = await create_evidence(client, owner, valid_until=(date.today() - timedelta(days=1)).isoformat())
    row = await link_evidence(client, owner, row, evidence)
    rejected = await review(client, owner, row)
    assert rejected.status_code in (409, 422), rejected.text
    assert "expir" in rejected.text.lower() or "current" in rejected.text.lower(), rejected.text


async def test_foreign_evidence_is_rejected_before_creating_a_coverage_reference(
    client, documentation_actors, default_jurisdiction
):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    secret = await create_evidence(client, documentation_actors["foreign"], visibility="secret")
    response = await client.put(f"{BASE}/expectations/{row['id']}/coverage", headers=owner["headers"], json={
        "revision": row["revision"], "links": [{"evidence_id": secret["id"], "rationale": "Not accessible"}],
    })
    assert response.status_code == 404, response.text
    listing = await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"])
    assert listing.json()["items"][0]["coverage"] == []


async def test_requirement_links_require_approved_matching_version_and_never_change_compliance(
    client, db_session, documentation_actors, default_jurisdiction
):
    from app.models import Document, Requirement, RequirementStatus
    from sqlalchemy import select
    from app.models.program import RequirementSetVersion

    owner = documentation_actors["owner"]
    user = owner["user"]
    document = Document(organization_id=user.organization_id, jurisdiction_id=default_jurisdiction.id,
        name="Synthetic source", filename="synthetic.pdf", file_path="synthetic.pdf",
        document_type="standard", status="draft", uploaded_by=user.id)
    db_session.add(document)
    await db_session.flush()
    versions = [RequirementSetVersion(organization_id=user.organization_id, document_id=document.id,
        version_number=index, status=status, is_current=status == "approved", created_by=user.id)
        for index, status in [(1, "draft"), (2, "approved")]]
    db_session.add_all(versions)
    await db_session.flush()
    requirements = [Requirement(organization_id=user.organization_id, document_id=document.id,
        jurisdiction_id=default_jurisdiction.id, requirement_set_version_id=version.id,
        reference_id=f"SYN-{index}", title="Governance", text="Record accountable oversight",
        requirement_type="mandatory", sort_order=index)
        for index, version in enumerate(versions)]
    db_session.add_all(requirements)
    await db_session.commit()
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register, source_reference="UNRESOLVED-999")
    assert row["requirements"] == []
    for requirement_id, version_id in [
        (requirements[0].id, versions[0].id),
        (requirements[1].id, versions[0].id),
    ]:
        denied = await client.put(f"{BASE}/expectations/{row['id']}/requirements", headers=owner["headers"],
            json={"revision": row["revision"], "links": [{"requirement_id": str(requirement_id),
                "requirement_set_version_id": str(version_id)}]})
        assert denied.status_code in (409, 422), denied.text
    linked = await client.put(f"{BASE}/expectations/{row['id']}/requirements", headers=owner["headers"],
        json={"revision": row["revision"], "links": [{"requirement_id": str(requirements[1].id),
            "requirement_set_version_id": str(versions[1].id)}]})
    assert linked.status_code == 200, linked.text
    assert linked.json()["requirements"][0]["requirement_id"] == str(requirements[1].id)
    evidence = await create_evidence(client, owner)
    linked_row = await link_evidence(client, owner, linked.json(), evidence)
    decision = await review(client, owner, linked_row)
    assert decision.status_code == 200, decision.text
    compliance_events = (await db_session.scalars(select(RequirementStatus).where(
        RequirementStatus.requirement_id == requirements[1].id))).all()
    assert compliance_events == []


async def test_editor_cannot_silently_remove_hidden_shared_evidence_associations(
    client, documentation_actors, default_jurisdiction
):
    owner, peer = documentation_actors["owner"], documentation_actors["peer"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    evidence = await create_evidence(client, owner, visibility="secret")
    row = await link_evidence(client, owner, row, evidence)
    access_path = f"/api/v1/access/documentation_register/{register['id']}"
    granted = await client.put(access_path, headers=owner["headers"], json={
        "expected_revision": 1, "visibility": "secret", "grants": [{"subject_type": "user",
            "subject_id": str(peer["user"].id), "permissions": ["view", "edit"]}],
        "reason": "Edit expectation wording; source evidence remains confidential"})
    assert granted.status_code == 200, granted.text
    readable = await client.get(f"{BASE}/expectations/{row['id']}", headers=peer["headers"])
    assert readable.status_code == 200, readable.text
    assert evidence["id"] not in readable.text
    replacement = await client.put(f"{BASE}/expectations/{row['id']}/coverage", headers=peer["headers"],
        json={"revision": row["revision"], "links": []})
    assert replacement.status_code in (403, 404, 409), replacement.text
    owner_read = await client.get(f"{BASE}/expectations/{row['id']}", headers=owner["headers"])
    assert owner_read.json()["coverage"][0]["evidence_id"] == evidence["id"]


async def test_reconciliation_reports_both_unmatched_requests_and_unrequested_expectations_in_project_scope(
    client, documentation_actors, default_jurisdiction
):
    owner = documentation_actors["owner"]
    project = await client.post("/api/v1/certification-projects", headers=owner["headers"], json={
        "name": "Synthetic audit project", "jurisdiction_id": str(default_jurisdiction.id), "visibility": "secret"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    template = await client.post("/api/v1/preparation/templates", headers=owner["headers"], json={
        "name": "Synthetic auditor list", "kind": "audit", "fields": [
            {"key": "requested_policy", "label": "Provide the oversight policy", "type": "evidence"},
            {"key": "auditor_report", "label": "Auditor report to be received", "type": "evidence"}]})
    assert template.status_code == 201, template.text
    case = await client.post("/api/v1/preparation/cases", headers=owner["headers"], json={
        "name": "Synthetic request list", "template_id": template.json()["id"],
        "jurisdiction_id": str(default_jurisdiction.id), "project_id": project_id})
    assert case.status_code == 201, case.text
    register = await create_register(client, owner, default_jurisdiction)
    expected = await create_expectation(client, owner, register, project_id=project_id)
    omitted = await create_expectation(client, owner, register, title="Additional required record", project_id=project_id)
    evidence = await create_evidence(client, owner)
    expected = await link_evidence(client, owner, expected, evidence)
    for field, direction, ids in [
        ("requested_policy", "operator_input", [expected["id"]]),
        ("auditor_report", "auditor_output", []),
    ]:
        mapped = await client.post(f"{BASE}/registers/{register['id']}/auditor-requests", headers=owner["headers"], json={
            "case_id": case.json()["id"], "field_key": field, "project_id": project_id,
            "request_id": field, "request_wording": "Synthetic request wording", "list_revision": "v2",
            "direction": direction, "expectation_ids": ids, "evidence_ids": [evidence["id"]] if ids else []})
        assert mapped.status_code == 201, mapped.text
    response = await client.get(f"{BASE}/registers/{register['id']}/reconciliation", headers=owner["headers"],
        params={"project_id": project_id, "list_revision": "v2"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert {row["request_id"] for row in result["requests_without_matches"]} == {"auditor_report"}
    assert {row["id"] for row in result["expectations_absent_from_requests"]} == {omitted["id"]}
    assert {row["id"] for row in result["missing_evidence"]} == {omitted["id"]}
    assert result["requests_without_matches"][0]["direction"] == "auditor_output"
    assert "not compliance decisions" in result["notice"]
    for name in ("peer", "foreign"):
        denied = await client.get(f"{BASE}/registers/{register['id']}/reconciliation",
            headers=documentation_actors[name]["headers"], params={"project_id": project_id})
        assert denied.status_code == 404, denied.text


async def create_section(client, actor, register, name):
    current = await client.get(f"{BASE}/registers/{register['id']}", headers=actor["headers"])
    assert current.status_code == 200, current.text
    response = await client.post(f"{BASE}/registers/{register['id']}/sections", headers=actor["headers"],
        json={"revision": current.json()["revision"], "name": name})
    assert response.status_code == 201, response.text
    return response.json()


async def test_named_empty_sections_persist_rename_with_revision_and_inherit_register_access(
    client, documentation_actors, default_jurisdiction
):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    section = await create_section(client, owner, register, "Supplier records")
    listed = await client.get(f"{BASE}/registers/{register['id']}/sections", headers=owner["headers"])
    assert listed.status_code == 200, listed.text
    assert [(row["id"], row["name"]) for row in listed.json()["items"]] == [(section["id"], "Supplier records")]
    assert (await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"])).json()["total"] == 0
    renamed = await client.patch(f"{BASE}/sections/{section['id']}", headers=owner["headers"], json={
        "revision": listed.json()["revision"], "name": "Supplier policies"})
    assert renamed.status_code == 200, renamed.text
    stale = await client.patch(f"{BASE}/sections/{section['id']}", headers=owner["headers"], json={
        "revision": listed.json()["revision"], "name": "Stale replacement"})
    assert stale.status_code == 409, stale.text
    for name in ("peer", "foreign"):
        actor = documentation_actors[name]
        denied = await client.get(f"{BASE}/registers/{register['id']}/sections", headers=actor["headers"])
        assert denied.status_code == 404, denied.text
        denied = await client.patch(f"{BASE}/sections/{section['id']}", headers=actor["headers"], json={
            "revision": renamed.json()["register_revision"], "name": "Hidden replacement"})
        assert denied.status_code == 404, denied.text
    final = await client.get(f"{BASE}/registers/{register['id']}/sections", headers=owner["headers"])
    assert [(row["id"], row["name"]) for row in final.json()["items"]] == [(section["id"], "Supplier policies")]
    duplicate = await client.post(f"{BASE}/registers/{register['id']}/sections", headers=owner["headers"],
        json={"revision": final.json()["revision"], "name": "SUPPLIER POLICIES"})
    assert duplicate.status_code == 409, duplicate.text


async def test_four_field_rows_keep_long_required_text_empty_comments_and_validate_section_parent(
    client, documentation_actors, default_jurisdiction
):
    owner = documentation_actors["owner"]
    register = await create_register(client, owner, default_jurisdiction)
    section = await create_section(client, owner, register, "Policies")
    required = "  Original required documentation — α\n" + "Retain accountable oversight records. " * 40 + "\nEnd of original text.  "
    document_name = "  Supplier governance policy – draft version\nSecond document line  "
    created = await client.post(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"], json={
        "section_id": section["id"], "required_documentation": required, "source_reference": "SCP 4.2",
        "description": "", "document_name": document_name})
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["required_documentation"] == required
    assert row["description"] == ""
    assert row["document_name"] == document_name
    assert row["source_reference"] == "SCP 4.2"
    assert row["section_id"] == section["id"]
    other_register = await create_register(client, owner, default_jurisdiction, name="Other permitted register")
    other_section = await create_section(client, owner, other_register, "Other policies")
    mismatch = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"], json={
        "revision": row["revision"], "section_id": other_section["id"]})
    assert mismatch.status_code == 404, mismatch.text
    foreign = documentation_actors["foreign"]
    foreign_register = await create_register(client, foreign, default_jurisdiction)
    foreign_section = await create_section(client, foreign, foreign_register, "Confidential foreign section")
    denied = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"], json={
        "revision": row["revision"], "section_id": foreign_section["id"]})
    assert denied.status_code in (404, 422), denied.text
    assert "Confidential foreign section" not in denied.text
    other_local_section = await create_section(client, owner, register, "Records")
    await create_expectation(client, owner, register, section_id=other_local_section["id"], title="Unrelated record")
    another_policy = await create_expectation(client, owner, register, section_id=section["id"], title="Another policy")
    paged = await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"],
        params={"section_id": section["id"], "limit": 1})
    assert paged.status_code == 200, paged.text
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1
    assert paged.json()["items"][0]["id"] in {row["id"], another_policy["id"]}
    scoped = await client.get(f"{BASE}/registers/{register['id']}/expectations", headers=owner["headers"],
                              params={"section_id": section["id"]})
    assert scoped.status_code == 200, scoped.text
    assert {item["id"] for item in scoped.json()["items"]} == {row["id"], another_policy["id"]}
    original = next(item for item in scoped.json()["items"] if item["id"] == row["id"])
    assert original["required_documentation"] == required
    assert original["description"] == ""
    assert original["document_name"] == document_name


async def test_owner_assignment_changes_preserve_review_and_reject_invalid_or_readonly_writes(
    client, db_session, documentation_actors, default_jurisdiction
):
    owner, peer = documentation_actors["owner"], documentation_actors["peer"]
    register = await create_register(client, owner, default_jurisdiction)
    row = await create_expectation(client, owner, register)
    evidence = await create_evidence(client, owner)
    row = await link_evidence(client, owner, row, evidence)
    accepted = await review(client, owner, row)
    assert accepted.status_code == 200, accepted.text
    row = accepted.json()
    section = await create_section(client, owner, register, "Responsible team")
    reviewed = {key: row[key] for key in ("coverage_status", "review_rationale", "reviewed_by", "reviewed_at")}
    links = row["coverage"]
    assignments = [str(peer["user"].id), str(documentation_actors["contributor"]["user"].id), None]
    for selected in assignments:
        saved = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"], json={
            "revision": row["revision"], "owner_id": selected, "section_id": section["id"]})
        assert saved.status_code == 200, saved.text
        row = saved.json()
        assert row["owner_id"] == selected
        assert {key: row[key] for key in reviewed} == reviewed
        assert row["effective_coverage_status"] == "sufficient"
        assert row["coverage"] == links
    documentation_actors["contributor"]["user"].active = False
    await db_session.commit()
    for invalid in (documentation_actors["foreign"]["user"], documentation_actors["contributor"]["user"]):
        denied = await client.patch(f"{BASE}/expectations/{row['id']}", headers=owner["headers"], json={
            "revision": row["revision"], "owner_id": str(invalid.id)})
        assert denied.status_code == 404, denied.text
    policy_path = f"/api/v1/access/documentation_register/{register['id']}"
    policy = (await client.get(policy_path, headers=owner["headers"])).json()
    granted = await client.put(policy_path, headers=owner["headers"], json={
        "expected_revision": policy["revision"], "visibility": "secret", "reason": "Read-only assignment observer",
        "grants": [{"subject_type": "user", "subject_id": str(peer["user"].id), "permissions": ["view"]}]})
    assert granted.status_code == 200, granted.text
    denied = await client.patch(f"{BASE}/expectations/{row['id']}", headers=peer["headers"], json={
        "revision": row["revision"], "owner_id": str(peer["user"].id)})
    assert denied.status_code == 404, denied.text
    current = (await client.get(f"{BASE}/expectations/{row['id']}", headers=owner["headers"])).json()
    assert current["revision"] == row["revision"]
    assert current["owner_id"] is None
    assert current["coverage"] == links
    assert {key: current[key] for key in reviewed} == reviewed
