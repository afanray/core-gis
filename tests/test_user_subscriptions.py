import pytest
from datetime import datetime, timezone, timedelta
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

    # 2. Create a test transaction
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
