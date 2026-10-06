import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketPack(Base):
    __tablename__ = "market_packs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jurisdictions.id"), nullable=False, unique=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    parser_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    supports_deterministic_import: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    coverage_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
