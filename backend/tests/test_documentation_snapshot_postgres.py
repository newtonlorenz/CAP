"""Real owner writes cannot produce mixed documentation handover revisions."""

import asyncio
import json
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.documentation_integrations import create_snapshot
from app.models import Document, Jurisdiction, Organization, Requirement, User
from app.models.application import Application, ApplicationComponent
from app.models.documentation import (
    DocumentationExpectation,
    DocumentationProcessTarget,
    DocumentationRegister,
)
from app.models.documentation_integrations import DocumentationSnapshot
from app.models.preparation import PreparationCase, PreparationEvidence
from app.models.program import RequirementSetVersion
from app.schemas.documentation_integrations import SnapshotCreate
from app.schemas.preparation import PreparationField
from app.services.documentation_process_applications import resolve_application_target
from app.services.documentation_processes import process_fingerprint
from app.services.preparation import field_for, save_response
from app.services.preparation_requirements import field_source


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_snapshot_waits_for_owner_write_before_freezing_alias_coverage_and_collection():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pending = None
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            organization = Organization(code=key, name="Disposable snapshot consistency fixture")
            jurisdiction = Jurisdiction(code=key, name="Synthetic jurisdiction")
            db.add_all([organization, jurisdiction])
            await db.flush()
            owner = User(
                email=f"{key}@example.test",
                full_name="Snapshot fixture",
                role="admin",
                password_hash="not-a-login",
                organization_id=organization.id,
            )
            db.add(owner)
            await db.flush()
            document = Document(
                organization_id=organization.id,
                jurisdiction_id=jurisdiction.id,
                filename="synthetic.txt",
                name="Synthetic requirements",
                file_path="unused.txt",
                document_type="annex",
                status="approved",
                uploaded_by=owner.id,
            )
            db.add(document)
            await db.flush()
            version = RequirementSetVersion(
                organization_id=organization.id,
                document_id=document.id,
                version_number=1,
                status="approved",
                is_current=True,
                created_by=owner.id,
            )
            db.add(version)
            await db.flush()
            requirement = Requirement(
                organization_id=organization.id,
                jurisdiction_id=jurisdiction.id,
                document_id=document.id,
                requirement_set_version_id=version.id,
                reference_id="1.1",
                title="Oversight records",
                text="Retain accountable oversight records",
                requirement_type="mandatory",
            )
            db.add(requirement)
            await db.flush()
            field = PreparationField(
                key="proof",
                label="Oversight records",
                type="text",
                source=field_source(document, version, requirement),
            )
            case = PreparationCase(
                organization_id=organization.id,
                jurisdiction_id=jurisdiction.id,
                name="Canonical licence form",
                template_name="Synthetic private form",
                template_revision=1,
                kind="licence_application",
                created_by=owner.id,
                fields_json=json.dumps([field.model_dump(mode="json")]),
            )
            application = Application(
                organization_id=organization.id,
                jurisdiction_id=jurisdiction.id,
                name="Synthetic draft application",
                scope="casino",
                created_by=owner.id,
            )
            before = PreparationEvidence(
                organization_id=organization.id,
                title="Prior policy",
                kind="note",
                body="Prior oversight record",
                created_by=owner.id,
            )
            after = PreparationEvidence(
                organization_id=organization.id,
                title="Updated policy",
                kind="note",
                body="Updated oversight record",
                created_by=owner.id,
            )
            db.add_all([case, application, before, after])
            await db.flush()
            db.add(
                ApplicationComponent(
                    application_id=application.id, name=case.name, kind="form", case_id=case.id
                )
            )
            register = DocumentationRegister(
                organization_id=organization.id,
                jurisdiction_id=jurisdiction.id,
                application_id=application.id,
                name="Synthetic linked register",
                created_by=owner.id,
            )
            db.add(register)
            await db.flush()
            await save_response(
                db,
                case,
                field,
                case.revision,
                value="Prior answer",
                reason=None,
                evidence=[before],
                saved_by=owner.id,
            )
            rows = [
                DocumentationExpectation(
                    register_id=register.id,
                    title=f"Alias {index}",
                    description="",
                    applicability="applicable",
                    coverage_status="sufficient",
                    created_by=owner.id,
                )
                for index in range(2)
            ]
            db.add_all(rows)
            await db.flush()
            for row in rows:
                db.add(
                    DocumentationProcessTarget(
                        expectation_id=row.id,
                        case_id=case.id,
                        field_key=field.key,
                        requirement_id=requirement.id,
                        requirement_set_version_id=version.id,
                        created_by=owner.id,
                    )
                )
            await db.flush()
            target = await resolve_application_target(
                db, application.id, case.id, field.key, register, owner
            )
            for row in rows:
                row.process_review_fingerprint = process_fingerprint([target])
            await db.commit()

        async with sessions() as writer, sessions() as freezer, sessions() as observer:
            current = await writer.get(PreparationCase, case.id)
            updated = await writer.get(PreparationEvidence, after.id)
            await save_response(
                writer,
                current,
                field_for(current, "proof"),
                current.revision,
                value="Updated answer",
                reason=None,
                evidence=[updated],
                saved_by=owner.id,
            )
            # The actual owner write has updated case/response/associations but has
            # not committed. The handover must wait before reading any collection.
            pid = await freezer.scalar(text("select pg_backend_pid()"))
            pending = asyncio.create_task(
                create_snapshot(
                    register.id, SnapshotCreate(revision=register.revision), freezer, owner
                )
            )
            deadline = asyncio.get_running_loop().time() + 10
            while True:
                state = await observer.scalar(
                    text("select wait_event_type from pg_stat_activity where pid = :pid"),
                    {"pid": pid},
                )
                await observer.rollback()
                if state == "Lock":
                    break
                assert not pending.done(), "Snapshot bypassed the canonical case writer"
                assert (
                    asyncio.get_running_loop().time() < deadline
                ), "Snapshot never reached the owner fence"
                await asyncio.sleep(0.02)
            await writer.commit()
            created = await asyncio.wait_for(pending, 10)
            frozen = await observer.get(DocumentationSnapshot, uuid.UUID(created["id"]))
            data = json.loads(frozen.content_json)
            assert len(data["expectations"]) == 2
            for row in data["expectations"]:
                assert row["effective_coverage_status"] == "unreviewed"
                collection = row["process_targets"][0]["collection"]
                assert collection["current_value"] == "Updated answer"
                assert [entry["evidence_id"] for entry in collection["items"]] == [str(after.id)]
            assert [entry["id"] for entry in data["frozen_evidence"]] == [str(after.id)]
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await engine.dispose()
