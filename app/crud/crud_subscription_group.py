from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_

from app.models.subscription_group import SubscriptionGroup, SubscriptionGroupMember
from app.models.user import User

class CRUDSubscriptionGroup:
    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[SubscriptionGroup]:
        result = await db.execute(select(SubscriptionGroup).where(SubscriptionGroup.id == id))
        return result.scalars().first()

    async def get_by_owner_id(self, db: AsyncSession, owner_id: str) -> Optional[SubscriptionGroup]:
        result = await db.execute(select(SubscriptionGroup).where(SubscriptionGroup.owner_id == owner_id))
        return result.scalars().first()

    async def get_member_membership(
        self, 
        db: AsyncSession, 
        user_id: Optional[str] = None, 
        email: Optional[str] = None
    ) -> Optional[SubscriptionGroupMember]:
        filters = []
        if user_id:
            filters.append(SubscriptionGroupMember.user_id == user_id)
        if email:
            filters.append(SubscriptionGroupMember.email == email)
        
        if not filters:
            return None

        result = await db.execute(
            select(SubscriptionGroupMember)
            .where(
                and_(
                    or_(*filters),
                    SubscriptionGroupMember.status == "active"
                )
            )
        )
        return result.scalars().first()

    async def create_or_update_group(
        self,
        db: AsyncSession,
        owner_id: str,
        subscription_id: str,
        name: str = "Grup Surveyor",
        max_members: int = 5
    ) -> SubscriptionGroup:
        group = await self.get_by_owner_id(db, owner_id=owner_id)
        if group:
            group.subscription_id = subscription_id
            group.name = name
            group.max_members = max_members
            await db.commit()
            await db.refresh(group)
            return group

        group = SubscriptionGroup(
            owner_id=owner_id,
            subscription_id=subscription_id,
            name=name,
            max_members=max_members
        )
        db.add(group)
        await db.commit()
        await db.refresh(group)
        return group

    async def add_member(
        self,
        db: AsyncSession,
        group_id: str,
        email: str,
        user_id: Optional[str] = None
    ) -> SubscriptionGroupMember:
        from app.core.exceptions import ConflictException, ValidationException
        from app.crud.crud_user import crud_user
        from app.crud.crud_user_subscription import crud_user_subscription

        clean_email = email.strip().lower()
        now = datetime.now(timezone.utc)

        # 1. Resolve user_id if user exists in database
        if not user_id:
            existing_user = await crud_user.get_by_email(db, email=clean_email)
            if existing_user:
                user_id = existing_user.id

        # 2. Check if user is an owner of ANY group
        if user_id:
            owned_group = await self.get_by_owner_id(db, owner_id=user_id)
            if owned_group:
                raise ConflictException(message="Pengguna ini merupakan pemilik Paket Bersama lain, tidak dapat dijadikan anggota.")

        # 3. Check if user/email is already an active member of ANY group
        existing_other = await self.get_member_membership(db, user_id=user_id, email=clean_email)
        if existing_other and existing_other.group_id != group_id:
            raise ConflictException(message="Pengguna ini sudah terdaftar sebagai anggota di Paket Bersama lain. Satu akun hanya dapat menjadi anggota pada satu grup.")

        # 4. Check if user already has an active group subscription from another group
        if user_id:
            active_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=user_id)
            if active_sub and active_sub.billing_period == "group" and active_sub.group_id and active_sub.group_id != group_id:
                raise ConflictException(message="Pengguna ini sudah memiliki langganan aktif dari Paket Bersama lain.")

        # 5. Check existing member entry in this group
        result = await db.execute(
            select(SubscriptionGroupMember).where(
                and_(
                    SubscriptionGroupMember.group_id == group_id,
                    SubscriptionGroupMember.email == clean_email
                )
            )
        )
        existing = result.scalars().first()
        if existing:
            existing.status = "active"
            if user_id:
                existing.user_id = user_id
                existing.joined_at = now
            await db.commit()
            await db.refresh(existing)
            return existing

        new_member = SubscriptionGroupMember(
            group_id=group_id,
            email=clean_email,
            user_id=user_id,
            status="active",
            invited_at=now,
            joined_at=now if user_id else None
        )
        db.add(new_member)
        await db.commit()
        await db.refresh(new_member)
        return new_member

    async def remove_member(self, db: AsyncSession, group_id: str, member_id: str) -> bool:
        result = await db.execute(
            select(SubscriptionGroupMember).where(
                and_(
                    SubscriptionGroupMember.group_id == group_id,
                    SubscriptionGroupMember.id == member_id
                )
            )
        )
        member = result.scalars().first()
        if member:
            await db.delete(member)
            await db.commit()
            return True
        return False

    async def get_active_members_count(self, db: AsyncSession, group_id: str) -> int:
        result = await db.execute(
            select(SubscriptionGroupMember).where(
                and_(
                    SubscriptionGroupMember.group_id == group_id,
                    SubscriptionGroupMember.status == "active"
                )
            )
        )
        return len(result.scalars().all())

    async def link_user_invites(self, db: AsyncSession, email: str, user_id: str) -> Optional[SubscriptionGroupMember]:
        clean_email = email.strip().lower()
        result = await db.execute(
            select(SubscriptionGroupMember).where(
                SubscriptionGroupMember.email == clean_email
            )
        )
        member = result.scalars().first()
        if member:
            member.user_id = user_id
            if not member.joined_at:
                member.joined_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(member)
            return member
        return None

    async def is_user_group_member(
        self,
        db: AsyncSession,
        user_id: str,
        email: Optional[str] = None
    ) -> bool:
        """
        Returns True if the user is an active member of a group (and NOT the owner).
        """
        # 1. Check membership in subscription_group_members table
        membership = await self.get_member_membership(db, user_id=user_id, email=email)
        if membership:
            group = await self.get_by_id(db, id=membership.group_id)
            if group and group.owner_id != user_id:
                return True

        # 2. Check active subscription table where payment_method is group_invite
        from app.crud.crud_user_subscription import crud_user_subscription
        active_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=user_id)
        if active_sub and active_sub.billing_period == "group" and active_sub.payment_method == "group_invite":
            return True

        return False

crud_subscription_group = CRUDSubscriptionGroup()
