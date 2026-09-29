from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import desc, asc, and_, or_, func

from app.models.user_subscription import UserSubscription

class CRUDUserSubscription:
    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[UserSubscription]:
        result = await db.execute(
            select(UserSubscription)
            .options(
                joinedload(UserSubscription.user),
                joinedload(UserSubscription.product)
            )
            .where(UserSubscription.id == id)
        )
        return result.scalars().first()

    async def sync_expired_subscriptions(self, db: AsyncSession):
        """
        Automatically updates active subscriptions whose end_date has passed to 'expired',
        and promotes any queued subscriptions for those users.
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(UserSubscription).where(
                and_(
                    UserSubscription.status == "active",
                    UserSubscription.end_date < now
                )
            )
        )
        expired_subs = list(result.scalars().all())
        if expired_subs:
            user_ids_to_check = set()
            for sub in expired_subs:
                sub.status = "expired"
                user_ids_to_check.add(sub.user_id)
            await db.commit()

            # Check if any of these users have a queued subscription waiting to be activated
            for u_id in user_ids_to_check:
                try:
                    await self.promote_queued_subscription(db, user_id=u_id)
                except Exception:
                    pass

    async def get_filtered(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        status: Optional[str] = None,
        product_id: Optional[str] = None,
        billing_period: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        order: str = "desc"
    ) -> Tuple[List[UserSubscription], int]:
        from app.models.user import User
        from app.models.product import Product

        # Sync expired subscriptions in background
        await self.sync_expired_subscriptions(db)
        now = datetime.now(timezone.utc)

        query = (
            select(UserSubscription)
            .outerjoin(User, UserSubscription.user_id == User.id)
            .outerjoin(Product, UserSubscription.product_id == Product.id)
            .options(
                joinedload(UserSubscription.user),
                joinedload(UserSubscription.product)
            )
        )
        count_query = (
            select(func.count(UserSubscription.id))
            .outerjoin(User, UserSubscription.user_id == User.id)
            .outerjoin(Product, UserSubscription.product_id == Product.id)
        )

        filters = []
        if q:
            search = f"%{q}%"
            filters.append(
                or_(
                    User.name.ilike(search),
                    User.email.ilike(search),
                    UserSubscription.user_id.ilike(search),
                    UserSubscription.id.ilike(search),
                    Product.title.ilike(search),
                    UserSubscription.product_id.ilike(search)
                )
            )
        if status and status.lower() != "all":
            clean_status = status.strip().lower()
            if clean_status == "active":
                filters.append(
                    and_(
                        UserSubscription.status == "active",
                        UserSubscription.end_date > now
                    )
                )
            elif clean_status == "expired":
                filters.append(
                    or_(
                        UserSubscription.status == "expired",
                        and_(
                            UserSubscription.status == "active",
                            UserSubscription.end_date <= now
                        )
                    )
                )
            else:
                filters.append(UserSubscription.status == status)

        if product_id and product_id.lower() != "all":
            filters.append(UserSubscription.product_id == product_id)
        if billing_period and billing_period.lower() != "all":
            filters.append(UserSubscription.billing_period == billing_period)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        # Sorting
        sort_column = UserSubscription.created_at
        if sort_by == "start_date":
            sort_column = UserSubscription.start_date
        elif sort_by == "end_date":
            sort_column = UserSubscription.end_date
        elif sort_by == "user_name":
            sort_column = User.name
        elif sort_by == "amount":
            sort_column = UserSubscription.amount
        elif sort_by == "status":
            sort_column = UserSubscription.status

        if order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        total_result = await db.execute(count_query)
        total = total_result.scalar_one_or_none() or 0

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        items = list(result.scalars().unique().all())

        return items, total

    async def get_stats(self, db: AsyncSession) -> dict:
        now = datetime.now(timezone.utc)
        await self.sync_expired_subscriptions(db)

        total_res = await db.execute(select(func.count(UserSubscription.id)))
        total = total_res.scalar_one_or_none() or 0

        active_res = await db.execute(
            select(func.count(UserSubscription.id)).where(
                and_(
                    UserSubscription.status == "active",
                    UserSubscription.end_date > now
                )
            )
        )
        active = active_res.scalar_one_or_none() or 0

        queued_res = await db.execute(
            select(func.count(UserSubscription.id)).where(UserSubscription.status == "queued")
        )
        queued = queued_res.scalar_one_or_none() or 0

        expired_res = await db.execute(
            select(func.count(UserSubscription.id)).where(
                or_(
                    UserSubscription.status == "expired",
                    and_(
                        UserSubscription.status == "active",
                        UserSubscription.end_date <= now
                    )
                )
            )
        )
        expired = expired_res.scalar_one_or_none() or 0

        cancelled_res = await db.execute(
            select(func.count(UserSubscription.id)).where(UserSubscription.status == "cancelled")
        )
        cancelled = cancelled_res.scalar_one_or_none() or 0

        return {
            "total": total,
            "active": active,
            "queued": queued,
            "expired": expired,
            "cancelled": cancelled
        }


    async def update_status(self, db: AsyncSession, sub: UserSubscription, new_status: str) -> UserSubscription:
        sub.status = new_status
        await db.commit()
        await db.refresh(sub)
        return sub


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
        transaction_id: Optional[str] = None,
        start_date: datetime = None,
        end_date: datetime = None,
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
