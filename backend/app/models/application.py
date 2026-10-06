"""Flexible application packs and retained approval artefacts."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(20))
    applicant: Mapped[str | None] = mapped_column(String(255))
    authority: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    profile_snapshot_json: Mapped[str | None] = mapped_column(Text)
    setup_answers_json: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    outcome: Mapped[str | None] = mapped_column(Text)
    review_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationComponent(Base):
    __tablename__ = "application_components"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("preparation_cases.id"), index=True
    )
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("preparation_evidence.id"))
    profile_item_key: Mapped[str | None] = mapped_column(String(100))


class ApplicationMarketProfile(Base):
    __tablename__ = "application_market_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "jurisdiction_id",
            name="uq_application_market_profile_org_jurisdiction",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationFollowup(Base):
    __tablename__ = "application_followups"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    response: Mapped[str | None] = mapped_column(Text)
    evidence_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationSnapshot(Base):
    __tablename__ = "application_snapshots"
    __table_args__ = (
        UniqueConstraint("application_id", "version", name="uq_application_snapshot_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    archive: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
