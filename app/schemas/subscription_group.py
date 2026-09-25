from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime

class GroupInviteRequest(BaseModel):
    email: EmailStr

class GroupMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    group_id: str
    email: str
    user_id: Optional[str] = None
    status: str
    invited_at: datetime
    joined_at: Optional[datetime] = None

class GroupDetailsOut(BaseModel):
    id: str
    owner_id: str
    owner_email: str
    name: str
    max_members: int
    current_members_count: int
    is_owner: bool
    is_active: bool
    subscription_ends_at: Optional[datetime] = None
    members: List[GroupMemberOut]

class UpgradePreviewResponse(BaseModel):
    can_upgrade: bool
    action_type: str = "upgrade"  # upgrade, downgrade_queue, new, already_queued
    current_plan_id: Optional[str] = None
    current_plan_title: Optional[str] = None
    target_plan_id: str
    target_plan_title: str
    target_price: float
    total_days: int
    days_used: int
    days_remaining: int
    unused_credit: float
    payable_amount: float
    effective_start_date: Optional[datetime] = None
    queued_already: bool = False
    message: str

