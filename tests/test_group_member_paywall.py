import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient

from app.models.product import Product
from app.crud.crud_user import crud_user
from app.crud.crud_user_subscription import crud_user_subscription
from app.crud.crud_subscription_group import crud_subscription_group
from app.core.security import create_access_token
from app.schemas.auth import UserCreate

@pytest.mark.asyncio
async def test_group_member_paywall_and_restrictions(client: AsyncClient, db_session):
    now = datetime.now(timezone.utc)

    # 1. Seed Products if not present
    group_prod = await db_session.get(Product, "terragis_sub_group")
    if not group_prod:
        group_prod = Product(
            id="terragis_sub_group",
            title="Paket Bersama (Team 5 User)",
            amount=500000.0,
            currency="IDR",
            billing_period="group",
            trial_days=7,
            is_active=True
        )
        db_session.add(group_prod)

    yearly_prod = await db_session.get(Product, "terragis_sub_yearly")
    if not yearly_prod:
        yearly_prod = Product(
            id="terragis_sub_yearly",
            title="Paket Pertahun",
            amount=150000.0,
            currency="IDR",
            billing_period="yearly",
            trial_days=7,
            is_active=True
        )
        db_session.add(yearly_prod)
    await db_session.commit()

    # 2. Create Owner User and Group Subscription
    owner = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="team_leader@terragis.io",
            name="Team Leader",
            password="Password123!",
            role="user"
        )
    )
    owner_sub = await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=owner.id,
        product_id="terragis_sub_group",
        transaction_id="INV-OWNER-GROUP-001",
        start_date=now,
        end_date=now + timedelta(days=365),
        billing_period="group",
        amount=500000.0,
        currency="IDR"
    )
    group = await crud_subscription_group.create_or_update_group(
        db_session,
        owner_id=owner.id,
        subscription_id=owner_sub.id,
        name="Tim Survey Lapangan",
        max_members=5
    )

    # 3. Create Member User and add to group
    member = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="field_surveyor@terragis.io",
            name="Field Surveyor Member",
            password="Password123!",
            role="user"
        )
    )
    await crud_subscription_group.add_member(
        db_session,
        group_id=group.id,
        email=member.email,
        user_id=member.id
    )
    # Inherit group subscription
    await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=member.id,
        product_id="terragis_sub_group",
        transaction_id=None,
        start_date=owner_sub.start_date,
        end_date=owner_sub.end_date,
        billing_period="group",
        amount=0.0,
        currency="IDR",
        payment_method="group_invite",
        group_id=group.id
    )
    await db_session.commit()

    member_token = create_access_token(subject=member.id)
    member_headers = {"Authorization": f"Bearer {member_token}"}

    owner_token = create_access_token(subject=owner.id)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 4. Test GET /api/v1/auth/me
    res_member_me = await client.get("/api/v1/auth/me", headers=member_headers)
    assert res_member_me.status_code == 200
    assert res_member_me.json()["data"]["is_group_member"] is True

    res_owner_me = await client.get("/api/v1/auth/me", headers=owner_headers)
    assert res_owner_me.status_code == 200
    assert res_owner_me.json()["data"]["is_group_member"] is False

    # 5. Test GET /api/v1/products - member should NOT see terragis_sub_group
    res_member_products = await client.get("/api/v1/products", headers=member_headers)
    assert res_member_products.status_code == 200
    member_product_ids = [p["id"] for p in res_member_products.json()["data"]]
    assert "terragis_sub_group" not in member_product_ids
    assert not any(p["billing_period"] == "group" for p in res_member_products.json()["data"])

    # Owner can see terragis_sub_group
    res_owner_products = await client.get("/api/v1/products", headers=owner_headers)
    assert res_owner_products.status_code == 200
    owner_product_ids = [p["id"] for p in res_owner_products.json()["data"]]
    assert "terragis_sub_group" in owner_product_ids

    # 6. Test GET /api/v1/payments/upgrade-preview for group package
    res_preview = await client.get(
        "/api/v1/payments/upgrade-preview?target_product_id=terragis_sub_group",
        headers=member_headers
    )
    assert res_preview.status_code == 200
    preview_data = res_preview.json()["data"]
    assert preview_data["can_upgrade"] is False
    assert preview_data["action_type"] == "blocked"
    assert "paket bersama" in preview_data["message"].lower()

    # 7. Test POST /api/v1/payments/create-midtrans-snap - member blocked from buying group package
    res_snap_group = await client.post(
        "/api/v1/payments/create-midtrans-snap",
        json={"product_id": "terragis_sub_group"},
        headers=member_headers
    )
    assert res_snap_group.status_code == 403
    assert "paket bersama" in res_snap_group.json()["error"]["message"].lower()

    # 8. Test Member CAN preview other packages (e.g. yearly) as queued (status quo)
    res_preview_yearly = await client.get(
        "/api/v1/payments/upgrade-preview?target_product_id=terragis_sub_yearly",
        headers=member_headers
    )
    assert res_preview_yearly.status_code == 200
    preview_yearly_data = res_preview_yearly.json()["data"]
    assert preview_yearly_data["can_upgrade"] is True
    assert preview_yearly_data["action_type"] == "queue"
    assert "status quo" in preview_yearly_data["message"].lower()

    # 9. Test Member CAN purchase yearly package via Midtrans Snap (scheduled status quo)
    res_snap_yearly = await client.post(
        "/api/v1/payments/create-midtrans-snap",
        json={"product_id": "terragis_sub_yearly"},
        headers=member_headers
    )
    assert res_snap_yearly.status_code == 201
    assert "token" in res_snap_yearly.json()["data"]
    assert "invoice_number" in res_snap_yearly.json()["data"]


    # 9. Test Single Group Membership Constraint (1 account can only belong to 1 group)
    owner2 = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="team_leader2@terragis.io",
            name="Team Leader 2",
            password="Password123!",
            role="user"
        )
    )
    owner2_sub = await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=owner2.id,
        product_id="terragis_sub_group",
        transaction_id="INV-OWNER-GROUP-002",
        start_date=now,
        end_date=now + timedelta(days=365),
        billing_period="group",
        amount=500000.0,
        currency="IDR"
    )
    group2 = await crud_subscription_group.create_or_update_group(
        db_session,
        owner_id=owner2.id,
        subscription_id=owner2_sub.id,
        name="Tim Survey 2",
        max_members=5
    )
    await db_session.commit()

    owner2_token = create_access_token(subject=owner2.id)
    owner2_headers = {"Authorization": f"Bearer {owner2_token}"}

    # Attempt to invite an existing member of group 1 to group 2 via API -> Expect 409 Conflict
    res_invite_dup = await client.post(
        "/api/v1/group/invite",
        json={"email": member.email},
        headers=owner2_headers
    )
    assert res_invite_dup.status_code == 409
    assert "anggota di paket bersama lain" in res_invite_dup.json()["error"]["message"].lower()

    # Attempt to invite an owner of another group to group 2 -> Expect 409 Conflict
    res_invite_owner = await client.post(
        "/api/v1/group/invite",
        json={"email": owner.email},
        headers=owner2_headers
    )
    assert res_invite_owner.status_code == 409
    assert "pemilik" in res_invite_owner.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_group_invite_sends_email_with_deeplink(client: AsyncClient, db_session, monkeypatch):
    called_invites = []
    async def mock_send_group_invite_notification(to_email, invited_user_name, owner_name, owner_email, group_name, deeplink_url, app_scheme_url):
        called_invites.append({
            "to_email": to_email,
            "invited_user_name": invited_user_name,
            "owner_name": owner_name,
            "owner_email": owner_email,
            "group_name": group_name,
            "deeplink_url": deeplink_url,
            "app_scheme_url": app_scheme_url
        })

    from app.services.email_service import email_service
    monkeypatch.setattr(email_service, "send_group_invite_notification", mock_send_group_invite_notification)

    # 1. Create Owner & Group
    now = datetime.now(timezone.utc)
    owner = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="invite_owner@terragis.io",
            name="Invite Test Owner",
            password="Password123!",
            role="user"
        )
    )
    owner_sub = await crud_user_subscription.create_or_update_subscription(
        db_session,
        user_id=owner.id,
        product_id="terragis_sub_group",
        transaction_id="INV-OWNER-INVITE-001",
        start_date=now,
        end_date=now + timedelta(days=365),
        billing_period="group",
        amount=500000.0,
        currency="IDR"
    )
    group = await crud_subscription_group.create_or_update_group(
        db_session,
        owner_id=owner.id,
        subscription_id=owner_sub.id,
        name="Kelompok Ahli GIS",
        max_members=5
    )
    await db_session.commit()

    owner_token = create_access_token(subject=owner.id)
    headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Invite a new email
    target_email = "new_surveyor@terragis.io"
    res = await client.post(
        "/api/v1/group/invite",
        json={"email": target_email},
        headers=headers
    )
    assert res.status_code == 201
    assert "email dan tautan aplikasi telah dikirimkan" in res.json()["message"].lower()

    # 3. Verify email notification background task
    assert len(called_invites) == 1
    invite_data = called_invites[0]
    assert invite_data["to_email"] == target_email
    assert invite_data["owner_name"] == "Invite Test Owner"
    assert invite_data["owner_email"] == "invite_owner@terragis.io"
    assert invite_data["group_name"] == "Kelompok Ahli GIS"
    assert "open-app?group_id=" in invite_data["deeplink_url"]
    assert invite_data["app_scheme_url"].startswith("terragis://group")


@pytest.mark.asyncio
async def test_group_open_app_redirect_endpoint(client: AsyncClient):
    res = await client.get("/api/v1/group/open-app?group_id=group-xyz-123")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "terragis://group?id=group-xyz-123" in res.text
    assert "Buka Aplikasi Terra GIS" in res.text


