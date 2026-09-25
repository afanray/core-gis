import pytest
from datetime import datetime, timezone, timedelta
from app.models.user import User
from app.models.product import Product
from app.models.user_subscription import UserSubscription
from app.crud.crud_user import crud_user
from app.crud.crud_product import crud_product
from app.crud.crud_user_subscription import crud_user_subscription
from app.crud.crud_subscription_group import crud_subscription_group
from app.api.v1.endpoints.payments import calculate_upgrade_proration
from app.schemas.auth import UserCreate

@pytest.mark.asyncio
async def test_upgrade_proration_monthly_to_yearly(db_session):
    # Seed products
    monthly_prod = Product(
        id="terragis_sub_monthly",
        title="Paket Perbulan",
        amount=49000.0,
        currency="IDR",
        billing_period="monthly",
        is_active=True
    )
    yearly_prod = Product(
        id="terragis_sub_yearly",
        title="Paket Pertahun",
        amount=499000.0,
        currency="IDR",
        billing_period="yearly",
        is_active=True
    )
    group_prod = Product(
        id="terragis_sub_group",
        title="Paket Bersama (Team 5 User)",
        amount=500000.0,
        currency="IDR",
        billing_period="group",
        is_active=True
    )
    lifetime_prod = Product(
        id="terragis_sub_lifetime",
        title="Paket Permanen (Lifetime)",
        amount=1200000.0,
        currency="IDR",
        billing_period="lifetime",
        is_active=True
    )
    db_session.add_all([monthly_prod, yearly_prod, group_prod, lifetime_prod])
    await db_session.commit()

    # Create active user with 15 days used out of 30
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=15)
    end_date = now + timedelta(days=15)

    sub = UserSubscription(
        user_id="user-123",
        product_id=monthly_prod.id,
        start_date=start_date,
        end_date=end_date,
        billing_period="monthly",
        amount=49000.0,
        currency="IDR",
        status="active"
    )

    # 1. Monthly -> Yearly upgrade
    result = calculate_upgrade_proration(sub, yearly_prod)
    assert result["can_upgrade"] is True
    assert result["days_used"] == 15
    assert result["days_remaining"] == 15
    assert result["unused_credit"] == 24500.0
    assert result["payable_amount"] == 499000.0 - 24500.0

    # 2. Monthly -> Paket Bersama (500k) upgrade
    result_group = calculate_upgrade_proration(sub, group_prod)
    assert result_group["can_upgrade"] is True
    assert result_group["payable_amount"] == 500000.0 - 24500.0

    # 3. Monthly -> Lifetime upgrade
    result_life = calculate_upgrade_proration(sub, lifetime_prod)
    assert result_life["can_upgrade"] is True
    assert result_life["payable_amount"] == 1200000.0 - 24500.0


@pytest.mark.asyncio
async def test_downgrade_queue_and_restrictions(db_session):
    yearly_prod = Product(
        id="terragis_sub_yearly",
        title="Paket Pertahun",
        amount=499000.0,
        currency="IDR",
        billing_period="yearly",
        is_active=True
    )
    monthly_prod = Product(
        id="terragis_sub_monthly",
        title="Paket Perbulan",
        amount=49000.0,
        currency="IDR",
        billing_period="monthly",
        is_active=True
    )
    lifetime_prod = Product(
        id="terragis_sub_lifetime",
        title="Paket Permanen (Lifetime)",
        amount=1200000.0,
        currency="IDR",
        billing_period="lifetime",
        is_active=True
    )

    now = datetime.now(timezone.utc)
    yearly_sub = UserSubscription(
        user_id="user-yearly",
        product_id=yearly_prod.id,
        start_date=now - timedelta(days=30),
        end_date=now + timedelta(days=335),
        billing_period="yearly",
        amount=499000.0,
        currency="IDR",
        status="active"
    )

    # 1. Yearly -> Monthly (downgrade) is scheduled into the queue
    downgrade_res = calculate_upgrade_proration(yearly_sub, monthly_prod)
    assert downgrade_res["can_upgrade"] is True
    assert downgrade_res["action_type"] == "downgrade_queue"
    assert downgrade_res["payable_amount"] == 49000.0
    assert downgrade_res["effective_start_date"] is not None

    # 2. If user already has a queued subscription, further queues are blocked
    blocked_res = calculate_upgrade_proration(yearly_sub, monthly_prod, has_queued_sub=True)
    assert blocked_res["can_upgrade"] is False
    assert blocked_res["action_type"] == "already_queued"

    # 3. Lifetime users cannot downgrade to yearly or monthly
    lifetime_sub = UserSubscription(
        user_id="user-lifetime",
        product_id=lifetime_prod.id,
        start_date=now,
        end_date=now + timedelta(days=36500),
        billing_period="lifetime",
        amount=1200000.0,
        currency="IDR",
        status="active"
    )
    downgrade_lifetime = calculate_upgrade_proration(lifetime_sub, yearly_prod)
    assert downgrade_lifetime["can_upgrade"] is False
    assert downgrade_lifetime["action_type"] == "lifetime_active"


@pytest.mark.asyncio
async def test_queued_subscription_lifecycle_and_promotion(db_session):
    now = datetime.now(timezone.utc)

    # 1. Create user
    user = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="queue_user@terragis.io",
            name="Queue User",
            password="Password123!",
            role="user"
        )
    )

    # 2. Create active subscription expiring in 2 days
    active_sub = await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=user.id,
        product_id="terragis_sub_yearly",
        transaction_id="INV-ACT-1",
        start_date=now - timedelta(days=363),
        end_date=now + timedelta(days=2),
        billing_period="yearly",
        amount=499000.0,
        currency="IDR",
        status="active"
    )

    # 3. Create queued monthly subscription scheduled after active_sub ends
    queued_sub = await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=user.id,
        product_id="terragis_sub_monthly",
        transaction_id="INV-QUE-2",
        start_date=active_sub.end_date,
        end_date=active_sub.end_date + timedelta(days=30),
        billing_period="monthly",
        amount=49000.0,
        currency="IDR",
        status="queued"
    )

    await db_session.refresh(user, attribute_names=["subscriptions"])
    assert user.active_subscription is not None
    assert user.active_plan_id == "terragis_sub_yearly"
    assert user.queued_subscription is not None
    assert user.queued_plan_id == "terragis_sub_monthly"

    # 4. Simulate active plan expiration
    active_sub.end_date = now - timedelta(hours=1)
    await db_session.commit()

    # 5. Trigger lazy promotion
    promoted = await crud_user_subscription.promote_queued_subscription(db_session, user_id=user.id)
    assert promoted is not None
    assert promoted.id == queued_sub.id
    assert promoted.status == "active"
    assert promoted.product_id == "terragis_sub_monthly"

    # Verify old active_sub is marked expired
    await db_session.refresh(active_sub)
    assert active_sub.status == "expired"

    # Verify user's properties reflect the newly promoted active subscription
    await db_session.refresh(user, attribute_names=["subscriptions"])
    assert user.active_plan_id == "terragis_sub_monthly"
    assert user.queued_subscription is None
    assert user.queued_plan_id is None


@pytest.mark.asyncio
async def test_group_subscription_and_member_limits(db_session):
    # 1. Create owner user
    owner = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="owner@group.io",
            name="Group Owner",
            password="Password123!",
            role="user"
        )
    )

    # 2. Owner purchases Paket Bersama (500k)
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=365)
    owner_sub = await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=owner.id,
        product_id="terragis_sub_group",
        transaction_id="INV-GROUP-001",
        start_date=now,
        end_date=end_date,
        billing_period="group",
        amount=500000.0,
        currency="IDR"
    )

    group = await crud_subscription_group.create_or_update_group(
        db_session,
        owner_id=owner.id,
        subscription_id=owner_sub.id,
        name="Team GIS Surveyor",
        max_members=5
    )
    assert group.max_members == 5
    assert group.owner_id == owner.id

    # 3. Add 5 members (max capacity)
    for i in range(1, 6):
        email = f"member{i}@group.io"
        member = await crud_subscription_group.add_member(
            db_session,
            group_id=group.id,
            email=email
        )
        assert member.email == email
        assert member.status == "active"

    # Verify active count is 5
    count = await crud_subscription_group.get_active_members_count(db_session, group_id=group.id)
    assert count == 5

    # 4. Member 1 registers account -> link invites & inherit subscription
    member1_user = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="member1@group.io",
            name="Member Satu",
            password="Password123!",
            role="user"
        )
    )
    linked = await crud_subscription_group.link_user_invites(db_session, email="member1@group.io", user_id=member1_user.id)
    assert linked is not None
    assert linked.user_id == member1_user.id

    # Inherit group subscription
    await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=member1_user.id,
        product_id=owner_sub.product_id,
        transaction_id=None,
        start_date=owner_sub.start_date,
        end_date=owner_sub.end_date,
        billing_period="group",
        amount=0.0,
        currency="IDR",
        payment_method="group_invite",
        group_id=group.id
    )

    await db_session.refresh(member1_user)
    assert member1_user.subscription_status == "active"
    assert member1_user.active_plan_id == "terragis_sub_group"

    # 5. Remove member from group -> revoke subscription
    success = await crud_subscription_group.remove_member(db_session, group_id=group.id, member_id=linked.id)
    assert success is True
    new_count = await crud_subscription_group.get_active_members_count(db_session, group_id=group.id)
    assert new_count == 4
