from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class LoginHistoryBase(BaseModel):
    login_type: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class LoginHistoryCreate(LoginHistoryBase):
    user_id: str
    access_token: str
    refresh_token: str
    expires_at: datetime

class LoginHistoryOut(LoginHistoryBase):
    id: str
    user_id: str
    expires_at: datetime
    is_revoked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
