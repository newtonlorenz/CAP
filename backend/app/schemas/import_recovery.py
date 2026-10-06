"""Explicit decisions on ambiguous structured import candidates."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ImportRecoveryDecision(BaseModel):
    action: Literal["correct", "attach_continuation", "exclude"]
    reference_id: str | None = Field(default=None, max_length=100)
    parent_reference: str | None = Field(default=None, max_length=100)
    target_id: uuid.UUID | None = None
    corrected_text: str | None = None
    requirement_type: Literal["mandatory", "recommended", "informational", "not_applicable"] | None = None


class ImportReconciliationRequest(BaseModel):
    source_fingerprint: str
    draft_fingerprint: str
