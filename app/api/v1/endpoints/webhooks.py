import base64
import json
import logging
from typing import Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud.crud_user import crud_user
from app.crud.crud_transaction import crud_transaction
from app.crud.crud_product import crud_product
from app.crud.crud_user_subscription import crud_user_subscription
from app.crud.crud_subscription_group import crud_subscription_group
from app.services.google_play_service import google_play_service
from app.services.doku_service import doku_service
from app.services.midtrans_service import midtrans_service
from app.services.analytics_service import analytics_service
from app.api.v1.endpoints.payments import SUBSCRIPTION_TIERS

logger = logging.getLogger("webhooks")
router = APIRouter()

@router.post("/google-play", status_code=status.HTTP_200_OK, summary="Google Play RTDN Webhook Listener")
async def google_play_rtdn_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Endpoint for Google Cloud Pub/Sub Push Subscription (Real-Time Developer Notifications / RTDN).
    Receives automatic notifications for subscription renewals, cancellations, grace periods, etc.
    URL: /api/v1/webhooks/google-play
    """
    try:
        body = await request.json()
        message = body.get("message", {})
        data_b64 = message.get("data")
        
        if not data_b64:
            logger.warning("RTDN Webhook received payload without message.data")
            return {"status": "ignored", "reason": "no data"}

        # 1. Decode base64 Google Pub/Sub notification payload
        decoded_bytes = base64.b64decode(data_b64)
        payload = json.loads(decoded_bytes.decode("utf-8"))
        logger.info(f"Received RTDN Payload: {payload}")

        developer_notification = payload.get("developerNotification", payload)
        subscription_notification = developer_notification.get("subscriptionNotification")

        if not subscription_notification:
            logger.info("RTDN Payload is not a subscription notification, ignoring.")
            return {"status": "ok", "reason": "non-subscription event"}

        notification_type = subscription_notification.get("notificationType")
        purchase_token = subscription_notification.get("purchaseToken")
        subscription_id = subscription_notification.get("subscriptionId")

        if not purchase_token or not subscription_id:
            return {"status": "ok", "reason": "missing token or subscriptionId"}

        # 2. Find matching user by purchase token
        user = await crud_user.get_by_purchase_token(db, purchase_token)
        if not user:
            logger.warning(f"No user found matching purchaseToken: {purchase_token}")
            return {"status": "ok", "reason": "user not found"}

        # 3. Verify current subscription status with Google Play API
        verification = await google_play_service.verify_subscription_purchase(
            package_name=developer_notification.get("packageName"),
            subscription_id=subscription_id,
            purchase_token=purchase_token
        )

        expiry_date = verification.get("expiry_date")

        # Notification Types Mapping:
        # 1: RECOVERED, 2: RENEWED, 4: PURCHASED, 7: RESTARTED -> ACTIVE
        # 3: CANCELED (Auto-renew turned off, active until expiry_date)
        # 5: ON_HOLD -> ON_HOLD
        # 6: IN_GRACE_PERIOD -> GRACE_PERIOD
        # 12: REVOKED, 13: EXPIRED -> EXPIRED / CANCELED
        
        new_status = user.subscription_status
        if notification_type in (1, 2, 4, 7):
            new_status = "active"
        elif notification_type == 5:
            new_status = "on_hold"
        elif notification_type == 6:
            new_status = "grace_period"
        elif notification_type == 3:
            new_status = "active"
        elif notification_type in (12, 13):
            new_status = "expired"

        # 4. Update user status and expiry date in database
        if expiry_date:
            await crud_user.update_subscription_verified(
                db,
                user=user,
                status=new_status,
                plan_id=subscription_id,
                expiry_date=expiry_date,
                purchase_token=purchase_token
            )
            analytics_service.invalidate_cache()
            logger.info(f"Updated user {user.email} subscription status to '{new_status}' (Expires: {expiry_date})")

        return {"status": "ok", "message": "Notification processed successfully"}

    except Exception as e:
        logger.error(f"Error processing Google Play RTDN Webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/doku", status_code=status.HTTP_200_OK, summary="DOKU Payment Gateway HTTP Notification Webhook Listener")
async def doku_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Endpoint for DOKU HTTP Payment Notification Webhook.
    Receives real-time payment notifications for QRIS, Virtual Account, E-Wallet, Credit Card.
    URL: /api/v1/webhooks/doku
    """
    try:
        body_bytes = await request.body()
        body_json = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        logger.info(f"Received DOKU Webhook Notification Payload: {body_json}")

        # 1. Verify DOKU Signature
        is_valid_sig = doku_service.verify_webhook_signature(dict(request.headers), body_bytes)
        if not is_valid_sig:
            logger.warning("DOKU Webhook signature verification warning (proceeding with invoice lookup)")

        order_data = body_json.get("order", {})
        transaction_data = body_json.get("transaction", {})
        invoice_number = order_data.get("invoice_number")
        status_str = str(transaction_data.get("status", "")).upper()

        if not invoice_number:
            return {"status": "ignored", "reason": "missing invoice_number"}

        # 2. Lookup transaction in DB by invoice_number
        tx = await crud_transaction.get_by_id(db, id=invoice_number)
        
        is_success = status_str in ("SUCCESS", "SETTLEMENT", "PAID", "CAPTURE")
        
        if tx:
            new_tx_status = "Success" if is_success else ("Pending" if status_str == "PENDING" else "Failed")
            await crud_transaction.update_status(db, tx=tx, new_status=new_tx_status)
            
            if is_success and tx.user_email:
                user = await crud_user.get_by_email(db, tx.user_email)
                if user:
                    product = await crud_product.get_by_id(db, id=tx.product_id)
                    billing_period = product.billing_period if product else "monthly"
                    duration_days = 365 if billing_period in ("yearly", "group") else (36500 if billing_period == "lifetime" else 30)
                    now = datetime.now(timezone.utc)

                    active_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=user.id)
                    current_tier = SUBSCRIPTION_TIERS.get(active_sub.product_id, 1) if active_sub else 0
                    target_tier = SUBSCRIPTION_TIERS.get(tx.product_id, 1)
                    is_member = await crud_subscription_group.is_user_group_member(db, user_id=user.id, email=user.email)

                    if (active_sub and target_tier <= current_tier) or (active_sub and is_member):
                        # Downgrade / Queue: begins when active_sub ends
                        active_end_tz = active_sub.end_date if active_sub.end_date.tzinfo else active_sub.end_date.replace(tzinfo=timezone.utc)
                        sub_start = active_end_tz
                        sub_end = sub_start + timedelta(days=duration_days)
                        new_sub = await crud_user_subscription.create_or_update_subscription(
                            db,
                            user_id=user.id,
                            product_id=tx.product_id,
                            transaction_id=tx.id,
                            start_date=sub_start,
                            end_date=sub_end,
                            billing_period=billing_period,
                            amount=tx.amount,
                            currency=tx.currency or "IDR",
                            payment_method="doku",
                            status="queued"
                        )
                        logger.info(f"Queued subscription for user {user.email} (starts: {sub_start}) via DOKU payment for Invoice {invoice_number}")
                    else:
                        sub_start = now
                        sub_end = now + timedelta(days=duration_days)
                        new_sub = await crud_user_subscription.create_or_update_subscription(
                            db,
                            user_id=user.id,
                            product_id=tx.product_id,
                            transaction_id=tx.id,
                            start_date=sub_start,
                            end_date=sub_end,
                            billing_period=billing_period,
                            amount=tx.amount,
                            currency=tx.currency or "IDR",
                            payment_method="doku",
                            status="active"
                        )

                        if tx.product_id == "terragis_sub_group":
                            group = await crud_subscription_group.create_or_update_group(
                                db,
                                owner_id=user.id,
                                subscription_id=new_sub.id,
                                name=f"Grup {user.name}",
                                max_members=5
                            )
                            new_sub.group_id = group.id
                            await db.commit()

                        logger.info(f"Activated subscription for user {user.email} via DOKU payment for Invoice {invoice_number}")

        analytics_service.invalidate_cache()
        return {"status": "OK", "invoice_number": invoice_number, "is_success": is_success}

    except Exception as e:
        logger.error(f"Error processing DOKU Webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/midtrans", status_code=status.HTTP_200_OK, summary="Midtrans HTTP Notification Webhook Listener")
async def midtrans_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Endpoint for Midtrans HTTP Payment Notification Webhook.
    Receives real-time payment notifications for GoPay, QRIS, Virtual Accounts (BCA/Mandiri/BRI/BNI/Permata), ShopeePay, Indomaret/Alfamart, Credit Card.
    URL: /api/v1/webhooks/midtrans
    """
    try:
        body_bytes = await request.body()
        body_json = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        logger.info(f"Received Midtrans Webhook Notification Payload: {body_json}")

        order_id = body_json.get("order_id")
        status_code = str(body_json.get("status_code", ""))
        gross_amount = str(body_json.get("gross_amount", ""))
        signature_key = body_json.get("signature_key", "")
        transaction_status = str(body_json.get("transaction_status", "")).lower()
        fraud_status = str(body_json.get("fraud_status", "")).lower()

        if not order_id:
            return {"status": "ignored", "reason": "missing order_id"}

        # 1. Verify Midtrans SHA-512 Signature
        is_valid_sig = midtrans_service.verify_notification_signature(
            order_id=order_id,
            status_code=status_code,
            gross_amount=gross_amount,
            signature_key=signature_key
        )
        if not is_valid_sig:
            logger.warning(f"Midtrans signature verification mismatch for Order {order_id} (proceeding with invoice lookup)")

        # 2. Map transaction status
        # 'capture' (for credit card with fraud_status 'accept') or 'settlement' -> Success
        is_success = (transaction_status == "settlement") or (transaction_status == "capture" and fraud_status == "accept")
        is_pending = transaction_status in ("pending", "authorize")

        # 3. Lookup transaction in DB by order_id (invoice_number)
        tx = await crud_transaction.get_by_id(db, id=order_id)

        if tx:
            new_tx_status = "Success" if is_success else ("Pending" if is_pending else "Failed")
            await crud_transaction.update_status(db, tx=tx, new_status=new_tx_status)

            if is_success and tx.user_email:
                user = await crud_user.get_by_email(db, tx.user_email)
                if user:
                    product = await crud_product.get_by_id(db, id=tx.product_id)
                    billing_period = product.billing_period if product else "monthly"
                    duration_days = 365 if billing_period in ("yearly", "group") else (36500 if billing_period == "lifetime" else 30)
                    now = datetime.now(timezone.utc)

                    active_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=user.id)
                    current_tier = SUBSCRIPTION_TIERS.get(active_sub.product_id, 1) if active_sub else 0
                    target_tier = SUBSCRIPTION_TIERS.get(tx.product_id, 1)
                    is_member = await crud_subscription_group.is_user_group_member(db, user_id=user.id, email=user.email)

                    if (active_sub and target_tier <= current_tier) or (active_sub and is_member):
                        # Downgrade / Queue: begins when active_sub ends
                        active_end_tz = active_sub.end_date if active_sub.end_date.tzinfo else active_sub.end_date.replace(tzinfo=timezone.utc)
                        sub_start = active_end_tz
                        sub_end = sub_start + timedelta(days=duration_days)
                        new_sub = await crud_user_subscription.create_or_update_subscription(
                            db,
                            user_id=user.id,
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
                        logger.info(f"Queued subscription for user {user.email} (starts: {sub_start}) via Midtrans for Order {order_id}")
                    else:
                        sub_start = now
                        sub_end = now + timedelta(days=duration_days)
                        new_sub = await crud_user_subscription.create_or_update_subscription(
                            db,
                            user_id=user.id,
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
                                owner_id=user.id,
                                subscription_id=new_sub.id,
                                name=f"Grup {user.name}",
                                max_members=5
                            )
                            new_sub.group_id = group.id
                            await db.commit()

                        logger.info(f"Activated subscription for user {user.email} and recorded in user_subscriptions for Order {order_id}")

        analytics_service.invalidate_cache()
        return {"status": "OK", "order_id": order_id, "is_success": is_success}

    except Exception as e:
        logger.error(f"Error processing Midtrans Webhook: {e}")
        return {"status": "error", "message": str(e)}


