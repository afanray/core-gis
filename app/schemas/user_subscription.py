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
    product_id: str
    transaction_id: Optional[str] = None
    start_date: datetime
    end_date: datetime
    status: str
    billing_period: str
    amount: float
    currency: str
    payment_method: str
    created_at: datetime
    product_title: Optional[str] = None
    is_active: bool = True
