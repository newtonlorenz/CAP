import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PreparationTemplate(Base):
    __tablename__ = "preparation_templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PreparationCase(Base):
    __tablename__ = "preparation_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("preparation_templates.id"), nullable=True, index=True
    )
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    original_evidence_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("certification_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PreparationResponse(Base):
    __tablename__ = "preparation_responses"
    __table_args__ = (
        UniqueConstraint("case_id", "field_key", name="uq_preparation_response_case_field"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preparation_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_json: Mapped[Optional[str]] = mapped_column(Text)
    not_applicable_reason: Mapped[Optional[str]] = mapped_column(Text)
    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reused_from_case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("preparation_cases.id", ondelete="SET NULL"), index=True
    )
    reused_from_field_key: Mapped[Optional[str]] = mapped_column(String(64))


class PreparationEvidence(Base):
    __tablename__ = "preparation_evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    link_url: Mapped[Optional[str]] = mapped_column(String(2000))
    filename: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    sha256: Mapped[Optional[str]] = mapped_column(String(64))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    valid_from: Mapped[Optional[date]] = mapped_column(Date)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreparationResponseEvidence(Base):
    __tablename__ = "preparation_response_evidence"

    response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preparation_responses.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preparation_evidence.id"), primary_key=True, index=True
    )
