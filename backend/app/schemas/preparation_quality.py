"""Bounded, transient source-only form preview enhancement."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Column = Literal["question", "reference", "section", "type", "options", "required", "help"]
FieldType = Literal["text", "multiline", "yes_no", "date", "number", "choice", "evidence"]


class PreviewSourceRow(BaseModel):
    row_index: int = Field(ge=0, le=10000)
    question: str = Field(max_length=2000)
    help: str = Field(default="", max_length=2000)
    explicit_type: bool = False
    explicit_required: bool = False


class ImportEnhancementRequest(BaseModel):
    headers: list[str] = Field(max_length=100)
    rows: list[PreviewSourceRow] = Field(max_length=100)
    header_row: int = Field(ge=0, le=10000)
    mapping: dict[Column, int]
    external_processing_confirmed: bool = False
    settings_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def bounded(self):
        if any(
            text.lstrip().startswith("=")
            for text in self.headers
            + [value for row in self.rows for value in (row.question, row.help)]
        ):
            raise ValueError("Formula cells cannot be enhanced")
        if any(len(header) > 255 for header in self.headers):
            raise ValueError("Column headings must be at most 255 characters")
        if any(index < -1 or index >= len(self.headers) for index in self.mapping.values()):
            raise ValueError("Column mapping is outside the preview")
        if len({row.row_index for row in self.rows}) != len(self.rows):
            raise ValueError("Row indices must be unique")
        if sum(len(row.question) + len(row.help) for row in self.rows) > 50000:
            raise ValueError("Preview text exceeds the enhancement limit")
        return self


class FieldSuggestion(BaseModel):
    row_index: int
    type: FieldType | None = None
    required: bool | None = None
    duplicate_of: int | None = None
    confidence: float


class ImportEnhancementResponse(BaseModel):
    status: Literal["completed", "partial", "skipped"]
    suggested_mapping: dict[Column, int] = Field(default_factory=dict)
    field_suggestions: list[FieldSuggestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    model: str | None = None
    input_fingerprint: str
