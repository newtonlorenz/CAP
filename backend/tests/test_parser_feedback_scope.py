"""Parser corrections are learned only from the requesting document's scope."""

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.organization import Organization
from app.models.requirement import ExtractedRequirement, ExtractionFeedback
from app.models.user import User
from app.services.parser_feedback import apply_parser_template, load_parser_template

FAMILY = "synthetic-family"
DOCUMENT_TYPE = "standard"


async def _add_corrected_runs(db, jurisdiction_id, user_id, organization_id, number, *, count=3):
    """Create distinct reviewed runs with the same parser family and correction."""
    for index in range(count):
        doc = Document(
            organization_id=organization_id,
            jurisdiction_id=jurisdiction_id,
            uploaded_by=user_id,
            document_type=DOCUMENT_TYPE,
            filename=f"source-{number}-{index}.pdf",
        )
        db.add(doc)
        await db.flush()
        run = ExtractionRun(
            document_id=doc.id,
            ai_provider="none",
            ai_model="none",
            family_fingerprint=FAMILY,
            status="completed",
        )
        db.add(run)
        await db.flush()
        extracted = ExtractedRequirement(
            document_id=doc.id,
            extraction_run_id=run.id,
            reference_id="4.2.tt",
            text="Control tt applies.",
            original_text="Control tt applies.",
            page_number=1,
        )
        db.add(extracted)
        await db.flush()
        db.add(
            ExtractionFeedback(
                extraction_run_id=run.id,
                extracted_requirement_id=extracted.id,
                action="edit",
                corrected_reference_id=f"4.2.{number}",
                corrected_text=f"Control {number} applies.",
            )
        )
    await db.commit()


async def _template(db, jurisdiction_id, organization_id):
    return await load_parser_template(
        db,
        jurisdiction_id=jurisdiction_id,
        organization_id=organization_id,
        document_type=DOCUMENT_TYPE,
        family_fingerprint=FAMILY,
    )


async def test_foreign_organisation_runs_never_satisfy_support_threshold(
    db_session,
    default_jurisdiction,
):
    owner = User(
        email="feedback-scope@example.test", full_name="Scope", role="admin", password_hash="unused"
    )
    foreign = Organization(code="foreign", name="Foreign")
    local = Organization(code="local", name="Local")
    db_session.add_all([owner, foreign, local])
    await db_session.flush()

    await _add_corrected_runs(db_session, default_jurisdiction.id, owner.id, foreign.id, "9")
    assert await _template(db_session, default_jurisdiction.id, local.id) is None
    foreign_template = await _template(db_session, default_jurisdiction.id, foreign.id)
    assert foreign_template.support_runs == 3
    assert foreign_template.replacements == {"tt": "9"}

    await _add_corrected_runs(db_session, default_jurisdiction.id, owner.id, local.id, "7", count=2)
    assert await _template(db_session, default_jurisdiction.id, local.id) is None


async def test_same_organisation_learns_its_own_corrections_amid_foreign_runs(
    db_session,
    default_jurisdiction,
):
    owner = User(
        email="feedback-own@example.test", full_name="Scope", role="admin", password_hash="unused"
    )
    foreign = Organization(code="foreign", name="Foreign")
    local = Organization(code="local", name="Local")
    db_session.add_all([owner, foreign, local])
    await db_session.flush()

    await _add_corrected_runs(db_session, default_jurisdiction.id, owner.id, foreign.id, "9")
    await _add_corrected_runs(db_session, default_jurisdiction.id, owner.id, local.id, "7")
    template = await _template(db_session, default_jurisdiction.id, local.id)
    assert template.support_runs == 3
    assert template.heading_style == "split"
    assert template.replacements == {"tt": "7"}
    assert apply_parser_template("4.2.tt", template) == "4.2.7"


async def test_null_organisation_is_its_own_learning_scope(
    db_session,
    default_jurisdiction,
):
    owner = User(
        email="feedback-null@example.test", full_name="Scope", role="admin", password_hash="unused"
    )
    local = Organization(code="local", name="Local")
    db_session.add_all([owner, local])
    await db_session.flush()

    await _add_corrected_runs(db_session, default_jurisdiction.id, owner.id, local.id, "7")
    assert await _template(db_session, default_jurisdiction.id, None) is None

    await _add_corrected_runs(db_session, default_jurisdiction.id, owner.id, None, "5")
    legacy_template = await _template(db_session, default_jurisdiction.id, None)
    assert legacy_template.support_runs == 3
    assert legacy_template.replacements == {"tt": "5"}
    assert apply_parser_template("4.2.tt", legacy_template) == "4.2.5"
    local_template = await _template(db_session, default_jurisdiction.id, local.id)
    assert local_template.support_runs == 3
    assert local_template.replacements == {"tt": "7"}
