import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

Kind = Literal[
    "licence_application",
    "certification",
    "pre_audit",
    "audit",
    "evidence_collection",
    "questionnaire",
]
FieldType = Literal["text", "multiline", "yes_no", "date", "number", "choice", "evidence"]
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class RequirementFieldSource(BaseModel):
    kind: Literal["requirement", "extracted_requirement"] = "requirement"
    document_id: uuid.UUID
    document_name: str = Field(max_length=500)
    document_status: str = Field(max_length=30)
    jurisdiction_id: uuid.UUID
    requirement_id: uuid.UUID | None = None
    extracted_requirement_id: uuid.UUID | None = None
    requirement_set_version_id: uuid.UUID | None = None
    version_number: int | None = None
    version_status: str | None = Field(default=None, max_length=30)
    reference_id: str = Field(max_length=100)
    source_extraction_id: uuid.UUID | None = None
    extraction_run_id: uuid.UUID | None = None
    extraction_status: str | None = Field(default=None, max_length=30)
    extraction_review_status: str | None = Field(default=None, max_length=30)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def source_identity(self):
        if self.kind == "requirement" and (
            self.requirement_id is None or self.extracted_requirement_id is not None
        ):
            raise ValueError("Requirement source needs a requirement ID")
        if self.kind == "extracted_requirement" and (
            self.extracted_requirement_id is None
            or self.requirement_id is not None
            or self.extraction_run_id is None
            or self.requirement_set_version_id is not None
        ):
            raise ValueError("Extracted source needs an extraction item and run")
        return self


class PreparationField(BaseModel):
    key: str = Field(max_length=64)
    label: str = Field(max_length=2000)
    section: str = Field(default="General", max_length=100)
    help_text: str | None = Field(default=None, max_length=10000)
    type: FieldType
    required: bool = True
    options: list[str] = Field(default_factory=list)
    reuse_key: str | None = Field(default=None, max_length=100)
    source: RequirementFieldSource | None = None

    @field_validator("key", "reuse_key")
    @classmethod
    def safe_identifier(cls, value: str | None) -> str | None:
        if value is not None and not IDENTIFIER.fullmatch(value):
            raise ValueError("Must be a safe identifier")
        return value

    @field_validator("label", "section")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_options(self):
        if self.type == "choice":
            if not 1 <= len(self.options) <= 50 or any(
                not x.strip() or len(x) > 255 for x in self.options
            ):
                raise ValueError("Choice needs 1 to 50 nonblank options")
            if len({x.strip() for x in self.options}) != len(self.options):
                raise ValueError("Choice options must be distinct")
        elif self.options:
            raise ValueError("Only choice fields may have options")
        return self


class TemplateFields(BaseModel):
    fields: list[PreparationField] = Field(max_length=500)

    @field_validator("fields")
    @classmethod
    def unique_keys(cls, fields: list[PreparationField]) -> list[PreparationField]:
        keys = [field.key for field in fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Field keys must be unique")
        return fields


class TemplateCreate(TemplateFields):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    kind: Kind

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class TemplatePatch(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    kind: Kind | None = None
    fields: list[PreparationField] | None = Field(default=None, max_length=500)
    active: bool | None = None

    @field_validator("fields")
    @classmethod
    def unique_keys(cls, fields: list[PreparationField] | None):
        if fields is not None:
            TemplateFields(fields=fields)
        return fields

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip() if value is not None else None


class TemplateOut(TemplateCreate):
    id: uuid.UUID
    revision: int
    active: bool
    created_at: datetime
    updated_at: datetime


class StarterOut(TemplateCreate):
    pass


class SpreadsheetPreview(BaseModel):
    sheets: list[str]
    sheet_name: str
    rows: list[list[str]]
    warnings: list[str]


class RequirementsPreviewSource(BaseModel):
    kind: Literal["requirements", "extracted_requirements"]
    document_id: uuid.UUID
    name: str
    status: str
    jurisdiction_id: uuid.UUID
    version_id: uuid.UUID | None
    version_number: int | None
    version_status: str | None
    has_source: bool
    extraction_run_id: uuid.UUID | None
    extraction_status: str | None


class UnavailableRequirement(BaseModel):
    requirement_id: uuid.UUID
    reference_id: str
    reason: str


class RequirementsPreview(BaseModel):
    source: RequirementsPreviewSource
    fields: list[PreparationField]
    unavailable: list[UnavailableRequirement]
    warnings: list[str]
    total: int
    skip: int
    limit: int


class CaseCreate(BaseModel):
    visibility: Literal["organisation", "restricted", "secret"] = "secret"
    template_id: uuid.UUID | None = None
    fields: list[PreparationField] | None = Field(default=None, max_length=500)
    original_evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    jurisdiction_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    project_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_form_source(self):
        if (self.template_id is None) == (self.fields is None):
            raise ValueError("Choose exactly one of a template or private fields")
        if self.fields is not None:
            TemplateFields(fields=self.fields)
        return self

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class CasePatch(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    project_id: uuid.UUID | None = None
    status: Literal["active", "archived"] | None = None
    fields: list[PreparationField] | None = Field(default=None, max_length=500)
    original_evidence_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip() if value is not None else None


class ResponsePut(BaseModel):
    expected_revision: int = Field(ge=1)
    value: StrictStr | StrictInt | StrictFloat | StrictBool | None = None
    not_applicable_reason: str | None = Field(default=None, max_length=2000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)

    @field_validator("value")
    @classmethod
    def bounded_string(cls, value):
        if isinstance(value, str) and len(value) > 10000:
            raise ValueError("Answer is too long")
        return value


class RevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class ReuseRequest(RevisionRequest):
    source_case_id: uuid.UUID
    source_field_key: str


class Blocker(BaseModel):
    field_key: str
    code: str
    message: str


class Readiness(BaseModel):
    required_count: int
    answered_count: int
    accepted_count: int
    blockers: list[Blocker]
    ready: bool


class ResponseOut(BaseModel):
    field_key: str
    value: str | float | bool | None
    not_applicable_reason: str | None
    evidence_ids: list[uuid.UUID]
    accepted_by: uuid.UUID | None
    accepted_at: datetime | None
    reused_from_case_id: uuid.UUID | None
    reused_from_field_key: str | None


class CaseOut(BaseModel):
    access: dict | None = None
    id: uuid.UUID
    name: str
    kind: Kind
    jurisdiction_id: uuid.UUID
    project_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    due_date: date | None
    status: Literal["active", "archived"]
    revision: int
    template_id: uuid.UUID | None
    template_name: str
    template_revision: int
    original_evidence_ids: list[uuid.UUID] = Field(default_factory=list)
    fields: list[PreparationField]
    created_at: datetime
    updated_at: datetime
    readiness: Readiness
    responses: list[ResponseOut]


class ReuseSuggestion(BaseModel):
    source_case_id: uuid.UUID
    source_case_name: str
    source_jurisdiction_id: uuid.UUID
    source_field_key: str
    value: str | float | bool | None
    accepted_at: datetime | None
