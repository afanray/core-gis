from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class AdminToggleActiveRequest(BaseModel):
    isActive: bool

class AdminCreateRequest(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(..., min_length=6)
    role: str = Field("admin", json_schema_extra={"example": "admin"})
