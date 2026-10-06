from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class JiraIntegrationResponse(BaseModel):
    base_url: str
    project_key: str
    user_email: str
    enabled: bool
    token_configured: bool
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_message: Optional[str] = None


class JiraIntegrationUpdate(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=255)
    project_key: str = Field(..., min_length=2, max_length=50)
    user_email: str = Field(..., min_length=3, max_length=255)
    api_token: Optional[str] = Field(default=None, max_length=4000)
    enabled: bool = True


class JiraIntegrationTestRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=255)
    project_key: str = Field(..., min_length=2, max_length=50)
    user_email: str = Field(..., min_length=3, max_length=255)
    api_token: Optional[str] = Field(default=None, max_length=4000)


class JiraIntegrationTestResponse(BaseModel):
    ok: bool
    message: str
