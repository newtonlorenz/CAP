import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.api import product_feedback
from app.config import Settings, settings
from app.models.audit import AuditLog
from app.models.user import User
from app.services.auth import create_access_token


@pytest.fixture
async def identities(db_session):
    users = [
        User(
            id=uuid4(),
            email=f"{role}@feedback.test",
            full_name=role,
            password_hash="not-used",
            role=role,
            active=True,
            auth_version=0,
        )
        for role in ["admin", "contributor"]
    ]
    db_session.add_all(users)
    await db_session.commit()
    return users


def auth(user):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            {
                "sub": str(user.id),
                "role": user.role,
                "ver": 0,
            }
        )
    }


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(settings, "feedback_service_url", "http://feedback.internal")
    monkeypatch.setattr(
        settings, "feedback_service_key", "fixture-service-secret-at-least-32-characters"
    )
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.endswith("/screenshot"):
            return httpx.Response(
                200, content=b"jpeg-fixture", headers={"Content-Type": "image/jpeg"}
            )
        if request.method == "GET":
            return httpx.Response(200, json={"items": [], "total": 0})
        body = json.loads(request.content)
        return httpx.Response(
            201 if request.method == "POST" else 200,
            json={
                "id": body.get("id", str(uuid4())),
                "kind": "bug",
                "page_path": "/guide",
                "status": body.get("status", "new"),
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        product_feedback.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw),
    )
    return calls


def payload(**extra):
    return {"id": str(uuid4()), "kind": "bug", "message": "Overlap", "page_path": "/guide", **extra}


async def test_submit_trusted_context_and_audit(client, identities, service, db_session):
    user = identities[1]
    response = await client.post(
        "/api/v1/product-feedback",
        json=payload(),
        headers={
            **auth(user),
            "X-Feedback-Scope": "spoofed",
            "X-Feedback-Role": "admin",
        },
    )
    assert response.status_code == 201
    assert service[0].headers["X-Feedback-Scope"] == "cap:legacy"
    assert service[0].headers["X-Feedback-Actor"] == str(user.id)
    assert service[0].headers["X-Feedback-Role"] == "reporter"
    assert service[0].headers["Authorization"] == "Bearer " + settings.feedback_service_key
    event = (
        await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "product_feedback"))
    ).scalar_one()
    assert str(event.user_id) == str(user.id)


async def test_organisation_scope_derived_from_user(service):
    user = User(id=uuid4(), organization_id=uuid4(), role="admin")
    await product_feedback.forward("GET", "reports", user)
    assert service[0].headers["X-Feedback-Scope"] == f"cap:{user.organization_id}"


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/config", None),
        ("GET", "", None),
        ("POST", "", payload()),
        ("GET", f"/{uuid4()}/screenshot", None),
        ("PATCH", f"/{uuid4()}", {"status": "done"}),
    ],
)
async def test_auth_required(client, method, path, body):
    assert (
        await client.request(method, "/api/v1/product-feedback" + path, json=body)
    ).status_code == 401


async def test_admin_routes_and_image_headers(client, identities, service):
    root = "/api/v1/product-feedback"
    for method, path, body in [
        ("GET", "", None),
        ("GET", f"/{uuid4()}/screenshot", None),
        ("PATCH", f"/{uuid4()}", {"status": "done"}),
    ]:
        assert (
            await client.request(method, root + path, json=body, headers=auth(identities[1]))
        ).status_code == 403
        response = await client.request(method, root + path, json=body, headers=auth(identities[0]))
        assert response.status_code == 200
        if path.endswith("/screenshot"):
            assert response.headers["cache-control"] == "private, no-store"
    assert (await client.get(root + "/config", headers=auth(identities[1]))).json() == {
        "enabled": True
    }


async def test_invalid_input_and_csrf(client, identities, service):
    root = "/api/v1/product-feedback"
    for extra in [
        {"kind": "no"},
        {"message": " "},
        {"page_path": "//other.invalid"},
        {"scope": "spoofed"},
    ]:
        assert (
            await client.post(root, json=payload(**extra), headers=auth(identities[1]))
        ).status_code == 422
    assert (
        await client.post(root, content=b"x" * 3_000_001, headers=auth(identities[1]))
    ).status_code == 413
    assert (
        await client.patch(root + f"/{uuid4()}", json={"status": "no"}, headers=auth(identities[0]))
    ).status_code == 422
    assert (await client.get(root + "?limit=101", headers=auth(identities[0]))).status_code == 422
    client.cookies.set("access_token", auth(identities[1])["Authorization"].split(" ")[1])
    assert (await client.post(root, json=payload())).status_code == 403
    assert not service


async def test_disabled_and_upstream_failure(client, identities, monkeypatch):
    root = "/api/v1/product-feedback"
    monkeypatch.setattr(settings, "feedback_service_url", "")
    monkeypatch.setattr(settings, "feedback_service_key", "")
    assert (await client.get(root + "/config", headers=auth(identities[0]))).json() == {
        "enabled": False
    }
    assert (await client.post(root, json=payload(), headers=auth(identities[1]))).status_code == 503
    monkeypatch.setattr(settings, "feedback_service_url", "http://feedback.internal")
    monkeypatch.setattr(settings, "feedback_service_key", "fixture-" * 5)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        product_feedback.httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(500, text="private error")), **kw
        ),
    )
    response = await client.post(root, json=payload(), headers=auth(identities[1]))
    assert response.status_code == 503
    assert "private error" not in response.text


def test_config_rejects_incomplete_settings():
    with pytest.raises(ValueError):
        Settings(_env_file=None, feedback_service_url="http://feedback")
