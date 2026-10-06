import os
import re
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False
    )
    filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    effective_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    testing_frequency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approval_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    current_extraction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=True
    )
    maintenance_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("maintenance_plans.id"), nullable=True
    )
    cadence_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def has_source(self) -> bool:
        return self.source_available(self.filename, self.file_path)

    @staticmethod
    def source_available(filename: Optional[str], file_path: Optional[str]) -> bool:
        if not filename or not file_path:
            return False
        # Legacy manual sets used exactly this display name and generated path.
        # A real upload called manual.pdf or manual-placeholder.pdf remains a source.
        return not (
            filename == "manual-placeholder.pdf"
            and re.fullmatch(
                r"manual_[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\.pdf",
                os.path.basename(file_path),
            )
        )
