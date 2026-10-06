from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BackupMetadataResponse(BaseModel):
    id: str
    archive_filename: str
    created_at: datetime
    reason: str
    source_backup_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_user_name: Optional[str] = None
    size_bytes: int
    sha256: str
    format_version: int


class BackupListResponse(BaseModel):
    items: list[BackupMetadataResponse]
    total: int


class BackupRestoreRequest(BaseModel):
    confirmation: str = Field(..., min_length=1, max_length=32)
    reason: Optional[str] = Field(default=None, max_length=255)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        if value != "RESTORE":
            raise ValueError("confirmation must be RESTORE")
        return value


class BackupRestoreResponse(BaseModel):
    restored_backup_id: str
    pre_restore_backup_id: str
    completed_at: datetime
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
