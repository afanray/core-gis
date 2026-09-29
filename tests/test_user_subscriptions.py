import pytest
from datetime import datetime, timezone, timedelta
from app.models.product import Product
from app.crud.crud_user import crud_user
from app.crud.crud_product import crud_product
from app.crud.crud_transaction import crud_transaction
from app.crud.crud_user_subscription import crud_user_subscription
from app.schemas.auth import UserCreate
from app.schemas.transaction import TransactionCreate


@pytest.mark.asyncio
async def test_user_subscription_lifecycle(db_session):
    # 1. Create a test user
    user_in = UserCreate(
        email="subscriber@terragis.io",
        name="Subscriber Tester",
        password="Password123!",
        role="user"
    )
    user = await crud_user.create(db_session, obj_in=user_in, trial_days=7)
    assert user.subscription_status == "unsubscribed"

    # 2. Create a test product and transaction
    prod = await crud_product.get_by_id(db_session, id="terragis_sub_monthly")
    if not prod:
        prod = Product(
            id="terragis_sub_monthly",
            title="Paket Perbulan",
            amount=49000.0,
            currency="IDR",
            billing_period="monthly",
            is_active=True
        )
        db_session.add(prod)
        await db_session.commit()

    invoice_number = "INV-TERRA-TEST-001"
    tx = await crud_transaction.create(
        db_session,
        obj_in=TransactionCreate(
            productId="terragis_sub_monthly",
            name="Paket Perbulan",
            amount=49000.0,
            currency="IDR",
            status="Success",
            userName=user.name,
            userEmail=user.email,
            orderId=invoice_number
        ),
        tx_id=invoice_number
    )
    assert tx.id == invoice_number

    # 3. Create a UserSubscription record
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=30)
    sub = await crud_user_subscription.create_subscription(
        db_session,
        user_id=user.id,
        product_id="terragis_sub_monthly",
        transaction_id=tx.id,
        start_date=now,
        end_date=end_date,
        billing_period="monthly",
        amount=49000.0,
        currency="IDR",
        payment_method="midtrans"
    )

    assert sub.id is not None
    assert sub.user_id == user.id
    assert sub.product_id == "terragis_sub_monthly"
    assert sub.transaction_id == invoice_number
    assert sub.status == "active"
    assert sub.billing_period == "monthly"

    # 4. Query active subscription
    active_sub = await crud_user_subscription.get_active_by_user_id(db_session, user_id=user.id)
    assert active_sub is not None
    assert active_sub.id == sub.id
    assert active_sub.product_id == "terragis_sub_monthly"

    # 5. Update user subscription in users table
    await crud_user.update_subscription(
        db_session,
        user=user,
        status="active",
        plan_id=sub.product_id,
        duration_days=30
    )
    await db_session.refresh(user)
    assert user.subscription_status == "active"
    assert user.active_plan_id == "terragis_sub_monthly"
    assert user.subscription_ends_at is not None

    # 6. Test get_filtered
    items, total = await crud_user_subscription.get_filtered(
        db_session,
        q="Subscriber Tester",
        status="active"
    )
    assert total >= 1
    assert any(i.id == sub.id for i in items)
    matched_sub = next(i for i in items if i.id == sub.id)
    assert matched_sub.user.name == "Subscriber Tester"
    assert matched_sub.product.title == "Paket Perbulan"

    # 7. Test get_stats
    stats = await crud_user_subscription.get_stats(db_session)
    assert stats["total"] >= 1
    assert stats["active"] >= 1

    # 8. Test update_status
    updated = await crud_user_subscription.update_status(db_session, sub=sub, new_status="cancelled")
    assert updated.status == "cancelled"

@pytest.mark.asyncio
async def test_user_subscriptions_api_endpoints(client, auth_headers, db_session):
    # Ensure test user and product and subscription exist in db_session
    user_in = UserCreate(
        email="api_sub@terragis.io",
        name="API Sub User",
        password="Password123!",
        role="user"
    )
    user = await crud_user.create(db_session, obj_in=user_in, trial_days=7)
    
    prod = await crud_product.get_by_id(db_session, id="terragis_sub_monthly")
    if not prod:
        prod = Product(
            id="terragis_sub_monthly",
            title="Paket Perbulan",
            amount=49000.0,
            currency="IDR",
            billing_period="monthly",
            is_active=True
        )
        db_session.add(prod)
        await db_session.commit()

    now = datetime.now(timezone.utc)
    sub = await crud_user_subscription.create_subscription(
        db_session,
        user_id=user.id,
        product_id="terragis_sub_monthly",
        start_date=now,
        end_date=now + timedelta(days=30),
        billing_period="monthly",
        amount=49000.0,
        currency="IDR",
        payment_method="midtrans"
    )

    # 1. Test GET /api/v1/user-subscriptions
    res = await client.get("/api/v1/user-subscriptions", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "data" in data
    assert "meta" in data
    assert data["meta"]["total"] >= 1
    item = next(i for i in data["data"] if i["id"] == sub.id)
    assert item["user_id"] == user.id
    assert item["user_name"] == "API Sub User"
    assert item["product_title"] == "Paket Perbulan"

    # 2. Test GET /api/v1/user-subscriptions/stats
    stats_res = await client.get("/api/v1/user-subscriptions/stats", headers=auth_headers)
    assert stats_res.status_code == 200
    stats_data = stats_res.json()
    assert stats_data["success"] is True
    assert stats_data["data"]["total"] >= 1

    # 3. Test GET /api/v1/user-subscriptions/export
    export_res = await client.get("/api/v1/user-subscriptions/export?format=csv", headers=auth_headers)
    assert export_res.status_code == 200
    assert "User ID" in export_res.text
    assert "API Sub User" in export_res.text

    # 4. Test GET /api/v1/user-subscriptions/{id}
    detail_res = await client.get(f"/api/v1/user-subscriptions/{sub.id}", headers=auth_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["id"] == sub.id

    # 5. Test PATCH /api/v1/user-subscriptions/{id}/status
    patch_res = await client.patch(
        f"/api/v1/user-subscriptions/{sub.id}/status",
        json={"status": "expired"},
        headers=auth_headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["status"] == "expired"


