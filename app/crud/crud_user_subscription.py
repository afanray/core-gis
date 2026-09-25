from typing import Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, and_

from app.models.user_subscription import UserSubscription

class CRUDUserSubscription:
    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[UserSubscription]:
        result = await db.execute(select(UserSubscription).where(UserSubscription.id == id))
        return result.scalars().first()

    async def get_by_user_id(self, db: AsyncSession, user_id: str) -> Optional[UserSubscription]:
        result = await db.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .order_by(desc(UserSubscription.created_at))
        )
        return result.scalars().first()

    async def get_all_by_user_id(self, db: AsyncSession, user_id: str) -> List[UserSubscription]:
        result = await db.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .order_by(desc(UserSubscription.created_at))
        )
        return list(result.scalars().all())

    async def get_by_transaction_id(self, db: AsyncSession, transaction_id: str) -> Optional[UserSubscription]:
        result = await db.execute(select(UserSubscription).where(UserSubscription.transaction_id == transaction_id))
        return result.scalars().first()

    async def get_active_by_user_id(self, db: AsyncSession, user_id: str) -> Optional[UserSubscription]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(UserSubscription)
            .where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status == "active",
                    UserSubscription.end_date > now
                )
            )
            .order_by(desc(UserSubscription.end_date))
        )
        return result.scalars().first()

    async def get_queued_by_user_id(self, db: AsyncSession, user_id: str) -> Optional[UserSubscription]:
        result = await db.execute(
            select(UserSubscription)
            .where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status == "queued"
                )
            )
            .order_by(desc(UserSubscription.created_at))
        )
        return result.scalars().first()

    async def promote_queued_subscription(self, db: AsyncSession, user_id: str) -> Optional[UserSubscription]:
        """
        Promotes queued subscription to active if active subscription has expired or does not exist.
        """
        now = datetime.now(timezone.utc)
        active_sub = await self.get_active_by_user_id(db, user_id=user_id)
        if active_sub:
            return active_sub

        queued_sub = await self.get_queued_by_user_id(db, user_id=user_id)
        if not queued_sub:
            return None

        # Mark any other active subscriptions for this user as expired
        old_subs = await db.execute(
            select(UserSubscription).where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status == "active",
                    UserSubscription.id != queued_sub.id
                )
            )
        )
        for s in old_subs.scalars().all():
            s.status = "expired"

        duration_days = 365 if queued_sub.billing_period in ("yearly", "group") else (36500 if queued_sub.billing_period == "lifetime" else 30)
        queued_sub.status = "active"
        queued_sub.start_date = now
        queued_sub.end_date = now + timedelta(days=duration_days)

        await db.commit()
        await db.refresh(queued_sub)
        return queued_sub

    async def create_or_update_subscription(
        self,
        db: AsyncSession,
        user_id: str,
        product_id: str,
        transaction_id: Optional[str],
        start_date: datetime,
        end_date: datetime,
        billing_period: str = "monthly",
        amount: float = 0.0,
        currency: str = "IDR",
        payment_method: str = "midtrans",
        group_id: Optional[str] = None,
        status: str = "active"
    ) -> UserSubscription:
        """
        Maintains max 1 active plan and max 1 queued plan per user.
        """
        if status == "active":
            existing_active = await self.get_active_by_user_id(db, user_id=user_id)
            if existing_active:
                existing_active.product_id = product_id
                existing_active.transaction_id = transaction_id
                existing_active.group_id = group_id
                existing_active.start_date = start_date
                existing_active.end_date = end_date
                existing_active.billing_period = billing_period
                existing_active.amount = amount
                existing_active.currency = currency
                existing_active.payment_method = payment_method
                await db.commit()
                await db.refresh(existing_active)
                return existing_active
        elif status == "queued":
            existing_queued = await self.get_queued_by_user_id(db, user_id=user_id)
            if existing_queued:
                existing_queued.product_id = product_id
                existing_queued.transaction_id = transaction_id
                existing_queued.group_id = group_id
                existing_queued.start_date = start_date
                existing_queued.end_date = end_date
                existing_queued.billing_period = billing_period
                existing_queued.amount = amount
                existing_queued.currency = currency
                existing_queued.payment_method = payment_method
                await db.commit()
                await db.refresh(existing_queued)
                return existing_queued

        new_sub = UserSubscription(
            user_id=user_id,
            product_id=product_id,
            transaction_id=transaction_id,
            group_id=group_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            billing_period=billing_period,
            amount=amount,
            currency=currency,
            payment_method=payment_method
        )
        db.add(new_sub)
        await db.commit()
        await db.refresh(new_sub)
        return new_sub

    # Alias create_subscription for backward compatibility
    async def create_subscription(self, *args, **kwargs) -> UserSubscription:
        return await self.create_or_update_subscription(*args, **kwargs)

crud_user_subscription = CRUDUserSubscription()
