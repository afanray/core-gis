import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    transaction_id = Column(String, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True)
    group_id = Column(String, ForeignKey("subscription_groups.id", ondelete="SET NULL", use_alter=True), nullable=True, index=True)
    
    start_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, default="active", nullable=False, index=True)  # active, queued, expired, cancelled
    billing_period = Column(String, default="monthly", nullable=False)    # monthly, yearly, lifetime, group
    amount = Column(Float, default=0.0, nullable=False)
    currency = Column(String, default="IDR", nullable=False)
    payment_method = Column(String, default="midtrans", nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    product = relationship("Product")
    transaction = relationship("Transaction")

Index("idx_user_sub_active", UserSubscription.user_id, UserSubscription.status, UserSubscription.end_date)
Index("idx_user_sub_status", UserSubscription.user_id, UserSubscription.status)
