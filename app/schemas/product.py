from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class ProductBase(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "terragis_sub_monthly"})
    title: str = Field(..., json_schema_extra={"example": "Paket Langganan Bulanan"})
    description: Optional[str] = None
    amount: float = Field(..., gt=0)
    currency: str = "IDR"
    billingPeriod: str = Field("monthly", alias="billing_period")
    trialDays: int = Field(7, alias="trial_days")
    originalAmount: Optional[float] = Field(None, alias="original_amount")
    discountPercent: int = Field(0, alias="discount_percent")
    googlePlayProductId: Optional[str] = Field(None, alias="google_play_product_id")
    isActive: bool = Field(True, alias="is_active")

class ProductCreate(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    amount: float = Field(..., gt=0)
    currency: str = "IDR"
    billing_period: str = "monthly"
    trial_days: int = 7
    original_amount: Optional[float] = None
    discount_percent: int = 0
    google_play_product_id: Optional[str] = None
    is_active: bool = True

class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    billing_period: Optional[str] = None
    trial_days: Optional[int] = None
    original_amount: Optional[float] = None
    discount_percent: Optional[int] = None
    google_play_product_id: Optional[str] = None
    is_active: Optional[bool] = None

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    title: str
    description: Optional[str] = None
    amount: float
    currency: str
    billingPeriod: str = Field("monthly", alias="billing_period")
    trialDays: int = Field(7, alias="trial_days")
    originalAmount: Optional[float] = Field(None, alias="original_amount")
    discountPercent: int = Field(0, alias="discount_percent")
    googlePlayProductId: Optional[str] = Field(None, alias="google_play_product_id")
    isActive: bool = Field(..., alias="is_active")
    createdAt: datetime = Field(..., alias="created_at")

