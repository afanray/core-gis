from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class TransactionBase(BaseModel):
    productId: str
    name: str
    amount: float = Field(..., gt=0)
    currency: str = "IDR"
    status: str = Field("Pending", json_schema_extra={"example": "Success"})
    userName: str
    userEmail: str
    orderId: Optional[str] = None
    purchaseToken: Optional[str] = None

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdateStatus(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "Success"})

class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    productId: str = Field(..., validation_alias="product_id")
    name: str
    amount: float
    currency: str
    status: str
    userName: str = Field(..., validation_alias="user_name")
    userEmail: str = Field(..., validation_alias="user_email")
    createdAt: str

class TransactionFilterParams(BaseModel):
    q: Optional[str] = None
    status: Optional[str] = None
    productId: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    page: int = 1
    pageSize: int = 20
    sortBy: str = "createdAt"
    order: str = "desc"
