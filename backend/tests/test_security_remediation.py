import subprocess
import uuid
from pathlib import Path

from app.models.document import Document
from app.models.organization import Organization
from app.models.program import CertificationProject
from app.models.requirement import Requirement
from app.models.review import ReviewCycle, ReviewItem
from app.models.user import User
from app.services.auth import create_access_token, hash_password


ROOT = Path(__file__).resolve().parents[2]


async def _org_user(db_session, *, code: str, email: str, role: str = "manager"):
    org_id = uuid.uuid4()
    org = Organization(id=org_id, code=code, name=f"{code} org", active=True)
    user = User(
        organization_id=org_id,
        email=email,
        password_hash=hash_password("testpass"),
        full_name=email.split("@")[0],
        role=role,
        active=True,
    )
    db_session.add_all([org, user])
    await db_session.commit()
    await db_session.refresh(org)
    await db_session.refresh(user)
    return org, user


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _document(db_session, user: User, jurisdiction_id, *, name: str):
    document = Document(
        organization_id=user.organization_id,
        jurisdiction_id=jurisdiction_id,
        filename=f"{name}.pdf",
        name=name,
        document_type="scp",
        status="approved",
        file_path=f"/tmp/{name}.pdf",
        uploaded_by=user.id,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


async def _requirement(db_session, user: User, document: Document, jurisdiction_id, *, ref: str):
    requirement = Requirement(
        organization_id=user.organization_id,
        jurisdiction_id=jurisdiction_id,
        document_id=document.id,
        reference_id=ref,
        text=f"{ref} text",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(requirement)
    await db_session.commit()
    await db_session.refresh(requirement)
    return requirement


async def test_org_scoped_document_list_and_direct_read(
    client,
    db_session,
    default_jurisdiction,
):
    _, user_a = await _org_user(db_session, code="tenant-a", email="a@example.com")
    _, user_b = await _org_user(db_session, code="tenant-b", email="b@example.com")
    doc_a = await _document(db_session, user_a, default_jurisdiction.id, name="tenant-a-doc")
    doc_b = await _document(db_session, user_b, default_jurisdiction.id, name="tenant-b-doc")

    list_response = await client.get("/api/v1/documents", headers=_headers(user_a))
    assert list_response.status_code == 200
    ids = {item["id"] for item in list_response.json()["items"]}
    assert str(doc_a.id) in ids
    assert str(doc_b.id) not in ids

    direct_response = await client.get(f"/api/v1/documents/{doc_b.id}", headers=_headers(user_a))
    assert direct_response.status_code == 404


async def test_program_fk_writes_reject_cross_org_references(
    client,
    db_session,
    default_jurisdiction,
):
    _, user_a = await _org_user(db_session, code="tenant-a", email="a-fk@example.com")
    _, user_b = await _org_user(db_session, code="tenant-b", email="b-fk@example.com")
    doc_b = await _document(db_session, user_b, default_jurisdiction.id, name="tenant-b-plan")
    req_b = await _requirement(
        db_session,
        user_b,
        doc_b,
        default_jurisdiction.id,
        ref="B-1",
    )

    plan_response = await client.post(
        "/api/v1/maintenance-plans",
        headers=_headers(user_a),
        json={
            "jurisdiction_id": str(default_jurisdiction.id),
            "document_id": str(doc_b.id),
            "name": "Cross-org plan",
            "cadence_days": 30,
        },
    )
    assert plan_response.status_code == 404

    evidence_response = await client.post(
        "/api/v1/evidence-items",
        headers=_headers(user_a),
        json={
            "requirement_id": str(req_b.id),
            "evidence_type": "file",
            "title": "Cross-org evidence",
        },
    )
    assert evidence_response.status_code == 404


async def test_review_bulk_mutation_reports_partial_failures(
    client,
    db_session,
    default_jurisdiction,
):
    _, admin = await _org_user(
        db_session, code="bulk-org", email="bulk-admin@example.com", role="admin"
    )
    document = await _document(db_session, admin, default_jurisdiction.id, name="bulk-doc")
    requirement = await _requirement(
        db_session,
        admin,
        document,
        default_jurisdiction.id,
        ref="BULK-1",
    )
    cycle = ReviewCycle(
        organization_id=admin.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        name="Bulk review",
        scope="all",
        status="active",
        created_by=admin.id,
    )
    db_session.add(cycle)
    await db_session.flush()
    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=requirement.id,
        review_status="pending",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    missing_item_id = uuid.uuid4()
    response = await client.patch(
        f"/api/v1/review-cycles/{cycle.id}/items/bulk",
        headers=_headers(admin),
        json={
            "item_ids": [str(item.id), str(missing_item_id)],
            "review_status": "escalated",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["updated_count"] == 1
    assert data["failed_count"] == 1
    assert data["failures"][0]["item_id"] == str(missing_item_id)

    await db_session.refresh(item)
    assert item.review_status == "escalated"


async def test_submission_checklist_blocks_package_approval(
    client,
    db_session,
    default_jurisdiction,
):
    _, manager = await _org_user(db_session, code="checklist-org", email="checklist@example.com")
    project = CertificationProject(
        organization_id=manager.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        name="Checklist project",
        stage="pre_audit",
        status="active",
        created_by=manager.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    checklist = {
        "sections": [
            {
                "id": "submission",
                "title": "Submission readiness",
                "items": [
                    {
                        "id": "required-artifacts",
                        "label": "All required artifacts are included",
                        "required": True,
                        "completed": False,
                    }
                ],
            }
        ]
    }
    create_response = await client.post(
        "/api/v1/submission-packages",
        headers=_headers(manager),
        json={
            "project_id": str(project.id),
            "version": "v1",
            "status": "draft",
            "checklist": checklist,
        },
    )
    assert create_response.status_code == 201
    package = create_response.json()
    assert package["checklist_completion"]["ready"] is False
    assert package["checklist_completion"]["blocking_items"] == [
        "All required artifacts are included"
    ]

    gate_response = await client.get(
        f"/api/v1/submission-packages/{package['id']}/gate-check",
        headers=_headers(manager),
    )
    assert gate_response.status_code == 200
    assert gate_response.json()["checklist_blocking_items"] == [
        "All required artifacts are included"
    ]

    request_response = await client.post(
        f"/api/v1/submission-packages/{package['id']}/request-approval",
        headers=_headers(manager),
    )
    assert request_response.status_code == 400


def test_repository_hygiene_blocks_tracked_backup_sql_dumps():
    if not (ROOT / ".git").exists():
        # An exported source snapshot deliberately has no Git history.
        assert not list((ROOT / "backups").glob("**/*.sql"))
        return
    result = subprocess.run(
        ["git", "ls-files", "backups/*.sql", "backups/**/*.sql"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    tracked_sql_dumps = [
        path for path in result.stdout.splitlines() if path.strip() and (ROOT / path).exists()
    ]
    assert tracked_sql_dumps == []


def test_public_dev_credentials_are_not_defaulted():
    compose = (ROOT / "docker-compose.yml").read_text()
    login = (ROOT / "frontend/src/pages/Login.tsx").read_text()
    vite = (ROOT / "frontend/vite.config.ts").read_text()
    e2e_seed = (ROOT / "backend/app/seed_e2e.py").read_text()

    assert "BOOTSTRAP_ADMIN_PASSWORD:-adminpass" not in compose
    assert "adminpass123" not in login
    assert 'ADMIN_PASSWORD = "adminpass123"' not in e2e_seed
    assert "VITE_TEST_ADMIN_PASSWORD" not in compose
    assert "VITE_TEST_ADMIN_PASSWORD" not in login
    assert "VITE_TEST_ADMIN_EMAIL" not in compose
    assert "VITE_TEST_ADMIN_EMAIL" not in login
    assert "VITE_ALLOW_ALL_HOSTS === 'true'" in vite
