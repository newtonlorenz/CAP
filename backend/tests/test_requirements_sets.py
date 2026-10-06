import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, select

from app.models import (
    CertificationProject,
    Document,
    EvidenceFile,
    ExtractedRequirement,
    ExtractionFeedback,
    ExtractionRun,
    ExtractionRunDiagnostic,
    Requirement,
    RequirementStatus,
    ReviewCycle,
    ReviewItem,
    ReviewItemComment,
    ReviewItemEvidenceFile,
    User,
)
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def admin_user(db_session):
    user = User(
        email="reqsets@example.com",
        password_hash=hash_password("testpass"),
        full_name="Req Sets Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def contributor_user(db_session):
    user = User(
        email="reqsets-contrib@example.com",
        password_hash=hash_password("testpass"),
        full_name="Req Sets Contributor",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def contributor_headers(contributor_user):
    token = create_access_token({"sub": str(contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def seeded_sets(db_session, admin_user, default_jurisdiction):
    # 1) Active set
    doc_active = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="active.pdf",
        name="Active Doc",
        document_type="policy",
        status="approved",
        file_path="/tmp/active.pdf",
        uploaded_by=admin_user.id,
    )
    db_session.add(doc_active)

    # 2) Archived set (requirements exist but all inactive)
    doc_archived_set = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="archived-set.pdf",
        name="Archived Set Doc",
        document_type="policy",
        status="approved",
        file_path="/tmp/archived-set.pdf",
        uploaded_by=admin_user.id,
    )
    db_session.add(doc_archived_set)

    # 3) Empty doc (0 requirements)
    doc_empty = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="empty.pdf",
        name="Empty Doc",
        document_type="policy",
        status="approved",
        file_path="/tmp/empty.pdf",
        uploaded_by=admin_user.id,
    )
    db_session.add(doc_empty)

    # 4) Archived document (should be excluded when include_archived_documents=false)
    doc_archived_document = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="archived-doc.pdf",
        name="Archived Document",
        document_type="policy",
        status="archived",
        file_path="/tmp/archived-doc.pdf",
        uploaded_by=admin_user.id,
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add(doc_archived_document)

    await db_session.commit()
    await db_session.refresh(doc_active)
    await db_session.refresh(doc_archived_set)
    await db_session.refresh(doc_empty)
    await db_session.refresh(doc_archived_document)

    # Requirements
    def add_req(doc_id: uuid.UUID, ref: str, active: bool):
        db_session.add(
            Requirement(
                jurisdiction_id=default_jurisdiction.id,
                document_id=doc_id,
                reference_id=ref,
                text="x",
                requirement_type="mandatory",
                active=active,
                version=1,
                sort_order=0,
            )
        )

    add_req(doc_active.id, "1", True)
    add_req(doc_active.id, "1.1", True)
    add_req(doc_archived_set.id, "2", False)
    add_req(doc_archived_set.id, "2.1", False)
    add_req(doc_archived_document.id, "3", True)

    await db_session.commit()

    return {
        "active": doc_active,
        "archived_set": doc_archived_set,
        "empty": doc_empty,
        "archived_document": doc_archived_document,
    }


async def test_sets_default_hides_empty_and_archived_sets(client, auth_headers, seeded_sets):
    resp = await client.get(
        "/api/v1/requirements/sets?limit=1000&include_archived_documents=false",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["document_id"] for item in data["items"]}
    assert ids == {str(seeded_sets["active"].id)}
    assert data["total"] == 1


async def test_legacy_delete_by_document_preserves_approved_set(
    client, auth_headers, seeded_sets, db_session,
):
    document = seeded_sets["active"]
    before = (await db_session.execute(
        select(Requirement.id).where(Requirement.document_id == document.id)
    )).scalars().all()
    response = await client.delete(
        f"/api/v1/requirements/by-document/{document.id}", headers=auth_headers
    )
    assert response.status_code == 409
    after = (await db_session.execute(
        select(Requirement.id).where(Requirement.document_id == document.id)
    )).scalars().all()
    assert set(after) == set(before)


async def test_legacy_delete_preserves_published_version_even_if_document_is_draft(
    client, auth_headers, seeded_sets, db_session, admin_user,
):
    from app.models.program import RequirementSetVersion

    document = seeded_sets["active"]
    document.status = "draft"
    db_session.add(RequirementSetVersion(
        document_id=document.id, version_number=1, status="approved",
        is_current=True, created_by=admin_user.id,
    ))
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/requirements/by-document/{document.id}", headers=auth_headers
    )
    assert response.status_code == 409
    assert (await db_session.execute(
        select(Requirement.id).where(Requirement.document_id == document.id)
    )).scalars().all()


async def test_sets_include_empty_sets(client, auth_headers, seeded_sets):
    resp = await client.get(
        "/api/v1/requirements/sets?limit=1000&include_archived_documents=false&include_empty_sets=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["document_id"] for item in data["items"]}
    assert ids == {str(seeded_sets["active"].id), str(seeded_sets["empty"].id)}
    assert data["total"] == 2


async def test_sets_include_archived_sets(client, auth_headers, seeded_sets):
    resp = await client.get(
        "/api/v1/requirements/sets?limit=1000&include_archived_documents=false&include_archived_sets=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["document_id"] for item in data["items"]}
    assert ids == {str(seeded_sets["active"].id), str(seeded_sets["archived_set"].id)}
    assert data["total"] == 2


async def test_sets_include_both(client, auth_headers, seeded_sets):
    resp = await client.get(
        "/api/v1/requirements/sets?limit=1000&include_archived_documents=false&include_empty_sets=true&include_archived_sets=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["document_id"] for item in data["items"]}
    assert ids == {
        str(seeded_sets["active"].id),
        str(seeded_sets["archived_set"].id),
        str(seeded_sets["empty"].id),
    }
    assert data["total"] == 3


async def test_sets_include_archived_documents(client, auth_headers, seeded_sets):
    resp = await client.get(
        "/api/v1/requirements/sets?limit=1000&include_archived_documents=true&include_empty_sets=true&include_archived_sets=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["document_id"] for item in data["items"]}
    assert ids == {
        str(seeded_sets["active"].id),
        str(seeded_sets["archived_set"].id),
        str(seeded_sets["empty"].id),
        str(seeded_sets["archived_document"].id),
    }
    assert data["total"] == 4


async def test_hard_delete_empty_manual_set(client, auth_headers, db_session, default_jurisdiction):
    resp = await client.post(
        "/api/v1/requirements/sets",
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Empty Manual Set",
            "document_type": "annex_b",
            "testing_frequency": "one_off",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    set_id = uuid.UUID(resp.json()["id"])

    doc_result = await db_session.execute(select(Document).where(Document.id == set_id))
    doc = doc_result.scalar_one()
    assert doc.filename is None
    assert doc.file_path is None

    del_resp = await client.delete(f"/api/v1/requirements/sets/{set_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    doc_result = await db_session.execute(select(Document).where(Document.id == set_id))
    assert doc_result.scalar_one_or_none() is None


async def test_hard_delete_uploaded_set_with_no_requirements(
    client, auth_headers, db_session, admin_user, default_jurisdiction, tmp_path
):
    file_path = tmp_path / "uploaded.pdf"
    file_path.write_bytes(b"not-a-real-pdf")

    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="uploaded.pdf",
        name="Uploaded Set",
        document_type="annex_b",
        status="uploaded",
        file_path=str(file_path),
        uploaded_by=admin_user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    del_resp = await client.delete(f"/api/v1/requirements/sets/{doc.id}", headers=auth_headers)
    assert del_resp.status_code == 204

    doc_result = await db_session.execute(select(Document).where(Document.id == doc.id))
    assert doc_result.scalar_one_or_none() is None
    assert not file_path.exists()


async def test_hard_delete_set_with_extraction_feedback_and_diagnostics(
    client, auth_headers, db_session, admin_user, default_jurisdiction, setup_database, tmp_path
):
    # The normal SQLite test connection does not enforce foreign keys by default.
    # Match PostgreSQL's behaviour for the delete request.
    engine = setup_database.kw["bind"]

    def enable_foreign_keys(dbapi_connection, _connection_record, _connection_proxy):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine.sync_engine, "checkout", enable_foreign_keys)

    file_path = tmp_path / "source.pdf"
    file_path.write_bytes(b"source")
    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="source.pdf",
        name="Extracted Set",
        document_type="annex_b",
        status="extracted",
        file_path=str(file_path),
        uploaded_by=admin_user.id,
    )
    db_session.add(doc)
    await db_session.flush()
    run = ExtractionRun(
        document_id=doc.id, status="completed", ai_provider="none", ai_model="test"
    )
    db_session.add(run)
    await db_session.flush()
    doc.current_extraction_id = run.id
    extracted = ExtractedRequirement(
        document_id=doc.id,
        extraction_run_id=run.id,
        reference_id="1",
        text="Requirement",
        original_text="Requirement",
        page_number=1,
    )
    db_session.add(extracted)
    await db_session.flush()
    db_session.add_all([
        ExtractionFeedback(
            extraction_run_id=run.id,
            extracted_requirement_id=extracted.id,
            action="accept",
            created_by=admin_user.id,
        ),
        ExtractionRunDiagnostic(extraction_run_id=run.id, document_id=doc.id),
    ])
    await db_session.commit()
    document_id, run_id = doc.id, run.id

    response = await client.delete(f"/api/v1/requirements/sets/{document_id}", headers=auth_headers)
    assert response.status_code == 204
    db_session.expire_all()
    assert await db_session.get(Document, document_id) is None
    assert await db_session.get(ExtractionRun, run_id) is None
    assert (await db_session.execute(select(ExtractionFeedback))).scalars().first() is None
    assert (await db_session.execute(select(ExtractionRunDiagnostic))).scalars().first() is None
    assert not file_path.exists()


async def test_hard_delete_keeps_source_file_when_database_work_fails(
    client, auth_headers, db_session, admin_user, default_jurisdiction, monkeypatch, tmp_path
):
    file_path = tmp_path / "source.pdf"
    file_path.write_bytes(b"source")
    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="source.pdf",
        name="Failing Set",
        document_type="annex_b",
        status="uploaded",
        file_path=str(file_path),
        uploaded_by=admin_user.id,
    )
    db_session.add(doc)
    await db_session.commit()

    async def fail_audit(*_args, **_kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr("app.api.requirements.log_action", fail_audit)
    with pytest.raises(RuntimeError, match="simulated database failure"):
        await client.delete(f"/api/v1/requirements/sets/{doc.id}", headers=auth_headers)

    assert file_path.exists()
    assert await db_session.get(Document, doc.id) is not None


async def test_hard_delete_preserves_source_document_for_certification_projects(
    client, auth_headers, db_session, admin_user, default_jurisdiction, tmp_path
):
    file_path = tmp_path / "source-for-project.pdf"
    file_path.write_bytes(b"source")

    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="source-for-project.pdf",
        name="Source For Project",
        document_type="annex_a",
        status="approved",
        file_path=str(file_path),
        uploaded_by=admin_user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    project = CertificationProject(
        jurisdiction_id=default_jurisdiction.id,
        source_document_id=doc.id,
        name="Certification Project",
        stage="intake",
        status="active",
        created_by=admin_user.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    del_resp = await client.delete(f"/api/v1/requirements/sets/{doc.id}", headers=auth_headers)
    assert del_resp.status_code == 409

    doc_result = await db_session.execute(select(Document).where(Document.id == doc.id))
    assert doc_result.scalar_one_or_none() is not None

    project_result = await db_session.execute(
        select(CertificationProject).where(CertificationProject.id == project.id)
    )
    project_after_delete = project_result.scalar_one_or_none()
    assert project_after_delete is not None
    # API requests run in a separate session; refresh to observe committed DB state.
    await db_session.refresh(project_after_delete)
    assert project_after_delete.source_document_id == doc.id
    assert file_path.exists()


async def test_hard_delete_rejects_sets_used_in_reviews(
    client, auth_headers, db_session, admin_user, default_jurisdiction, tmp_path
):
    doc_file_path = tmp_path / "source.pdf"
    doc_file_path.write_bytes(b"source")

    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="source.pdf",
        name="Hard Delete Set",
        document_type="annex_b",
        status="approved",
        file_path=str(doc_file_path),
        uploaded_by=admin_user.id,
        testing_frequency="one_off",
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    # Extraction artifacts (and current_extraction_id FK) should be removed.
    run = ExtractionRun(
        document_id=doc.id,
        status="pending",
        ai_provider="none",
        ai_model="test",
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    doc.current_extraction_id = run.id
    extracted = ExtractedRequirement(
        document_id=doc.id,
        extraction_run_id=run.id,
        reference_id="X-1",
        title="X",
        text="x",
        original_text="x",
        requirement_type="mandatory",
        parent_id=None,
        page_number=1,
        confidence_score=1.0,
        status="pending",
        sort_order=0,
    )
    db_session.add(extracted)

    req = Requirement(
        jurisdiction_id=default_jurisdiction.id,
        document_id=doc.id,
        reference_id="R-1",
        text="Requirement",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)

    db_session.add(
        RequirementStatus(
            requirement_id=req.id,
            status="not_started",
            comment="seed",
            changed_by=admin_user.id,
        )
    )

    evidence_file_path = tmp_path / "evidence.txt"
    evidence_file_path.write_text("evidence")
    db_session.add(
        EvidenceFile(
            requirement_id=req.id,
            filename="evidence.txt",
            file_path=str(evidence_file_path),
            description=None,
            uploaded_by=admin_user.id,
        )
    )

    cycle = ReviewCycle(
        jurisdiction_id=default_jurisdiction.id,
        name="Cycle",
        scope="documents",
        scope_filter=f'["{doc.id}"]',
        status="active",
        created_by=admin_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(review_cycle_id=cycle.id, requirement_id=req.id, review_status="pending")
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    db_session.add(
        ReviewItemComment(
            review_item_id=item.id,
            author_id=admin_user.id,
            body="comment",
        )
    )

    review_item_file_path = tmp_path / "review-item.txt"
    review_item_file_path.write_text("review-item")
    db_session.add(
        ReviewItemEvidenceFile(
            review_item_id=item.id,
            filename="review-item.txt",
            file_path=str(review_item_file_path),
            description=None,
            uploaded_by=admin_user.id,
        )
    )

    await db_session.commit()

    assert doc_file_path.exists()
    assert evidence_file_path.exists()
    assert review_item_file_path.exists()

    del_resp = await client.delete(f"/api/v1/requirements/sets/{doc.id}", headers=auth_headers)
    assert del_resp.status_code == 409

    # All source, review and evidence records must be retained.
    assert doc_file_path.exists()
    assert evidence_file_path.exists()
    assert review_item_file_path.exists()

    assert (
        await db_session.execute(select(Document).where(Document.id == doc.id))
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(select(Requirement).where(Requirement.id == req.id))
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(select(ExtractionRun).where(ExtractionRun.id == run.id))
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(
            select(ExtractedRequirement).where(ExtractedRequirement.id == extracted.id)
        )
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(select(ReviewItem).where(ReviewItem.id == item.id))
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(
            select(ReviewItemComment).where(ReviewItemComment.review_item_id == item.id)
        )
    ).scalars().first() is not None
    assert (
        await db_session.execute(
            select(ReviewItemEvidenceFile).where(ReviewItemEvidenceFile.review_item_id == item.id)
        )
    ).scalars().first() is not None


async def test_contributor_cannot_hard_delete_requirement_set(
    client, contributor_headers, db_session, admin_user, default_jurisdiction, tmp_path
):
    file_path = tmp_path / "restricted.pdf"
    file_path.write_bytes(b"x")

    doc = Document(
        jurisdiction_id=default_jurisdiction.id,
        filename="restricted.pdf",
        name="Restricted",
        document_type="annex_b",
        status="uploaded",
        file_path=str(file_path),
        uploaded_by=admin_user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    resp = await client.delete(f"/api/v1/requirements/sets/{doc.id}", headers=contributor_headers)
    assert resp.status_code == 403

    # Still exists.
    assert (
        await db_session.execute(select(Document).where(Document.id == doc.id))
    ).scalar_one_or_none() is not None


async def test_set_counts_only_current_version_and_preserves_legacy_sets(
    client, auth_headers, admin_user, db_session, default_jurisdiction
):
    from app.models.program import RequirementSetVersion

    document = Document(
        jurisdiction_id=default_jurisdiction.id, filename="versions.pdf", name="Versioned scope",
        document_type="standard", status="approved", file_path="versions.pdf",
        uploaded_by=admin_user.id,
    )
    db_session.add(document)
    await db_session.flush()
    old = RequirementSetVersion(document_id=document.id, version_number=1, status="approved", is_current=False, created_by=admin_user.id)
    current = RequirementSetVersion(document_id=document.id, version_number=2, status="approved", is_current=True, created_by=admin_user.id)
    db_session.add_all([old, current])
    await db_session.flush()
    for index, version in enumerate([None, old.id, old.id, current.id, current.id]):
        db_session.add(Requirement(
            jurisdiction_id=default_jurisdiction.id, document_id=document.id,
            requirement_set_version_id=version, reference_id=str(index), text="Control",
            requirement_type="mandatory", active=index != 4,
        ))
    await db_session.commit()
    response = await client.get(f"/api/v1/requirements/sets?document_id={document.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    row = response.json()["items"][0]
    assert row["requirements_total"] == 2
    assert row["requirements_active"] == 1
    assert row["current_version_number"] == 2
    current.is_current = False
    await db_session.commit()
    response = await client.get(f"/api/v1/requirements/sets?document_id={document.id}", headers=auth_headers)
    assert response.json()["items"][0]["requirements_total"] == 1
