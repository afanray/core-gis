from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_

from app.models.login_history import LoginHistory

class CRUDLoginHistory:
    async def create_entry(
        self,
        db: AsyncSession,
        user_id: str,
        access_token: str,
        refresh_token: str,
        login_type: str = "email",
        expires_at: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> LoginHistory:
        if not expires_at:
            # Default session expiration 7 days if not provided
            expires_at = datetime.now(timezone.utc)

        db_obj = LoginHistory(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            login_type=login_type,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            is_revoked=False
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_access_token(self, db: AsyncSession, access_token: str) -> Optional[LoginHistory]:
        result = await db.execute(select(LoginHistory).where(LoginHistory.access_token == access_token))
        return result.scalars().first()

    async def get_by_refresh_token(self, db: AsyncSession, refresh_token: str) -> Optional[LoginHistory]:
        result = await db.execute(select(LoginHistory).where(LoginHistory.refresh_token == refresh_token))
        return result.scalars().first()

    async def is_token_active(self, db: AsyncSession, access_token: str) -> bool:
        session = await self.get_by_access_token(db, access_token)
        if not session:
            # If session is not found in login history table (e.g. legacy session before table creation), fallback to valid
            return True

        if session.is_revoked:
            return False

        now = datetime.now(timezone.utc)
        expires_at = session.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at < now:
            return False

        return True

    async def revoke_token(self, db: AsyncSession, token: str) -> bool:
        result = await db.execute(
            select(LoginHistory).where(
                or_(
                    LoginHistory.access_token == token,
                    LoginHistory.refresh_token == token
                )
            )
        )
        session = result.scalars().first()
        if session:
            session.is_revoked = True
            await db.commit()
            return True
        return False

    async def get_user_history(
        self,
        db: AsyncSession,
        user_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[LoginHistory]:
        result = await db.execute(
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

crud_login_history = CRUDLoginHistory()
