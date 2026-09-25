from typing import Any, Optional
from fastapi import APIRouter, Depends, status, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException, ConflictException, ForbiddenException
from app.crud.crud_user import crud_user
from app.crud.crud_subscription_group import crud_subscription_group
from app.crud.crud_user_subscription import crud_user_subscription
from app.schemas.common import BaseResponse
from app.schemas.subscription_group import GroupInviteRequest, GroupDetailsOut, GroupMemberOut
from app.api.deps import get_current_user
from app.models.user import User
from app.services.email_service import email_service

router = APIRouter()

@router.get("", response_model=BaseResponse[GroupDetailsOut], summary="Get Current User Group Details")
async def get_my_group(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Returns group details where current user is owner or active member.
    """
    # 1. Check if user is owner of a group
    group = await crud_subscription_group.get_by_owner_id(db, owner_id=current_user.id)
    is_owner = True
    owner_user = current_user

    if not group:
        # 2. Check if user is a member of an active group
        membership = await crud_subscription_group.get_member_membership(db, user_id=current_user.id, email=current_user.email)
        if not membership:
            raise NotFoundException(message="Anda belum memiliki atau tergabung dalam Paket Bersama (Team).")
        
        group = await crud_subscription_group.get_by_id(db, id=membership.group_id)
        if not group:
            raise NotFoundException(message="Grup tidak ditemukan.")
        is_owner = False
        owner_user = await crud_user.get_by_id(db, id=group.owner_id)

    # Check owner active subscription
    owner_sub = await crud_user_subscription.get_by_user_id(db, user_id=group.owner_id)
    is_active = owner_sub is not None and owner_sub.status == "active"
    if owner_sub and owner_sub.end_date:
        now = datetime.now(timezone.utc)
        end_tz = owner_sub.end_date if owner_sub.end_date.tzinfo else owner_sub.end_date.replace(tzinfo=timezone.utc)
        if now > end_tz:
            is_active = False

    members_out = [
        GroupMemberOut(
            id=m.id,
            group_id=m.group_id,
            email=m.email,
            user_id=m.user_id,
            status=m.status,
            invited_at=m.invited_at,
            joined_at=m.joined_at
        ) for m in group.members if m.status == "active"
    ]

    return BaseResponse(
        data=GroupDetailsOut(
            id=group.id,
            owner_id=group.owner_id,
            owner_email=owner_user.email if owner_user else "-",
            name=group.name,
            max_members=group.max_members,
            current_members_count=len(members_out),
            is_owner=is_owner,
            is_active=is_active,
            subscription_ends_at=owner_sub.end_date if owner_sub else None,
            members=members_out
        ),
        message="Group details retrieved successfully"
    )

@router.get("/open-app", response_class=HTMLResponse, summary="Deep Link Redirect Landing Page to Terra GIS Mobile App")
async def open_app_redirect(
    group_id: Optional[str] = None
) -> Any:
    """
    Web landing page that automatically opens the mobile application via 'terragis://group'
    with fallback button for all mobile and desktop browsers.
    """
    app_url = f"{settings.APP_DEEP_LINK_SCHEME}://group"
    if group_id:
        app_url += f"?id={group_id}"

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Membuka Terra GIS...</title>
    <meta http-equiv="refresh" content="0; url={app_url}">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f6f8;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 24px;
            color: #212529;
        }}
        .card {{
            background: #ffffff;
            border-radius: 18px;
            padding: 36px 28px;
            max-width: 440px;
            width: 100%;
            text-align: center;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.08);
            border: 1px solid #e9ecef;
        }}
        .icon-box {{
            width: 72px;
            height: 72px;
            background: #e8f5e9;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px auto;
            font-size: 34px;
        }}
        h2 {{
            margin: 0 0 10px 0;
            color: #0f5132;
            font-size: 22px;
        }}
        p {{
            color: #6c757d;
            font-size: 14px;
            line-height: 1.6;
            margin: 0 0 24px 0;
        }}
        .btn {{
            display: inline-block;
            background: linear-gradient(135deg, #0f5132 0%, #198754 100%);
            color: #ffffff !important;
            text-decoration: none;
            padding: 14px 32px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 15px;
            box-shadow: 0 4px 14px rgba(25, 135, 84, 0.35);
        }}
        .hint {{
            margin-top: 24px;
            font-size: 12px;
            color: #adb5bd;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-box">🗺️</div>
        <h2>Membuka Aplikasi Terra GIS</h2>
        <p>Sedang mengalihkan Anda secara otomatis ke aplikasi Terra GIS di perangkat Anda...</p>
        <a href="{app_url}" class="btn" id="openBtn">Buka Aplikasi Terra GIS</a>
        <div class="hint">
            Jika aplikasi tidak terbuka secara otomatis dalam beberapa detik, silakan sentuh tombol hijau di atas.
        </div>
    </div>
    <script>
        setTimeout(function() {{
            window.location.href = "{app_url}";
        }}, 200);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@router.post("/invite", response_model=BaseResponse[GroupMemberOut], status_code=status.HTTP_201_CREATED, summary="Invite Member to Group")
async def invite_group_member(
    body: GroupInviteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Owner invites a colleague/member by email (max 5 members).
    """
    group = await crud_subscription_group.get_by_owner_id(db, owner_id=current_user.id)
    if not group:
        raise ForbiddenException(message="Hanya pemilik Paket Bersama yang dapat mengundang anggota.")

    # Check active subscription
    owner_sub = await crud_user_subscription.get_by_user_id(db, user_id=current_user.id)
    if not owner_sub or owner_sub.status != "active":
        raise ValidationException(message="Paket Bersama Anda tidak aktif. Silakan lakukan perpanjangan terlebih dahulu.")

    clean_email = body.email.strip().lower()
    if clean_email == current_user.email.strip().lower():
        raise ValidationException(message="Anda tidak dapat mengundang email Anda sendiri ke dalam grup.")

    # Check capacity limit
    active_count = await crud_subscription_group.get_active_members_count(db, group_id=group.id)
    if active_count >= group.max_members:
        raise ValidationException(message=f"Batas maksimal anggota grup ({group.max_members} user) telah tercapai.")

    # Check if user already exists in DB
    existing_user = await crud_user.get_by_email(db, email=clean_email)
    existing_user_id = existing_user.id if existing_user else None

    # Check if target email/user is an owner of any group
    if existing_user_id:
        owned_group = await crud_subscription_group.get_by_owner_id(db, owner_id=existing_user_id)
        if owned_group:
            raise ConflictException(message="Pengguna ini merupakan pemilik Paket Bersama lain, tidak dapat dijadikan anggota.")

    # Check if target email already in another active group
    existing_membership = await crud_subscription_group.get_member_membership(
        db, user_id=existing_user_id, email=clean_email
    )
    if existing_membership and existing_membership.group_id == group.id:
        raise ConflictException(message="Pengguna dengan email ini sudah terdaftar sebagai anggota grup Anda.")
    elif existing_membership:
        raise ConflictException(message="Pengguna dengan email ini sudah terdaftar sebagai anggota di Paket Bersama lain. Satu akun hanya dapat menjadi anggota pada satu grup.")

    # Check if target user has active subscription from another group
    if existing_user_id:
        existing_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=existing_user_id)
        if existing_sub and existing_sub.billing_period == "group" and existing_sub.group_id and existing_sub.group_id != group.id:
            raise ConflictException(message="Pengguna ini sudah memiliki langganan aktif dari Paket Bersama lain.")

    member = await crud_subscription_group.add_member(
        db,
        group_id=group.id,
        email=clean_email,
        user_id=existing_user_id
    )

    # If invited user exists, grant inherited subscription immediately
    if existing_user and owner_sub:
        await crud_user_subscription.create_or_update_subscription(
            db,
            user_id=existing_user.id,
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

    # Prepare recipient details and deeplinks for email notification
    invited_name = existing_user.name if existing_user and existing_user.name else clean_email.split("@")[0]
    owner_name = current_user.name if current_user.name else current_user.email.split("@")[0]
    web_redirect_url = f"{settings.APP_WEB_BASE_URL}{settings.API_V1_STR}/group/open-app?group_id={group.id}"
    app_scheme_url = f"{settings.APP_DEEP_LINK_SCHEME}://group?id={group.id}"

    background_tasks.add_task(
        email_service.send_group_invite_notification,
        to_email=clean_email,
        invited_user_name=invited_name,
        owner_name=owner_name,
        owner_email=current_user.email,
        group_name=group.name,
        deeplink_url=web_redirect_url,
        app_scheme_url=app_scheme_url
    )

    return BaseResponse(
        data=GroupMemberOut(
            id=member.id,
            group_id=member.group_id,
            email=member.email,
            user_id=member.user_id,
            status=member.status,
            invited_at=member.invited_at,
            joined_at=member.joined_at
        ),
        message=f"Undangan berhasil dikirim! Notifikasi email dan tautan aplikasi telah dikirimkan ke {clean_email}."
    )

@router.delete("/members/{member_id}", response_model=BaseResponse[dict], summary="Remove Member from Group")
async def remove_group_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Owner removes a member from the group.
    """
    group = await crud_subscription_group.get_by_owner_id(db, owner_id=current_user.id)
    if not group:
        raise ForbiddenException(message="Hanya pemilik grup yang dapat menghapus anggota.")

    # Find member to remove
    removed_member = next((m for m in group.members if m.id == member_id), None)
    if not removed_member:
        raise NotFoundException(message="Anggota grup tidak ditemukan.")

    # If member has a user account, revoke inherited group subscription
    if removed_member.user_id:
        member_sub = await crud_user_subscription.get_by_user_id(db, user_id=removed_member.user_id)
        if member_sub and member_sub.group_id == group.id:
            member_sub.status = "cancelled"
            await db.commit()

    success = await crud_subscription_group.remove_member(db, group_id=group.id, member_id=member_id)
    return BaseResponse(
        data={"removed": success, "member_id": member_id},
        message="Anggota berhasil dihapus dari grup."
    )
