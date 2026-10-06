import uuid
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"
    approver = "approver"
    contributor = "contributor"
    assigned_reviewer = "assigned_reviewer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    role: Literal[
        "admin",
        "manager",
        "approver",
        "contributor",
        "assigned_reviewer",
    ] = "contributor"


class UserResponse(BaseModel):
    installation_operator: bool = False
    system_admin_designated: bool = False
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    email: str
    full_name: str
    role: str
    active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserMentionResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8)
    full_name: Optional[str] = None
    role: Optional[
        Literal[
            "admin",
            "manager",
            "approver",
            "contributor",
            "assigned_reviewer",
        ]
    ] = None
    active: Optional[bool] = None


class LoginRequest(BaseModel):
    email: str
    password: str = Field(max_length=256)


class TokenResponse(BaseModel):
    token_type: str = "bearer"


class AccountUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(extra="forbid")

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be blank")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=72)

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def check_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password exceeds 72 UTF-8 bytes")
        return value


class NotificationSettings(BaseModel):
    review_mentions: bool
    review_reminders: bool

    model_config = ConfigDict(from_attributes=True, extra="forbid")
