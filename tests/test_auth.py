import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_success_json(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@terragis.io", "password": "AdminPassword123!"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]
    assert data["data"]["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@terragis.io", "password": "WrongPassword!"}
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHENTICATED"
    assert "Incorrect email or password" in data["error"]["message"]

@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@terragis.io", "password": "Password123!"}
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "deactivated" in data["error"]["message"]

@pytest.mark.asyncio
async def test_get_me_profile_success(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email"] == "admin@terragis.io"
    assert data["data"]["role"] == "superadmin"

@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHENTICATED"

@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    # Login to get refresh token
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@terragis.io", "password": "AdminPassword123!"}
    )
    refresh_token = login_res.json()["data"]["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]

@pytest.mark.asyncio
async def test_register_user_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@terragis.io", "name": "New User", "password": "SecurePassword123!"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]

@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@terragis.io", "name": "Duplicate Admin", "password": "SecurePassword123!"}
    )
    assert response.status_code == 409
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "CONFLICT"

@pytest.mark.asyncio
async def test_google_login_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/google",
        json={"email": "googleuser@terragis.io", "name": "Google SSO User"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]

@pytest.mark.asyncio
async def test_google_login_triggers_email_alert(client: AsyncClient, monkeypatch):
    called = []
    async def mock_send_login_alert(to_email, user_name, ip_address=None, user_agent=None, **kwargs):
        called.append({"to_email": to_email, "name": user_name, "ip": ip_address, "ua": user_agent, "kwargs": kwargs})

    from app.services.email_service import email_service
    monkeypatch.setattr(email_service, "send_login_alert", mock_send_login_alert)

    response = await client.post(
        "/api/v1/auth/google",
        json={"email": "alert_google@terragis.io", "name": "Alert User"},
        headers={"User-Agent": "Flutter Test Agent", "X-Forwarded-For": "203.0.113.195"}
    )
    assert response.status_code == 200
    assert len(called) == 1
    assert called[0]["to_email"] == "alert_google@terragis.io"
    assert called[0]["name"] == "Alert User"
    assert called[0]["ip"] == "203.0.113.195"
    assert called[0]["ua"] == "Flutter Test Agent"
    assert called[0]["kwargs"]["login_method"] == "Google SSO"


