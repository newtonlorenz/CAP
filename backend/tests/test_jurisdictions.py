import pytest

from app.config import settings
from app.models import MarketPack, Organization, User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def admin_user(db_session):
    user = User(
        email="jurisdictions-admin@example.com",
        password_hash=hash_password("testpass"),
        full_name="Jurisdictions Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def two_org_headers(db_session, monkeypatch):
    first = Organization(code="jurisdictions-first", name="First organisation")
    second = Organization(code="jurisdictions-second", name="Second organisation")
    db_session.add_all([first, second])
    await db_session.flush()

    users = {
        "first_admin": User(
            organization_id=first.id,
            email="first-jurisdictions-admin@example.com",
            password_hash=hash_password("testpass"),
            full_name="First Admin",
            role="admin",
        ),
        "second_admin": User(
            organization_id=second.id,
            email="second-jurisdictions-admin@example.com",
            password_hash=hash_password("testpass"),
            full_name="Second Admin",
            role="admin",
        ),
        "operator": User(
            organization_id=first.id,
            email="jurisdictions-operator@example.com",
            password_hash=hash_password("testpass"),
            full_name="Installation Operator",
            role="admin",
        ),
    }
    db_session.add_all(users.values())
    await db_session.commit()
    monkeypatch.setattr(settings, "installation_operator_ids", [str(users["operator"].id)])
    return {
        name: {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
        for name, user in users.items()
    }


@pytest.mark.parametrize("admin", ["first_admin", "second_admin"])
async def test_organisation_admin_cannot_update_shared_jurisdiction(
    client, default_jurisdiction, two_org_headers, admin
):
    url = f"/api/v1/jurisdictions/{default_jurisdiction.id}"
    response = await client.put(
        url,
        json={"code": "fi", "name": "Changed for every organisation", "active": False},
        headers=two_org_headers[admin],
    )
    assert response.status_code == 403

    for viewer in ("first_admin", "second_admin"):
        listing = await client.get("/api/v1/jurisdictions", headers=two_org_headers[viewer])
        assert listing.status_code == 200
        assert [
            (item["code"], item["name"], item["active"]) for item in listing.json()["items"]
        ] == [("dk", "Denmark", True)]


async def test_installation_operator_can_update_shared_jurisdiction_for_both_organisations(
    client, default_jurisdiction, two_org_headers
):
    response = await client.put(
        f"/api/v1/jurisdictions/{default_jurisdiction.id}",
        json={"code": "fi", "name": "Finland", "regulator_name": "Finnish regulator"},
        headers=two_org_headers["operator"],
    )
    assert response.status_code == 200

    for viewer in ("first_admin", "second_admin"):
        listing = await client.get("/api/v1/jurisdictions", headers=two_org_headers[viewer])
        assert listing.status_code == 200
        assert [
            (item["code"], item["name"], item["regulator_name"]) for item in listing.json()["items"]
        ] == [("fi", "Finland", "Finnish regulator")]


@pytest.mark.parametrize("admin", ["first_admin", "second_admin"])
async def test_organisation_admin_cannot_create_shared_jurisdiction(client, two_org_headers, admin):
    response = await client.post(
        "/api/v1/jurisdictions",
        json={"code": "se", "name": "Sweden"},
        headers=two_org_headers[admin],
    )
    assert response.status_code == 403

    listing = await client.get("/api/v1/jurisdictions", headers=two_org_headers["second_admin"])
    assert listing.status_code == 200
    assert [item["code"] for item in listing.json()["items"]] == ["dk"]


async def test_installation_operator_can_create_shared_jurisdiction_for_both_organisations(
    client, two_org_headers
):
    response = await client.post(
        "/api/v1/jurisdictions",
        json={"code": "se", "name": "Sweden"},
        headers=two_org_headers["operator"],
    )
    assert response.status_code == 201

    for viewer in ("first_admin", "second_admin"):
        listing = await client.get("/api/v1/jurisdictions", headers=two_org_headers[viewer])
        assert listing.status_code == 200
        assert {item["code"] for item in listing.json()["items"]} == {"dk", "se"}


async def test_list_jurisdictions_includes_market_pack_metadata(
    client, db_session, default_jurisdiction, auth_headers
):
    db_session.add(
        MarketPack(
            jurisdiction_id=default_jurisdiction.id,
            version="2026.1.0",
            status="published",
            parser_mode="dk_hybrid",
            supports_deterministic_import=True,
            coverage_notes="Production-ready Denmark pack.",
            source_label="Denmark baseline",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/jurisdictions?limit=1000", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    dk = next((item for item in data["items"] if item["code"] == "dk"), None)
    assert dk is not None
    assert dk["pack_status"] == "published"
    assert dk["pack_version"] == "2026.1.0"
    assert dk["parser_mode"] == "dk_hybrid"
    assert dk["supports_deterministic_import"] is True
    assert dk["coverage_notes"] == "Production-ready Denmark pack."


async def test_list_jurisdictions_defaults_pack_metadata_to_null(client, auth_headers):
    response = await client.get("/api/v1/jurisdictions?limit=1000", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    dk = next((item for item in data["items"] if item["code"] == "dk"), None)
    assert dk is not None
    assert dk["pack_status"] is None
    assert dk["pack_version"] is None
    assert dk["parser_mode"] is None
    assert dk["supports_deterministic_import"] is None
    assert dk["coverage_notes"] is None
