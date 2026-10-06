"""Small, explicit synthetic draft for a non-production installation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.jurisdiction import Jurisdiction
from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement, RequirementStatus
from app.models.user import User

EXAMPLE_CODE = "example"
EXAMPLE_JURISDICTION_NAME = "EXAMPLE - synthetic training scope"
EXAMPLE_SET_NAME = "EXAMPLE - training controls (not regulatory text)"


async def add_setup_example(db: AsyncSession, user: User) -> bool:
    """Add one unapproved manual set, isolated from the requested live jurisdiction."""
    jurisdiction = (
        await db.execute(select(Jurisdiction).where(Jurisdiction.code == EXAMPLE_CODE))
    ).scalar_one_or_none()
    if jurisdiction is None:
        jurisdiction = Jurisdiction(code=EXAMPLE_CODE, name=EXAMPLE_JURISDICTION_NAME)
        db.add(jurisdiction)
        await db.flush()
    elif jurisdiction.name != EXAMPLE_JURISDICTION_NAME or not jurisdiction.active:
        raise ValueError("The example jurisdiction code is already used; setup changed nothing.")

    existing = (
        await db.execute(
            select(Document).where(
                Document.organization_id == user.organization_id,
                Document.jurisdiction_id == jurisdiction.id,
                Document.name == EXAMPLE_SET_NAME,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    document = Document(
        organization_id=user.organization_id,
        jurisdiction_id=jurisdiction.id,
        name=EXAMPLE_SET_NAME,
        document_type="example",
        version="training-1",
        status="draft",
        uploaded_by=user.id,
        testing_frequency="one_off",
    )
    db.add(document)
    await db.flush()
    version = RequirementSetVersion(
        organization_id=user.organization_id,
        document_id=document.id,
        version_number=1,
        status="draft",
        is_current=True,
        created_by=user.id,
    )
    db.add(version)
    await db.flush()
    requirement = Requirement(
        organization_id=user.organization_id,
        jurisdiction_id=jurisdiction.id,
        document_id=document.id,
        requirement_set_version_id=version.id,
        reference_id="EX-1",
        title="Record a training decision",
        text="EXAMPLE ONLY: Record a reviewer, a decision, and evidence for training.",
        requirement_type="mandatory",
        active=True,
    )
    db.add(requirement)
    await db.flush()
    db.add(
        RequirementStatus(
            requirement_id=requirement.id,
            status="not_started",
            comment="Synthetic example; not approved for compliance use",
            changed_by=user.id,
        )
    )
    return True
