from typing import AsyncGenerator, Optional
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.core.exceptions import AuthenticationException, ForbiddenException
from app.crud.crud_user import crud_user
from app.crud.crud_login_history import crud_login_history
from app.models.user import User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False
)

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(reusable_oauth2)
) -> User:
    if not token:
        raise AuthenticationException(message="Not authenticated. Bearer token missing.")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise AuthenticationException(message="Could not validate credentials or token expired.")

    user_id: str = payload.get("sub")
    if not user_id:
        raise AuthenticationException(message="Token payload invalid.")

    # Check session status in login history table
    is_active_session = await crud_login_history.is_token_active(db, access_token=token)
    if not is_active_session:
        raise AuthenticationException(message="Session revoked or expired. Please log in again.")

    user = await crud_user.get_by_id(db, id=user_id)
    if not user:
        raise AuthenticationException(message="User not found.")

    if not user.is_active:
        raise ForbiddenException(message="Inactive user account.")

    return user

async def get_optional_current_user(
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2)
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        user_id: str = payload.get("sub")
        if not user_id:
            return None
        user = await crud_user.get_by_id(db, id=user_id)
        if not user or not user.is_active:
            return None
        return user
    except Exception:
        return None

async def get_current_active_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role not in ["superadmin", "admin"]:
        raise ForbiddenException(message="Insufficient permissions for administrator role.")
    return current_user

async def get_current_superadmin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "superadmin":
        raise ForbiddenException(message="Superadmin permissions required.")
    return current_user
