"""Installation-wide settings, with secrets kept outside the public JSON payload."""

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InstallationSettings(Base):
    __tablename__ = "installation_settings"

    section: Mapped[str] = mapped_column(String(20), primary_key=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
