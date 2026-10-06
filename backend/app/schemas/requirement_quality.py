import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class QualityRunCreate(BaseModel):
    extraction_run_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    allow_external_ai: bool = False
    jev_settings_revision: int | None = None

    @model_validator(mode="after")
    def exclusive_target(self):
        if self.extraction_run_id and self.version_id:
            raise ValueError("Select either an extraction run or a requirement-set version")
        return self


class QualityFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    requirement_id: str | None
    kind: str
    source_page: int | None
    source_excerpt: str | None
    source_span_id: str | None
    before: dict
    after: dict
    answers: dict
    auto_eligible: bool
    applied: bool


class QualityRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    extraction_run_id: uuid.UUID | None
    version_id: uuid.UUID | None
    mode: str
    status: str
    model: str
    settings_revision: int
    question_policy_version: str
    coverage: dict[str, Any]
    usage: dict[str, Any]
    warnings: list[str]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    findings: list[QualityFindingResponse] = []
