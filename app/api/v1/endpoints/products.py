from typing import Any, List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ConflictException
from app.crud.crud_product import crud_product
from app.crud.crud_subscription_group import crud_subscription_group
from app.schemas.product import ProductOut, ProductCreate, ProductUpdate
from app.schemas.common import BaseResponse
from app.api.deps import get_optional_current_user, get_current_active_admin, get_current_superadmin
from app.models.user import User

router = APIRouter()

@router.get("", response_model=BaseResponse[List[ProductOut]], summary="List Subscription Products")
async def list_products(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
) -> Any:
    products = await crud_product.get_multi(db, active_only=active_only)
    if current_user:
        is_member = await crud_subscription_group.is_user_group_member(
            db, user_id=current_user.id, email=current_user.email
        )
        if is_member:
            products = [p for p in products if p.billing_period != "group" and p.id != "terragis_sub_group"]
            
    return BaseResponse(data=[ProductOut.model_validate(p) for p in products])

@router.post("", response_model=BaseResponse[ProductOut], status_code=status.HTTP_201_CREATED, summary="Create Product Package")
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    existing = await crud_product.get_by_id(db, id=body.id)
    if existing:
        raise ConflictException(message=f"Product with ID '{body.id}' already exists.")

    product = await crud_product.create(db, obj_in=body)
    return BaseResponse(data=ProductOut.model_validate(product), message="Product created successfully")

@router.put("/{id}", response_model=BaseResponse[ProductOut], summary="Update Product Package")
async def update_product(
    id: str,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    product = await crud_product.get_by_id(db, id=id)
    if not product:
        raise NotFoundException(message=f"Product with ID '{id}' not found.")

    updated_product = await crud_product.update(db, db_obj=product, obj_in=body)
    return BaseResponse(data=ProductOut.model_validate(updated_product), message="Product updated successfully")

@router.delete("/{id}", response_model=BaseResponse[dict], summary="Delete Product Package")
async def delete_product(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    deleted = await crud_product.delete(db, id=id)
    if not deleted:
        raise NotFoundException(message=f"Product with ID '{id}' not found.")
    return BaseResponse(data={"id": id}, message="Product deleted successfully")
