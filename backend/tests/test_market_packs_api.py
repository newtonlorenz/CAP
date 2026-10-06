import pytest

from app.models import Jurisdiction, MarketPack, User
from app.services.auth import create_access_token, hash_password


@pytest.fixture
async def admin_user(db_session):
    user = User(
        email="market-packs-admin@example.com",
        password_hash=hash_password("testpass"),
        full_name="Market Packs Admin",
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
async def seeded_market_packs(db_session, default_jurisdiction):
    se = Jurisdiction(
        code="se",
        name="Sweden",
        regulator_name="Spelinspektionen",
        active=True,
    )
    fi = Jurisdiction(
        code="fi",
        name="Finland",
        regulator_name="National Police Board",
        active=True,
    )
    db_session.add_all([se, fi])
    await db_session.commit()
    await db_session.refresh(se)
    await db_session.refresh(fi)

    db_session.add_all(
        [
            MarketPack(
                jurisdiction_id=default_jurisdiction.id,
                version="2026.1.0",
                status="published",
                parser_mode="dk_hybrid",
                supports_deterministic_import=True,
                coverage_notes="Denmark production pack.",
                source_label="Denmark baseline",
            ),
            MarketPack(
                jurisdiction_id=se.id,
                version="2026.1.0",
                status="scaffold",
                parser_mode="generic_ai",
                supports_deterministic_import=False,
                coverage_notes="Sweden scaffold.",
                source_label="Sweden scaffold baseline",
            ),
            MarketPack(
                jurisdiction_id=fi.id,
                version="2026.1.0",
                status="scaffold",
                parser_mode="generic_ai",
                supports_deterministic_import=False,
                coverage_notes="Finland scaffold.",
                source_label="Finland scaffold baseline",
            ),
        ]
    )
    await db_session.commit()
    return


async def test_list_market_packs_returns_seeded_rows(client, auth_headers, seeded_market_packs):
    response = await client.get("/api/v1/market-packs?limit=1000", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3

    by_code = {item["jurisdiction_code"]: item for item in data["items"]}
    assert set(by_code) == {"dk", "se", "fi"}
    assert by_code["dk"]["status"] == "published"
    assert by_code["dk"]["parser_mode"] == "dk_hybrid"
    assert by_code["dk"]["supports_deterministic_import"] is True
    assert by_code["se"]["status"] == "scaffold"
    assert by_code["fi"]["status"] == "scaffold"


async def test_get_market_pack_by_jurisdiction_code_is_case_insensitive(
    client, auth_headers, seeded_market_packs
):
    response = await client.get("/api/v1/market-packs/SE", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["jurisdiction_code"] == "se"
    assert data["status"] == "scaffold"
    assert data["parser_mode"] == "generic_ai"
    assert data["supports_deterministic_import"] is False


async def test_get_market_pack_by_jurisdiction_code_404_when_missing(client, auth_headers):
    response = await client.get("/api/v1/market-packs/nope", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Market pack not found"
