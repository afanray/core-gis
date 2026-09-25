from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from app.core.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)  # e.g., TX-1001
    product_id = Column(String, ForeignKey("products.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="IDR", nullable=False)
    status = Column(String, index=True, nullable=False)  # Success, Pending, Failed, Cancelled
    user_name = Column(String, nullable=False)
    user_email = Column(String, index=True, nullable=False)
    order_id = Column(String, nullable=True)
    purchase_token = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), index=True, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

Index("idx_tx_status_created", Transaction.status, Transaction.created_at)
