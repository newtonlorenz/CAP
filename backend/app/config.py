import fnmatch
import os
from typing import Literal, Optional
from urllib.parse import unquote, urlparse

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    test_database_url: str = "sqlite+aiosqlite:///./test.db"
    db_password: str = Field(default="postgres", validation_alias="DB_PASSWORD")
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    installation_operator_ids: list[str] = []
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    redis_url: str = ""
    celery_task_always_eager: bool = False
    pdf_preprocess_timeout_seconds: int = Field(default=180, ge=1)
    pdf_max_pages: int = Field(default=300, ge=1)
    # Structured extraction is an optional local installation capability.
    pdf_structure_engine: Literal["native", "opendataloader"] = "native"
    cloud_location_exemption_standard: str = ""
    extraction_timeout_minutes: int = 30
    extraction_page_timeout_seconds: int = 300
    extraction_stuck_timeout_seconds: int = 300
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    ai_provider_setting: Literal["none", "openai", "anthropic", "auto"] = Field(
        default="none", validation_alias="AI_PROVIDER"
    )
    ai_request_timeout_seconds: int = 120
    jev_enabled: bool = False
    jev_model: str = "jev-1.13.0"
    typesafe_api_key: str = Field(default="", repr=False)
    jev_settings_revision: int = 0
    jev_request_timeout_seconds: int = Field(default=30, ge=1, le=30)
    ocr_enabled: bool = False
    ocr_mode: str = "image_only"
    ocr_languages: str = "eng"
    ocr_timeout_seconds: int = 600
    ocr_image_page_ratio_threshold: float = 0.5
    parseability_low_page_threshold: float = 0.58
    parseability_low_ratio_threshold: float = 0.15
    vision_fallback_enabled: bool = True
    vision_fallback_max_regions_per_doc: int = 24
    vision_fallback_confidence_threshold: float = 0.75
    vision_fallback_render_dpi: int = 180
    vision_anchor_min_similarity: float = 0.82
    upload_dir: str = "./uploads"
    postgres_bin_dir: str = ""
    backup_dir: str = ""
    backup_retention_count: int = Field(default=20, ge=1)
    backup_expanded_max_mb: int = Field(default=8192, ge=1)
    backup_max_members: int = Field(default=50000, ge=1)
    backup_upload_max_mb: int = Field(default=2048, ge=1)
    max_document_upload_mb: int = Field(default=50, ge=1)
    max_evidence_upload_mb: int = Field(default=25, ge=1)
    cors_origins: list[str] = ["http://localhost:5173"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    enable_docs: Optional[bool] = None
    # Email delivery:
    # - "disabled": no delivery; core workflows remain available
    # - "smtp": send via SMTP_* settings
    # - "log": do not send; log emails for MVP/testing (disabled in production)
    email_mode: Literal["disabled", "smtp", "log"] = Field(
        default="disabled", validation_alias="EMAIL_MODE"
    )
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    frontend_base_url: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_name: str = ""
    bootstrap_admin_password: str = ""
    jira_allowed_hosts: list[str] = []
    jira_sync_ttl_minutes: int = 15
    jira_request_timeout_seconds: int = 15
    # Optional private Page Feedback service; the browser never receives this key.
    feedback_service_url: str = ""
    feedback_service_key: str = ""
    feedback_project: str = "cap"

    @model_validator(mode="after")
    def validate_feedback(self):
        if self.feedback_service_url or self.feedback_service_key:
            parsed = urlparse(self.feedback_service_url)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ValueError("FEEDBACK_SERVICE_URL must be an http(s) service URL")
            if len(self.feedback_service_key) < 32:
                raise ValueError("FEEDBACK_SERVICE_KEY must contain at least 32 characters")
        if not self.feedback_project or len(self.feedback_project) > 100:
            raise ValueError("FEEDBACK_PROJECT must contain 1 to 100 characters")
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator(
        "database_url",
        "redis_url",
        "secret_key",
        "frontend_base_url",
        "smtp_host",
        "smtp_user",
        "smtp_password",
        "smtp_from",
        "bootstrap_admin_email",
        "bootstrap_admin_name",
        mode="before",
    )
    @classmethod
    def normalize_string_fields(cls, value: str):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            return ""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def ai_provider(self) -> str:
        """Return the configured AI provider. Prefers Anthropic if both are set."""
        provider = self.ai_provider_setting.lower()
        if provider in {"openai", "anthropic", "none"}:
            return provider
        if provider != "auto":
            return "none"
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "none"

    @property
    def ai_model(self) -> str:
        """Return the model name for the configured provider."""
        if self.ai_provider == "anthropic":
            return self.anthropic_model
        return self.openai_model

    @property
    def email_available(self) -> bool:
        if self.email_mode == "log":
            return not self.is_production
        return self.email_mode == "smtp" and bool(
            self.smtp_host.strip() and self.smtp_from.strip()
            and (not self.smtp_user.strip() or self.smtp_password)
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def docs_enabled(self) -> bool:
        if self.enable_docs is not None:
            return self.enable_docs
        return not self.is_production

    @model_validator(mode="after")
    def set_backup_dir_default(self):
        if not self.database_url:
            db_host = "db" if self.is_production else "localhost"
            self.database_url = (
                f"postgresql+asyncpg://postgres:{self.db_password}@{db_host}:5432/cap"
            )
        if not self.redis_url:
            redis_host = "redis" if self.is_production else "localhost"
            self.redis_url = f"redis://{redis_host}:6379/0"
        if not self.backup_dir:
            self.backup_dir = os.path.join(self.upload_dir, ".system_backups")
        if self.is_production:
            errors = self._production_config_errors()
            if errors:
                raise ValueError("\n".join(errors))
        return self

    def _production_config_errors(self) -> list[str]:
        errors: list[str] = []

        database_password = unquote(urlparse(self.database_url).password or "")
        if database_password.strip().lower() in {"postgres", "replace-with-strong-db-password"}:
            errors.append("The effective database password must not use a shipped or default value in production.")

        if (
            len(self.secret_key.strip()) < 32
            or self.secret_key.strip().lower() in {
                "change-me-in-production",
                "generate-a-secure-random-key-here",
                "replace-with-a-long-random-secret",
            }
        ):
            errors.append(
                "SECRET_KEY must be set to a non-placeholder value at least 32 characters long."
            )

        frontend_url = self.frontend_base_url.strip()
        parsed_frontend_url = urlparse(frontend_url)
        if parsed_frontend_url.scheme not in {"http", "https"} or not parsed_frontend_url.hostname:
            errors.append("FRONTEND_BASE_URL must be a valid http(s) URL.")

        frontend_origin = ""
        frontend_host = ""
        if parsed_frontend_url.scheme and parsed_frontend_url.hostname:
            frontend_host = parsed_frontend_url.hostname
            frontend_origin = f"{parsed_frontend_url.scheme}://{frontend_host}"
            if parsed_frontend_url.port:
                frontend_origin = f"{frontend_origin}:{parsed_frontend_url.port}"

        if not self.cors_origins:
            errors.append("CORS_ORIGINS must include at least one allowed origin in production.")
        elif frontend_origin and frontend_origin not in self.cors_origins:
            errors.append("CORS_ORIGINS must include the FRONTEND_BASE_URL origin.")

        if not self.allowed_hosts:
            errors.append("ALLOWED_HOSTS must include at least one trusted host in production.")
        elif frontend_host and not any(
            fnmatch.fnmatch(frontend_host, allowed_host) for allowed_host in self.allowed_hosts
        ):
            errors.append("ALLOWED_HOSTS must include the FRONTEND_BASE_URL hostname.")

        if self.ai_provider == "openai" and not self.openai_api_key.strip():
            errors.append("OPENAI_API_KEY is required when AI_PROVIDER resolves to openai.")
        elif self.ai_provider == "anthropic" and not self.anthropic_api_key.strip():
            errors.append("ANTHROPIC_API_KEY is required when AI_PROVIDER resolves to anthropic.")

        email_mode = (self.email_mode or "smtp").strip().lower()
        if email_mode not in {"disabled", "smtp", "log"}:
            errors.append("EMAIL_MODE must be disabled, smtp or log.")
        elif email_mode == "log":
            errors.append("EMAIL_MODE=log is not allowed in production.")
        elif email_mode == "smtp":
            if not self.smtp_host.strip():
                errors.append("SMTP_HOST is required when EMAIL_MODE=smtp.")
            if not self.smtp_from.strip():
                errors.append("SMTP_FROM is required when EMAIL_MODE=smtp.")
            if self.smtp_user.strip() and not self.smtp_password:
                errors.append("SMTP_PASSWORD is required when SMTP_USER is set.")

        bootstrap_fields = [
            bool(self.bootstrap_admin_email.strip()),
            bool(self.bootstrap_admin_name.strip()),
            bool(self.bootstrap_admin_password),
        ]
        if any(bootstrap_fields) and not all(bootstrap_fields):
            errors.append(
                "BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_NAME, and BOOTSTRAP_ADMIN_PASSWORD must either all be set or all be blank."
            )

        return errors


def load_settings(**kwargs) -> Settings:
    try:
        return Settings(**kwargs)
    except ValidationError as exc:
        details: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ()) if part != "__root__")
            message = error.get("msg", "invalid value")
            details.append(f"{location}: {message}" if location else message)
        raise RuntimeError(
            "Invalid application configuration:\n- " + "\n- ".join(details)
        ) from None


settings = load_settings()
