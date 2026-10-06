import pytest

from app.config import load_settings


@pytest.mark.parametrize(
    "placeholder",
    [
        "change-me-in-production",
        "generate-a-secure-random-key-here",
        "replace-with-a-long-random-secret",
    ],
)
def test_production_rejects_shipped_signing_key_placeholders(placeholder):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings(
            _env_file=None,
            app_env="production",
            secret_key=placeholder,
            frontend_base_url="https://cap.example.test",
            allowed_hosts=["cap.example.test"],
            cors_origins=["https://cap.example.test"],
        )


@pytest.mark.parametrize("placeholder", ["postgres", "replace-with-strong-db-password"])
def test_production_rejects_shipped_database_passwords(placeholder):
    with pytest.raises(RuntimeError, match="effective database password"):
        load_settings(
            _env_file=None,
            app_env="production",
            DB_PASSWORD=placeholder,
            database_url="",  # Test the local default, independent of the runner's isolated DB.
            secret_key="disposable-test-secret-that-is-not-a-placeholder",
            frontend_base_url="https://cap.example.test",
            allowed_hosts=["cap.example.test"],
            cors_origins=["https://cap.example.test"],
        )


def test_production_accepts_managed_database_url_with_default_local_password():
    settings = load_settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://managed:strong-db-secret@managed.example.test:5432/cap",
        secret_key="x" * 32,
        frontend_base_url="https://cap.example.test",
        allowed_hosts=["cap.example.test"],
        cors_origins=["https://cap.example.test"],
    )
    assert settings.database_url.endswith("@managed.example.test:5432/cap")


def test_production_rejects_placeholder_password_in_managed_url():
    with pytest.raises(RuntimeError, match="effective database password"):
        load_settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql+asyncpg://managed:postgres@managed.example.test:5432/cap",
            secret_key="x" * 32,
            frontend_base_url="https://cap.example.test",
            allowed_hosts=["cap.example.test"],
            cors_origins=["https://cap.example.test"],
        )


def test_production_defaults_same_host_database_and_redis_urls(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    settings = load_settings(
        _env_file=None,
        app_env="production",
        DB_PASSWORD="db-secret",
        secret_key="x" * 32,
        cors_origins=["https://app.example.com"],
        allowed_hosts=["app.example.com"],
        frontend_base_url="https://app.example.com",
        AI_PROVIDER="openai",
        openai_api_key="test-key",
        EMAIL_MODE="smtp",
        smtp_host="smtp.example.com",
        smtp_from="noreply@example.com",
    )

    assert settings.database_url == "postgresql+asyncpg://postgres:db-secret@db:5432/cap"
    assert settings.redis_url == "redis://redis:6379/0"


def test_production_config_requires_matching_frontend_ai_and_email_settings():
    with pytest.raises(RuntimeError) as excinfo:
        load_settings(
            _env_file=None,
            app_env="production",
            DB_PASSWORD="db-secret",
            secret_key="short-secret",
            cors_origins=["https://wrong.example.com"],
            allowed_hosts=["wrong.example.com"],
            frontend_base_url="https://app.example.com",
            AI_PROVIDER="openai",
            openai_api_key="",
            EMAIL_MODE="smtp",
            smtp_host="",
            smtp_from="",
        )

    message = str(excinfo.value)
    assert "SECRET_KEY" in message
    assert "CORS_ORIGINS" in message
    assert "ALLOWED_HOSTS" in message
    assert "OPENAI_API_KEY" in message
    assert "SMTP_HOST" in message
    assert "SMTP_FROM" in message


def test_production_config_accepts_wildcard_allowed_host_and_complete_bootstrap_admin():
    settings = load_settings(
        _env_file=None,
        app_env="production",
        DB_PASSWORD="db-secret",
        secret_key="x" * 32,
        cors_origins=["https://cap.example.com"],
        allowed_hosts=["*.example.com"],
        frontend_base_url="https://cap.example.com",
        AI_PROVIDER="anthropic",
        anthropic_api_key="test-key",
        EMAIL_MODE="smtp",
        smtp_host="smtp.example.com",
        smtp_from="noreply@example.com",
        bootstrap_admin_email="admin@example.com",
        bootstrap_admin_name="Admin User",
        bootstrap_admin_password="strong-password",
    )

    assert settings.allowed_hosts == ["*.example.com"]
