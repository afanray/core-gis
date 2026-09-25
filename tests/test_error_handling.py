import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_error_handler_401_unauthenticated(client: AsyncClient):
    # No auth header
    response = await client.get("/api/v1/analytics/overview")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHENTICATED"
    assert "timestamp" in data["error"]

@pytest.mark.asyncio
async def test_error_handler_403_forbidden(client: AsyncClient, admin_token: str):
    # Regular admin trying to perform superadmin delete action
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.delete("/api/v1/transactions/TX-TEST-001", headers=headers)
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "FORBIDDEN"

@pytest.mark.asyncio
async def test_error_handler_404_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/transactions/TX-9999999", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_FOUND"

@pytest.mark.asyncio
async def test_error_handler_422_validation_error(client: AsyncClient):
    # Missing required body fields in login
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(data["error"]["details"], list)

@pytest.mark.asyncio
async def test_error_handler_405_method_not_allowed(client: AsyncClient):
    # POST to a GET-only endpoint
    response = await client.post("/api/v1/health")
    assert response.status_code == 405
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "METHOD_NOT_ALLOWED"
