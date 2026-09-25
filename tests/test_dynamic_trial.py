import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from app.models.product import Product

@pytest.mark.asyncio
async def test_new_user_unsubscribed_has_no_access(client: AsyncClient, db_session):
    # 1. Register a new user
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "newuser@terragis.io",
        "name": "New User",
        "password": "Password123!"
    })
    assert reg_res.status_code == 201
    token = reg_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Check profile: without choosing plan or claiming trial, user has NO access
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    user_data = me_res.json()["data"]
    assert user_data["subscription_status"] == "unsubscribed"
    assert user_data["has_access"] is False
    assert user_data["active_plan_id"] is None
    assert user_data["days_left_in_trial"] == 0


@pytest.mark.asyncio
async def test_claim_trial_success(client: AsyncClient, db_session):
    # Ensure trial product exists
    trial_prod = await db_session.get(Product, "terragis_sub_trial")
    if not trial_prod:
        trial_prod = Product(
            id="terragis_sub_trial",
            title="Uji Coba Gratis",
            amount=0.0,
            currency="IDR",
            billing_period="trial",
            trial_days=7,
            is_active=True
        )
        db_session.add(trial_prod)
        await db_session.commit()

    # 1. Register new user
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "trialuser@terragis.io",
        "name": "Trial User",
        "password": "Password123!"
    })
    token = reg_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Claim free trial
    claim_res = await client.post("/api/v1/payments/claim-trial", headers=headers)
    assert claim_res.status_code == 201
    claim_data = claim_res.json()["data"]
    assert claim_data["status"] == "active"
    assert claim_data["product_id"] == "terragis_sub_trial"
    assert claim_data["trial_days"] == 7
    assert claim_data["has_access"] is True

    # 3. Verify user profile now has trial access
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()["data"]
    assert me_data["subscription_status"] == "trial"
    assert me_data["has_access"] is True
    assert me_data["days_left_in_trial"] == 7
    assert me_data["active_plan_id"] == "terragis_sub_trial"


@pytest.mark.asyncio
async def test_claim_trial_anti_abuse_second_claim(client: AsyncClient, db_session):
    # 1. Register new user
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "abuseuser@terragis.io",
        "name": "Abuse User",
        "password": "Password123!"
    })
    token = reg_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Claim first time -> Success
    res1 = await client.post("/api/v1/payments/claim-trial", headers=headers)
    assert res1.status_code == 201

    # 3. Claim second time -> 409 Conflict (Anti-Abuse)
    res2 = await client.post("/api/v1/payments/claim-trial", headers=headers)
    assert res2.status_code == 409
    assert "sudah pernah mengklaim" in res2.json()["error"]["message"]


@pytest.mark.asyncio
async def test_admin_toggle_trial_off(client: AsyncClient, db_session, auth_headers: dict):
    # 1. Admin turns off trial
    patch_res = await client.patch("/api/v1/payments/admin/trial-config", json={
        "is_active": False,
        "trial_days": 7
    }, headers=auth_headers)
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["is_active"] is False

    # 2. Register a new user
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "notrialuser@terragis.io",
        "name": "No Trial User",
        "password": "Password123!"
    })
    token = reg_res.json()["data"]["access_token"]
    user_headers = {"Authorization": f"Bearer {token}"}

    # 3. User attempts to claim trial while disabled -> 422 Validation Error
    claim_res = await client.post("/api/v1/payments/claim-trial", headers=user_headers)
    assert claim_res.status_code == 422
    assert "dinonaktifkan" in claim_res.json()["error"]["message"]

    # 4. Admin restores trial to active with 14 days
    restore_res = await client.patch("/api/v1/payments/admin/trial-config", json={
        "is_active": True,
        "trial_days": 14
    }, headers=auth_headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["data"]["is_active"] is True
    assert restore_res.json()["data"]["trial_days"] == 14

    # 5. User now claims trial with 14 days
    claim_success = await client.post("/api/v1/payments/claim-trial", headers=user_headers)
    assert claim_success.status_code == 201
    assert claim_success.json()["data"]["trial_days"] == 14
