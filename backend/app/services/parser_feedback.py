from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.extraction import ExtractionRun
from app.models.requirement import ExtractionFeedback, ExtractedRequirement


@dataclass
class ParserTemplate:
    heading_style: str
    replacements: dict[str, str] = field(default_factory=dict)
    support_runs: int = 0


async def load_parser_template(
    db: AsyncSession,
    *,
    jurisdiction_id,
    organization_id,
    document_type: str,
    family_fingerprint: Optional[str],
) -> Optional[ParserTemplate]:
    if not family_fingerprint:
        return None

    run_query = (
        select(ExtractionFeedback.extraction_run_id)
        .join(ExtractionRun, ExtractionRun.id == ExtractionFeedback.extraction_run_id)
        .join(Document, Document.id == ExtractionRun.document_id)
        .where(
            and_(
                Document.jurisdiction_id == jurisdiction_id,
                Document.organization_id == organization_id,
                Document.document_type == document_type,
                ExtractionRun.family_fingerprint == family_fingerprint,
                ExtractionFeedback.action.in_(["accept", "edit"]),
            )
        )
        .distinct()
    )
    run_rows = await db.execute(run_query)
    run_ids = [row[0] for row in run_rows.all()]
    if len(run_ids) < 3:
        return None

    detail_query = (
        select(
            ExtractionFeedback.corrected_reference_id,
            ExtractionFeedback.corrected_text,
            ExtractedRequirement.reference_id,
            ExtractedRequirement.text,
        )
        .join(
            ExtractedRequirement,
            ExtractedRequirement.id == ExtractionFeedback.extracted_requirement_id,
        )
        .where(
            ExtractionFeedback.extraction_run_id.in_(run_ids),
            ExtractionFeedback.action.in_(["accept", "edit"]),
        )
    )
    detail_rows = (await db.execute(detail_query)).all()

    split_votes = 0
    inline_votes = 0
    replacement_candidates: dict[str, int] = {}

    for corrected_ref, corrected_text, original_ref, original_text in detail_rows:
        if corrected_ref and corrected_ref.count(".") >= 2:
            split_votes += 1
        elif corrected_ref:
            inline_votes += 1

        replacement = _extract_tt_replacement(original_ref or "", corrected_ref or "")
        if replacement:
            replacement_candidates[replacement] = replacement_candidates.get(replacement, 0) + 1
            continue

        replacement_from_text = _extract_tt_replacement_from_text(
            original_text or "", corrected_text or ""
        )
        if replacement_from_text:
            replacement_candidates[replacement_from_text] = (
                replacement_candidates.get(replacement_from_text, 0) + 1
            )

    replacements: dict[str, str] = {}
    if replacement_candidates:
        best = max(replacement_candidates.items(), key=lambda item: item[1])[0]
        replacements["tt"] = best

    heading_style = "split" if split_votes >= inline_votes else "inline"
    return ParserTemplate(
        heading_style=heading_style, replacements=replacements, support_runs=len(run_ids)
    )


def apply_parser_template(text: str, template: Optional[ParserTemplate]) -> str:
    if not template:
        return text

    output = text
    for source, target in template.replacements.items():
        if not source or source == target:
            continue
        output = re.sub(rf"\b{re.escape(source)}\b", target, output)
    return output


def _extract_tt_replacement(original_ref: str, corrected_ref: str) -> Optional[str]:
    if "tt" not in (original_ref or "").lower() or not corrected_ref:
        return None

    original_tokens = set(re.findall(r"\d+", original_ref))
    corrected_tokens = re.findall(r"\d+", corrected_ref)
    for token in corrected_tokens:
        if token not in original_tokens:
            return token
    return None


def _extract_tt_replacement_from_text(original_text: str, corrected_text: str) -> Optional[str]:
    if "tt" not in original_text.lower() or not corrected_text:
        return None
    corrected_numbers = re.findall(r"\b\d{1,3}\b", corrected_text)
    if not corrected_numbers:
        return None
    return corrected_numbers[0]
