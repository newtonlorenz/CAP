"""Explicit revision-bound requests for the documentation register."""
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator


PreservedText = Annotated[str, StringConstraints(strip_whitespace=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Revision(Input):
    revision: int = Field(ge=1)


class RegisterCreate(Input):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=20000)
    jurisdiction_id: uuid.UUID
    visibility: Literal["secret", "restricted", "organisation"] = "secret"


class RegisterPatch(Revision):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=20000)


class SectionCreate(Revision):
    name: str = Field(min_length=1, max_length=255)
    position: int | None = Field(None, ge=0)


class SectionPatch(Revision):
    name: str | None = Field(None, min_length=1, max_length=255)
    position: int | None = Field(None, ge=0)


class ExpectationCreate(Input):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: PreservedText = Field("", max_length=50000)
    section_id: uuid.UUID | None = None
    required_documentation: PreservedText | None = Field(None, max_length=100000)
    document_name: PreservedText | None = Field(None, max_length=50000)
    category: str | None = Field(None, max_length=100)
    interpretation: str | None = Field(None, max_length=20000)
    basis: str | None = Field(None, max_length=20000)
    source_reference: PreservedText | None = Field(None, max_length=20000)
    applicability: Literal["unknown", "applicable", "not_applicable"] = "unknown"
    not_applicable_reason: str | None = Field(None, max_length=20000)
    responsible_party: str | None = Field(None, max_length=255)
    owner_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    review_cycle_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def reason_required(self):
        if self.title is None:
            if not self.required_documentation or not self.required_documentation.strip():
                raise ValueError("Provide required documentation or a title")
            self.title = " ".join(self.required_documentation.split())[:500]
        if self.applicability == "not_applicable" and not self.not_applicable_reason:
            raise ValueError("Explain why this expectation is not applicable")
        return self


class ExpectationPatch(Revision):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: PreservedText | None = Field(None, max_length=50000)
    section_id: uuid.UUID | None = None
    required_documentation: PreservedText | None = Field(None, max_length=100000)
    document_name: PreservedText | None = Field(None, max_length=50000)
    category: str | None = Field(None, max_length=100)
    interpretation: str | None = Field(None, max_length=20000)
    basis: str | None = Field(None, max_length=20000)
    source_reference: PreservedText | None = Field(None, max_length=20000)
    applicability: Literal["unknown", "applicable", "not_applicable"] | None = None
    not_applicable_reason: str | None = Field(None, max_length=20000)
    responsible_party: str | None = Field(None, max_length=255)
    owner_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class RequirementLink(Input):
    requirement_id: uuid.UUID
    requirement_set_version_id: uuid.UUID


class RequirementLinks(Revision):
    links: list[RequirementLink] = Field(max_length=500)


class CoverageLink(Input):
    evidence_id: uuid.UUID
    locator: str | None = Field(None, max_length=20000)
    scope: str | None = Field(None, max_length=20000)
    period: str | None = Field(None, max_length=255)
    rationale: str = Field(min_length=1, max_length=20000)


class CoverageLinks(Revision):
    links: list[CoverageLink] = Field(max_length=500)


class CoverageReview(Revision):
    status: Literal["unreviewed", "partial", "sufficient"]
    rationale: str = Field(min_length=1, max_length=20000)


class GroupCreate(Input):
    title: str = Field(min_length=1, max_length=255)
    evidence_id: uuid.UUID


class GroupVersion(Revision):
    evidence_id: uuid.UUID


class JiraReference(Input):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]*-[1-9][0-9]*$", max_length=100)
    url: HttpUrl | None = None


class ReferenceLinks(Revision):
    component_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    change_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    jira_references: list[JiraReference] = Field(default_factory=list, max_length=200)


class AuditorRequestCreate(Input):
    case_id: uuid.UUID
    field_key: str = Field(min_length=1, max_length=64)
    project_id: uuid.UUID
    request_id: str = Field(min_length=1, max_length=255)
    request_wording: str = Field(min_length=1, max_length=50000)
    list_revision: str = Field(min_length=1, max_length=100)
    due_date: date | None = None
    period: str | None = Field(None, max_length=255)
    direction: Literal["operator_input", "auditor_output"] = "operator_input"
    expectation_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class AuditorRequestPatch(Revision):
    due_date: date | None = None
    period: str | None = Field(None, max_length=255)
    direction: Literal["operator_input", "auditor_output"] | None = None
    expectation_ids: list[uuid.UUID] | None = Field(None, max_length=500)
    evidence_ids: list[uuid.UUID] | None = Field(None, max_length=500)


class AssessmentEvidenceLink(Input):
    evidence_id: uuid.UUID
    locator: str | None = Field(None, max_length=20000)
    rationale: str = Field(min_length=1, max_length=20000)


class AssessmentEvidenceLinks(Input):
    expected_evidence_changed_at: datetime | None
    links: list[AssessmentEvidenceLink] = Field(max_length=200)


class RegisterProcessPut(Revision):
    clear_targets: bool = False
    review_cycle_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_process(self):
        if self.review_cycle_id is not None and self.application_id is not None:
            raise ValueError("Choose a review cycle or a licence application")
        return self


class RowReviewPut(Revision):
    review_cycle_id: uuid.UUID | None = None
    clear_targets: bool = False


class ProcessTargetInput(Input):
    requirement_id: uuid.UUID
    requirement_set_version_id: uuid.UUID
    review_item_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    field_key: str | None = Field(None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def typed_target(self):
        if self.review_item_id is not None:
            if self.case_id is not None or self.field_key is not None:
                raise ValueError("Choose one target type")
        elif self.case_id is None or self.field_key is None:
            raise ValueError("Choose an assessment item or a form field")
        return self


class ProcessTargetsPut(Revision):
    targets: list[ProcessTargetInput] = Field(max_length=50)
