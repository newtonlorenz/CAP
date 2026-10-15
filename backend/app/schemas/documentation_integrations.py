"""Explicit import choices and bounded optional processing requests."""

import uuid
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportChoice(StrictModel):
    row_key: str = Field(min_length=1, max_length=300)
    action: Literal["create", "update", "skip"]
    expectation_id: uuid.UUID | None = None
    expectation_revision: int | None = Field(default=None, ge=1)


class ImportConfirm(StrictModel):
    revision: int = Field(ge=1)
    choices: list[ImportChoice] = Field(min_length=1, max_length=2000)


class SnapshotCreate(StrictModel):
    project_id: uuid.UUID | None = None
    revision: int = Field(ge=1)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class SuggestionCreate(StrictModel):
    revision: int = Field(ge=1)
    input_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    mode: Literal["local", "jev", "ai"] = "local"
    external_processing_confirmed: bool = False
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    expectation_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)


class SuggestionResume(StrictModel):
    external_processing_confirmed: bool = False


class SuggestionDecision(StrictModel):
    index: int = Field(ge=0)
    decision: Literal["apply", "edit", "dismiss"]
    category: str | None = Field(default=None, max_length=100)
    requirement_id: uuid.UUID | None = None
    rationale: str | None = Field(default=None, max_length=10000)


class AuditorImportChoice(ImportChoice):
    @model_validator(mode="after")
    def explicit_mapping(self):
        if self.action == "update":
            if self.expectation_id is None or self.expectation_revision is None:
                raise ValueError("Mapping requires an explicit documentation row and its revision")
        elif self.expectation_id is not None or self.expectation_revision is not None:
            raise ValueError("Creation and skipping must not include a documentation mapping")
        return self


class AuditorImport(StrictModel):
    revision: int = Field(ge=1)
    case_id: uuid.UUID
    list_revision: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(min_length=1, max_length=100)
    direction: Literal["operator_input", "auditor_output"] = "operator_input"
    period: str = Field(default="", max_length=255)
    choices: list[AuditorImportChoice] = Field(min_length=1, max_length=2000)


class SheetMapping(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    header_row: int = Field(ge=1, le=2000)
    mapping: dict[
        Literal[
            "required_documentation",
            "title",
            "description",
            "category",
            "source_reference",
            "document_name",
        ],
        int,
    ] = Field(max_length=6)


class ImportRemap(StrictModel):
    sheets: list[SheetMapping] = Field(min_length=1, max_length=100)
