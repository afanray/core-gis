import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_records_history(client: AsyncClient):
    payload = {
        "email": "admin@terragis.io",
        "password": "AdminPassword123!"
    }
    res = await client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data["data"]
    token = data["data"]["access_token"]

    # Verify fetching login history
    headers = {"Authorization": f"Bearer {token}"}
    history_res = await client.get("/api/v1/auth/login-history", headers=headers)
    assert history_res.status_code == 200
    history_data = history_res.json()["data"]
    assert len(history_data) >= 1
    assert history_data[0]["is_revoked"] is False

@pytest.mark.asyncio
async def test_google_login_records_history(client: AsyncClient):
    payload = {
        "email": "surveyor.gis@gmail.com",
        "name": "Surveyor GIS"
    }
    res = await client.post("/api/v1/auth/google", json=payload)
    assert res.status_code == 200
    data = res.json()
    token = data["data"]["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    history_res = await client.get("/api/v1/auth/login-history", headers=headers)
    assert history_res.status_code == 200
    history_data = history_res.json()["data"]
    assert len(history_data) >= 1
    assert history_data[0]["login_type"] == "google"

@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient):
    # 1. Login
    payload = {
        "email": "admin@terragis.io",
        "password": "AdminPassword123!"
    }
    login_res = await client.post("/api/v1/auth/login", json=payload)
    token = login_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Check profile works
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200

    # 3. Logout
    logout_res = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200

    # 4. Check profile with revoked token now returns 401 Unauthorized
    revoked_res = await client.get("/api/v1/auth/me", headers=headers)
    assert revoked_res.status_code == 401
