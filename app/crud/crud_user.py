from typing import Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.schemas.auth import UserCreate
from app.core.security import get_password_hash

class CRUDUser:
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == id))
        return result.scalars().first()

    async def get_multi(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        result = await db.execute(select(User).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, obj_in: UserCreate, trial_days: int = 7) -> User:
        login_type = getattr(obj_in, "login_type", "email") or "email"
        is_email_verified = getattr(obj_in, "is_email_verified", False)
        if login_type == "google":
            is_email_verified = True

        db_obj = User(
            email=obj_in.email,
            name=obj_in.name,
            hashed_password=get_password_hash(obj_in.password),
            role=obj_in.role,
            is_active=True,
            login_type=login_type,
            is_email_verified=is_email_verified
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update_last_login(self, db: AsyncSession, user_id: str) -> None:
        user = await self.get_by_id(db, user_id)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            await db.commit()

    async def update_password(self, db: AsyncSession, user_id: str, new_password: str) -> None:
        user = await self.get_by_id(db, user_id)
        if user:
            user.hashed_password = get_password_hash(new_password)
            user.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(user)

    async def mark_email_verified(self, db: AsyncSession, user_id: str) -> None:
        user = await self.get_by_id(db, user_id)
        if user:
            user.is_email_verified = True
            user.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(user)

    async def get_by_purchase_token(self, db: AsyncSession, purchase_token: str) -> Optional[User]:
        from app.models.user_subscription import UserSubscription
        result = await db.execute(
            select(User).join(User.subscriptions).where(UserSubscription.transaction_id == purchase_token)
        )
        return result.scalars().first()

    async def update_subscription(
        self,
        db: AsyncSession,
        user: User,
        status: str,
        plan_id: str,
        duration_days: int = 30
    ) -> User:
        from app.crud.crud_user_subscription import crud_user_subscription
        now = datetime.now(timezone.utc)
        sub = await crud_user_subscription.get_by_user_id(db, user_id=user.id)
        end = sub.end_date if sub else None
        end_tz = end if (end and end.tzinfo) else (end.replace(tzinfo=timezone.utc) if end else None)
        if end_tz and end_tz > now:
            new_end = end_tz + timedelta(days=duration_days)
        else:
            new_end = now + timedelta(days=duration_days)

        await crud_user_subscription.create_or_update_subscription(
            db,
            user_id=user.id,
            product_id=plan_id,
            transaction_id=sub.transaction_id if sub else None,
            start_date=now,
            end_date=new_end,
            billing_period="yearly" if duration_days >= 365 else "monthly"
        )
        await db.refresh(user)
        return user

    async def update_subscription_verified(
        self,
        db: AsyncSession,
        user: User,
        status: str,
        plan_id: str,
        expiry_date: datetime,
        purchase_token: Optional[str] = None
    ) -> User:
        from app.crud.crud_user_subscription import crud_user_subscription
        now = datetime.now(timezone.utc)
        await crud_user_subscription.create_or_update_subscription(
            db,
            user_id=user.id,
            product_id=plan_id,
            transaction_id=purchase_token,
            start_date=now,
            end_date=expiry_date,
            billing_period="monthly"
        )
        await db.refresh(user)
        return user

    async def toggle_active(self, db: AsyncSession, user: User, is_active: bool) -> User:
        user.is_active = is_active
        await db.commit()
        await db.refresh(user)
        return user

crud_user = CRUDUser()

