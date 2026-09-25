import csv
import io
from typing import Any, Optional, List
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException, AuthenticationException
from app.crud.crud_product import crud_product
from app.crud.crud_transaction import crud_transaction
from app.crud.crud_user import crud_user
from app.schemas.transaction import (
    TransactionOut, 
    TransactionCreate, 
    TransactionUpdateStatus
)
from app.schemas.auth import UserOut, UserCreate
from app.schemas.common import BaseResponse, PaginatedResponse, PaginationMeta
from app.api.deps import get_current_user, get_optional_current_user, get_current_active_admin, get_current_superadmin
from app.models.user import User
from app.services.analytics_service import analytics_service
from app.services.google_play_service import google_play_service
from app.core.config import settings
from pydantic import BaseModel, Field

router = APIRouter()

import uuid

class GooglePlayVerifyRequest(BaseModel):
    purchase_token: str = Field(..., json_schema_extra={"example": "gplay_token_xyz123"})
    product_id: str = Field(..., json_schema_extra={"example": "terragis_sub_monthly"})
    user_email: Optional[str] = None


def format_transaction_out(tx) -> TransactionOut:
    created_str = tx.created_at.isoformat() if hasattr(tx, "created_at") and tx.created_at else ""
    return TransactionOut(
        id=tx.id,
        product_id=tx.product_id,
        name=tx.name,
        amount=tx.amount,
        currency=tx.currency,
        status=tx.status,
        user_name=tx.user_name,
        user_email=tx.user_email,
        createdAt=created_str
    )

@router.get("", response_model=PaginatedResponse[TransactionOut], summary="List Paginated Transactions")
async def list_transactions(
    q: Optional[str] = Query(None, description="Search by donor name, email, transaction ID, or title"),
    status: Optional[str] = Query(None, description="Filter by status (Success, Pending, Failed, Cancelled)"),
    productId: Optional[str] = Query(None, description="Filter by product ID (e.g. support_10000)"),
    startDate: Optional[str] = Query(None, description="Start date ISO string filter"),
    endDate: Optional[str] = Query(None, description="End date ISO string filter"),
    page: int = Query(1, ge=1, description="Page number"),
    pageSize: int = Query(20, ge=1, le=10000, description="Items per page"),
    sortBy: str = Query("createdAt", description="Sort field: createdAt, amount, userName"),
    order: str = Query("desc", description="Sort direction: asc or desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    skip = (page - 1) * pageSize
    items, total = await crud_transaction.get_filtered(
        db,
        q=q,
        status=status,
        product_id=productId,
        start_date=startDate,
        end_date=endDate,
        skip=skip,
        limit=pageSize,
        sort_by=sortBy,
        order=order
    )

    total_pages = (total + pageSize - 1) // pageSize if total > 0 else 1
    formatted_items = [format_transaction_out(tx) for tx in items]

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

@router.get("/export", summary="Export Transactions Data (CSV / JSON)")
async def export_transactions(
    status: Optional[str] = Query(None),
    productId: Optional[str] = Query(None),
    format: str = Query("csv", description="Export format: csv or json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    items, _ = await crud_transaction.get_filtered(
        db,
        status=status,
        product_id=productId,
        skip=0,
        limit=10000
    )

    if format.lower() == "json":
        json_data = [
            {
                "id": tx.id,
                "productId": tx.product_id,
                "name": tx.name,
                "amount": tx.amount,
                "currency": tx.currency,
                "status": tx.status,
                "userName": tx.user_name,
                "userEmail": tx.user_email,
                "createdAt": tx.created_at.isoformat() if tx.created_at else ""
            }
            for tx in items
        ]
        import json
        return Response(
            content=json.dumps(json_data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=transactions_export.json"}
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Product ID", "Title", "Amount", "Currency", "Status", "User Name", "User Email", "Created At"])

    for tx in items:
        writer.writerow([
            tx.id,
            tx.product_id,
            tx.name,
            tx.amount,
            tx.currency,
            tx.status,
            tx.user_name,
            tx.user_email,
            tx.created_at.isoformat() if tx.created_at else ""
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"}
    )

@router.get("/{id}", response_model=BaseResponse[TransactionOut], summary="Get Transaction Detail")
async def get_transaction(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    tx = await crud_transaction.get_by_id(db, id=id)
    if not tx:
        raise NotFoundException(message=f"Transaction with ID '{id}' not found.")

    return BaseResponse(data=format_transaction_out(tx))

@router.post("", response_model=BaseResponse[TransactionOut], status_code=status.HTTP_201_CREATED, summary="Create Transaction")
async def create_transaction(
    body: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    tx = await crud_transaction.create(db, obj_in=body)
    analytics_service.invalidate_cache()
    return BaseResponse(
        data=format_transaction_out(tx),
        message="Transaction created successfully"
    )

@router.patch("/{id}/status", response_model=BaseResponse[TransactionOut], summary="Update Transaction Status")
async def update_transaction_status(
    id: str,
    body: TransactionUpdateStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    valid_statuses = ["Success", "Pending", "Failed", "Cancelled"]
    if body.status not in valid_statuses:
        raise ValidationException(message=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    tx = await crud_transaction.get_by_id(db, id=id)
    if not tx:
        raise NotFoundException(message=f"Transaction with ID '{id}' not found.")

    updated_tx = await crud_transaction.update_status(db, tx=tx, new_status=body.status)
    analytics_service.invalidate_cache()

    return BaseResponse(
        data=format_transaction_out(updated_tx),
        message="Transaction status updated successfully"
    )

@router.delete("/{id}", response_model=BaseResponse[dict], summary="Delete Transaction")
async def delete_transaction(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    deleted = await crud_transaction.delete(db, id=id)
    if not deleted:
        raise NotFoundException(message=f"Transaction with ID '{id}' not found.")
    analytics_service.invalidate_cache()
    return BaseResponse(data={"id": id}, message="Transaction deleted successfully")

@router.post("/verify-google-play", response_model=BaseResponse[UserOut], summary="Verify Google Play Purchase & Activate Subscription")
async def verify_google_play(
    body: GooglePlayVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Verifies Google Play purchase token via Google Play Developer API (Server-to-Server)
    and activates user subscription in backend DB.
    Requires authenticated user JWT token.
    """
    # 1. Server-to-Server Verification with Google Play API
    result = await google_play_service.verify_subscription_purchase(
        package_name=settings.ANDROID_PACKAGE_NAME,
        subscription_id=body.product_id,
        purchase_token=body.purchase_token
    )

    if not result.get("is_valid", False):
        raise ValidationException(message="Pembelian Google Play tidak valid atau tidak dapat diverifikasi.")

    expiry_date = result["expiry_date"]
    product = await crud_product.get_by_id(db, id=body.product_id)

    # 2. Activate/update user subscription in DB with verified expiry date and purchase token
    updated_user = await crud_user.update_subscription_verified(
        db,
        user=current_user,
        status="active",
        plan_id=body.product_id,
        expiry_date=expiry_date,
        purchase_token=body.purchase_token
    )

    # 3. Log successful purchase transaction
    await crud_transaction.create(
        db,
        obj_in=TransactionCreate(
            productId=body.product_id,
            name=product.title if product else "Google Play Subscription",
            amount=product.amount if product else 49000.0,
            currency=product.currency if product else "IDR",
            status="Success",
            userName=current_user.name,
            userEmail=current_user.email
        )
    )
    analytics_service.invalidate_cache()

    return BaseResponse(
        data=UserOut.model_validate(updated_user),
        message="Subscription activated successfully via Server-to-Server verification"
    )

