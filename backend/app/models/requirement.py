import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExtractedRequirement(Base):
    __tablename__ = "extracted_requirements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    extraction_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=True
    )
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(20), nullable=False, default="mandatory")
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("extracted_requirements.id"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    quality_auto_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parser_strategy: Mapped[str] = mapped_column(String(50), nullable=False, default="rule_based")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractionFeedback(Base):
    __tablename__ = "extraction_feedback"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=False
    )
    extracted_requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_requirements.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    corrected_reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    corrected_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False
    )
    source_extraction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("extracted_requirements.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    requirement_set_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("requirement_set_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_requirement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("requirements.id"), nullable=True, index=True
    )
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(20), nullable=False, default="mandatory")
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("requirements.id"), nullable=True
    )
    default_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequirementStatus(Base):
    __tablename__ = "requirement_statuses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_started")
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
