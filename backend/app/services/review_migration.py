from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.requirement import Requirement, RequirementStatus
from app.models.review import ReviewItem, ReviewItemComment, ReviewItemEvidenceFile
from app.schemas.program import BaselineMigrationDeltaItem, ProjectMigrationChangedDecision


class ReviewMigrationCloneError(Exception):
    pass


class ReviewMigrationDecisionError(ValueError):
    pass


@dataclass
class BaselineMigrationComparison:
    matched: list[BaselineMigrationDeltaItem] = field(default_factory=list)
    changed: list[BaselineMigrationDeltaItem] = field(default_factory=list)
    added: list[BaselineMigrationDeltaItem] = field(default_factory=list)
    removed: list[BaselineMigrationDeltaItem] = field(default_factory=list)


def requirement_changed(previous: Requirement, target: Requirement) -> bool:
    return previous.text != target.text or previous.requirement_type != target.requirement_type


def should_carry_forward_requirement(
    target: Requirement,
    previous: Requirement,
    changed_actions: Mapping[uuid.UUID, str],
) -> bool:
    return (
        not requirement_changed(previous, target)
        or changed_actions.get(target.id) == "carry_forward"
    )


def compare_baseline_requirements(
    target_requirements: Iterable[Requirement],
    previous_lookup: Mapping[tuple[Optional[uuid.UUID], str], tuple[ReviewItem, Requirement]],
    set_names: Mapping[uuid.UUID, str],
) -> BaselineMigrationComparison:
    """Compare scoped target requirements with a locked cycle, including renamed references."""
    target_lookup = {
        (requirement.document_id, requirement.reference_id): requirement
        for requirement in target_requirements
    }
    previous_by_id = {
        requirement.id: (item, requirement) for item, requirement in previous_lookup.values()
    }
    comparison = BaselineMigrationComparison()
    matched_old_ids: set[uuid.UUID] = set()

    for key, requirement in target_lookup.items():
        previous = previous_lookup.get(key)
        if previous is None and requirement.source_requirement_id is not None:
            previous = previous_by_id.get(requirement.source_requirement_id)
        if previous is None:
            comparison.added.append(
                BaselineMigrationDeltaItem(
                    document_id=requirement.document_id,
                    set_name=set_names.get(requirement.document_id),
                    reference_id=requirement.reference_id,
                    new_requirement_id=requirement.id,
                    new_text=requirement.text,
                )
            )
            continue

        _, old_requirement = previous
        matched_old_ids.add(old_requirement.id)
        delta = BaselineMigrationDeltaItem(
            document_id=requirement.document_id,
            set_name=set_names.get(requirement.document_id),
            reference_id=requirement.reference_id,
            old_requirement_id=old_requirement.id,
            new_requirement_id=requirement.id,
            old_text=old_requirement.text,
            new_text=requirement.text,
        )
        (
            comparison.changed
            if requirement_changed(old_requirement, requirement)
            else comparison.matched
        ).append(delta)

    for key, (_, old_requirement) in previous_lookup.items():
        if old_requirement.id in matched_old_ids or key in target_lookup:
            continue
        comparison.removed.append(
            BaselineMigrationDeltaItem(
                document_id=old_requirement.document_id,
                reference_id=old_requirement.reference_id,
                old_requirement_id=old_requirement.id,
                old_text=old_requirement.text,
            )
        )
    return comparison


def resolve_project_changed_decisions(
    changed_items: list[dict],
    decisions: list[ProjectMigrationChangedDecision],
) -> dict[uuid.UUID, str]:
    changed_by_id = {uuid.UUID(item["new_requirement_id"]): item for item in changed_items}
    changed_ids_by_reference: dict[str, list[uuid.UUID]] = {}
    for requirement_id, item in changed_by_id.items():
        changed_ids_by_reference.setdefault(item["reference_id"], []).append(requirement_id)

    resolved: dict[uuid.UUID, str] = {}
    for decision in decisions:
        if decision.new_requirement_id is not None:
            requirement_id = decision.new_requirement_id
            if requirement_id not in changed_by_id:
                raise ReviewMigrationDecisionError("Changed requirement ID is not in the preview")
            if (
                decision.reference_id is not None
                and decision.reference_id != changed_by_id[requirement_id]["reference_id"]
            ):
                raise ReviewMigrationDecisionError("Changed requirement ID and reference disagree")
        else:
            try:
                candidate_id = uuid.UUID(decision.reference_id) if decision.reference_id else None
            except ValueError:
                candidate_id = None
            if candidate_id in changed_by_id:
                requirement_id = candidate_id
            else:
                matches = changed_ids_by_reference.get(decision.reference_id, [])
                if len(matches) != 1:
                    raise ReviewMigrationDecisionError(
                        "Changed decision must identify one changed requirement by new requirement ID."
                    )
                requirement_id = matches[0]
        if requirement_id in resolved:
            raise ReviewMigrationDecisionError("Duplicate changed requirement decision")
        resolved[requirement_id] = decision.action
    return resolved


@dataclass
class ReviewMigrationSourceState:
    latest_status_by_requirement_id: dict[uuid.UUID, RequirementStatus]
    comments_by_item_id: dict[uuid.UUID, list[ReviewItemComment]]
    evidence_files_by_item_id: dict[uuid.UUID, list[ReviewItemEvidenceFile]]


@dataclass
class ReviewMigrationCloneResult:
    migrated_items: int = 0
    cloned_file_paths: list[str] = field(default_factory=list)


async def get_latest_requirement_status_map(
    db: AsyncSession,
    requirement_ids: list[uuid.UUID],
) -> dict[uuid.UUID, RequirementStatus]:
    if not requirement_ids:
        return {}

    latest_status_subq = (
        select(
            RequirementStatus.id.label("status_id"),
            RequirementStatus.requirement_id.label("requirement_id"),
            func.row_number()
            .over(
                partition_by=RequirementStatus.requirement_id,
                order_by=(RequirementStatus.changed_at.desc(), RequirementStatus.id.desc()),
            )
            .label("rn"),
        )
        .where(RequirementStatus.requirement_id.in_(requirement_ids))
        .subquery()
    )

    result = await db.execute(
        select(RequirementStatus).join(
            latest_status_subq,
            and_(
                RequirementStatus.id == latest_status_subq.c.status_id,
                latest_status_subq.c.rn == 1,
            ),
        )
    )
    return {status.requirement_id: status for status in result.scalars().all()}


def build_carried_requirement_status(
    source_status: RequirementStatus,
    target_requirement_id: uuid.UUID,
    changed_by: uuid.UUID,
) -> RequirementStatus:
    return RequirementStatus(
        requirement_id=target_requirement_id,
        status=source_status.status,
        assigned_to=source_status.assigned_to,
        comment=source_status.comment or "",
        changed_by=changed_by,
        changed_at=datetime.now(timezone.utc),
    )


async def load_review_migration_source_state(
    db: AsyncSession,
    source_pairs: Iterable[tuple[ReviewItem, Requirement]],
) -> ReviewMigrationSourceState:
    pairs = list(source_pairs)
    item_ids = list({item.id for item, _ in pairs})
    requirement_ids = list({requirement.id for _, requirement in pairs})

    latest_status_by_requirement_id = await get_latest_requirement_status_map(db, requirement_ids)

    comments_by_item_id: dict[uuid.UUID, list[ReviewItemComment]] = {
        item_id: [] for item_id in item_ids
    }
    evidence_files_by_item_id: dict[uuid.UUID, list[ReviewItemEvidenceFile]] = {
        item_id: [] for item_id in item_ids
    }

    if item_ids:
        comments_result = await db.execute(
            select(ReviewItemComment)
            .where(ReviewItemComment.review_item_id.in_(item_ids))
            .order_by(ReviewItemComment.created_at.asc(), ReviewItemComment.id.asc())
        )
        for comment in comments_result.scalars().all():
            comments_by_item_id.setdefault(comment.review_item_id, []).append(comment)

        evidence_result = await db.execute(
            select(ReviewItemEvidenceFile)
            .where(ReviewItemEvidenceFile.review_item_id.in_(item_ids))
            .order_by(ReviewItemEvidenceFile.uploaded_at.asc(), ReviewItemEvidenceFile.id.asc())
        )
        for evidence_file in evidence_result.scalars().all():
            evidence_files_by_item_id.setdefault(evidence_file.review_item_id, []).append(
                evidence_file
            )

    return ReviewMigrationSourceState(
        latest_status_by_requirement_id=latest_status_by_requirement_id,
        comments_by_item_id=comments_by_item_id,
        evidence_files_by_item_id=evidence_files_by_item_id,
    )


def cleanup_cloned_files(file_paths: Iterable[str]) -> None:
    for file_path in file_paths:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


def _build_carried_review_item(
    source_item: ReviewItem,
    successor_cycle_id: uuid.UUID,
    target_requirement_id: uuid.UUID,
) -> ReviewItem:
    return ReviewItem(
        id=uuid.uuid4(),
        review_cycle_id=successor_cycle_id,
        requirement_id=target_requirement_id,
        review_status=source_item.review_status,
        assessment_status=source_item.assessment_status,
        assessment_rationale=source_item.assessment_rationale,
        assigned_reviewer_id=source_item.assigned_reviewer_id,
        responsible_user_id=source_item.responsible_user_id,
        reviewer_id=source_item.reviewer_id,
        review_comment=source_item.review_comment,
        review_evidence=source_item.review_evidence,
        jira_issue_key=source_item.jira_issue_key,
        jira_issue_url=source_item.jira_issue_url,
        jira_status=source_item.jira_status,
        jira_summary=source_item.jira_summary,
        jira_assignee=source_item.jira_assignee,
        jira_priority=source_item.jira_priority,
        jira_updated_at=source_item.jira_updated_at,
        jira_synced_at=source_item.jira_synced_at,
        jira_sync_error=source_item.jira_sync_error,
        reviewed_at=source_item.reviewed_at,
    )


def _clone_review_item_comment(
    source_comment: ReviewItemComment,
    target_item_id: uuid.UUID,
) -> ReviewItemComment:
    return ReviewItemComment(
        id=uuid.uuid4(),
        review_item_id=target_item_id,
        author_id=source_comment.author_id,
        body=source_comment.body,
        created_at=source_comment.created_at,
        updated_at=source_comment.updated_at,
    )


def _sanitize_evidence_filename(filename: str) -> str:
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    if safe_filename:
        return safe_filename
    extension = os.path.splitext(filename)[1]
    return f"evidence{extension}"


def _clone_review_item_evidence_file(
    source_file: ReviewItemEvidenceFile,
    target_item_id: uuid.UUID,
) -> tuple[ReviewItemEvidenceFile, str]:
    if not source_file.file_path or not os.path.exists(source_file.file_path):
        raise ReviewMigrationCloneError(
            f"Cannot carry forward evidence file '{source_file.filename}' because the source file is missing."
        )

    evidence_dir = os.path.join(settings.upload_dir, "review-item-evidence")
    os.makedirs(evidence_dir, exist_ok=True)

    safe_filename = _sanitize_evidence_filename(source_file.filename)
    destination_path = os.path.join(evidence_dir, f"{uuid.uuid4()}_{safe_filename}")

    try:
        shutil.copy2(source_file.file_path, destination_path)
    except OSError as exc:
        if os.path.exists(destination_path):
            os.remove(destination_path)
        raise ReviewMigrationCloneError(
            f"Cannot carry forward evidence file '{source_file.filename}' because it could not be copied."
        ) from exc

    return (
        ReviewItemEvidenceFile(
            id=uuid.uuid4(),
            review_item_id=target_item_id,
            filename=source_file.filename,
            file_path=destination_path,
            description=source_file.description,
            uploaded_by=source_file.uploaded_by,
            uploaded_at=source_file.uploaded_at,
        ),
        destination_path,
    )


async def clone_review_cycle_items_for_migration(
    *,
    db: AsyncSession,
    successor_cycle_id: uuid.UUID,
    target_requirements: Iterable[Requirement],
    previous_lookup: Mapping[tuple[Optional[uuid.UUID], str], tuple[ReviewItem, Requirement]],
    previous_lookup_by_source_id: Mapping[uuid.UUID, tuple[ReviewItem, Requirement]],
    should_carry_forward: Callable[[Requirement, ReviewItem, Requirement], bool],
    default_review_state_for_requirement: Callable[[Requirement], tuple[str, Optional[str]]],
    current_user_id: uuid.UUID,
) -> ReviewMigrationCloneResult:
    source_state = await load_review_migration_source_state(db, previous_lookup.values())
    result = ReviewMigrationCloneResult()

    try:
        for requirement in target_requirements:
            previous = previous_lookup.get((requirement.document_id, requirement.reference_id))
            if previous is None and requirement.source_requirement_id is not None:
                previous = previous_lookup_by_source_id.get(requirement.source_requirement_id)

            if previous is not None:
                previous_item, previous_requirement = previous
                if should_carry_forward(requirement, previous_item, previous_requirement):
                    new_item = _build_carried_review_item(
                        previous_item,
                        successor_cycle_id,
                        requirement.id,
                    )
                    changed = requirement_changed(previous_requirement, requirement)
                    if changed:
                        # Reuse the evidence and working context, but never treat an
                        # assessment of the old wording as approval of the new one.
                        new_item.review_status = "pending"
                        new_item.assessment_status = "not_started"
                        new_item.assessment_rationale = None
                        new_item.reviewer_id = None
                        new_item.reviewed_at = None
                    db.add(new_item)

                    source_status = source_state.latest_status_by_requirement_id.get(
                        previous_requirement.id
                    )
                    if new_item.assessment_status is None:
                        new_item.assessment_status = (
                            source_status.status if source_status else "not_started"
                        )
                        new_item.assessment_rationale = (
                            source_status.comment if source_status else None
                        )
                    if source_status is not None and not changed:
                        db.add(
                            build_carried_requirement_status(
                                source_status,
                                requirement.id,
                                current_user_id,
                            )
                        )

                    comment_ids = {}
                    for comment in source_state.comments_by_item_id.get(previous_item.id, []):
                        cloned_comment = _clone_review_item_comment(comment, new_item.id)
                        comment_ids[comment.id] = cloned_comment.id
                        db.add(cloned_comment)
                    await db.flush()

                    for evidence_file in source_state.evidence_files_by_item_id.get(
                        previous_item.id,
                        [],
                    ):
                        cloned_file, cloned_path = _clone_review_item_evidence_file(
                            evidence_file,
                            new_item.id,
                        )
                        cloned_file.comment_id = comment_ids.get(evidence_file.comment_id)
                        db.add(cloned_file)
                        result.cloned_file_paths.append(cloned_path)

                    result.migrated_items += 1
                    continue

            review_status, review_comment = default_review_state_for_requirement(requirement)
            db.add(
                ReviewItem(
                    id=uuid.uuid4(),
                    review_cycle_id=successor_cycle_id,
                    requirement_id=requirement.id,
                    review_status=review_status,
                    assessment_status="not_started",
                    review_comment=review_comment,
                )
            )
            result.migrated_items += 1
    except Exception:
        cleanup_cloned_files(result.cloned_file_paths)
        raise

    return result
