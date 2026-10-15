"""Documentation expectations and evidence associations, independent of compliance decisions."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentationRegister(Base):
    __tablename__ = "documentation_registers"
    __table_args__ = (CheckConstraint("review_cycle_id IS NULL OR application_id IS NULL", name="ck_documentation_register_one_process"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    review_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_cycles.id"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentationSection(Base):
    """An ordered register tab that remains present when it has no rows."""
    __tablename__ = "documentation_sections"
    __table_args__ = (
        UniqueConstraint("register_id", "name_key", name="uq_documentation_section_name"),
        CheckConstraint("position >= 0", name="ck_documentation_section_position"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_registers.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(1024))
    position: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentationExpectation(Base):
    __tablename__ = "documentation_expectations"
    __table_args__ = (
        CheckConstraint("applicability IN ('unknown', 'applicable', 'not_applicable')", name="ck_documentation_applicability"),
        CheckConstraint("coverage_status IN ('unreviewed', 'partial', 'sufficient')", name="ck_documentation_coverage_status"),
        CheckConstraint("applicability != 'not_applicable' OR (not_applicable_reason IS NOT NULL AND length(trim(not_applicable_reason)) > 0)", name="ck_documentation_na_reason"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_registers.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("certification_projects.id"), index=True)
    review_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_cycles.id"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentation_sections.id"), index=True)
    required_documentation: Mapped[str | None] = mapped_column(Text)
    document_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    interpretation: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    applicability: Mapped[str] = mapped_column(String(30), default="unknown")
    not_applicable_reason: Mapped[str | None] = mapped_column(Text)
    responsible_party: Mapped[str | None] = mapped_column(String(255))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    coverage_status: Mapped[str] = mapped_column(String(20), default="unreviewed")
    review_rationale: Mapped[str | None] = mapped_column(Text)
    process_review_fingerprint: Mapped[str | None] = mapped_column(String(64))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentationProcessTarget(Base):
    """An explicit pointer to an existing owner collection, never a second evidence list."""
    __tablename__ = "documentation_process_targets"
    __table_args__ = (
        CheckConstraint("(review_item_id IS NOT NULL AND case_id IS NULL AND field_key IS NULL) OR (review_item_id IS NULL AND case_id IS NOT NULL AND field_key IS NOT NULL)", name="ck_documentation_process_target_kind"),
        UniqueConstraint("expectation_id", "review_item_id", name="uq_documentation_review_target"),
        UniqueConstraint("expectation_id", "case_id", "field_key", name="uq_documentation_response_target"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    expectation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_expectations.id", ondelete="CASCADE"), index=True)
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_items.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("preparation_cases.id"))
    field_key: Mapped[str | None] = mapped_column(String(64))
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"))
    requirement_set_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement_set_versions.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExpectationRequirement(Base):
    __tablename__ = "documentation_expectation_requirements"
    expectation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_expectations.id", ondelete="CASCADE"), primary_key=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"), primary_key=True)
    requirement_set_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement_set_versions.id"), index=True)


class EvidenceGroup(Base):
    __tablename__ = "documentation_evidence_groups"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_registers.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    current_evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preparation_evidence.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceGroupVersion(Base):
    __tablename__ = "documentation_evidence_group_versions"
    __table_args__ = (UniqueConstraint("group_id", "version", name="uq_documentation_group_version"), UniqueConstraint("evidence_id", name="uq_documentation_evidence_identity"))
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_evidence_groups.id"), primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preparation_evidence.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentationCoverage(Base):
    __tablename__ = "documentation_coverage"
    __table_args__ = (UniqueConstraint("expectation_id", "evidence_id", name="uq_documentation_coverage_evidence"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    expectation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_expectations.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preparation_evidence.id"), index=True)
    locator: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(String(255))
    rationale: Mapped[str] = mapped_column(Text)


class DocumentationReference(Base):
    __tablename__ = "documentation_references"
    __table_args__ = (CheckConstraint("(kind = 'component' AND component_id IS NOT NULL AND change_id IS NULL AND jira_key IS NULL) OR (kind = 'change' AND change_id IS NOT NULL AND component_id IS NULL AND jira_key IS NULL) OR (kind = 'jira' AND jira_key IS NOT NULL AND component_id IS NULL AND change_id IS NULL)", name="ck_documentation_typed_reference"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    expectation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_expectations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("components.id"))
    change_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("change_entries.id"))
    jira_key: Mapped[str | None] = mapped_column(String(100))
    jira_url: Mapped[str | None] = mapped_column(String(2000))


class AuditorRequestMapping(Base):
    __tablename__ = "documentation_auditor_requests"
    __table_args__ = (CheckConstraint("direction IN ('operator_input', 'auditor_output')", name="ck_documentation_request_direction"), UniqueConstraint("register_id", "case_id", "field_key", "list_revision", name="uq_documentation_auditor_request_revision"))
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_registers.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preparation_cases.id"), index=True)
    field_key: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("certification_projects.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(255))
    request_wording: Mapped[str] = mapped_column(Text)
    list_revision: Mapped[str] = mapped_column(String(100))
    due_date: Mapped[date | None] = mapped_column(Date)
    period: Mapped[str | None] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(30), default="operator_input")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditorRequestExpectation(Base):
    __tablename__ = "documentation_request_expectations"
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_auditor_requests.id", ondelete="CASCADE"), primary_key=True)
    expectation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_expectations.id"), primary_key=True)


class AuditorRequestEvidence(Base):
    __tablename__ = "documentation_request_evidence"
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_auditor_requests.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preparation_evidence.id"), primary_key=True)


class DocumentationAssessmentEvidence(Base):
    """A shared-library association; legacy assessment uploads retain their own storage."""
    __tablename__ = "documentation_assessment_evidence"
    review_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_items.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("preparation_evidence.id"), primary_key=True)
    locator: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentationSnapshotSource(Base):
    """Typed original source index permits SQL visibility before audit pagination."""
    __tablename__ = "documentation_snapshot_sources"
    __table_args__ = (CheckConstraint("(CASE WHEN evidence_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN case_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN expectation_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN request_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN review_cycle_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN review_item_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN review_file_id IS NOT NULL THEN 1 ELSE 0 END) = 1", name="ck_documentation_snapshot_typed_source"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentation_snapshots.id"), index=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("preparation_evidence.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("certification_projects.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("preparation_cases.id"))
    expectation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentation_expectations.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentation_auditor_requests.id"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id"))
    review_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_cycles.id"))
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_items.id"))
    review_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_item_evidence_files.id", ondelete="CASCADE"))

