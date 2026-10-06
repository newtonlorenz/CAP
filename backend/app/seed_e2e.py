"""Seed deterministic data for Playwright E2E tests."""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.test_environment import validate_test_database

# Validate the explicit target before loading application settings or DB sessions.
validate_test_database(os.environ)

from app.database import async_session
from app.config import settings
from app.models.document import Document
from app.models.jurisdiction import Jurisdiction
from app.models.requirement import Requirement, RequirementStatus, ExtractedRequirement
from app.models.extraction import ExtractionRun
from app.models.program import RequirementSetVersion
from app.models.user import LoginThrottle, User
from app.models.organization import Organization
from app.services.auth import hash_password

ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD") or os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
ADMIN_NAME = "Admin User"

if not ADMIN_PASSWORD:
    raise RuntimeError(
        "Set E2E_ADMIN_PASSWORD or BOOTSTRAP_ADMIN_PASSWORD before seeding E2E data."
    )

DOC_NAME = "E2E Document"
DOC_FILENAME = "e2e.pdf"
DOC_TYPE = "standard"
DOC_STATUS = "approved"
DOC_TESTING_FREQUENCY = "quarterly"
DOC_FILE_PATH = str(Path(settings.upload_dir).resolve() / DOC_FILENAME)

REQ_REFERENCE = "REQ-001"
REQ_TEXT = "E2E requirement text"
REQ_TYPE = "mandatory"

JURISDICTION_CODE = "example"
JURISDICTION_NAME = "Example jurisdiction"


async def seed() -> None:
    # A real synthetic source is required when an assessment freezes its package.
    # Seed only after the disposable test-database guard above has succeeded.
    from reportlab.pdfgen.canvas import Canvas

    source = Path(DOC_FILE_PATH)
    source.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(source), invariant=1)
    canvas.drawString(72, 760, "Synthetic E2E source - not for regulatory submission")
    canvas.drawString(72, 730, f"{REQ_REFERENCE}: {REQ_TEXT}")
    canvas.save()
    async with async_session() as session:
        # Prior runs in this disposable database must not exhaust the real login limit.
        await session.execute(delete(LoginThrottle))
        user_result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = user_result.scalar_one_or_none()
        if user:
            user.full_name = ADMIN_NAME
            user.role = "admin"
            user.active = True
            user.password_hash = hash_password(ADMIN_PASSWORD)
        else:
            user = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name=ADMIN_NAME,
                role="admin",
                active=True,
            )
            session.add(user)
        if not user.organization_id:
            organisation = await session.scalar(
                select(Organization).where(Organization.code == "cap-e2e")
            )
            if not organisation:
                organisation = Organization(code="cap-e2e", name="Disposable E2E organisation")
                session.add(organisation)
                await session.flush()
            user.organization_id = organisation.id
        await session.commit()
        await session.refresh(user)

        contributor = await session.scalar(
            select(User).where(User.email == "contributor@example.com")
        )
        if not contributor:
            contributor = User(
                email="contributor@example.com",
                full_name="E2E Contributor",
                role="contributor",
                password_hash=hash_password(ADMIN_PASSWORD),
                active=True,
                organization_id=user.organization_id,
            )
            session.add(contributor)
        else:
            contributor.password_hash = hash_password(ADMIN_PASSWORD)
            contributor.organization_id = user.organization_id
            contributor.role = "contributor"
            contributor.active = True
        await session.commit()

        juris_result = await session.execute(
            select(Jurisdiction).where(Jurisdiction.code == JURISDICTION_CODE)
        )
        jurisdiction = juris_result.scalar_one_or_none()
        if not jurisdiction:
            jurisdiction = Jurisdiction(
                code=JURISDICTION_CODE,
                name=JURISDICTION_NAME,
                regulator_name="Example authority",
                report_header_text="Example assessment",
                active=True,
            )
            session.add(jurisdiction)
            await session.commit()
            await session.refresh(jurisdiction)

        # Reference configuration only; browser journeys create their own work through the UI.
        for code, name in (("dk", "Denmark"), ("fi", "Finland"), ("se", "Sweden")):
            existing_market = await session.scalar(select(Jurisdiction).where(Jurisdiction.code == code))
            if not existing_market:
                session.add(Jurisdiction(code=code, name=name, active=True))
        await session.commit()

        doc_result = await session.execute(select(Document).where(Document.name == DOC_NAME))
        doc = doc_result.scalar_one_or_none()
        if doc:
            doc.filename = DOC_FILENAME
            doc.document_type = DOC_TYPE
            doc.status = DOC_STATUS
            doc.file_path = DOC_FILE_PATH
            doc.testing_frequency = DOC_TESTING_FREQUENCY
            doc.uploaded_by = user.id
            doc.jurisdiction_id = jurisdiction.id
        else:
            doc = Document(
                jurisdiction_id=jurisdiction.id,
                filename=DOC_FILENAME,
                name=DOC_NAME,
                document_type=DOC_TYPE,
                status=DOC_STATUS,
                file_path=DOC_FILE_PATH,
                testing_frequency=DOC_TESTING_FREQUENCY,
                uploaded_by=user.id,
            )
            session.add(doc)
        doc.organization_id = user.organization_id
        await session.commit()
        await session.refresh(doc)

        baseline = await session.scalar(
            select(RequirementSetVersion).where(
                RequirementSetVersion.document_id == doc.id,
                RequirementSetVersion.is_current.is_(True),
            )
        )
        if not baseline:
            baseline = RequirementSetVersion(
                document_id=doc.id,
                version_number=1,
                status="approved",
                is_current=True,
                created_by=user.id,
                approved_by=user.id,
                organization_id=user.organization_id,
            )
            session.add(baseline)
            await session.flush()
        baseline.status = "approved"
        baseline.organization_id = user.organization_id

        req_result = await session.execute(
            select(Requirement)
            .where(
                Requirement.document_id == doc.id,
                Requirement.reference_id == REQ_REFERENCE,
                Requirement.requirement_set_version_id == baseline.id,
            )
            .order_by(Requirement.created_at.desc())
            .limit(1)
        )
        req = req_result.scalar_one_or_none()
        if not req:
            req = Requirement(
                jurisdiction_id=jurisdiction.id,
                document_id=doc.id,
                reference_id=REQ_REFERENCE,
                text=REQ_TEXT,
                requirement_type=REQ_TYPE,
                parent_id=None,
                active=True,
                version=1,
                sort_order=0,
            )
            session.add(req)
            await session.commit()
            await session.refresh(req)

        if not req.source_extraction_id:
            run = ExtractionRun(
                document_id=doc.id,
                status="completed",
                ai_provider="local",
                ai_model="synthetic-fixture",
                total_pages=1,
                current_page=1,
                requirements_found=1,
            )
            session.add(run)
            await session.flush()
            extracted = ExtractedRequirement(
                document_id=doc.id,
                extraction_run_id=run.id,
                reference_id=REQ_REFERENCE,
                text=REQ_TEXT,
                original_text=REQ_TEXT,
                requirement_type=REQ_TYPE,
                page_number=1,
                status="approved",
                needs_review=False,
            )
            session.add(extracted)
            await session.flush()
            doc.current_extraction_id = run.id
            req.source_extraction_id = extracted.id
        req.requirement_set_version_id = baseline.id
        req.active = True
        req.organization_id = user.organization_id
        await session.commit()

        status_result = await session.execute(
            select(RequirementStatus)
            .where(RequirementStatus.requirement_id == req.id)
            .order_by(RequirementStatus.changed_at.desc())
            .limit(1)
        )
        status = status_result.scalar_one_or_none()
        if not status:
            status = RequirementStatus(
                requirement_id=req.id,
                status="not_started",
                comment="Seeded for E2E",
                changed_by=user.id,
                changed_at=datetime.now(timezone.utc),
            )
            session.add(status)
            await session.commit()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
