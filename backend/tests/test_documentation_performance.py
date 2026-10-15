"""HTTP page boundaries must not scale SQL or file verification with row count."""

# ruff: noqa: F811 - shared fixtures imported from their existing owners
import json
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.models import Requirement, ReviewItem, PreparationCase, PreparationResponse, PreparationResponseEvidence
from app.models.documentation import DocumentationAssessmentEvidence, DocumentationExpectation, DocumentationSection, DocumentationProcessTarget, ExpectationRequirement
from app.services import preparation
from tests.test_documentation_processes import bind_process, checked, review_process, sourced_application  # noqa: F401
from tests.test_documentation_register import BASE, create_register, documentation_actors  # noqa: F401


@contextmanager
def counted_sql(db_session):
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def seed_target(db_session, process, jurisdiction, index, evidence_ids, prefix="PICKER"):
    actor = process["owner"]
    requirement = Requirement(organization_id=actor["user"].organization_id,
        jurisdiction_id=jurisdiction.id, document_id=process["document"].id,
        requirement_set_version_id=process["version"].id, reference_id=f"{prefix}-{index:03}",
        title=f"Synthetic picker target {index}", text="Synthetic requirement", requirement_type="mandatory")
    db_session.add(requirement)
    await db_session.flush()
    item = ReviewItem(review_cycle_id=uuid.UUID(process["cycle"]["id"]), requirement_id=requirement.id,
        review_status="pending", assessment_status="not_started")
    db_session.add(item)
    await db_session.flush()
    db_session.add_all([DocumentationAssessmentEvidence(review_item_id=item.id,
        evidence_id=evidence_id, rationale="Shared across synthetic targets", created_by=actor["user"].id)
        for evidence_id in evidence_ids])
    return requirement, item


async def seed_application_fields(db_session, case, source_field, previous, size, evidence_ids):
    for index in range(previous, size):
        response = PreparationResponse(case_id=case.id, field_key=f"picker_{index}")
        db_session.add(response)
        await db_session.flush()
        db_session.add_all([PreparationResponseEvidence(response_id=response.id, evidence_id=evidence_id)
            for evidence_id in evidence_ids])
    case.fields_json = json.dumps([{**source_field, "key": f"picker_{index}",
        "label": f"Synthetic picker target {index}", "required": False} for index in range(size)])


@pytest.mark.parametrize("mapping_kind", ["standalone", "review", "application"])
async def test_register_page_query_growth_is_bounded_independently_of_returned_rows(
    client, db_session, documentation_actors, default_jurisdiction, review_process, mapping_kind
):
    actor = documentation_actors["owner"]
    register = await create_register(client, actor, default_jurisdiction)
    evidence_ids = []
    case = None
    if mapping_kind != "standalone":
        if mapping_kind == "review":
            await bind_process(client, actor, register, review_cycle_id=review_process["cycle"]["id"])
        else:
            application, case_id = await sourced_application(client, actor, default_jurisdiction, review_process)
            await bind_process(client, actor, register, application_id=application["id"])
            case = await db_session.get(PreparationCase, uuid.UUID(case_id))
            source_field = json.loads(case.fields_json)[0]
        for index in range(3):
            uploaded = await checked(await client.post("/api/v1/preparation/evidence/upload", headers=actor["headers"],
                data={"title": f"Shared mapped file {index}", "visibility": "organisation"},
                files={"file": (f"mapped-{index}.txt", b"Synthetic canonical mapped bytes", "text/plain")}), 201)
            evidence_ids.append(uuid.UUID(uploaded["id"]))
    section = DocumentationSection(register_id=uuid.UUID(register["id"]), name="Synthetic page",
        name_key="synthetic page", position=0, created_by=actor["user"].id)
    db_session.add(section)
    await db_session.commit()
    counts = []
    previous = 0
    for size in (10, 100):
        rows = [DocumentationExpectation(register_id=uuid.UUID(register["id"]),
            section_id=section.id, required_documentation=f"Synthetic required record {index}",
            title=f"Synthetic required record {index}", description="", created_by=actor["user"].id)
            for index in range(previous, size)]
        db_session.add_all(rows)
        await db_session.flush()
        if mapping_kind != "standalone":
            if case is not None:
                await seed_application_fields(db_session, case, source_field, previous, size, evidence_ids)
            for index, row in enumerate(rows, start=previous):
                if case is None:
                    requirement, item = await seed_target(db_session, review_process, default_jurisdiction, index,
                        evidence_ids, prefix="PAGE")
                    identity = {"review_item_id": item.id}
                else:
                    requirement = review_process["requirement"]
                    identity = {"case_id": case.id, "field_key": f"picker_{index}"}
                db_session.add(DocumentationProcessTarget(expectation_id=row.id, **identity,
                    requirement_id=requirement.id, requirement_set_version_id=review_process["version"].id,
                    created_by=actor["user"].id))
                db_session.add(ExpectationRequirement(expectation_id=row.id, requirement_id=requirement.id,
                    requirement_set_version_id=review_process["version"].id))
        await db_session.commit()
        with counted_sql(db_session) as statements:
            response = await client.get(f"{BASE}/registers/{register['id']}/expectations",
                headers=actor["headers"], params={"limit": 100})
        body = await checked(response)
        assert body["total"] == size
        assert len(body["items"]) == size
        assert {item["required_documentation"] for item in body["items"]} == {
            f"Synthetic required record {index}" for index in range(size)}
        assert all(item["section_name"] == section.name for item in body["items"])
        if mapping_kind != "standalone":
            assert all(len(item["process_targets"]) == 1 for item in body["items"])
            assert all({evidence["evidence_id"] for evidence in item["process_targets"][0]["collection"]["items"]} == {
                str(evidence_id) for evidence_id in evidence_ids} for item in body["items"])
        counts.append(len(statements))
        previous = size
    # A generous page budget permits extra batch/ACL queries without permitting
    # even one database round trip for each additional returned row.
    assert counts[1] <= counts[0] + 20, counts
    assert counts[1] <= 80, counts


@pytest.mark.parametrize("kind", ["review", "application"])
async def test_process_picker_reads_metadata_without_verifying_each_shared_file(
    client, db_session, review_process, default_jurisdiction, monkeypatch, kind
):
    process = review_process
    actor = process["owner"]
    register = await create_register(client, actor, default_jurisdiction)
    case = None
    if kind == "review":
        await bind_process(client, actor, register, review_cycle_id=process["cycle"]["id"])
    else:
        application, case_id = await sourced_application(client, actor, default_jurisdiction, process)
        await bind_process(client, actor, register, application_id=application["id"])
        case = await db_session.get(PreparationCase, uuid.UUID(case_id))
        source_field = json.loads(case.fields_json)[0]
    uploaded = await checked(await client.post("/api/v1/preparation/evidence/upload", headers=actor["headers"],
        data={"title": "One shared canonical picker file", "visibility": "organisation"},
        files={"file": ("shared-picker.txt", b"Synthetic shared bytes are needed only when opening the collection", "text/plain")}), 201)
    verify_calls = []
    real_verify = preparation.verify_evidence_file

    def record_verify(item):
        verify_calls.append(item.id)
        return real_verify(item)

    monkeypatch.setattr(preparation, "verify_evidence_file", record_verify)
    counts = []
    previous = 0
    for size in (10, 100):
        if case is None:
            for index in range(previous, size):
                await seed_target(db_session, process, default_jurisdiction, index, [uuid.UUID(uploaded["id"])])
        else:
            await seed_application_fields(db_session, case, source_field, previous, size, [uuid.UUID(uploaded["id"])])
        await db_session.commit()
        with counted_sql(db_session) as statements:
            response = await client.get(f"{BASE}/registers/{register['id']}/process-targets",
                headers=actor["headers"], params={"q": "Synthetic picker target", "limit": 100})
        body = await checked(response)
        assert body["total"] == size
        assert len(body["items"]) == size
        if kind == "review":
            assert {item["reference_id"] for item in body["items"]} == {f"PICKER-{index:03}" for index in range(size)}
        else:
            assert {item["field_key"] for item in body["items"]} == {f"picker_{index}" for index in range(size)}
            assert all(item["requirement_id"] == str(process["requirement"].id) for item in body["items"])
        assert all(item["requirement_set_version_id"] == str(process["version"].id) for item in body["items"])
        assert all("collection" not in item for item in body["items"])
        assert uploaded["id"] not in response.text
        counts.append(len(statements))
        previous = size
    assert verify_calls == [], "Choosing a requirement must not hash document contents"
    assert counts[1] <= counts[0] + 20, counts
    assert counts[1] <= 80, counts


async def test_reconciliation_batches_rows_sharing_a_project_and_evidence_collection(
    client, db_session, review_process, default_jurisdiction, monkeypatch,
):
    actor = review_process["owner"]
    register = await create_register(client, actor, default_jurisdiction)
    await bind_process(client, actor, register, review_cycle_id=review_process["cycle"]["id"])
    uploaded = await checked(await client.post(
        "/api/v1/preparation/evidence/upload", headers=actor["headers"],
        data={"title": "Canonical audit policy", "visibility": "organisation"},
        files={"file": ("audit-policy.txt", b"Synthetic shared audit policy", "text/plain")},
    ), 201)
    requirement, target = await seed_target(
        db_session, review_process, default_jurisdiction, 0, [uuid.UUID(uploaded["id"])],
        prefix="RECONCILIATION",
    )
    verify_calls = []
    real_verify = preparation.verify_evidence_file

    def record_verify(item):
        verify_calls.append(item.id)
        return real_verify(item)

    monkeypatch.setattr(preparation, "verify_evidence_file", record_verify)
    counts = []
    verification_counts = []
    previous = 0
    for size in (10, 100):
        for index in range(previous, size):
            row = DocumentationExpectation(
                register_id=uuid.UUID(register["id"]), project_id=uuid.UUID(review_process["project"]["id"]),
                title=f"Synthetic audit record {index}", description="", applicability="applicable",
                created_by=actor["user"].id,
            )
            db_session.add(row)
            await db_session.flush()
            db_session.add_all([
                DocumentationProcessTarget(
                    expectation_id=row.id, review_item_id=target.id,
                    requirement_id=requirement.id, requirement_set_version_id=review_process["version"].id,
                    created_by=actor["user"].id,
                ),
                ExpectationRequirement(
                    expectation_id=row.id, requirement_id=requirement.id,
                    requirement_set_version_id=review_process["version"].id,
                ),
            ])
        await db_session.commit()
        verify_calls.clear()
        with counted_sql(db_session) as statements:
            response = await client.get(
                f"{BASE}/registers/{register['id']}/reconciliation", headers=actor["headers"],
                params={"project_id": review_process["project"]["id"]},
            )
        body = await checked(response)
        assert {item["title"] for item in body["unreviewed_coverage"]} == {
            f"Synthetic audit record {index}" for index in range(size)
        }
        assert len(body["expectations_absent_from_requests"]) == size
        assert body["missing_evidence"] == []
        assert all(
            item["process_targets"][0]["collection"]["items"][0]["evidence_id"] == uploaded["id"]
            for item in body["unreviewed_coverage"]
        )
        assert set(verify_calls) == {uuid.UUID(uploaded["id"])}
        verification_counts.append(len(verify_calls))
        counts.append(len(statements))
        previous = size
    assert counts[1] <= counts[0] + 20, counts
    assert verification_counts == [1, 1], "Shared evidence is verified once per reconciliation"
