import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

class SubscriptionGroup(Base):
    __tablename__ = "subscription_groups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    subscription_id = Column(String, ForeignKey("user_subscriptions.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, default="Grup Surveyor", nullable=False)
    max_members = Column(Integer, default=5, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("SubscriptionGroupMember", back_populates="group", cascade="all, delete-orphan", lazy="selectin")


class SubscriptionGroupMember(Base):
    __tablename__ = "subscription_group_members"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String, ForeignKey("subscription_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    status = Column(String, default="active", nullable=False)  # active, invited, removed
    
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    joined_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    group = relationship("SubscriptionGroup", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("group_id", "email", name="uq_group_member_email"),
    )
