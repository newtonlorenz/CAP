"""Durable, document-scoped source quality checks and their audit evidence."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RequirementQualityRun(Base):
    __tablename__ = "requirement_quality_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE")
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("requirement_set_versions.id", ondelete="CASCADE")
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(String(20), default="recheck")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    model: Mapped[str] = mapped_column(String(100))
    settings_revision: Mapped[int] = mapped_column(Integer)
    question_policy_version: Mapped[str] = mapped_column(String(40), default="source_quality_v1")
    source_sha256: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    dispatch_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_token: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RequirementQualityFinding(Base):
    __tablename__ = "requirement_quality_findings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_quality_runs.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(50))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    source_span_id: Mapped[str | None] = mapped_column(String(100))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    auto_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
