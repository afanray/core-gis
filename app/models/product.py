from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, DateTime, Integer
from app.core.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True)  # e.g., terragis_sub_monthly
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="IDR", nullable=False)
    billing_period = Column(String, default="monthly", nullable=False)  # monthly, yearly, lifetime
    trial_days = Column(Integer, default=7, nullable=False)
    original_amount = Column(Float, nullable=True)
    discount_percent = Column(Integer, default=0, nullable=False)
    google_play_product_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

