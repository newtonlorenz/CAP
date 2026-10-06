from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class EmailFields(BaseModel):
    mode: Literal["disabled", "smtp"]
    smtp_host: str = Field(default="", max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = Field(default="", max_length=255)
    smtp_from: str = Field(default="", max_length=255)
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"

    @field_validator("smtp_host", "smtp_user", "smtp_from")
    @classmethod
    def clean_fields(cls, value):
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("Control characters are not allowed")
        return value.strip()


class EmailUpdate(EmailFields):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    password: SecretStr | None = None
    clear_password: bool = False


class EmailResponse(EmailFields):
    password_configured: bool
    source: Literal["environment", "database"]
    revision: int


class AIFields(BaseModel):
    provider: Literal["none", "openai", "anthropic"]
    model: str = Field(default="", max_length=255)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        return value.strip()


class AIUpdate(AIFields):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    api_key: SecretStr | None = None
    clear_api_key: bool = False


class AIResponse(AIFields):
    credential_provider: Literal["openai", "anthropic"] | None = None
    api_key_configured: bool
    source: Literal["environment", "database"]
    revision: int


class JevFields(BaseModel):
    enabled: bool = False
    model: str = Field(default="jev-1.13.0", min_length=1, max_length=255)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        value = value.strip()
        if not value or any(c in value for c in ("\r", "\n", "\x00")):
            raise ValueError("A valid Jev model is required")
        return value


class JevUpdate(JevFields):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    api_key: SecretStr | None = None
    clear_api_key: bool = False


class JevResponse(JevFields):
    api_key_configured: bool
    source: Literal["environment", "database"]
    revision: int


class InstallationSettingsResponse(BaseModel):
    email: EmailResponse
    ai: AIResponse
    jev: JevResponse


class SettingsTestResponse(BaseModel):
    ok: bool
    message: str
