import uuid
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="admin", nullable=False)  # superadmin, admin, viewer
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    login_type = Column(String, default="email", nullable=False)  # email, google
    is_email_verified = Column(Boolean, default=False, nullable=False)

    # 1-to-many relationship with UserSubscription (active and queued plans)
    subscriptions = relationship(
        "UserSubscription",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    @property
    def active_subscription(self):
        now = datetime.now(timezone.utc)
        for s in (self.subscriptions or []):
            if s.status == "active":
                end = s.end_date
                end_tz = end if (end and end.tzinfo) else (end.replace(tzinfo=timezone.utc) if end else None)
                if end_tz and now < end_tz:
                    return s
        return None

    @property
    def queued_subscription(self):
        for s in (self.subscriptions or []):
            if s.status == "queued":
                return s
        return None

    @property
    def subscription(self):
        """Backward compatibility: returns active_subscription or first non-cancelled subscription."""
        return self.active_subscription or self.queued_subscription or (self.subscriptions[0] if self.subscriptions else None)

    @subscription.setter
    def subscription(self, val):
        pass

    @property
    def subscription_status(self) -> str:
        active = self.active_subscription
        if active:
            if active.billing_period == "trial" or active.product_id == "terragis_sub_trial":
                return "trial"
            return "active"
        if self.subscriptions:
            return "expired"
        return "unsubscribed"

    @subscription_status.setter
    def subscription_status(self, val):
        pass

    @property
    def trial_ends_at(self) -> Optional[datetime]:
        active = self.active_subscription
        if active and (active.billing_period == "trial" or active.product_id == "terragis_sub_trial"):
            return active.end_date
        return None

    @trial_ends_at.setter
    def trial_ends_at(self, val):
        pass

    @property
    def subscription_ends_at(self) -> Optional[datetime]:
        active = self.active_subscription
        return active.end_date if active else None

    @subscription_ends_at.setter
    def subscription_ends_at(self, val):
        pass

    @property
    def active_plan_id(self) -> Optional[str]:
        active = self.active_subscription
        return active.product_id if active else None

    @active_plan_id.setter
    def active_plan_id(self, val):
        pass

    @property
    def queued_plan_id(self) -> Optional[str]:
        queued = self.queued_subscription
        return queued.product_id if queued else None

    @queued_plan_id.setter
    def queued_plan_id(self, val):
        pass

    @property
    def queued_ends_at(self) -> Optional[datetime]:
        queued = self.queued_subscription
        return queued.end_date if queued else None

    @queued_ends_at.setter
    def queued_ends_at(self, val):
        pass

    @property
    def purchase_token(self) -> Optional[str]:
        sub = self.subscription
        return sub.transaction_id if sub else None

    @purchase_token.setter
    def purchase_token(self, val):
        pass

    @property
    def is_group_member(self) -> bool:
        if hasattr(self, "_is_group_member") and self._is_group_member is not None:
            return self._is_group_member
        active = self.active_subscription
        if active and active.billing_period == "group" and active.payment_method == "group_invite":
            return True
        return False

    @is_group_member.setter
    def is_group_member(self, val: bool):
        self._is_group_member = val



