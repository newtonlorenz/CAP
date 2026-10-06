import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class NoteCreate(BaseModel):
    note_text: str


class NoteResponse(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    note_text: str
    created_by: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileResponse(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    filename: str
    description: Optional[str]
    uploaded_by: uuid.UUID
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LinkCreate(BaseModel):
    url: str
    label: str


class LinkResponse(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    url: str
    label: str
    added_by: uuid.UUID
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceResponse(BaseModel):
    notes: List[NoteResponse]
    files: List[FileResponse]
    links: List[LinkResponse]
