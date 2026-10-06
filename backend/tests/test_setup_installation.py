import secrets

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models.document import Document
from app.models.jurisdiction import Jurisdiction
from app.models.organization import Organization
from app.models.program import RequirementSetVersion
from app.models.user import User
from app.services.auth import create_access_token, verify_password
from app.services.bootstrap import setup_installation
from app.services.setup_example import EXAMPLE_CODE, EXAMPLE_SET_NAME

SETUP_PASSWORD = secrets.token_urlsafe(18)


def _options(**changes):
    return {
        "email": "operator@example.com",
        "name": "Local Operator",
        "password": SETUP_PASSWORD,
        "jurisdiction_code": "xy",
        "jurisdiction_name": "Example jurisdiction",
        **changes,
    }


@pytest.mark.asyncio
async def test_first_setup_creates_trusted_operator_and_jurisdiction_without_example(
    setup_database, client, monkeypatch
):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    async with setup_database() as db:
        result = await setup_installation(db, **_options())
    assert result.created_user and result.created_jurisdiction
    assert not result.created_example

    async with setup_database() as db:
        user = (await db.execute(select(User).where(User.email == result.email))).scalar_one()
        assert user.role == "admin" and user.operator_trusted and user.organization_id
        assert verify_password(SETUP_PASSWORD, user.password_hash)
        assert (await db.execute(select(func.count(Document.id)))).scalar_one() == 0
        user_id = user.id

    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["installation_operator"] is True
    assert "operator_trusted" not in me.json()
    users_me = await client.get("/api/v1/users/me", headers=headers)
    assert users_me.json()["installation_operator"] is True
    assert "operator_trusted" not in users_me.json()
    created = await client.post(
        "/api/v1/jurisdictions",
        json={"code": "zz", "name": "Second scope"},
        headers=headers,
    )
    assert created.status_code == 201


@pytest.mark.asyncio
async def test_repeat_setup_is_safe_and_conflicting_scope_rolls_back(setup_database):
    async with setup_database() as db:
        await setup_installation(db, **_options())
    async with setup_database() as db:
        user = (
            await db.execute(select(User).where(User.email == "operator@example.com"))
        ).scalar_one()
        original_hash = user.password_hash
    async with setup_database() as db:
        repeated = await setup_installation(
            db, **_options(name=None, password=None, existing_admin=True)
        )
    assert not repeated.created_user and not repeated.created_jurisdiction
    async with setup_database() as db:
        assert (await db.execute(select(func.count(User.id)))).scalar_one() == 1
        assert (
            await db.execute(select(func.count(Jurisdiction.id)).where(Jurisdiction.code == "xy"))
        ).scalar_one() == 1
        user = (
            await db.execute(select(User).where(User.email == "operator@example.com"))
        ).scalar_one()
        assert user.password_hash == original_hash
        assert user.auth_version == 0

    async with setup_database() as db:
        with pytest.raises(ValueError, match="different or inactive"):
            await setup_installation(
                db,
                **_options(
                    name=None,
                    password=None,
                    existing_admin=True,
                    jurisdiction_name="Conflicting scope",
                ),
            )
    async with setup_database() as db:
        assert (
            await db.execute(select(Jurisdiction).where(Jurisdiction.code == "xy"))
        ).scalar_one().name == "Example jurisdiction"


@pytest.mark.asyncio
async def test_existing_tenant_admin_requires_explicit_local_designation_and_http_cannot_grant_it(
    setup_database, client, monkeypatch
):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    async with setup_database() as db:
        organization = Organization(code="tenant", name="Tenant")
        db.add(organization)
        await db.flush()
        admin = User(
            organization_id=organization.id,
            email="tenant@example.com",
            full_name="Tenant admin",
            password_hash="unused",
            role="admin",
            active=True,
        )
        db.add(admin)
        await db.commit()
        admin_id = admin.id

    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin_id)})}"}
    forbidden = await client.post(
        "/api/v1/jurisdictions",
        json={"code": "qa", "name": "QA"},
        headers=headers,
    )
    assert forbidden.status_code == 403
    attempt = await client.put(
        f"/api/v1/users/{admin_id}",
        json={"operator_trusted": True, "installation_operator": True},
        headers=headers,
    )
    assert attempt.status_code == 200
    assert "operator_trusted" not in attempt.json()
    async with setup_database() as db:
        assert not (await db.get(User, admin_id)).operator_trusted
    async with setup_database() as db:
        with pytest.raises(ValueError, match="Use --existing-admin"):
            await setup_installation(db, **_options(email="tenant@example.com"))
    async with setup_database() as db:
        await setup_installation(
            db,
            **_options(email="tenant@example.com", name=None, password=None, existing_admin=True),
        )
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    async with setup_database() as db:
        assert (await db.get(User, admin_id)).auth_version == 1
    designated_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(admin_id), 'ver': 1})}"
    }
    designated_me = await client.get("/api/v1/auth/me", headers=designated_headers)
    assert designated_me.status_code == 200
    assert designated_me.json()["installation_operator"] is True
    async with setup_database() as db:
        await setup_installation(
            db,
            **_options(email="tenant@example.com", name=None, password=None, existing_admin=True),
        )
    async with setup_database() as db:
        assert (await db.get(User, admin_id)).auth_version == 1
    assert (await client.get("/api/v1/auth/me", headers=designated_headers)).status_code == 200
    async with setup_database() as db:
        other = User(
            organization_id=organization.id,
            email="other@example.com",
            full_name="Other admin",
            password_hash="unused",
            role="admin",
            active=True,
        )
        db.add(other)
        await db.commit()
        other_id = other.id
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_id)})}"}
    blocked = await client.put(
        f"/api/v1/users/{admin_id}", json={"active": False}, headers=other_headers
    )
    assert blocked.status_code == 403
    async with setup_database() as db:
        designated = await db.get(User, admin_id)
        designated.active = False
        designated.role = "contributor"
        await db.commit()
    reactivation = await client.put(
        f"/api/v1/users/{admin_id}",
        json={"active": True, "role": "admin"},
        headers=other_headers,
    )
    assert reactivation.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"role": "contributor"}, {"active": False}])
async def test_operator_cannot_demote_or_deactivate_self(
    setup_database, client, monkeypatch, change
):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    async with setup_database() as db:
        await setup_installation(db, **_options())
    async with setup_database() as db:
        operator = (
            await db.execute(select(User).where(User.email == "operator@example.com"))
        ).scalar_one()
        operator_id = operator.id
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(operator_id)})}"}

    blocked = await client.put(
        f"/api/v1/users/{operator_id}", json=change, headers=headers
    )
    assert blocked.status_code == 400
    async with setup_database() as db:
        operator = await db.get(User, operator_id)
        assert operator.role == "admin" and operator.active and operator.operator_trusted
        assert operator.auth_version == 0
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_another_operator_can_demote_designated_operator(
    setup_database, client, monkeypatch
):
    monkeypatch.setattr(settings, "installation_operator_ids", [])
    async with setup_database() as db:
        await setup_installation(db, **_options())
    async with setup_database() as db:
        first = (
            await db.execute(select(User).where(User.email == "operator@example.com"))
        ).scalar_one()
        second = User(
            organization_id=first.organization_id,
            email="second@example.com",
            full_name="Second operator",
            password_hash="unused",
            role="admin",
            active=True,
        )
        db.add(second)
        await db.commit()
        first_id, second_id = first.id, second.id
    async with setup_database() as db:
        await setup_installation(
            db,
            **_options(email="second@example.com", name=None, password=None, existing_admin=True),
        )
    second_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(second_id), 'ver': 1})}"
    }
    updated = await client.put(
        f"/api/v1/users/{first_id}",
        json={"role": "contributor"},
        headers=second_headers,
    )
    assert updated.status_code == 200
    async with setup_database() as db:
        first = await db.get(User, first_id)
        assert first.role == "contributor" and first.auth_version == 1


@pytest.mark.asyncio
async def test_opt_in_example_is_separate_unapproved_and_repeat_safe(setup_database, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    async with setup_database() as db:
        result = await setup_installation(db, **_options(example=True))
    assert result.created_example
    async with setup_database() as db:
        sample = (
            await db.execute(select(Document).where(Document.name == EXAMPLE_SET_NAME))
        ).scalar_one()
        sample_scope = await db.get(Jurisdiction, sample.jurisdiction_id)
        assert sample_scope.code == EXAMPLE_CODE
        assert sample.status == "draft" and sample.approved_by is None
        version = (
            await db.execute(
                select(RequirementSetVersion).where(RequirementSetVersion.document_id == sample.id)
            )
        ).scalar_one()
        assert version.status == "draft" and version.approved_by is None
    async with setup_database() as db:
        repeated = await setup_installation(
            db, **_options(name=None, password=None, existing_admin=True, example=True)
        )
    assert not repeated.created_example
    async with setup_database() as db:
        assert (await db.execute(select(func.count(Document.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_example_rejected_in_production_without_writes(setup_database, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    async with setup_database() as db:
        with pytest.raises(ValueError, match="only in development or test"):
            await setup_installation(db, **_options(example=True))
    async with setup_database() as db:
        assert (await db.execute(select(func.count(User.id)))).scalar_one() == 0
        assert (
            await db.execute(select(func.count(Jurisdiction.id)).where(Jurisdiction.code == "xy"))
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_invalid_email_stops_before_database_changes(setup_database):
    async with setup_database() as db:
        with pytest.raises(ValueError, match="valid operator email"):
            await setup_installation(db, **_options(email="not-an-email"))
    async with setup_database() as db:
        assert (await db.execute(select(func.count(User.id)))).scalar_one() == 0
