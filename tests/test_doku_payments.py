import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_doku_checkout(client: AsyncClient, auth_headers: dict):
    payload = {
        "product_id": "support_10000"
    }
    response = await client.post("/api/v1/payments/create-doku-checkout", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "invoice_number" in data["data"]
    assert "payment_url" in data["data"]
    assert data["data"]["amount"] == 10000

@pytest.mark.asyncio
async def test_doku_webhook_payment_success(client: AsyncClient, auth_headers: dict):
    # 1. Create a checkout first to log transaction
    create_res = await client.post(
        "/api/v1/payments/create-doku-checkout",
        json={"product_id": "support_10000"},
        headers=auth_headers
    )
    invoice_number = create_res.json()["data"]["invoice_number"]

    # 2. Simulate DOKU HTTP Webhook Notification Payload
    webhook_payload = {
        "service": {
            "id": "ONLINE_PAYMENT"
        },
        "order": {
            "invoice_number": invoice_number,
            "amount": 10000
        },
        "transaction": {
            "status": "SUCCESS",
            "date": "2026-09-24T22:58:00Z"
        }
    }

    webhook_headers = {
        "Client-Id": "BRN-0266-1790264635586",
        "Request-Id": "req-12345",
        "Request-Timestamp": "2026-09-24T22:58:00Z",
        "Signature": "HMACSHA256=mock_signature"
    }

    # 3. Post webhook notification to /api/v1/webhooks/doku
    response = await client.post("/api/v1/webhooks/doku", json=webhook_payload, headers=webhook_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert data["invoice_number"] == invoice_number
    assert data["is_success"] is True
