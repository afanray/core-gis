import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_list_transactions(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/transactions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "meta" in data
    assert data["meta"]["total"] >= 1
    assert data["meta"]["page"] == 1

@pytest.mark.asyncio
async def test_get_transaction_by_id(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/transactions/TX-TEST-001", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == "TX-TEST-001"
    assert data["data"]["userName"] == "Budi Santoso"

@pytest.mark.asyncio
async def test_get_transaction_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/transactions/TX-NONEXISTENT", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_FOUND"

@pytest.mark.asyncio
async def test_create_transaction(client: AsyncClient, auth_headers: dict):
    payload = {
        "productId": "support_10000",
        "name": "Dukungan Rp10.000",
        "amount": 10000,
        "currency": "IDR",
        "status": "Pending",
        "userName": "Dewi Lestari",
        "userEmail": "dewi@gmail.com"
    }
    response = await client.post("/api/v1/transactions", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["userName"] == "Dewi Lestari"
    assert data["data"]["status"] == "Pending"

@pytest.mark.asyncio
async def test_update_transaction_status(client: AsyncClient, auth_headers: dict):
    response = await client.patch(
        "/api/v1/transactions/TX-TEST-001/status",
        json={"status": "Failed"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "Failed"

@pytest.mark.asyncio
async def test_delete_transaction(client: AsyncClient, auth_headers: dict):
    response = await client.delete("/api/v1/transactions/TX-TEST-001", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == "TX-TEST-001"

@pytest.mark.asyncio
async def test_export_transactions_csv(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/transactions/export", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "ID,Product ID,Title" in response.text

@pytest.mark.asyncio
async def test_verify_google_play(client: AsyncClient, auth_headers: dict):
    payload = {
        "purchase_token": "token_test_12345",
        "product_id": "terragis_sub_monthly"
    }
    response = await client.post("/api/v1/transactions/verify-google-play", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["subscription_status"] == "active"
    assert data["data"]["has_access"] is True

