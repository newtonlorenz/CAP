import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Control(Base):
    __tablename__ = "controls"
    __table_args__ = (
        UniqueConstraint("jurisdiction_id", "code", name="uq_controls_jurisdiction_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_expectations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cadence_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Obligation(Base):
    __tablename__ = "obligations"
    __table_args__ = (
        UniqueConstraint("jurisdiction_id", "code", name="uq_obligations_jurisdiction_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    legal_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ControlCrosswalk(Base):
    __tablename__ = "control_crosswalks"
    __table_args__ = (
        UniqueConstraint(
            "source_control_id",
            "target_obligation_id",
            name="uq_control_crosswalks_source_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_control_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("controls.id"), nullable=False, index=True
    )
    target_obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("obligations.id"), nullable=False, index=True
    )
    mapping_strength: Mapped[str] = mapped_column(String(30), nullable=False, default="partial")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CertificationProject(Base):
    __tablename__ = "certification_projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="intake")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    target_submission_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assurance_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    provider_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    engagement_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assurance_scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scheduled_test_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_test_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    report_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    report_outcome: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    report_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    report_link: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequirementSetVersion(Base):
    __tablename__ = "requirement_set_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_requirement_set_versions_document_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    based_on_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("requirement_set_versions.id"), nullable=True, index=True
    )
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CertificationProjectRequirementBaseline(Base):
    __tablename__ = "certification_project_requirement_baselines"
    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id",
            "document_id",
            name="pk_certification_project_requirement_baselines",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True
    )
    requirement_set_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_set_versions.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CertificationProjectMilestone(Base):
    __tablename__ = "certification_project_milestones"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewCycleRequirementBaseline(Base):
    __tablename__ = "review_cycle_requirement_baselines"
    __table_args__ = (
        PrimaryKeyConstraint(
            "review_cycle_id",
            "document_id",
            name="pk_review_cycle_requirement_baselines",
        ),
    )

    review_cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True
    )
    requirement_set_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_set_versions.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BaselineMigration(Base):
    __tablename__ = "baseline_migrations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=False, index=True
    )
    from_cycle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=True, index=True
    )
    to_cycle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="previewed")
    preview_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionPackage(Base):
    __tablename__ = "submission_packages"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_submission_packages_project_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=False, index=True
    )
    review_cycle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=True, index=True
    )
    snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("snapshots.id"), nullable=True, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    checklist_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionPackageArtifact(Base):
    __tablename__ = "submission_package_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submission_packages.id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    link_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"

    certification_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=True, index=True
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, index=True
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reminder_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    escalation_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    maintenance_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("maintenance_plans.id"), nullable=False, index=True
    )
    review_cycle_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("review_cycles.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id"), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    link_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_in_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class EvidenceValidation(Base):
    __tablename__ = "evidence_validations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_items.id"), nullable=False, index=True
    )
    validator_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_sync_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ExportManifest(Base):
    __tablename__ = "export_manifests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    hash_algo: Mapped[str] = mapped_column(String(30), nullable=False, default="sha256")
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
