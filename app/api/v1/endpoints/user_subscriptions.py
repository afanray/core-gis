import csv
import io
import json
from typing import Any, Optional, List
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException
from app.crud.crud_user_subscription import crud_user_subscription
from app.schemas.user_subscription import (
    UserSubscriptionOut, 
    UserSubscriptionUpdateStatus,
    UserSubscriptionStatsOut
)
from app.schemas.common import BaseResponse, PaginatedResponse, PaginationMeta
from app.api.deps import get_current_active_admin
from app.models.user import User
from app.models.user_subscription import UserSubscription

router = APIRouter()

def format_user_subscription_out(sub: UserSubscription) -> UserSubscriptionOut:
    user_name = sub.user.name if sub.user else "User"
    user_email = sub.user.email if sub.user else ""
    product_title = sub.product.title if sub.product else (sub.product_id or "Terra GIS Plan")

    return UserSubscriptionOut(
        id=sub.id,
        user_id=sub.user_id,
        user_name=user_name,
        user_email=user_email,
        product_id=sub.product_id,
        product_title=product_title,
        transaction_id=sub.transaction_id,
        group_id=sub.group_id,
        start_date=sub.start_date,
        end_date=sub.end_date,
        status=sub.status,
        billing_period=sub.billing_period,
        amount=sub.amount,
        currency=sub.currency,
        payment_method=sub.payment_method,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        is_active=(sub.status == "active")
    )

@router.get("", response_model=PaginatedResponse[UserSubscriptionOut], summary="List Paginated User Subscriptions")
async def list_user_subscriptions(
    q: Optional[str] = Query(None, description="Search by user ID, user name, email, product title"),
    status: Optional[str] = Query(None, description="Filter by status (active, queued, expired, cancelled)"),
    productId: Optional[str] = Query(None, description="Filter by product ID"),
    billingPeriod: Optional[str] = Query(None, description="Filter by billing period (monthly, yearly, lifetime, group, trial)"),
    page: int = Query(1, ge=1, description="Page number"),
    pageSize: int = Query(20, ge=1, le=1000, description="Items per page"),
    sortBy: str = Query("created_at", description="Sort field: created_at, start_date, end_date, user_name, amount, status"),
    order: str = Query("desc", description="Sort direction: asc or desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    skip = (page - 1) * pageSize
    items, total = await crud_user_subscription.get_filtered(
        db,
        q=q,
        status=status,
        product_id=productId,
        billing_period=billingPeriod,
        skip=skip,
        limit=pageSize,
        sort_by=sortBy,
        order=order
    )

    total_pages = (total + pageSize - 1) // pageSize if total > 0 else 1
    formatted_items = [format_user_subscription_out(sub) for sub in items]

    return PaginatedResponse(
        data=formatted_items,
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=pageSize,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )
    )

@router.get("/stats", response_model=BaseResponse[UserSubscriptionStatsOut], summary="Get User Subscriptions Overview Stats")
async def get_user_subscription_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    stats = await crud_user_subscription.get_stats(db)
    return BaseResponse(data=UserSubscriptionStatsOut(**stats))

@router.get("/export", summary="Export User Subscriptions (CSV / JSON)")
async def export_user_subscriptions(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    productId: Optional[str] = Query(None),
    billingPeriod: Optional[str] = Query(None),
    format: str = Query("csv", description="Export format: csv or json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    items, _ = await crud_user_subscription.get_filtered(
        db,
        q=q,
        status=status,
        product_id=productId,
        billing_period=billingPeriod,
        skip=0,
        limit=10000,
        sort_by="created_at",
        order="desc"
    )

    formatted = [format_user_subscription_out(sub) for sub in items]

    if format.lower() == "json":
        json_data = [item.model_dump(mode="json") for item in formatted]
        return Response(
            content=json.dumps(json_data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=user_subscriptions_export.json"}
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", 
        "User ID", 
        "Nama Pengguna", 
        "Email", 
        "Paket Berlangganan", 
        "Product ID", 
        "Mulai Berlangganan", 
        "Akhir Berlangganan", 
        "Status", 
        "Periode", 
        "Nominal", 
        "Mata Uang", 
        "Metode Pembayaran", 
        "Dibuat Pada"
    ])

    for item in formatted:
        writer.writerow([
            item.id,
            item.user_id,
            item.user_name or "",
            item.user_email or "",
            item.product_title or "",
            item.product_id,
            item.start_date.isoformat() if item.start_date else "",
            item.end_date.isoformat() if item.end_date else "",
            item.status,
            item.billing_period,
            item.amount,
            item.currency,
            item.payment_method,
            item.created_at.isoformat() if item.created_at else ""
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=user_subscriptions_export.csv"}
    )

@router.get("/{id}", response_model=BaseResponse[UserSubscriptionOut], summary="Get User Subscription Detail")
async def get_user_subscription_detail(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    sub = await crud_user_subscription.get_by_id(db, id=id)
    if not sub:
        raise NotFoundException(message=f"Langganan dengan ID '{id}' tidak ditemukan.")

    return BaseResponse(data=format_user_subscription_out(sub))

@router.patch("/{id}/status", response_model=BaseResponse[UserSubscriptionOut], summary="Update User Subscription Status")
async def update_user_subscription_status(
    id: str,
    body: UserSubscriptionUpdateStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    valid_statuses = ["active", "queued", "expired", "cancelled"]
    clean_status = body.status.strip().lower()
    if clean_status not in valid_statuses:
        raise ValidationException(message=f"Status tidak valid. Pilihan: {', '.join(valid_statuses)}")

    sub = await crud_user_subscription.get_by_id(db, id=id)
    if not sub:
        raise NotFoundException(message=f"Langganan dengan ID '{id}' tidak ditemukan.")

    updated_sub = await crud_user_subscription.update_status(db, sub=sub, new_status=clean_status)
    return BaseResponse(
        data=format_user_subscription_out(updated_sub),
        message="Status langganan berhasil diperbarui"
    )
