import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class JurisdictionResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    regulator_name: Optional[str] = None
    report_header_text: Optional[str] = None
    pack_status: Optional[Literal["published", "scaffold", "draft"]] = None
    pack_version: Optional[str] = None
    parser_mode: Optional[str] = None
    supports_deterministic_import: Optional[bool] = None
    coverage_notes: Optional[str] = None
    active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JurisdictionCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    regulator_name: Optional[str] = Field(default=None, max_length=255)
    report_header_text: Optional[str] = None
    active: bool = True


class JurisdictionUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=20)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    regulator_name: Optional[str] = Field(default=None, max_length=255)
    report_header_text: Optional[str] = None
    active: Optional[bool] = None
