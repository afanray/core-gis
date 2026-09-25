import base64
import json
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_google_play_rtdn_webhook_renewed(client: AsyncClient, auth_headers: dict):
    # 1. First register/verify subscription for a user
    verify_payload = {
        "purchase_token": "gplay_test_token_rtdn",
        "product_id": "terragis_sub_monthly"
    }
    await client.post("/api/v1/transactions/verify-google-play", json=verify_payload, headers=auth_headers)

    # 2. Construct Google Cloud Pub/Sub message data
    notification_payload = {
        "version": "1.0",
        "packageName": "com.terralium.terragis",
        "eventTimeMillis": 1727155200000,
        "subscriptionNotification": {
            "version": "1.0",
            "notificationType": 2,  # RENEWED
            "purchaseToken": "gplay_test_token_rtdn",
            "subscriptionId": "terragis_sub_monthly"
        }
    }
    data_b64 = base64.b64encode(json.dumps(notification_payload).encode("utf-8")).decode("utf-8")

    pubsub_body = {
        "message": {
            "data": data_b64,
            "messageId": "msg_9999",
            "publishTime": "2026-09-24T12:00:00Z"
        },
        "subscription": "projects/terragis/subscriptions/gplay-rtdn"
    }

    # 3. Call RTDN Webhook Endpoint
    response = await client.post("/api/v1/webhooks/google-play", json=pubsub_body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
