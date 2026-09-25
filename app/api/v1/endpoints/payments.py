import uuid
from typing import Any, Optional, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException, ConflictException, ForbiddenException
from app.crud.crud_product import crud_product
from app.crud.crud_transaction import crud_transaction
from app.crud.crud_user import crud_user
from app.crud.crud_user_subscription import crud_user_subscription
from app.crud.crud_subscription_group import crud_subscription_group
from app.schemas.transaction import TransactionCreate, TransactionOut
from app.schemas.common import BaseResponse
from app.schemas.subscription_group import UpgradePreviewResponse
from app.api.deps import get_current_user
from app.models.user import User
from app.models.product import Product
from app.services.doku_service import doku_service
from app.services.midtrans_service import midtrans_service
from app.services.analytics_service import analytics_service

router = APIRouter()

class CreateDokuCheckoutRequest(BaseModel):
    product_id: str = Field(..., json_schema_extra={"example": "terragis_sub_monthly"})

class DokuCheckoutResponse(BaseModel):
    invoice_number: str
    payment_url: str
    amount: float
    currency: str
    title: str

class CreateMidtransSnapRequest(BaseModel):
    product_id: str = Field(..., json_schema_extra={"example": "terragis_sub_monthly"})

class MidtransSnapResponse(BaseModel):
    invoice_number: str
    token: str
    redirect_url: str
    amount: float
    currency: str
    title: str

SUBSCRIPTION_TIERS = {
    "terragis_sub_trial": 0,
    "terragis_sub_monthly": 1,
    "terragis_sub_yearly": 2,
    "terragis_sub_lifetime": 3,
    "terragis_sub_group": 4
}

def calculate_upgrade_proration(current_sub, target_product, has_queued_sub: bool = False) -> dict:
    if has_queued_sub:
        return {
            "can_upgrade": False,
            "action_type": "already_queued",
            "message": "Anda sudah memiliki antrean paket berikutnya. Harap selesaikan atau tunggu hingga paket antrean aktif.",
            "payable_amount": float(target_product.amount),
            "unused_credit": 0.0,
            "days_used": 0,
            "days_remaining": 0,
            "total_days": 0,
            "effective_start_date": None,
            "queued_already": True
        }

    current_tier = SUBSCRIPTION_TIERS.get(current_sub.product_id, 1)
    target_tier = SUBSCRIPTION_TIERS.get(target_product.id, 1)

    now = datetime.now(timezone.utc)
    start_tz = current_sub.start_date if current_sub.start_date.tzinfo else current_sub.start_date.replace(tzinfo=timezone.utc)
    end_tz = current_sub.end_date if current_sub.end_date.tzinfo else current_sub.end_date.replace(tzinfo=timezone.utc)

    total_days = max(1, (end_tz.date() - start_tz.date()).days)
    days_used = max(0, (now.date() - start_tz.date()).days)
    days_remaining = max(0, (end_tz.date() - now.date()).days)

    # 1. Lifetime account check
    if current_sub.billing_period == "lifetime" and target_product.billing_period != "group":
        return {
            "can_upgrade": False,
            "action_type": "lifetime_active",
            "message": "Akun Anda telah memiliki akses Selamanya (Lifetime). Tidak memerlukan pembelian paket tambahan.",
            "payable_amount": float(target_product.amount),
            "unused_credit": 0.0,
            "days_used": 0,
            "days_remaining": 0,
            "total_days": total_days,
            "effective_start_date": None,
            "queued_already": False
        }

    # 2. Upgrade (target_tier > current_tier) -> immediate prorated switch
    if target_tier > current_tier:
        unused_credit = round((days_remaining / total_days) * current_sub.amount, 0)
        payable_amount = max(1000.0, round(target_product.amount - unused_credit, 0))
        return {
            "can_upgrade": True,
            "action_type": "upgrade",
            "message": f"Upgrade berhasil dihitung. Potongan sisa hari pemakaian paket lama: Rp {unused_credit:,.0f}.",
            "payable_amount": payable_amount,
            "unused_credit": unused_credit,
            "days_used": days_used,
            "days_remaining": days_remaining,
            "total_days": total_days,
            "effective_start_date": now,
            "queued_already": False
        }

    # 3. Same Plan Renewal or Downgrade (target_tier <= current_tier) -> Queued / Scheduled Subscription
    return {
        "can_upgrade": True,
        "action_type": "downgrade_queue" if target_tier < current_tier else "renewal_queue",
        "message": f"Paket ini akan otomatis aktif setelah paket saat ini berakhir pada {end_tz.strftime('%d %b %Y')}.",
        "payable_amount": float(target_product.amount),
        "unused_credit": 0.0,
        "days_used": days_used,
        "days_remaining": days_remaining,
        "total_days": total_days,
        "effective_start_date": end_tz,
        "queued_already": False
    }

@router.get("/upgrade-preview", response_model=BaseResponse[UpgradePreviewResponse], summary="Preview Prorated Upgrade Calculation")
async def preview_upgrade(
    target_product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Calculates prorated price for upgrading an existing subscription package.
    Credits unused days from the current active subscription. Downgrade is rejected.
    """
    target_product = await crud_product.get_by_id(db, id=target_product_id)
    if not target_product:
        raise NotFoundException(message=f"Produk tujuan '{target_product_id}' tidak ditemukan.")

    is_member = await crud_subscription_group.is_user_group_member(
        db, user_id=current_user.id, email=current_user.email
    )
    if is_member:
        if target_product.id == "terragis_sub_group" or target_product.billing_period == "group":
            return BaseResponse(
                data=UpgradePreviewResponse(
                    can_upgrade=False,
                    action_type="blocked",
                    current_plan_id=current_user.active_plan_id,
                    current_plan_title="Anggota Paket Bersama",
                    target_plan_id=target_product.id,
                    target_plan_title=target_product.title,
                    target_price=target_product.amount,
                    total_days=0,
                    days_used=0,
                    days_remaining=0,
                    unused_credit=0.0,
                    payable_amount=target_product.amount,
                    effective_start_date=None,
                    queued_already=False,
                    message="Akun Anda terdaftar sebagai anggota Paket Bersama. Anda tidak dapat membeli Paket Bersama lainnya."
                )
            )
        current_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=current_user.id)
        queued_sub = await crud_user_subscription.get_queued_by_user_id(db, user_id=current_user.id)
        if queued_sub:
            return BaseResponse(
                data=UpgradePreviewResponse(
                    can_upgrade=False,
                    action_type="blocked",
                    current_plan_id=current_user.active_plan_id,
                    current_plan_title="Anggota Paket Bersama",
                    target_plan_id=target_product.id,
                    target_plan_title=target_product.title,
                    target_price=target_product.amount,
                    total_days=0,
                    days_used=0,
                    days_remaining=0,
                    unused_credit=0.0,
                    payable_amount=target_product.amount,
                    effective_start_date=queued_sub.start_date,
                    queued_already=True,
                    message="Anda sudah memiliki antrean paket berikutnya (status quo). Harap tunggu hingga paket tersebut selesai."
                )
            )
        effective_start = current_sub.end_date if current_sub and current_sub.end_date else datetime.now(timezone.utc)
        return BaseResponse(
            data=UpgradePreviewResponse(
                can_upgrade=True,
                action_type="queue",
                current_plan_id=current_user.active_plan_id,
                current_plan_title="Anggota Paket Bersama",
                target_plan_id=target_product.id,
                target_plan_title=target_product.title,
                target_price=target_product.amount,
                total_days=0,
                days_used=0,
                days_remaining=0,
                unused_credit=0.0,
                payable_amount=target_product.amount,
                effective_start_date=effective_start,
                queued_already=False,
                message=f"Sebagai anggota Paket Bersama, paket {target_product.title} akan dijadwalkan (status quo) dan aktif otomatis setelah masa berlaku keanggotaan grup Anda berakhir."
            )
        )

    current_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=current_user.id)
    queued_sub = await crud_user_subscription.get_queued_by_user_id(db, user_id=current_user.id)
    
    if not current_sub:
        return BaseResponse(
            data=UpgradePreviewResponse(
                can_upgrade=True,
                action_type="new",
                current_plan_id=None,
                current_plan_title="Tidak Ada",
                target_plan_id=target_product.id,
                target_plan_title=target_product.title,
                target_price=target_product.amount,
                total_days=0,
                days_used=0,
                days_remaining=0,
                unused_credit=0.0,
                payable_amount=target_product.amount,
                effective_start_date=datetime.now(timezone.utc),
                queued_already=False,
                message="Pembelian paket baru dengan tarif penuh."
            )
        )

    current_product = await crud_product.get_by_id(db, id=current_sub.product_id)
    proration = calculate_upgrade_proration(current_sub, target_product, has_queued_sub=queued_sub is not None)

    return BaseResponse(
        data=UpgradePreviewResponse(
            can_upgrade=proration["can_upgrade"],
            action_type=proration["action_type"],
            current_plan_id=current_sub.product_id,
            current_plan_title=current_product.title if current_product else current_sub.product_id,
            target_plan_id=target_product.id,
            target_plan_title=target_product.title,
            target_price=target_product.amount,
            total_days=proration["total_days"],
            days_used=proration["days_used"],
            days_remaining=proration["days_remaining"],
            unused_credit=proration["unused_credit"],
            payable_amount=proration["payable_amount"],
            effective_start_date=proration.get("effective_start_date"),
            queued_already=proration.get("queued_already", False),
            message=proration["message"]
        )
    )

@router.post("/create-midtrans-snap", response_model=BaseResponse[MidtransSnapResponse], status_code=status.HTTP_201_CREATED, summary="Create Midtrans Snap Payment Session")
async def create_midtrans_snap(
    body: CreateMidtransSnapRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Creates a Midtrans Snap payment session for a subscription product package.
    Automatically applies proration discounts if user is upgrading from an active plan.
    """
    product = await crud_product.get_by_id(db, id=body.product_id)
    if not product:
        raise NotFoundException(message=f"Subscription product package '{body.product_id}' not found.")

    if product.billing_period == "trial" or product.amount <= 0:
        raise ValidationException(message="Paket uji coba gratis tidak memerlukan pembayaran gateway. Silakan gunakan tombol Klaim Uji Coba Gratis.")

    is_member = await crud_subscription_group.is_user_group_member(
        db, user_id=current_user.id, email=current_user.email
    )
    if is_member and (product.id == "terragis_sub_group" or product.billing_period == "group"):
        raise ForbiddenException(message="Akun Anda terdaftar sebagai anggota aktif Paket Bersama. Anda tidak dapat membeli Paket Bersama lainnya.")

    # Check active & queued subscriptions
    current_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=current_user.id)
    queued_sub = await crud_user_subscription.get_queued_by_user_id(db, user_id=current_user.id)
    charge_amount = int(product.amount)

    if queued_sub:
        raise ValidationException(message="Anda sudah memiliki antrean paket berikutnya. Harap tunggu hingga paket antrean aktif.")

    if current_sub:
        if is_member:
            charge_amount = int(product.amount)
        else:
            proration = calculate_upgrade_proration(current_sub, product, has_queued_sub=False)
            if not proration["can_upgrade"]:
                raise ValidationException(message=proration["message"])
            charge_amount = int(proration["payable_amount"])

    # Generate unique invoice number
    timestamp = int(datetime.now(timezone.utc).timestamp())
    random_hex = uuid.uuid4().hex[:6].upper()
    invoice_number = f"INV-TERRA-{timestamp}-{random_hex}"

    # Initiate Midtrans Snap Session via Midtrans API with prorated amount
    session_res = await midtrans_service.create_snap_transaction(
        user_id=current_user.id,
        user_name=current_user.name,
        user_email=current_user.email,
        product_id=product.id,
        product_title=product.title,
        amount=charge_amount,
        invoice_number=invoice_number
    )

    token = session_res.get("token", "")
    redirect_url = session_res.get("redirect_url", "")

    # Save transaction record in DB with Pending status using invoice_number as ID
    await crud_transaction.create(
        db,
        obj_in=TransactionCreate(
            productId=product.id,
            name=product.title,
            amount=charge_amount,
            currency=product.currency or "IDR",
            status="Pending",
            userName=current_user.name,
            userEmail=current_user.email,
            orderId=invoice_number,
            purchaseToken=token
        ),
        tx_id=invoice_number
    )

    return BaseResponse(
        data=MidtransSnapResponse(
            invoice_number=invoice_number,
            token=token,
            redirect_url=redirect_url,
            amount=product.amount,
            currency=product.currency or "IDR",
            title=product.title
        ),
        message="Midtrans Snap payment session created successfully"
    )

@router.post("/create-doku-checkout", response_model=BaseResponse[DokuCheckoutResponse], status_code=status.HTTP_201_CREATED, summary="Create DOKU Jokul Checkout Payment Session")
async def create_doku_checkout(
    body: CreateDokuCheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Creates a DOKU Jokul Checkout payment session for a subscription product package.
    Returns invoice_number and DOKU Hosted Checkout Payment URL for In-App WebView.
    """
    product = await crud_product.get_by_id(db, id=body.product_id)
    if not product:
        raise NotFoundException(message=f"Subscription product package '{body.product_id}' not found.")

    if product.billing_period == "trial" or product.amount <= 0:
        raise ValidationException(message="Paket uji coba gratis tidak memerlukan pembayaran gateway. Silakan gunakan tombol Klaim Uji Coba Gratis.")

    is_member = await crud_subscription_group.is_user_group_member(
        db, user_id=current_user.id, email=current_user.email
    )
    if is_member and (product.id == "terragis_sub_group" or product.billing_period == "group"):
        raise ForbiddenException(message="Akun Anda terdaftar sebagai anggota aktif Paket Bersama. Anda tidak dapat membeli Paket Bersama lainnya.")

    current_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=current_user.id)
    queued_sub = await crud_user_subscription.get_queued_by_user_id(db, user_id=current_user.id)
    charge_amount = int(product.amount)

    if queued_sub:
        raise ValidationException(message="Anda sudah memiliki antrean paket berikutnya. Harap tunggu hingga paket antrean aktif.")

    if current_sub:
        if is_member:
            charge_amount = int(product.amount)
        else:
            proration = calculate_upgrade_proration(current_sub, product, has_queued_sub=False)
            if not proration["can_upgrade"]:
                raise ValidationException(message=proration["message"])
            charge_amount = int(proration["payable_amount"])

    timestamp = int(datetime.now(timezone.utc).timestamp())
    random_hex = uuid.uuid4().hex[:6].upper()
    invoice_number = f"INV-TERRA-{timestamp}-{random_hex}"

    session_res = await doku_service.create_checkout_session(
        user_id=current_user.id,
        user_name=current_user.name,
        user_email=current_user.email,
        product_title=product.title,
        amount=charge_amount,
        invoice_number=invoice_number
    )

    payment_url = session_res.get("payment_url", "")

    await crud_transaction.create(
        db,
        obj_in=TransactionCreate(
            productId=product.id,
            name=product.title,
            amount=product.amount,
            currency=product.currency or "IDR",
            status="Pending",
            userName=current_user.name,
            userEmail=current_user.email,
            orderId=invoice_number
        ),
        tx_id=invoice_number
    )

    return BaseResponse(
        data=DokuCheckoutResponse(
            invoice_number=invoice_number,
            payment_url=payment_url,
            amount=product.amount,
            currency=product.currency or "IDR",
            title=product.title
        ),
        message="DOKU Checkout payment session created successfully"
    )

@router.get("/status/{invoice_number}", response_model=BaseResponse[dict], summary="Check Payment Transaction Status")
async def get_payment_status(
    invoice_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Checks status of transaction against Midtrans API & DB, automatically syncing 
    transaction status and user's subscription in DB if payment is completed.
    """
    tx = await crud_transaction.get_by_id(db, id=invoice_number)
    
    # If transaction is pending in DB, query Midtrans API directly for real-time status
    if tx and tx.status not in ("Success", "Settlement"):
        mt_res = await midtrans_service.get_transaction_status(invoice_number)
        tx_status = str(mt_res.get("transaction_status", "")).lower()
        fraud_status = str(mt_res.get("fraud_status", "")).lower()
        
        is_success = (tx_status == "settlement") or (tx_status == "capture" and fraud_status == "accept")
        
        if is_success:
            await crud_transaction.update_status(db, tx=tx, new_status="Success")
            
            # Retrieve subscription product package
            product = await crud_product.get_by_id(db, id=tx.product_id) if tx.product_id else None
            billing_period = product.billing_period if product else "monthly"
            duration_days = 365 if billing_period in ("yearly", "group") else (36500 if billing_period == "lifetime" else 30)
            
            now = datetime.now(timezone.utc)
            active_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=current_user.id)
            current_tier = SUBSCRIPTION_TIERS.get(active_sub.product_id, 1) if active_sub else 0
            target_tier = SUBSCRIPTION_TIERS.get(tx.product_id, 1)
            is_member = await crud_subscription_group.is_user_group_member(db, user_id=current_user.id, email=current_user.email)
            if (active_sub and target_tier <= current_tier) or (active_sub and is_member):
                # Downgrade / Queue (Status Quo): begins when active_sub ends
                active_end_tz = active_sub.end_date if active_sub.end_date.tzinfo else active_sub.end_date.replace(tzinfo=timezone.utc)
                sub_start = active_end_tz
                sub_end = sub_start + timedelta(days=duration_days)
                new_sub = await crud_user_subscription.create_or_update_subscription(
                    db,
                    user_id=current_user.id,
                    product_id=tx.product_id,
                    transaction_id=tx.id,
                    start_date=sub_start,
                    end_date=sub_end,
                    billing_period=billing_period,
                    amount=tx.amount,
                    currency=tx.currency or "IDR",
                    payment_method="midtrans",
                    status="queued"
                )
            else:
                # New plan or Upgrade: begins immediately
                sub_start = now
                sub_end = now + timedelta(days=duration_days)
                new_sub = await crud_user_subscription.create_or_update_subscription(
                    db,
                    user_id=current_user.id,
                    product_id=tx.product_id,
                    transaction_id=tx.id,
                    start_date=sub_start,
                    end_date=sub_end,
                    billing_period=billing_period,
                    amount=tx.amount,
                    currency=tx.currency or "IDR",
                    payment_method="midtrans",
                    status="active"
                )

                if tx.product_id == "terragis_sub_group":
                    group = await crud_subscription_group.create_or_update_group(
                        db,
                        owner_id=current_user.id,
                        subscription_id=new_sub.id,
                        name=f"Grup {current_user.name}",
                        max_members=5
                    )
                    new_sub.group_id = group.id
                    await db.commit()

            await db.refresh(current_user)
            analytics_service.invalidate_cache()

    user_status = current_user.subscription_status
    user_expires = current_user.subscription_ends_at.isoformat() if current_user.subscription_ends_at else None

    return BaseResponse(
        data={
            "invoice_number": invoice_number,
            "status": tx.status if tx else "Pending",
            "transaction_status": tx.status if tx else "Pending",
            "subscription_status": user_status,
            "active_plan_id": current_user.active_plan_id,
            "subscription_ends_at": user_expires,
            "is_active": (tx.status == "Success") if tx else False
        },
        message="Payment status retrieved and synchronized successfully"
    )

@router.get("/my-subscription", response_model=BaseResponse[Optional[dict]], summary="Get Current Active & Queued Subscription")
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Returns active subscription and queued subscription (if any).
    Automatically promotes queued subscription if active subscription has expired.
    """
    await crud_user_subscription.promote_queued_subscription(db, user_id=current_user.id)

    active_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=current_user.id)
    queued_sub = await crud_user_subscription.get_queued_by_user_id(db, user_id=current_user.id)

    if not active_sub and not queued_sub:
        return BaseResponse(data=None, message="No active or queued subscription found")

    product = await crud_product.get_by_id(db, id=active_sub.product_id) if active_sub else None
    q_product = await crud_product.get_by_id(db, id=queued_sub.product_id) if queued_sub else None

    return BaseResponse(
        data={
            "id": active_sub.id if active_sub else None,
            "user_id": current_user.id,
            "product_id": active_sub.product_id if active_sub else None,
            "product_title": product.title if product else (active_sub.product_id if active_sub else None),
            "transaction_id": active_sub.transaction_id if active_sub else None,
            "start_date": active_sub.start_date.isoformat() if active_sub else None,
            "end_date": active_sub.end_date.isoformat() if active_sub else None,
            "status": active_sub.status if active_sub else "expired",
            "billing_period": active_sub.billing_period if active_sub else None,
            "amount": active_sub.amount if active_sub else 0.0,
            "currency": active_sub.currency if active_sub else "IDR",
            "payment_method": active_sub.payment_method if active_sub else None,
            "created_at": active_sub.created_at.isoformat() if active_sub else None,
            "queued_subscription": {
                "id": queued_sub.id,
                "product_id": queued_sub.product_id,
                "product_title": q_product.title if q_product else queued_sub.product_id,
                "billing_period": queued_sub.billing_period,
                "scheduled_start_date": queued_sub.start_date.isoformat(),
                "scheduled_end_date": queued_sub.end_date.isoformat(),
                "status": queued_sub.status,
                "amount": queued_sub.amount
            } if queued_sub else None,
            "has_queued": queued_sub is not None
        },
        message="Subscription details retrieved successfully"
    )

@router.get("/my-transactions", response_model=BaseResponse[List[dict]], summary="Get My Transaction History")
async def get_my_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Returns transaction history for the currently logged-in user.
    """
    txs = await crud_transaction.get_by_user_email(db, user_email=current_user.email)
    data = []
    base_snap = "https://app.midtrans.com/snap/v2/vtweb/" if settings.MIDTRANS_IS_PRODUCTION else "https://app.sandbox.midtrans.com/snap/v2/vtweb/"
    for tx in txs:
        token = tx.purchase_token
        redirect_url = f"{base_snap}{token}" if token else None
        data.append({
            "id": tx.id,
            "product_id": tx.product_id,
            "product_name": tx.name,
            "amount": tx.amount,
            "currency": tx.currency or "IDR",
            "status": tx.status,
            "payment_method": "Midtrans Gateway",
            "snap_token": token,
            "redirect_url": redirect_url,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
            "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
        })
    return BaseResponse(
        data=data,
        message="Transaction history retrieved successfully"
    )

@router.post("/midtrans/resume/{invoice_number}", response_model=BaseResponse[MidtransSnapResponse], summary="Resume Pending Midtrans Snap Payment")
async def resume_midtrans_payment(
    invoice_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Retrieves or generates a Snap payment session for an existing pending transaction
    so that the user can resume and complete payment from transaction history.
    """
    tx = await crud_transaction.get_by_id(db, id=invoice_number)
    if not tx or tx.user_email != current_user.email:
        raise NotFoundException(message=f"Transaksi dengan nomor invoice '{invoice_number}' tidak ditemukan.")

    if tx.status.lower() != "pending":
        raise ValidationException(message=f"Transaksi ini berstatus '{tx.status}' dan tidak dapat dilanjutkan.")

    token = tx.purchase_token
    redirect_url = ""
    base_snap = "https://app.midtrans.com/snap/v2/vtweb/" if settings.MIDTRANS_IS_PRODUCTION else "https://app.sandbox.midtrans.com/snap/v2/vtweb/"
    if token:
        redirect_url = f"{base_snap}{token}"
    else:
        # Generate new Snap session if missing
        product = await crud_product.get_by_id(db, id=tx.product_id)
        product_title = product.title if product else tx.name
        session_res = await midtrans_service.create_snap_transaction(
            user_id=current_user.id,
            user_name=current_user.name,
            user_email=current_user.email,
            product_id=tx.product_id,
            product_title=product_title,
            amount=int(tx.amount),
            invoice_number=tx.id
        )
        token = session_res.get("token", "")
        redirect_url = session_res.get("redirect_url", "")
        if token:
            tx.purchase_token = token
            await db.commit()

    return BaseResponse(
        data=MidtransSnapResponse(
            invoice_number=tx.id,
            token=token or "",
            redirect_url=redirect_url or f"{base_snap}{token}",
            amount=tx.amount,
            currency=tx.currency or "IDR",
            title=tx.name
        ),
        message="Sesi Snap checkout berhasil dimuat"
    )

class TrialConfigUpdate(BaseModel):
    is_active: bool
    trial_days: int = Field(..., ge=1, le=90)

@router.post("/claim-trial", response_model=BaseResponse[dict], status_code=status.HTTP_201_CREATED, summary="Claim Free Trial Subscription")
async def claim_free_trial(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Activates a free trial subscription for a newly registered user.
    Enforces anti-abuse rule: each user can only claim a trial once.
    Checks dynamic configuration on product 'terragis_sub_trial'.
    """
    # 1. Check if trial product exists and is active
    trial_product = await crud_product.get_by_id(db, id="terragis_sub_trial")
    if not trial_product or not trial_product.is_active:
        raise ValidationException(message="Masa uji coba gratis (trial) saat ini sedang dinonaktifkan oleh administrator. Silakan pilih paket berlangganan.")

    # 2. Check anti-abuse: has user ever had any subscription?
    existing_subs = await crud_user_subscription.get_all_by_user_id(db, user_id=current_user.id)
    if existing_subs:
        raise ConflictException(message="Akun Anda sudah pernah mengklaim masa uji coba gratis atau memiliki riwayat paket.")

    # 3. Create trial subscription
    now = datetime.now(timezone.utc)
    duration_days = trial_product.trial_days or 7
    end_date = now + timedelta(days=duration_days)

    new_sub = await crud_user_subscription.create_or_update_subscription(
        db,
        user_id=current_user.id,
        product_id=trial_product.id,
        transaction_id=None,
        start_date=now,
        end_date=end_date,
        billing_period="trial",
        amount=0.0,
        currency="IDR",
        payment_method="free_trial",
        status="active"
    )

    await db.refresh(current_user)
    analytics_service.invalidate_cache()

    return BaseResponse(
        data={
            "subscription_id": new_sub.id,
            "product_id": trial_product.id,
            "status": "active",
            "trial_days": duration_days,
            "start_date": now.isoformat(),
            "end_date": end_date.isoformat(),
            "has_access": True
        },
        message=f"Masa uji coba gratis {duration_days} hari berhasil diaktifkan!"
    )

@router.patch("/admin/trial-config", response_model=BaseResponse[dict], summary="Admin: Configure Free Trial Settings")
async def update_trial_config(
    body: TrialConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Admin only: Toggle trial on/off and configure trial duration days.
    """
    if current_user.role not in ("superadmin", "admin"):
        raise ValidationException(message="Hanya administrator yang dapat mengubah pengaturan trial.")

    trial_product = await crud_product.get_by_id(db, id="terragis_sub_trial")
    if not trial_product:
        trial_product = Product(
            id="terragis_sub_trial",
            title="Uji Coba Gratis",
            description="Akses penuh seluruh fitur Terra GIS selama masa uji coba gratis",
            amount=0.0,
            currency="IDR",
            billing_period="trial",
            trial_days=body.trial_days,
            is_active=body.is_active
        )
        db.add(trial_product)
    else:
        trial_product.is_active = body.is_active
        trial_product.trial_days = body.trial_days

    await db.commit()
    await db.refresh(trial_product)

    return BaseResponse(
        data={
            "is_active": trial_product.is_active,
            "trial_days": trial_product.trial_days
        },
        message="Pengaturan masa uji coba gratis berhasil diperbarui."
    )
