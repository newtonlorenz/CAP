import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ExtractionRunResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    total_pages: Optional[int]
    current_page: int
    requirements_found: int
    error_message: Optional[str]
    error_page: Optional[int]
    ai_provider: str
    ai_model: str
    pipeline_version: str
    ocr_applied: bool
    ocr_pages: int
    warning_count: int
    parseability_score: Optional[float] = None
    fallback_trigger_reason: Optional[str] = None
    strategy_counts: Optional[dict[str, int]] = None
    diagnostics_available: bool = False
    started_at: Optional[datetime]
    last_progress_at: Optional[datetime] = None
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractionProgressResponse(BaseModel):
    """Lightweight response for polling extraction progress."""

    status: str
    total_pages: Optional[int]
    current_page: int
    requirements_found: int
    error_message: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ExtractionRunDiagnosticsResponse(BaseModel):
    extraction_run_id: uuid.UUID
    document_id: uuid.UUID
    parseability_score: Optional[float]
    fallback_trigger_reason: Optional[str]
    strategy_counts: Optional[dict[str, int]]
    decision_payload: Optional[dict[str, Any]]
    page_metrics: Optional[list[dict[str, Any]]]
    canonical_blocks: Optional[list[dict[str, Any]]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
