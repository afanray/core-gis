import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_list_products(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/products", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 1

@pytest.mark.asyncio
async def test_create_product(client: AsyncClient, auth_headers: dict):
    payload = {
        "id": "support_200000",
        "title": "Dukungan Rp200.000 (Sponsor)",
        "description": "Sponsor utama Terra GIS",
        "amount": 200000,
        "currency": "IDR",
        "isActive": True
    }
    response = await client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == "support_200000"

@pytest.mark.asyncio
async def test_update_product(client: AsyncClient, auth_headers: dict):
    payload = {"title": "Dukungan Rp10.000 Updated"}
    response = await client.put("/api/v1/products/support_10000", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["title"] == "Dukungan Rp10.000 Updated"

@pytest.mark.asyncio
async def test_delete_product(client: AsyncClient, auth_headers: dict):
    response = await client.delete("/api/v1/products/support_10000", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == "support_10000"
