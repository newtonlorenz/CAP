"""Explicit content authority, independent of account administration."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResourceAccess(Base):
    __tablename__ = "resource_access"
    __table_args__ = (UniqueConstraint("resource_type", "resource_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[uuid.UUID] = mapped_column(index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="secret")
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resource_access.id"))


class AccessTeam(Base):
    __tablename__ = "access_teams"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class AccessTeamMember(Base):
    __tablename__ = "access_team_members"
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("access_teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class AccessGrant(Base):
    __tablename__ = "access_grants"
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resource_access.id", ondelete="CASCADE"), primary_key=True
    )
    subject_type: Mapped[str] = mapped_column(String(10), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    permission: Mapped[str] = mapped_column(String(20), primary_key=True)
