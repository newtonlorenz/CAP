"""Immutable import provenance, optional suggestion runs and frozen handover metadata."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentationImport(Base):
    __tablename__ = "documentation_imports"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentation_registers.id"), index=True
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    register_revision: Mapped[int] = mapped_column(Integer)
    preview_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentationImportRow(Base):
    __tablename__ = "documentation_import_rows"
    __table_args__ = (
        UniqueConstraint(
            "register_id",
            "input_fingerprint",
            "sheet",
            "row_number",
            name="uq_doc_import_source_row",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentation_registers.id"), index=True
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    sheet: Mapped[str] = mapped_column(String(255))
    row_number: Mapped[int] = mapped_column(Integer)
    expectation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentation_expectations.id"), index=True
    )
    original_json: Mapped[str] = mapped_column(Text)


class DocumentationSuggestionRun(Base):
    __tablename__ = "documentation_suggestion_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentation_registers.id"), index=True
    )
    register_revision: Mapped[int] = mapped_column(Integer)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    settings_fingerprint: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(40), default="documentation-assist-v1")
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    input_json: Mapped[str] = mapped_column(Text)
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentationSnapshot(Base):
    __tablename__ = "documentation_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    register_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documentation_registers.id"), index=True
    )
    register_revision: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[str] = mapped_column(Text)
    evidence_ids_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
