import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_midtrans_snap(client: AsyncClient, auth_headers: dict):
    payload = {
        "product_id": "support_10000"
    }
    response = await client.post("/api/v1/payments/create-midtrans-snap", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "invoice_number" in data["data"]
    assert "token" in data["data"]
    assert "redirect_url" in data["data"]
    assert data["data"]["amount"] == 10000

@pytest.mark.asyncio
async def test_midtrans_webhook_payment_success(client: AsyncClient, auth_headers: dict):
    # 1. Create a Snap checkout session first
    create_res = await client.post(
        "/api/v1/payments/create-midtrans-snap",
        json={"product_id": "support_10000"},
        headers=auth_headers
    )
    invoice_number = create_res.json()["data"]["invoice_number"]

    # 2. Simulate Midtrans HTTP Webhook Notification Payload
    webhook_payload = {
        "order_id": invoice_number,
        "status_code": "200",
        "gross_amount": "10000.00",
        "signature_key": "mock_signature_key",
        "transaction_status": "settlement",
        "fraud_status": "accept"
    }

    # 3. Post webhook notification to /api/v1/webhooks/midtrans
    response = await client.post("/api/v1/webhooks/midtrans", json=webhook_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert data["order_id"] == invoice_number
    assert data["is_success"] is True

@pytest.mark.asyncio
async def test_resume_midtrans_payment_and_history(client: AsyncClient, auth_headers: dict):
    # 1. Create a pending snap transaction
    create_res = await client.post(
        "/api/v1/payments/create-midtrans-snap",
        json={"product_id": "support_10000"},
        headers=auth_headers
    )
    assert create_res.status_code == 201
    invoice_number = create_res.json()["data"]["invoice_number"]
    token = create_res.json()["data"]["token"]

    # 2. Check GET /api/v1/payments/my-transactions
    hist_res = await client.get("/api/v1/payments/my-transactions", headers=auth_headers)
    assert hist_res.status_code == 200
    tx_list = hist_res.json()["data"]
    target_tx = next((t for t in tx_list if t["id"] == invoice_number), None)
    assert target_tx is not None
    assert target_tx["status"] == "Pending"
    assert target_tx["snap_token"] == token
    assert "vtweb" in target_tx["redirect_url"]

    # 3. Test POST /api/v1/payments/midtrans/resume/{invoice_number}
    resume_res = await client.post(
        f"/api/v1/payments/midtrans/resume/{invoice_number}",
        headers=auth_headers
    )
    assert resume_res.status_code == 200
    resume_data = resume_res.json()["data"]
    assert resume_data["invoice_number"] == invoice_number
    assert resume_data["token"] == token
    assert "vtweb" in resume_data["redirect_url"]

