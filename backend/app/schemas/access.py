import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Permission = Literal["summary", "view", "edit", "approve", "export", "manage_access"]
Visibility = Literal["organisation", "restricted", "secret"]


class GrantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_type: Literal["user", "team"]
    subject_id: uuid.UUID
    permissions: list[Permission] = Field(min_length=1)


class AccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    visibility: Visibility
    grants: list[GrantInput] = Field(default_factory=list, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class TeamUpdate(TeamCreate):
    expected_revision: int = Field(ge=1)
