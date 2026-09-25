import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_analytics_overview(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "totalSupport" in data["data"]
    assert "totalCount" in data["data"]
    assert "averageSupport" in data["data"]
    assert data["data"]["totalSupport"] >= 10000

@pytest.mark.asyncio
async def test_analytics_monthly(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/analytics/monthly", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)

@pytest.mark.asyncio
async def test_analytics_products(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/analytics/products", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 4

@pytest.mark.asyncio
async def test_analytics_status_distribution(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/analytics/status-distribution", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
