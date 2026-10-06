import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ComponentRegister(Base):
    __tablename__ = "component_registers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, index=True
    )
    responsibility_role: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown", server_default="unknown"
    )
    programme_assurance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint("register_id", "component_uid", name="uq_components_register_uid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("component_registers.id"), nullable=False, index=True
    )
    component_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    regulatory_scope: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown", server_default="unknown"
    )
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    identifying_characteristics: Mapped[str] = mapped_column(Text, nullable=False)
    change_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    change_owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    confidentiality_code: Mapped[int] = mapped_column(Integer, nullable=False)
    integrity_code: Mapped[int] = mapped_column(Integer, nullable=False)
    availability_code: Mapped[int] = mapped_column(Integer, nullable=False)
    accountability_code: Mapped[int] = mapped_column(Integer, nullable=False)
    classification_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    checksum_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_hardware: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    geographic_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    hosting_model: Mapped[str] = mapped_column(String(40), nullable=False, default="on_prem")
    virtualized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_cloud_provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    public_cloud_certification: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    public_cloud_iso27001: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_cloud_independent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_cloud_redundancy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ComponentBaseline(Base):
    __tablename__ = "component_baselines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("component_registers.id"), nullable=False, index=True
    )
    certification_scope: Mapped[str] = mapped_column(
        String(40), nullable=False, default="manual", server_default="manual"
    )
    certification_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    certification_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    certification_ato: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    certification_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    established_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    established_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComponentBaselineItem(Base):
    __tablename__ = "component_baseline_items"
    __table_args__ = (
        UniqueConstraint(
            "baseline_id",
            "component_uid",
            name="uq_component_baseline_items_baseline_uid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("component_baselines.id"), nullable=False, index=True
    )
    component_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("components.id"), nullable=True
    )
    component_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    classification_code: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeEntry(Base):
    __tablename__ = "change_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("component_registers.id"), nullable=False, index=True
    )
    compliance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    approved_scope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    blocking_assessment_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False, default="normal")
    proposed_by_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    complexity_classification: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduling_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_components_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_docs_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    planned_start_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    planned_end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_documentation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    evaluation_effect: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_risk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_regulatory_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_ciaa_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    approval_decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejected_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    implementation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    implemented_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    implemented_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    implemented_start_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    implemented_end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    testing_org_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    testing_org_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    testing_org_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    testing_org_cycle: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    testing_org_next_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    testing_org_approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    integration_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChangeEntryComponent(Base):
    __tablename__ = "change_entry_components"
    __table_args__ = (
        UniqueConstraint(
            "change_entry_id",
            "component_id",
            name="uq_change_entry_components_change_component",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    change_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_entries.id"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("components.id"), nullable=False, index=True
    )
    frozen_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    baseline_scope_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    baseline_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("component_baselines.id"), nullable=True
    )
    planned_checksum_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    implemented_checksum_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    version_at_proposal: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    planned_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    implemented_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    change_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_entries.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status_from: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status_to: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IntegrationCheck(Base):
    __tablename__ = "integration_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    change_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_entries.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    action_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    completed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ChangeRequirementImpact(Base):
    __tablename__ = "change_requirement_impacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    change_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_entries.id"), nullable=False, index=True
    )
    requirement_set_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_set_versions.id"), nullable=False, index=True
    )
    requirement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("requirements.id"), nullable=True
    )
    certification_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("certification_projects.id"), nullable=True, index=True
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
