import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class MarketPackResponse(BaseModel):
    id: uuid.UUID
    jurisdiction_id: uuid.UUID
    jurisdiction_code: str
    jurisdiction_name: str
    version: str
    status: Literal["published", "scaffold", "draft"]
    parser_mode: str
    supports_deterministic_import: bool
    coverage_notes: Optional[str] = None
    source_label: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
