"""Synthetic integration checks for the local, versioned structure pipeline."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractedRequirement, Requirement
from app.models.program import RequirementSetVersion
from app.models.user import User
from app.services.structured_pdf import PIPELINE_VERSION
from app.tasks import extraction as task


def candidate(ref, page, parent=None):
    text = "The service shall retain audit records." if parent else "Audit controls"
    return dict(reference_id=ref, page_number=page, parent_reference=parent,
                text=text, original_text=text, source_excerpt=text,
                requirement_type="mandatory" if parent else "informational",
                parser_strategy="opendataloader", needs_review=True)


@pytest.fixture
async def source_run(db_session, default_jurisdiction):
    user = User(email="structure@example.test", full_name="Structure test",
                role="admin", password_hash="unused")
    db_session.add(user)
    await db_session.flush()
    doc = Document(jurisdiction_id=default_jurisdiction.id, uploaded_by=user.id,
                   filename="synthetic.pdf", file_path="synthetic.pdf",
                   document_type="standard", status="uploaded")
    db_session.add(doc)
    await db_session.flush()
    run = ExtractionRun(document_id=doc.id, ai_provider="local", ai_model="opendataloader_2.5.11",
                        pipeline_version=PIPELINE_VERSION, status="pending")
    db_session.add(run)
    await db_session.flush()
    doc.current_extraction_id = run.id
    await db_session.commit()
    return doc, run, user


def mock_preprocess(monkeypatch, setup_database, rows):
    result = SimpleNamespace(
        cleanup_paths=[], pages=[dict(page_number=1, text=""), dict(page_number=2, text="")],
        ocr_applied=False, ocr_pages=0, warning_count=0, family_fingerprint="synthetic",
        parseability_score=1.0, fallback_trigger_reason=None, diagnostics={},
        low_quality_pages=[], page_quality=[], structured_requirements=rows,
    )
    preprocess = AsyncMock(return_value=result)
    monkeypatch.setattr(task, "_get_session_factory", lambda: setup_database)
    monkeypatch.setattr(task, "bounded_preprocess", preprocess)
    monkeypatch.setattr(task, "load_parser_template", AsyncMock(return_value=None))
    monkeypatch.setattr(task, "publish_event", AsyncMock())
    adapter = SimpleNamespace(parse_requirements=AsyncMock(side_effect=AssertionError("AI invoked")))
    monkeypatch.setattr(task, "PdfParser", lambda: adapter)
    return preprocess, adapter


async def test_structured_import_and_publication_resolve_forward_parents(
    monkeypatch, setup_database, db_session, source_run,
):
    doc, run, user = source_run
    preprocess, adapter = mock_preprocess(monkeypatch, setup_database, [
        candidate("3.1.1.1", 1, "3.1.1"), candidate("3.1.1", 2, "3.1"),
        candidate("3.1", 2, "3"), candidate("3", 2),
    ])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(run)
    assert run.status == "completed"
    assert run.current_page == run.total_pages == 2
    assert run.requirements_found == 4
    assert preprocess.await_args.kwargs == {"structure_engine": "opendataloader"}
    adapter.parse_requirements.assert_not_called()
    rows = list((await db_session.scalars(select(ExtractedRequirement))).all())
    by_ref = {row.reference_id: row for row in rows}
    assert all(row.original_text == row.source_excerpt == row.text for row in rows)
    assert all(row.needs_review for row in rows)
    for ref in ("3.1", "3.1.1", "3.1.1.1"):
        assert by_ref[ref].parent_id == by_ref[ref.rsplit(".", 1)[0]].id

    version = RequirementSetVersion(document_id=doc.id, version_number=1, status="draft",
                                    is_current=False, created_by=user.id)
    db_session.add(version)
    await db_session.flush()
    from app.api.documents import _ensure_extracted_requirements_in_version
    assert await _ensure_extracted_requirements_in_version(db_session, doc, version, user.id, "Test") == 4
    published = {r.reference_id: r for r in (await db_session.scalars(select(Requirement))).all()}
    for ref in ("3.1", "3.1.1", "3.1.1.1"):
        assert published[ref].parent_id == published[ref.rsplit(".", 1)[0]].id
    by_ref["3.1.1.1"].text = "A reviewer amendment"
    assert published["3.1.1.1"].text != by_ref["3.1.1.1"].text
    assert by_ref["3.1.1.1"].original_text == "The service shall retain audit records."


@pytest.mark.parametrize("rows,message", [
    ([candidate("3", 1), candidate("3", 2)], "Duplicate structured reference"),
    ([], "no requirement candidates"),
])
async def test_bad_structured_result_cannot_complete(
    monkeypatch, setup_database, db_session, source_run, rows, message,
):
    doc, run, _ = source_run
    mock_preprocess(monkeypatch, setup_database, rows)
    for _ in range(4):
        await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(run)
    assert run.status == "failed"
    assert message in run.error_message


def test_missing_structured_installation_has_no_fallback(monkeypatch, tmp_path):
    from app.services import structured_pdf
    monkeypatch.setattr(structured_pdf, "structured_pdf_available", lambda: False)
    with pytest.raises(ValueError, match="requires OpenDataLoader"):
        structured_pdf.read_structured_pdf("synthetic.pdf", str(tmp_path), timeout=1)


def test_numbered_approval_gate_catches_skipped_hierarchy_levels():
    from app.services.source_validation import numbered_hierarchy_errors
    root = SimpleNamespace(id="root", reference_id="3", parent_id=None)
    section = SimpleNamespace(id="section", reference_id="3.1", parent_id="root")
    child = SimpleNamespace(id="child", reference_id="3.1.1", parent_id="root")
    assert numbered_hierarchy_errors([root, section, child]) == [
        "3.1.1: hierarchy must link to 3.1"
    ]
    child.parent_id = "section"
    assert numbered_hierarchy_errors([root, section, child]) == []


def test_structured_baseline_allows_manual_editorial_row_but_not_bad_source_reference():
    from app.services.source_validation import numbered_hierarchy_errors
    root = SimpleNamespace(id="root", reference_id="3", parent_id=None,
                           source_extraction_id="source")
    editorial = SimpleNamespace(id="note", reference_id="Editorial note", parent_id="root",
                                source_extraction_id=None)
    assert numbered_hierarchy_errors([root, editorial], required_source_ids={"source"}) == []
    root.reference_id = "l.3"
    assert "unnumbered source candidate" in numbered_hierarchy_errors(
        [root, editorial], required_source_ids={"source"})[0]


async def test_missing_parent_is_reviewable_but_cannot_be_published(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.services.source_validation import validate_extraction_complete
    doc, run, _ = source_run
    mock_preprocess(monkeypatch, setup_database, [candidate("3.1", 1, "3")])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(run)
    assert run.status == "completed"
    row = await db_session.scalar(select(ExtractedRequirement))
    assert row.needs_review and "Missing immediate parent" in row.review_reason
    with pytest.raises(HTTPException) as error:
        await validate_extraction_complete(db_session, doc)
    assert error.value.status_code == 422
    assert "missing immediate parent" in str(error.value.detail)


async def test_rejected_duplicate_becomes_durable_correctable_draft(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.api.requirements import resolve_structured_import_candidate
    from app.schemas.import_recovery import ImportRecoveryDecision
    from app.services.source_validation import validate_baseline, validate_extraction_complete

    doc, run, user = source_run
    duplicate = candidate("unresolved-2", 2)
    duplicate.update(text="1 Repeated source heading", original_text="1 Repeated source heading",
                     source_excerpt="1 Repeated source heading", review_reason="duplicate_reference:1")
    mock_preprocess(monkeypatch, setup_database, [candidate("1", 1), duplicate])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(doc)
    await db_session.refresh(run)
    assert run.status == "completed" and doc.status == "extracted"
    rows = {row.reference_id: row for row in (await db_session.scalars(select(ExtractedRequirement))).all()}
    unresolved = rows["unresolved-2"]
    assert unresolved.needs_review and unresolved.page_number == 2
    with pytest.raises(HTTPException) as blocked:
        await validate_extraction_complete(db_session, doc)
    assert blocked.value.status_code == 422
    assert "unresolved-2" in str(blocked.value.detail)
    from app.api.documents import approve_document
    with pytest.raises(HTTPException) as blocked_approval:
        await approve_document(doc.id, db=db_session, current_user=user)
    assert blocked_approval.value.status_code == 422
    # A copied version containing only the valid row must not bypass the
    # unresolved source candidate through the version approval route.
    version = RequirementSetVersion(document_id=doc.id, version_number=1,
                                    status="draft", is_current=False, created_by=user.id)
    db_session.add(version)
    await db_session.flush()
    db_session.add(Requirement(document_id=doc.id, jurisdiction_id=doc.jurisdiction_id,
        requirement_set_version_id=version.id, source_extraction_id=rows["1"].id,
        reference_id="1", title="Root", text="Audit controls",
        requirement_type="informational"))
    await db_session.flush()
    with pytest.raises(HTTPException) as blocked_version:
        await validate_baseline(db_session, version.id)
    assert blocked_version.value.status_code == 422
    staged_row = await db_session.scalar(select(Requirement).where(
        Requirement.requirement_set_version_id == version.id))
    staged_row.source_extraction_id = None
    await db_session.flush()
    with pytest.raises(HTTPException) as blocked_manual_copy:
        await validate_baseline(db_session, version.id)
    assert blocked_manual_copy.value.status_code == 422

    # Legacy bulk feedback can clear the flag while leaving an unresolved key.
    # Explicit recovery must still be available to the reviewer.
    unresolved.needs_review = False
    unresolved.review_reason = None
    await db_session.flush()
    with pytest.raises(HTTPException, match="already exists"):
        await resolve_structured_import_candidate(doc.id, unresolved.id,
            ImportRecoveryDecision(action="correct", reference_id="1", parent_reference=""),
            db_session, user)
    await resolve_structured_import_candidate(doc.id, unresolved.id,
        ImportRecoveryDecision(action="correct", reference_id="1.1", parent_reference="1",
                               corrected_text="Corrected reviewer wording", requirement_type="mandatory"),
        db_session, user)
    await db_session.refresh(unresolved)
    assert unresolved.reference_id == "1.1"
    assert unresolved.parent_id == rows["1"].id
    assert unresolved.original_text == unresolved.source_excerpt == "1 Repeated source heading"
    assert unresolved.text == "Corrected reviewer wording"
    rows["1"].needs_review = False
    await db_session.flush()
    await validate_extraction_complete(db_session, doc)


async def test_orphan_continuation_requires_explicit_target_and_source_review(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.api.requirements import resolve_structured_import_candidate
    from app.schemas.import_recovery import ImportRecoveryDecision
    from app.services.source_validation import validate_extraction_complete

    doc, run, user = source_run
    tail = candidate("unresolved-2", 2)
    tail.update(text="• source tail", original_text="• source tail",
                source_excerpt="• source tail", review_reason="orphan_continuation")
    mock_preprocess(monkeypatch, setup_database, [candidate("1", 1), tail])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(doc)
    await db_session.refresh(run)
    assert run.status == "completed", run.error_message
    rows = {row.reference_id: row for row in (await db_session.scalars(select(ExtractedRequirement))).all()}
    root, orphan = rows["1"], rows["unresolved-2"]
    with pytest.raises(HTTPException, match="Select an active numbered target"):
        await resolve_structured_import_candidate(doc.id, orphan.id,
            ImportRecoveryDecision(action="attach_continuation"), db_session, user)
    stale_run = ExtractionRun(document_id=doc.id, ai_provider="local", ai_model="opendataloader_2.5.11",
                              pipeline_version=PIPELINE_VERSION, status="completed")
    db_session.add(stale_run)
    await db_session.flush()
    stale_target = ExtractedRequirement(document_id=doc.id, extraction_run_id=stale_run.id,
        reference_id="9", title="Old run", text="Old text", original_text="Old text",
        requirement_type="informational", page_number=1, confidence_score=1.0,
        needs_review=False, parser_strategy="opendataloader")
    db_session.add(stale_target)
    await db_session.flush()
    with pytest.raises(HTTPException, match="Select an active numbered target"):
        await resolve_structured_import_candidate(doc.id, orphan.id,
            ImportRecoveryDecision(action="attach_continuation", target_id=stale_target.id),
            db_session, user)
    await resolve_structured_import_candidate(doc.id, orphan.id,
        ImportRecoveryDecision(action="attach_continuation", target_id=root.id), db_session, user)
    await db_session.refresh(root)
    await db_session.refresh(orphan)
    assert orphan.status == "rejected" and orphan.original_text == "• source tail"
    assert root.text.endswith("\n• source tail")
    assert root.original_text == "Audit controls"
    with pytest.raises(HTTPException, match="flagged source candidates"):
        await validate_extraction_complete(db_session, doc)
    root.needs_review = False
    await db_session.flush()
    await validate_extraction_complete(db_session, doc)


async def test_recovery_exclusion_respects_org_status_and_current_run(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.api.requirements import resolve_structured_import_candidate
    from app.models.organization import Organization
    from app.schemas.import_recovery import ImportRecoveryDecision
    from app.services.source_validation import validate_extraction_complete

    doc, run, user = source_run
    ambiguous = candidate("unresolved-2", 2)
    ambiguous.update(text="Unnumbered source row.", original_text="Unnumbered source row.",
                     source_excerpt="Unnumbered source row.",
                     review_reason="ambiguous_unnumbered_table_row")
    mock_preprocess(monkeypatch, setup_database, [candidate("1", 1), ambiguous])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(doc)
    await db_session.refresh(run)
    assert run.status == "completed", run.error_message
    rows = {row.reference_id: row for row in (await db_session.scalars(select(ExtractedRequirement))).all()}
    unresolved = rows["unresolved-2"]
    decision = ImportRecoveryDecision(action="exclude")

    other_org = Organization(code="other", name="Other organization")
    db_session.add(other_org)
    await db_session.flush()
    foreign = User(email="foreign@example.test", full_name="Foreign reviewer",
                   role="admin", password_hash="unused", organization_id=other_org.id)
    db_session.add(foreign)
    await db_session.commit()
    with pytest.raises(HTTPException) as denied:
        await resolve_structured_import_candidate(doc.id, unresolved.id, decision, db_session, foreign)
    assert denied.value.status_code == 404

    doc.status = "approved"
    await db_session.commit()
    with pytest.raises(HTTPException) as denied:
        await resolve_structured_import_candidate(doc.id, unresolved.id, decision, db_session, user)
    assert denied.value.status_code == 409

    doc.status = "extracted"
    newer = ExtractionRun(document_id=doc.id, ai_provider="local", ai_model="opendataloader_2.5.11",
                          pipeline_version=PIPELINE_VERSION, status="pending")
    db_session.add(newer)
    await db_session.flush()
    doc.current_extraction_id = newer.id
    await db_session.commit()
    with pytest.raises(HTTPException) as denied:
        await resolve_structured_import_candidate(doc.id, unresolved.id, decision, db_session, user)
    assert denied.value.status_code == 409

    doc.current_extraction_id = run.id
    await db_session.commit()
    await resolve_structured_import_candidate(doc.id, unresolved.id, decision, db_session, user)
    await db_session.refresh(unresolved)
    assert unresolved.status == "rejected"
    assert unresolved.original_text == unresolved.source_excerpt == "Unnumbered source row."
    rows["1"].needs_review = False
    await db_session.flush()
    await validate_extraction_complete(db_session, doc)


async def test_missing_parent_needs_explicit_child_relink_after_parent_correction(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.api.requirements import resolve_structured_import_candidate
    from app.schemas.import_recovery import ImportRecoveryDecision
    from app.services.source_validation import validate_extraction_complete

    doc, run, user = source_run
    parent = candidate("unresolved-2", 1)
    parent.update(text="2 Source chapter", original_text="2 Source chapter",
                  source_excerpt="2 Source chapter", review_reason="malformed_heading_reference")
    child = candidate("2.1", 2, "2")
    mock_preprocess(monkeypatch, setup_database, [parent, child])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(doc)
    await db_session.refresh(run)
    assert run.status == "completed", run.error_message
    rows = {row.reference_id: row for row in (await db_session.scalars(select(ExtractedRequirement))).all()}
    await resolve_structured_import_candidate(doc.id, rows["unresolved-2"].id,
        ImportRecoveryDecision(action="correct", reference_id="2", parent_reference=""),
        db_session, user)
    await db_session.refresh(rows["2.1"])
    assert rows["2.1"].needs_review and rows["2.1"].parent_id is None
    with pytest.raises(HTTPException) as blocked:
        await validate_extraction_complete(db_session, doc)
    assert blocked.value.status_code == 422
    await resolve_structured_import_candidate(doc.id, rows["2.1"].id,
        ImportRecoveryDecision(action="correct", reference_id="2.1", parent_reference="2"),
        db_session, user)
    await db_session.refresh(rows["2.1"])
    assert rows["2.1"].parent_id == rows["unresolved-2"].id
    await validate_extraction_complete(db_session, doc)


async def test_prepared_draft_requires_reconciliation_after_source_edit_and_preserves_human_text(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.api.documents import _ensure_extracted_requirements_in_version
    from app.api.requirements import reconcile_structured_import
    from app.schemas.import_recovery import ImportReconciliationRequest
    from app.services.source_validation import structured_baseline_reconciliation, validate_baseline

    doc, run, user = source_run
    root = candidate("1", 1)
    root["needs_review"] = False
    child = candidate("1.1", 2, "1")
    child["needs_review"] = False
    mock_preprocess(monkeypatch, setup_database, [root, child])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(doc)
    await db_session.refresh(run)
    assert run.status == "completed", run.error_message
    sources = {row.reference_id: row for row in (await db_session.scalars(select(ExtractedRequirement))).all()}
    for source in sources.values():
        source.needs_review = False
    await db_session.flush()
    version = RequirementSetVersion(document_id=doc.id, version_number=1,
                                    status="draft", created_by=user.id)
    db_session.add(version)
    await db_session.flush()
    await _ensure_extracted_requirements_in_version(db_session, doc, version, user.id, "Test")
    await validate_baseline(db_session, version.id)
    staged = {row.reference_id: row for row in (await db_session.scalars(select(Requirement))).all()}
    staged["1.1"].text = "A deliberate draft amendment."
    sources["1.1"].text = "Source corrected after draft preparation."
    await db_session.flush()
    with pytest.raises(HTTPException, match="Prepared draft differs"):
        await validate_baseline(db_session, version.id)
    report, _, _ = await structured_baseline_reconciliation(db_session, version, doc)
    assert {"text"} <= set(report["differences"][0]["fields"])
    staged["1.1"].text = "A newer deliberate draft amendment."
    await db_session.flush()
    with pytest.raises(HTTPException) as stale_preview:
        await reconcile_structured_import(doc.id, version.id,
            ImportReconciliationRequest(source_fingerprint=report["source_fingerprint"],
                                        draft_fingerprint=report["draft_fingerprint"]), db_session, user)
    assert stale_preview.value.status_code == 409
    report, _, _ = await structured_baseline_reconciliation(db_session, version, doc)
    await reconcile_structured_import(doc.id, version.id,
        ImportReconciliationRequest(source_fingerprint=report["source_fingerprint"],
                                    draft_fingerprint=report["draft_fingerprint"]), db_session, user)
    await validate_baseline(db_session, version.id)
    await db_session.refresh(staged["1.1"])
    assert staged["1.1"].text == "A newer deliberate draft amendment."
    assert sources["1.1"].original_text == "The service shall retain audit records."

    # Ordinary extraction edits, including feedback, change the same live row
    # and invalidate the explicit reconciliation fingerprint.
    sources["1.1"].text = "A later source feedback correction."
    await db_session.flush()
    with pytest.raises(HTTPException, match="Prepared draft differs"):
        await validate_baseline(db_session, version.id)


async def test_reconciliation_adds_newly_corrected_source_without_overwriting_prepared_rows(
    monkeypatch, setup_database, db_session, source_run,
):
    from fastapi import HTTPException
    from app.api.requirements import reconcile_structured_import, resolve_structured_import_candidate
    from app.schemas.import_recovery import ImportRecoveryDecision, ImportReconciliationRequest
    from app.services.source_validation import structured_baseline_reconciliation, validate_baseline

    doc, run, user = source_run
    root = candidate("1", 1)
    root["needs_review"] = False
    orphan = candidate("unresolved-2", 2)
    orphan.update(text="The service shall retain the evidence.",
                  original_text="The service shall retain the evidence.",
                  source_excerpt="The service shall retain the evidence.",
                  review_reason="malformed_table_row")
    mock_preprocess(monkeypatch, setup_database, [root, orphan])
    await task._extract(str(doc.id), str(run.id))
    await db_session.refresh(doc)
    await db_session.refresh(run)
    assert run.status == "completed", run.error_message
    sources = {row.reference_id: row for row in (await db_session.scalars(select(ExtractedRequirement))).all()}
    sources["1"].needs_review = False
    await db_session.flush()
    version = RequirementSetVersion(document_id=doc.id, version_number=1,
                                    status="draft", created_by=user.id)
    db_session.add(version)
    await db_session.flush()
    old_copy = Requirement(document_id=doc.id, jurisdiction_id=doc.jurisdiction_id,
        requirement_set_version_id=version.id, source_extraction_id=sources["1"].id,
        reference_id="1", title=sources["1"].title, text="Human draft wording",
        requirement_type="informational", active=True)
    db_session.add(old_copy)
    await db_session.flush()
    await resolve_structured_import_candidate(doc.id, sources["unresolved-2"].id,
        ImportRecoveryDecision(action="correct", reference_id="1.1", parent_reference="1"),
        db_session, user)
    with pytest.raises(HTTPException, match="Prepared draft differs"):
        await validate_baseline(db_session, version.id)
    report, _, _ = await structured_baseline_reconciliation(db_session, version, doc)
    assert [item["reference_id"] for item in report["missing"]] == ["1.1"]
    await reconcile_structured_import(doc.id, version.id,
        ImportReconciliationRequest(source_fingerprint=report["source_fingerprint"],
                                    draft_fingerprint=report["draft_fingerprint"]), db_session, user)
    await validate_baseline(db_session, version.id)
    copies = {row.reference_id: row for row in (await db_session.scalars(select(Requirement))).all()}
    assert copies["1"].id == old_copy.id and copies["1"].text == "Human draft wording"
    assert copies["1.1"].source_extraction_id == sources["unresolved-2"].id
    assert copies["1.1"].parent_id == old_copy.id
    assert sources["unresolved-2"].original_text == "The service shall retain the evidence."


async def test_reconciliation_preview_is_not_applicable_to_native_pdf_run(db_session, source_run):
    from app.api.requirements import preview_structured_import_reconciliation

    doc, run, user = source_run
    run.pipeline_version = "born_digital_v4"
    version = RequirementSetVersion(document_id=doc.id, version_number=1,
                                    status="draft", created_by=user.id)
    db_session.add(version)
    await db_session.flush()
    assert await preview_structured_import_reconciliation(doc.id, version.id, db_session, user) is None
