import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvidenceNote(Base):
    __tablename__ = "evidence_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceFile(Base):
    __tablename__ = "evidence_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EvidenceLink(Base):
    __tablename__ = "evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
