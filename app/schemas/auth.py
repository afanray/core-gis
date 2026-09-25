from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from datetime import datetime, timezone

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "admin@terragis.io"})
    password: str = Field(..., min_length=6, json_schema_extra={"example": "AdminPassword123!"})

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_verification: bool = False

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    email: EmailStr
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    subscription_status: str = "trial"
    trial_ends_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None
    active_plan_id: Optional[str] = None
    queued_plan_id: Optional[str] = None
    queued_ends_at: Optional[datetime] = None
    login_type: str = "email"
    has_access: bool = True
    days_left_in_trial: int = 0
    is_group_member: bool = False
    is_email_verified: bool = False

    @model_validator(mode="after")
    def compute_access_and_trial(self):
        now = datetime.now(timezone.utc)

        trial_active = False
        if self.trial_ends_at:
            trial_end = self.trial_ends_at if self.trial_ends_at.tzinfo else self.trial_ends_at.replace(tzinfo=timezone.utc)
            if now < trial_end:
                trial_active = True
                diff = trial_end - now
                self.days_left_in_trial = max(0, diff.days + (1 if diff.seconds > 0 else 0))

        sub_active = False
        if self.subscription_status == "active" and self.subscription_ends_at:
            sub_end = self.subscription_ends_at if self.subscription_ends_at.tzinfo else self.subscription_ends_at.replace(tzinfo=timezone.utc)
            if now < sub_end:
                sub_active = True

        if self.role in ["superadmin", "admin"]:
            self.has_access = True
        else:
            self.has_access = trial_active or sub_active

        return self


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(..., min_length=6)
    role: str = "admin"
    login_type: Optional[str] = "email"
    is_email_verified: bool = False

class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@terragis.io"})
    name: str = Field(..., json_schema_extra={"example": "Surveyor User"})
    password: str = Field(..., min_length=6, json_schema_extra={"example": "SecurePass123!"})

class GoogleLoginRequest(BaseModel):
    id_token: Optional[str] = Field(None, json_schema_extra={"example": "eyJhbGciOiJSUzI1NiIs..."})
    email: Optional[str] = None
    name: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@terragis.io"})

class VerifyOtpRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@terragis.io"})
    otp_code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

class VerifyOtpResponse(BaseModel):
    reset_token: Optional[str] = None
    message: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@terragis.io"})
    reset_token: str = Field(..., json_schema_extra={"example": "b4a8e3f92..."})
    new_password: str = Field(..., min_length=6, json_schema_extra={"example": "NewSecurePass123!"})

class VerifyEmailRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@terragis.io"})
    otp_code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})

class ResendOtpRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@terragis.io"})
    otp_type: str = Field("register", json_schema_extra={"example": "register"})


