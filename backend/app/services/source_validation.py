"""Publication gates for complete, reviewable requirement baselines."""

from collections import Counter
import hashlib
import json
import re
from fastapi import HTTPException
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.program import RequirementSetVersion
from app.models.requirement import Requirement, ExtractedRequirement
from app.services.review_assurance import plain_text


def _fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def structured_baseline_reconciliation(db, version, document):
    """Compare the live structured run with a prepared version without rewriting edits."""
    run = await db.get(ExtractionRun, document.current_extraction_id) if document.current_extraction_id else None
    if run is None or run.pipeline_version != "opendataloader_v1":
        return None, [], []
    sources = list((await db.scalars(select(ExtractedRequirement).where(
        ExtractedRequirement.document_id == document.id,
        ExtractedRequirement.extraction_run_id == run.id,
        ExtractedRequirement.status != "rejected",
    ))).all())
    staged = list((await db.scalars(select(Requirement).where(
        Requirement.requirement_set_version_id == version.id,
    ))).all())
    active = [row for row in staged if row.active]
    source_by_id = {row.id: row for row in sources}
    linked = {}
    for row in active:
        if row.source_extraction_id:
            linked.setdefault(row.source_extraction_id, []).append(row)
    missing = [row for row in sources if row.id not in linked]
    stale = [row for row in active if row.source_extraction_id and row.source_extraction_id not in source_by_id]
    duplicate = [str(source_id) for source_id, copies in linked.items() if len(copies) > 1]
    staged_by_id = {row.id: row for row in active}
    differences = []
    for source in sources:
        copies = linked.get(source.id, [])
        if len(copies) != 1:
            continue
        copy = copies[0]
        draft_parent = staged_by_id.get(copy.parent_id)
        values = {
            "reference_id": (source.reference_id, copy.reference_id),
            "title": (source.title, copy.title),
            "text": (source.text, copy.text),
            "requirement_type": (source.requirement_type, copy.requirement_type),
        }
        changed = {field: {"source": left, "draft": right}
                   for field, (left, right) in values.items() if left != right}
        draft_parent_source_id = draft_parent.source_extraction_id if draft_parent else None
        if source.parent_id != draft_parent_source_id:
            source_parent = source_by_id.get(source.parent_id)
            changed["parent_reference"] = {
                "source": source_parent.reference_id if source_parent else None,
                "draft": draft_parent.reference_id if draft_parent else None,
            }
        if changed:
            differences.append({"source_id": str(source.id), "draft_id": str(copy.id),
                                "reference_id": source.reference_id, "fields": changed})
    source_state = sorted((str(row.id), row.reference_id, row.title, row.text,
                           row.requirement_type, str(row.parent_id) if row.parent_id else None)
                          for row in sources)
    draft_state = sorted((str(row.id), str(row.source_extraction_id) if row.source_extraction_id else None,
                          row.reference_id, row.title, row.text, row.requirement_type,
                          str(row.parent_id) if row.parent_id else None, row.active)
                         for row in staged)
    source_fingerprint = _fingerprint([str(run.id), source_state])
    draft_fingerprint = _fingerprint(draft_state)
    reconciled = not (missing or stale or duplicate or differences)
    if differences and not (missing or stale or duplicate):
        records = (await db.scalars(select(AuditLog.new_value).where(
            AuditLog.organization_id == document.organization_id,
            AuditLog.entity_type == "structured_baseline_reconciliation",
            AuditLog.entity_id == str(version.id),
            AuditLog.action == "reconcile",
        ))).all()
        reconciled = any(
            (value := json.loads(record or "{}")).get("source_fingerprint") == source_fingerprint
            and value.get("draft_fingerprint") == draft_fingerprint
            for record in records
        )
    report = {"source_fingerprint": source_fingerprint,
              "draft_fingerprint": draft_fingerprint,
              "missing": [{"id": str(row.id), "reference_id": row.reference_id} for row in missing],
              "stale": [{"id": str(row.id), "reference_id": row.reference_id} for row in stale],
              "duplicate": duplicate, "differences": differences, "reconciled": reconciled}
    return report, sources, staged


def structure_errors(rows):
    errors = []
    refs = Counter(r.reference_id.strip().casefold() for r in rows)
    duplicates = [ref for ref, count in refs.items() if count > 1]
    if duplicates:
        errors.append("Duplicate references: " + ", ".join(duplicates[:10]))
    lookup = {r.id: r for r in rows}
    for row in rows:
        if not row.reference_id.strip():
            errors.append("A requirement has no reference")
        if row.requirement_type not in {
            "mandatory",
            "recommended",
            "informational",
            "not_applicable",
        }:
            errors.append(f"{row.reference_id}: unknown requirement type")
        if row.requirement_type in {"mandatory", "recommended"} and not plain_text(row.text):
            errors.append(f"{row.reference_id}: requirement text is empty")
        seen = {row.id}
        parent = row.parent_id
        while parent:
            if parent not in lookup:
                errors.append(f"{row.reference_id}: parent is outside the active requirement set")
                break
            if parent in seen:
                errors.append(f"{row.reference_id}: circular hierarchy")
                break
            seen.add(parent)
            parent = lookup[parent].parent_id
    return list(dict.fromkeys(errors))


def numbered_hierarchy_errors(rows, *, require_numeric=False, required_source_ids=None):
    """Structured numeric references must describe the persisted immediate-parent tree."""
    by_ref = {row.reference_id.strip().rstrip("."): row for row in rows}
    errors = []
    for ref, row in by_ref.items():
        if not re.fullmatch(r"\d+(?:\.\d+)*", ref):
            if (require_numeric or ref.startswith("unresolved-") or
                    (required_source_ids and getattr(row, "source_extraction_id", None) in required_source_ids)):
                errors.append(f"{ref}: resolve or exclude the unnumbered source candidate")
            continue
        parent_ref = ref.rpartition(".")[0]
        if parent_ref and parent_ref not in by_ref:
            errors.append(f"{ref}: missing immediate parent {parent_ref}")
        elif row.parent_id != (by_ref[parent_ref].id if parent_ref else None):
            errors.append(f"{ref}: hierarchy must link to {parent_ref or 'the root'}")
    return errors


async def validate_baseline(db, version_id):
    version = await db.get(RequirementSetVersion, version_id)
    document = await db.get(Document, version.document_id) if version else None
    if document is not None:
        await db.refresh(document, with_for_update=True)
        await db.refresh(version, with_for_update=True)
    rows = list(
        (
            await db.execute(
                select(Requirement).where(
                    Requirement.requirement_set_version_id == version_id,
                    Requirement.active.is_(True),
                )
            )
        ).scalars()
    )
    errors = structure_errors(rows) if rows else ["The requirement set is empty"]
    structured_source_ids = set((await db.scalars(
        select(ExtractedRequirement.id).join(
            Requirement, Requirement.source_extraction_id == ExtractedRequirement.id
        ).where(Requirement.requirement_set_version_id == version_id,
                ExtractedRequirement.parser_strategy == "opendataloader")
    )).all())
    if structured_source_ids:
        errors.extend(numbered_hierarchy_errors(rows, required_source_ids=structured_source_ids))
    run = await db.get(ExtractionRun, document.current_extraction_id) if document and document.current_extraction_id else None
    if document is not None and (structured_source_ids or (run and run.pipeline_version == "opendataloader_v1")):
        # A reviewer can replace every copied row. The current structured run
        # still has to be complete and resolved before version publication.
        await validate_extraction_complete(db, document)
        if structured_source_ids and (run is None or run.pipeline_version != "opendataloader_v1"):
            errors.append("The prepared draft links to a superseded structured extraction run.")
        if run and run.pipeline_version == "opendataloader_v1":
            report, _, _ = await structured_baseline_reconciliation(db, version, document)
            if report and not report["reconciled"]:
                errors.append("Prepared draft differs from the current structured source. Open Edit Requirements and reconcile source changes before submission or approval.")
    if errors:
        raise HTTPException(
            422,
            {
                "message": "Resolve source quality issues before submission or approval.",
                "gates": [{"message": x} for x in errors[:25]],
            },
        )


async def validate_extraction_complete(db, document):
    # Submission and approval must inspect the same current run as recovery
    # decisions and extraction reruns while holding the document row lock.
    await db.refresh(document, with_for_update=True)
    if document.current_extraction_id:
        run = await db.get(ExtractionRun, document.current_extraction_id)
        if not run or run.document_id != document.id or run.status != "completed":
            raise HTTPException(
                409, "Wait for a successful extraction before submitting this PDF for approval."
            )
        if not run.total_pages or run.current_page < run.total_pages:
            raise HTTPException(
                409,
                "The extraction has not covered every PDF page. Run extraction again before approval.",
            )

        if run.pipeline_version == "opendataloader_v1":
            rows = list((await db.scalars(select(ExtractedRequirement).where(
                ExtractedRequirement.extraction_run_id == run.id,
                ExtractedRequirement.status != "rejected",
            ))).all())
            errors = structure_errors(rows) + numbered_hierarchy_errors(rows, require_numeric=True)
            if any(row.needs_review for row in rows):
                errors.append("Resolve all flagged source candidates before approval")
            if errors:
                raise HTTPException(422, {
                    "message": "Repair the extracted hierarchy before submission or approval.",
                    "gates": [{"message": message} for message in errors[:25]],
                })
