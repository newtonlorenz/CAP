import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewCycle(Base):
    __tablename__ = "review_cycles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False
    )
    certification_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=True, index=True
    )
    change_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("change_entries.id"), nullable=True, index=True
    )
    predecessor_cycle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=True, index=True
    )
    cycle_type: Mapped[str] = mapped_column(String(30), nullable=False, default="operational")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False, default="all")
    scope_filter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("snapshots.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    assigned_reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    responsible_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    assessment_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    assessment_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    jira_issue_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    jira_issue_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    jira_status: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    jira_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_assignee: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jira_priority: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    jira_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jira_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jira_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewItemComment(Base):
    __tablename__ = "review_item_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_items.id"), nullable=False)
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewItemEvidenceFile(Base):
    __tablename__ = "review_item_evidence_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_items.id"), nullable=False)
    comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("review_item_comments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    total_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidenced_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
