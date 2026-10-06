"""Public evidence metadata; storage paths never leave the server."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class EvidenceDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=50000)
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("Valid until must be on or after valid from")
        return self


class EvidenceCreate(EvidenceDetails):
    visibility: Literal["organisation", "restricted", "secret"] = "secret"
    kind: Literal["note", "link"]
    link_url: HttpUrl | None = None

    @field_validator("link_url")
    @classmethod
    def bounded_public_url(cls, value):
        if value is not None and (len(str(value)) > 2000 or value.username or value.password):
            raise ValueError(
                "Use an HTTP(S) URL without embedded credentials, up to 2000 characters"
            )
        return value

    @model_validator(mode="after")
    def required_content(self):
        if self.kind == "note" and not self.body:
            raise ValueError("A note needs evidence text")
        if self.kind == "link" and self.link_url is None:
            raise ValueError("Link evidence needs an HTTP(S) URL")
        if self.kind == "note" and self.link_url is not None:
            raise ValueError("Use link evidence to record a URL")
        return self


class EvidenceArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool


class EvidenceResponse(BaseModel):
    access: dict | None = None
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    kind: Literal["note", "link", "file"]
    body: str | None
    link_url: str | None
    filename: str | None
    sha256: str | None
    size_bytes: int | None
    valid_from: date | None
    valid_until: date | None
    archived: bool
    created_at: datetime
    created_by: uuid.UUID
