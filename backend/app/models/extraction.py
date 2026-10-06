import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dispatch_after: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requirements_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(40), nullable=False, default="born_digital_v4")
    ocr_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    ocr_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    family_fingerprint: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    parseability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fallback_trigger_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_counts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    diagnostics_available: Mapped[bool] = mapped_column(nullable=False, default=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractionRunDiagnostic(Base):
    __tablename__ = "extraction_run_diagnostics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=False, unique=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    parseability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fallback_trigger_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_counts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    decision_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    page_metrics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    canonical_blocks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
