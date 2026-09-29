from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone

class UserSubscriptionBase(BaseModel):
    product_id: str
    transaction_id: Optional[str] = None
    start_date: datetime
    end_date: datetime
    status: str = "active"
    billing_period: str = "monthly"
    amount: float = 0.0
    currency: str = "IDR"
    payment_method: str = "midtrans"

class UserSubscriptionCreate(UserSubscriptionBase):
    user_id: str

class UserSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    product_id: str
    product_title: Optional[str] = None
    transaction_id: Optional[str] = None
    group_id: Optional[str] = None
    start_date: datetime
    end_date: datetime
    status: str
    billing_period: str
    amount: float
    currency: str
    payment_method: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool = True

class UserSubscriptionUpdateStatus(BaseModel):
    status: str

class UserSubscriptionStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    total: int = 0
    active: int = 0
    queued: int = 0
    expired: int = 0
    cancelled: int = 0

