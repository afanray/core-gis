from typing import Any, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ConflictException
from app.crud.crud_user import crud_user
from app.schemas.auth import UserOut, UserCreate
from app.schemas.admin import AdminToggleActiveRequest
from app.schemas.common import BaseResponse
from app.api.deps import get_current_superadmin
from app.models.user import User

router = APIRouter()

@router.get("", response_model=BaseResponse[List[UserOut]], summary="List Admins")
async def list_admins(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    users = await crud_user.get_multi(db, skip=skip, limit=limit)
    return BaseResponse(data=[UserOut.model_validate(u) for u in users])

@router.post("", response_model=BaseResponse[UserOut], status_code=status.HTTP_201_CREATED, summary="Create New Admin")
async def create_admin(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    existing = await crud_user.get_by_email(db, email=body.email)
    if existing:
        raise ConflictException(message=f"Admin with email '{body.email}' already exists.")

    new_user = await crud_user.create(db, obj_in=body)
    return BaseResponse(data=UserOut.model_validate(new_user), message="Admin account created successfully")

@router.patch("/{id}/toggle-active", response_model=BaseResponse[UserOut], summary="Toggle Admin Active State")
async def toggle_admin_active(
    id: str,
    body: AdminToggleActiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superadmin)
) -> Any:
    user = await crud_user.get_by_id(db, id=id)
    if not user:
        raise NotFoundException(message=f"Admin account with ID '{id}' not found.")

    updated_user = await crud_user.toggle_active(db, user=user, is_active=body.isActive)
    return BaseResponse(data=UserOut.model_validate(updated_user), message="Admin status updated successfully")
