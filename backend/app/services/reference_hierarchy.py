import uuid
from typing import Optional, Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.requirement import ExtractedRequirement, Requirement


def normalize_reference_id(reference_id: Optional[str]) -> str:
    return (reference_id or "").strip().rstrip(".")


def parent_reference_candidates(reference_id: Optional[str]) -> list[str]:
    normalized = normalize_reference_id(reference_id)
    if not normalized or "." not in normalized:
        return []

    parts = [part for part in normalized.split(".") if part]
    if len(parts) <= 1:
        return []

    return [".".join(parts[:end]) for end in range(len(parts) - 1, 0, -1)]


def normalize_reference_or_raise(reference_id: Optional[str], *, detail: str) -> str:
    normalized = normalize_reference_id(reference_id)
    if not normalized:
        raise ValueError(detail)
    return normalized


def _candidate_variants(candidates: Sequence[str]) -> list[str]:
    variants: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for variant in (candidate, f"{candidate}."):
            if variant in seen:
                continue
            seen.add(variant)
            variants.append(variant)
    return variants


async def _resolve_parent_id_by_reference(
    db: AsyncSession,
    *,
    reference_id: Optional[str],
    id_column,
    reference_column,
    sort_order_column,
    created_at_column,
    scope_filters: Sequence,
    exclude_id: Optional[uuid.UUID] = None,
) -> Optional[uuid.UUID]:
    candidates = parent_reference_candidates(reference_id)
    if not candidates:
        return None

    query = select(id_column, reference_column).where(
        and_(*scope_filters, reference_column.in_(_candidate_variants(candidates)))
    )
    if exclude_id is not None:
        query = query.where(id_column != exclude_id)

    query = query.order_by(sort_order_column.asc(), created_at_column.asc())
    result = await db.execute(query)

    id_by_reference: dict[str, uuid.UUID] = {}
    for row_id, row_reference in result.all():
        normalized_reference = normalize_reference_id(row_reference)
        if normalized_reference and normalized_reference not in id_by_reference:
            id_by_reference[normalized_reference] = row_id

    for candidate in candidates:
        parent_id = id_by_reference.get(candidate)
        if parent_id is not None:
            return parent_id
    return None


async def resolve_requirement_parent_id(
    db: AsyncSession,
    *,
    requirement_set_version_id: Optional[uuid.UUID],
    reference_id: Optional[str],
    exclude_requirement_id: Optional[uuid.UUID] = None,
) -> Optional[uuid.UUID]:
    if requirement_set_version_id is None:
        return None

    return await _resolve_parent_id_by_reference(
        db,
        reference_id=reference_id,
        id_column=Requirement.id,
        reference_column=Requirement.reference_id,
        sort_order_column=Requirement.sort_order,
        created_at_column=Requirement.created_at,
        scope_filters=[Requirement.requirement_set_version_id == requirement_set_version_id],
        exclude_id=exclude_requirement_id,
    )


async def resolve_extracted_requirement_parent_id(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    extraction_run_id: Optional[uuid.UUID],
    reference_id: Optional[str],
    exclude_extracted_requirement_id: Optional[uuid.UUID] = None,
) -> Optional[uuid.UUID]:
    scope_filters = [ExtractedRequirement.document_id == document_id]
    if extraction_run_id is not None:
        scope_filters.append(ExtractedRequirement.extraction_run_id == extraction_run_id)

    return await _resolve_parent_id_by_reference(
        db,
        reference_id=reference_id,
        id_column=ExtractedRequirement.id,
        reference_column=ExtractedRequirement.reference_id,
        sort_order_column=ExtractedRequirement.sort_order,
        created_at_column=ExtractedRequirement.created_at,
        scope_filters=scope_filters,
        exclude_id=exclude_extracted_requirement_id,
    )
