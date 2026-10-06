from secrets import token_urlsafe

from app.services.auth import hash_password, verify_password, create_access_token, decode_token


def test_password_hashing():
    password = token_urlsafe(24)
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_bcrypt_does_not_silently_truncate_passwords():
    import pytest
    with pytest.raises(ValueError):
        hash_password("é" * 37)


def test_create_and_decode_token():
    token = create_access_token({"sub": "user@example.com", "role": "admin"})
    payload = decode_token(token)
    assert payload["sub"] == "user@example.com"
    assert payload["role"] == "admin"


async def test_login_success(client, db_session):
    from app.models.user import User

    user = User(
        email="admin@example.com",
        password_hash=hash_password("password123"),
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"

    cookies = response.cookies
    assert cookies.get("access_token")
    assert cookies.get("refresh_token")
    assert cookies.get("csrf_token")


async def test_login_wrong_password(client, db_session):
    from app.models.user import User

    user = User(
        email="admin@example.com",
        password_hash=hash_password("password123"),
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


async def test_logout_clears_session_cookies(client):
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("access_token=" in header for header in set_cookie_headers)
    assert any("refresh_token=" in header for header in set_cookie_headers)
    assert any("csrf_token=" in header for header in set_cookie_headers)
