"""Portable defaults, provider boundaries and synthetic document regression checks."""

import io
import json
import secrets

import httpx
import pytest
from app.config import load_settings, settings
from app.services.ai_provider import ProviderConfig, create_parser, parse_candidates
from app.services.capabilities import installation_capabilities
from app.services.document_reader import LocalPDFReader
from app.services.email import EmailConfigError, send_email
from PIL import Image
from reportlab.pdfgen import canvas


@pytest.fixture
async def admin_headers(db_session):
    from app.models.user import User
    from app.services.auth import create_access_token, hash_password

    user = User(
        email="portable@example.test",
        full_name="Portable fixture",
        role="admin",
        password_hash=hash_password("test-only-password"),
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "Authorization": "Bearer " + create_access_token({"sub": str(user.id), "role": "admin"})
    }


def production_settings(**overrides):
    values = dict(
        _env_file=None,
        app_env="production",
        DB_PASSWORD="disposable-db-secret-for-tests",
        secret_key="x" * 40,
        frontend_base_url="https://cap.example.test",
        allowed_hosts=["cap.example.test"],
        cors_origins=["https://cap.example.test"],
        AI_PROVIDER="none",
        EMAIL_MODE="disabled",
    )
    values.update(overrides)
    return load_settings(**values)


def test_production_without_external_services():
    config = production_settings()
    assert config.ai_provider == "none"
    assert not config.email_available
    caps = installation_capabilities(config)
    assert caps["ai"]["external_processing"] is False
    assert caps["email"]["enabled"] is False


@pytest.mark.parametrize(
    "name,value", [("AI_PROVIDER", "typo"), ("EMAIL_MODE", "typo"), ("EMAIL_MODE", "log")]
)
def test_bad_or_unsafe_production_modes_fail(name, value):
    with pytest.raises(RuntimeError):
        production_settings(**{name: value})


def test_credentials_do_not_enable_ai_implicitly():
    config = load_settings(_env_file=None, openai_api_key="not-real", anthropic_api_key="not-real")
    assert config.ai_provider == "none"
    assert "not-real" not in json.dumps(installation_capabilities(config))


def test_disabled_email_cannot_send_even_with_smtp_credentials(monkeypatch):
    monkeypatch.setattr(settings, "email_mode", "disabled")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from", "sender@example.test")
    assert not settings.email_available
    with pytest.raises(EmailConfigError, match="disabled"):
        send_email(["user@example.test"], "test", "test")


def candidate_json():
    return json.dumps(
        {
            "requirements": [
                {
                    "reference_id": "1.1",
                    "title": None,
                    "text": "The system shall retain logs.",
                    "requirement_type": "mandatory",
                    "parent_reference": "1",
                    "confidence": 0.9,
                }
            ]
        }
    )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_provider_text_and_image_contracts(provider, monkeypatch):
    requests = []
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.example.test")
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.example.test")

    def handler(request):
        requests.append(request)
        if provider == "openai":
            assert request.url.host == "api.openai.com"
            return httpx.Response(
                200,
                json={
                    "choices": [{"finish_reason": "stop", "message": {"content": candidate_json()}}]
                },
            )
        assert request.url.host == "api.anthropic.com"
        return httpx.Response(
            200,
            json={
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": candidate_json()}],
            },
        )

    config = ProviderConfig(provider, "test-model", "not-a-real-key")
    parser = create_parser(config, transport=httpx.MockTransport(handler))
    assert "not-a-real-key" not in repr(config)
    rows = await parser.parse("The system shall retain logs.", "policy", 7)
    assert rows[0]["page_number"] == 7
    await parser.complete(
        "Read the image", {"name": "test", "schema": {}}, image_uri="data:image/png;base64,AAAA"
    )
    assert len(requests) == 2
    assert json.loads(requests[-1].content)["model"] == "test-model"


async def test_provider_errors_never_expose_response_or_follow_redirects():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            302, headers={"location": "https://untrusted.example.test"}, text="private-document"
        )

    parser = create_parser(
        ProviderConfig("openai", "test", "private-key"), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ValueError, match="HTTP 302") as exc:
        await parser.parse("private-document", "policy", 1)
    assert "private-document" not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '{"requirements": [{}]}',
        '{"requirements": [{"text":"x","requirement_type":"invalid","confidence":1}]}',
    ],
)
def test_invalid_provider_output_is_an_error(raw):
    with pytest.raises(ValueError, match="invalid requirement"):
        parse_candidates(raw, 1)


def test_saved_local_run_cannot_start_using_cloud_credentials():
    config = production_settings(AI_PROVIDER="openai", openai_api_key="test")
    assert ProviderConfig.from_settings(config, provider="local", model="rules").provider == "none"
    with pytest.raises(ValueError, match="changed"):
        ProviderConfig.from_settings(config, provider="anthropic", model="old-model")
    first = ProviderConfig.from_settings(config, provider="openai", model="saved-model")
    config.openai_model = "new-model"
    assert first.model == "saved-model"


def make_pdf():
    result = io.BytesIO()
    pdf = canvas.Canvas(result, pagesize=(595, 842), invariant=True)
    for page in range(2):
        pdf.drawString(40, 780, f"3.{page + 1} The system shall retain logs.")
        pdf.showPage()
    pdf.save()
    return result.getvalue()


def test_local_pdf_read_layout_render_and_limits(tmp_path):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(make_pdf())
    reader = LocalPDFReader()
    assert reader.validate(source, max_pages=2) == 2
    assert "shall retain logs" in reader.read_pages(source)[0]["text"]
    layout = reader.read_layout(source)
    assert layout[0]["words"][0][4] == "3.1"
    with Image.open(io.BytesIO(reader.render_png(source, 1, dpi=72))) as rendered:
        assert rendered.size == (595, 842)
    with pytest.raises(ValueError, match="page limit"):
        reader.validate(source, max_pages=1)
    with pytest.raises(ValueError, match="bounds"):
        reader.render_png(source, 0, dpi=72)


def test_seed_guard_refuses_application_databases(tmp_path):
    from app.test_environment import validate_test_database

    env = {"APP_ENV": "test", "CAP_ALLOW_TEST_SEED": "1"}
    for url in [
        "postgresql+asyncpg://u:p@db:5432/cap",
        "postgresql+asyncpg://u:p@127.0.0.1:5432/cap",
        "sqlite+aiosqlite:///./test.db",
    ]:
        with pytest.raises(RuntimeError):
            validate_test_database(dict(env, DATABASE_URL=url, E2E_DATABASE_URL=url))
    url = f"sqlite+aiosqlite:///{tmp_path}/cap_e2e.db"
    assert (
        validate_test_database(
            dict(env, DATABASE_URL=url, E2E_DATABASE_URL=url, E2E_WORK_DIR=str(tmp_path))
        )
        == url
    )
    with pytest.raises(RuntimeError):
        validate_test_database(dict(env, DATABASE_URL=url, E2E_DATABASE_URL=url))


def test_optional_ocr_preserves_native_pages_and_reads_scans(tmp_path):
    import shutil
    from reportlab.lib.utils import ImageReader
    from app.services.ocr_service import run_ocr_with_fallback

    if not shutil.which("tesseract"):
        pytest.skip("Optional OCR binary not installed")
    native = tmp_path / "native.pdf"
    native.write_bytes(make_pdf())
    raster = LocalPDFReader().render_png(native, 1, dpi=200)
    mixed = tmp_path / "mixed.pdf"
    pdf = canvas.Canvas(str(mixed), pagesize=(595, 842), invariant=True)
    pdf.drawImage(ImageReader(io.BytesIO(raster)), 0, 0, width=595, height=842)
    pdf.showPage()
    text = "4.1 The operator shall keep the original native text and logs."
    pdf.drawString(40, 780, text)
    pdf.save()
    before = mixed.read_bytes()
    result = run_ocr_with_fallback(
        str(mixed), work_dir=str(tmp_path / "ocr"), languages="eng", timeout_seconds=30
    )
    assert result.applied, result.error
    pages = LocalPDFReader().read_pages(result.output_path)
    assert len(pages) == 2
    assert "shall retain logs" in pages[0]["text"]
    assert text in pages[1]["text"]
    assert mixed.read_bytes() == before


async def test_capabilities_requires_login_and_exposes_no_credentials(
    client, admin_headers, monkeypatch
):
    monkeypatch.setattr(settings, "ai_provider_setting", "none")
    monkeypatch.setattr(settings, "openai_api_key", "not-real-private-key")
    assert (await client.get("/api/v1/capabilities")).status_code == 401
    response = await client.get("/api/v1/capabilities", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["ai"]["enabled"] is False
    assert "not-real-private-key" not in response.text


async def test_cloud_extraction_needs_per_request_consent(
    client, admin_headers, default_jurisdiction, db_session, monkeypatch
):
    from app.tasks.extraction import extract_requirements_task
    from app.schemas.installation_settings import AIUpdate
    from app.services.installation_settings import save_ai_settings

    monkeypatch.setattr(settings, "ai_provider_setting", "none")
    saved_key = secrets.token_urlsafe(24)
    await save_ai_settings(db_session, AIUpdate(
        revision=0, provider="openai", model="saved-test-model", api_key=saved_key
    ))
    await db_session.commit()
    capabilities = await client.get("/api/v1/capabilities", headers=admin_headers)
    assert capabilities.json()["ai"]["provider"] == "openai"
    assert capabilities.json()["ai"]["model"] == "saved-test-model"
    assert saved_key not in capabilities.text
    calls = []
    monkeypatch.setattr(
        extract_requirements_task, "delay", lambda *args, **kwargs: calls.append(args)
    )
    uploaded = await client.post(
        "/api/v1/documents",
        headers=admin_headers,
        files={"file": ("synthetic.pdf", make_pdf(), "application/pdf")},
        data={
            "document_type": "standard",
            "jurisdiction_id": str(default_jurisdiction.id),
        },
    )
    assert uploaded.status_code == 201
    url = "/api/v1/documents/" + uploaded.json()["id"] + "/extract"
    refused = await client.post(url, headers=admin_headers)
    assert refused.status_code == 400
    assert "Confirm external AI processing" in refused.text
    assert calls == []
    accepted = await client.post(url, headers=admin_headers, params={"allow_external_ai": "true"})
    assert accepted.status_code == 200, accepted.text
    assert len(calls) == 1


@pytest.mark.parametrize("implicit_ssl", [False, True])
def test_email_transport_uses_explicit_saved_snapshot(monkeypatch, implicit_ssl):
    from app.services import email
    import ssl

    events = []
    class FakeSMTP:
        def __init__(self, host, port, **options):
            assert (host, port) == ("saved.smtp.test", 465 if implicit_ssl else 587)
            assert options["timeout"] == 10
            assert isinstance(options.get("context"), ssl.SSLContext) == implicit_ssl
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, *, context):
            assert isinstance(context, ssl.SSLContext)
            events.append("starttls")
        def login(self, user, password):
            assert (user, password) == ("saved-user", "saved-password")
            events.append("login")
        def send_message(self, message):
            assert message["From"] == "saved@example.test"
            assert message["To"] == "recipient@example.test"
            events.append("send")

    def wrong_transport(*args, **kwargs):
        pytest.fail("Wrong SMTP security transport selected")
    monkeypatch.setattr(email.smtplib, "SMTP_SSL" if implicit_ssl else "SMTP", FakeSMTP)
    monkeypatch.setattr(email.smtplib, "SMTP" if implicit_ssl else "SMTP_SSL", wrong_transport)
    monkeypatch.setattr(settings, "email_mode", "disabled")
    snapshot = settings.model_copy(update={
        "email_mode": "smtp", "smtp_host": "saved.smtp.test",
        "smtp_port": 465 if implicit_ssl else 587, "smtp_use_ssl": implicit_ssl,
        "smtp_use_tls": True, "smtp_user": "saved-user", "smtp_password": "saved-password",
        "smtp_from": "saved@example.test",
    })
    send_email(["recipient@example.test"], "Synthetic test", "No network", config=snapshot)
    assert events == (["login", "send"] if implicit_ssl else ["starttls", "login", "send"])
    assert settings.email_mode == "disabled"
