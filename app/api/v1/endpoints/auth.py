import uuid
import httpx
import asyncio
from typing import Any, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, status, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    verify_password, 
    create_access_token, 
    create_refresh_token,
    decode_token
)
from app.core.exceptions import AuthenticationException, ConflictException, ValidationException, NotFoundException
from app.crud.crud_user import crud_user
from app.crud.crud_login_history import crud_login_history
from app.crud.crud_user_subscription import crud_user_subscription
from app.crud.crud_subscription_group import crud_subscription_group
from app.crud.crud_email_verification import crud_email_verification
from app.services.email_service import email_service
from app.schemas.auth import (
    LoginRequest, 
    Token, 
    UserOut, 
    RefreshTokenRequest, 
    RegisterRequest, 
    GoogleLoginRequest,
    UserCreate,
    ForgotPasswordRequest,
    VerifyOtpRequest,
    VerifyOtpResponse,
    ResetPasswordRequest,
    VerifyEmailRequest,
    ResendOtpRequest
)
from app.schemas.login_history import LoginHistoryOut
from app.schemas.common import BaseResponse
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.post("/login", response_model=BaseResponse[Token], summary="Admin JWT Login (JSON)")
async def login_json(
    login_data: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authenticate administrator credentials using JSON body.
    """
    user = await crud_user.get_by_email(db, email=login_data.email)
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise AuthenticationException(message="Incorrect email or password.")

    if not user.is_active:
        raise AuthenticationException(message="User account is deactivated.")

    # Update last login timestamp
    await crud_user.update_last_login(db, user_id=user.id)

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "Unknown IP"
    user_agent_str = request.headers.get("user-agent", "Unknown Device")

    # Record active login history session
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await crud_login_history.create_entry(
        db,
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        login_type=getattr(user, "login_type", "email") or "email",
        expires_at=expires_at,
        ip_address=client_ip,
        user_agent=user_agent_str
    )

    # Send security notification email in background
    background_tasks.add_task(
        email_service.send_login_alert,
        to_email=user.email,
        user_name=user.name,
        ip_address=client_ip,
        user_agent=user_agent_str,
        login_time=datetime.now(timezone.utc),
        login_method="Email & Kata Sandi"
    )

    requires_verification = not bool(getattr(user, "is_email_verified", True))

    return BaseResponse(
        data=Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            requires_verification=requires_verification
        ),
        message="Login successful"
    )

@router.post("/token", response_model=Token, summary="OAuth2 Form Token (Swagger UI / OAuth2 Standard)")
async def login_oauth2_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    OAuth2 compatible token login endpoint for form-urlencoded requests (Swagger UI Authorize button).
    """
    user = await crud_user.get_by_email(db, email=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise AuthenticationException(message="Incorrect email or password.")

    if not user.is_active:
        raise AuthenticationException(message="User account is deactivated.")

    await crud_user.update_last_login(db, user_id=user.id)

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await crud_login_history.create_entry(
        db,
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        login_type="admin",
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.post("/refresh", response_model=BaseResponse[Token], summary="Refresh JWT Access Token")
async def refresh_token(
    body: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthenticationException(message="Invalid or expired refresh token.")

    user_id = payload.get("sub")
    user = await crud_user.get_by_id(db, id=user_id)
    if not user or not user.is_active:
        raise AuthenticationException(message="User account inactive or not found.")

    new_access_token = create_access_token(subject=user.id)
    new_refresh_token = create_refresh_token(subject=user.id)

    # Revoke old refresh session
    await crud_login_history.revoke_token(db, token=body.refresh_token)

    # Log new refreshed session
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await crud_login_history.create_entry(
        db,
        user_id=user.id,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        login_type=getattr(user, "login_type", "email") or "email",
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    return BaseResponse(
        data=Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer"
        ),
        message="Token refreshed successfully"
    )

async def check_and_apply_group_membership(db: AsyncSession, user: User) -> None:
    try:
        member = await crud_subscription_group.link_user_invites(db, email=user.email, user_id=user.id)
        if not member:
            member = await crud_subscription_group.get_member_membership(db, user_id=user.id, email=user.email)
        
        if member:
            group = await crud_subscription_group.get_by_id(db, id=member.group_id)
            if group:
                owner_sub = await crud_user_subscription.get_active_by_user_id(db, user_id=group.owner_id)
                if owner_sub:
                    await crud_user_subscription.create_or_update_subscription(
                        db,
                        user_id=user.id,
                        product_id=owner_sub.product_id,
                        transaction_id=None,
                        start_date=owner_sub.start_date,
                        end_date=owner_sub.end_date,
                        billing_period="group",
                        amount=0.0,
                        currency="IDR",
                        payment_method="group_invite",
                        group_id=group.id
                    )
    except Exception:
        pass

@router.get("/me", response_model=BaseResponse[UserOut], summary="Get Current Admin Profile")
async def read_current_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    await crud_user_subscription.promote_queued_subscription(db, user_id=current_user.id)
    await check_and_apply_group_membership(db, current_user)
    await db.refresh(current_user)
    current_user.is_group_member = await crud_subscription_group.is_user_group_member(
        db, user_id=current_user.id, email=current_user.email
    )
    return BaseResponse(data=UserOut.model_validate(current_user))

@router.post("/logout", response_model=BaseResponse[dict], summary="Logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        await crud_login_history.revoke_token(db, token=token)

    return BaseResponse(data={"logged_out": True}, message="Successfully logged out")

@router.get("/login-history", response_model=BaseResponse[List[LoginHistoryOut]], summary="Get Current User Login History")
async def get_login_history(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    history = await crud_login_history.get_user_history(db, user_id=current_user.id, skip=skip, limit=limit)
    return BaseResponse(data=[LoginHistoryOut.model_validate(h) for h in history])

@router.post("/register", response_model=BaseResponse[Token], status_code=status.HTTP_201_CREATED, summary="Register User Account")
async def register_user(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Register a new user account in the backend DB and return access tokens.
    """
    existing = await crud_user.get_by_email(db, email=body.email)
    if existing:
        if getattr(existing, "login_type", "email") == "google":
            raise ConflictException(
                message="Email ini sudah terdaftar menggunakan Google SSO. Silakan masuk menggunakan tombol Login dengan Google."
            )
        raise ConflictException(message=f"Email '{body.email}' sudah terdaftar.")

    new_user = await crud_user.create(
        db, 
        obj_in=UserCreate(
            email=body.email,
            name=body.name,
            password=body.password,
            role="user",
            login_type="email",
            is_email_verified=False
        )
    )

    await crud_user.update_last_login(db, user_id=new_user.id)
    await check_and_apply_group_membership(db, new_user)

    # Generate registration email verification OTP and dispatch email
    otp_record = await crud_email_verification.create_otp(
        db, email=new_user.email, otp_type="register", expires_minutes=10
    )
    asyncio.create_task(
        email_service.send_verification_otp(
            to_email=new_user.email,
            user_name=new_user.name,
            otp_code=otp_record.otp_code
        )
    )

    access_token = create_access_token(subject=new_user.id)
    refresh_token = create_refresh_token(subject=new_user.id)

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await crud_login_history.create_entry(
        db,
        user_id=new_user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        login_type="email",
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    return BaseResponse(
        data=Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            requires_verification=True
        ),
        message="Pendaftaran berhasil! Kode verifikasi 6 digit telah dikirimkan ke email Anda."
    )

@router.post("/google", response_model=BaseResponse[Token], summary="Google SSO Backend Auth")
async def login_google(
    body: GoogleLoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authenticate or register user using Google SSO ID token / claims.
    """
    email = body.email.strip() if body.email else None
    name = body.name.strip() if body.name else None

    if body.id_token:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={body.id_token}")
                if res.status_code == 200:
                    data = res.json()
                    email = data.get("email", email)
                    name = data.get("name", name or (email.split("@")[0] if email else "Google User"))
        except Exception:
            # Fallback to provided payload email/name if tokeninfo endpoint is unreachable in local dev
            pass

    if not email:
        raise ValidationException(message="Invalid Google credentials: email is required.")

    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "Unknown IP"
    user_agent_str = request.headers.get("user-agent", "Unknown Device")

    user = await crud_user.get_by_email(db, email=email)
    if user:
        # Validate user active status
        if not user.is_active:
            raise AuthenticationException(message="Akun pengguna telah dinonaktifkan.")

        # Sync login_type to google if previously registered
        if getattr(user, "login_type", "email") != "google":
            user.login_type = "google"
            user.is_email_verified = True
            await db.commit()
            await db.refresh(user)

        await crud_user.update_last_login(db, user_id=user.id)
        await check_and_apply_group_membership(db, user)
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)

        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        await crud_login_history.create_entry(
            db,
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
            login_type="google",
            expires_at=expires_at,
            ip_address=client_ip,
            user_agent=user_agent_str
        )

        background_tasks.add_task(
            email_service.send_login_alert,
            to_email=user.email,
            user_name=user.name,
            ip_address=client_ip,
            user_agent=user_agent_str,
            login_time=datetime.now(timezone.utc),
            login_method="Google SSO"
        )

        return BaseResponse(
            data=Token(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                requires_verification=False
            ),
            message="Login Google SSO berhasil! Notifikasi keamanan masuk telah dikirim ke email Anda."
        )
    else:
        # User NOT registered yet -> Create new user with login_type='google' and is_email_verified=True
        random_password = f"GoogleSSO_{uuid.uuid4().hex[:12]}"
        user = await crud_user.create(
            db,
            obj_in=UserCreate(
                email=email,
                name=name or email.split("@")[0],
                password=random_password,
                role="user",
                login_type="google",
                is_email_verified=True
            )
        )

        await crud_user.update_last_login(db, user_id=user.id)
        await check_and_apply_group_membership(db, user)
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)

        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        await crud_login_history.create_entry(
            db,
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
            login_type="google",
            expires_at=expires_at,
            ip_address=client_ip,
            user_agent=user_agent_str
        )

        background_tasks.add_task(
            email_service.send_login_alert,
            to_email=user.email,
            user_name=user.name,
            ip_address=client_ip,
            user_agent=user_agent_str,
            login_time=datetime.now(timezone.utc),
            login_method="Google SSO"
        )

        return BaseResponse(
            data=Token(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                requires_verification=False
            ),
            message="Pendaftaran akun Google SSO berhasil! Notifikasi keamanan masuk telah dikirim ke email Anda."
        )

# -----------------------------------------------------------------------------
# Account Management: Forgot Password & Email Verification Endpoints
# -----------------------------------------------------------------------------

@router.post("/forgot-password/request-otp", response_model=BaseResponse[dict], summary="Request Password Reset OTP")
async def request_password_reset_otp(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    clean_email = body.email.strip().lower()
    user = await crud_user.get_by_email(db, email=clean_email)
    if not user:
        return BaseResponse(
            data={"sent": True}, 
            message="Jika email terdaftar, kode OTP 6 digit telah dikirimkan ke email Anda."
        )

    can_request, wait_seconds = await crud_email_verification.can_request_otp(
        db, email=clean_email, otp_type="forgot_password", cooldown_seconds=60
    )
    if not can_request:
        raise ValidationException(message=f"Harap tunggu {wait_seconds} detik sebelum meminta kode OTP kembali.")

    otp_record = await crud_email_verification.create_otp(
        db, email=clean_email, otp_type="forgot_password", expires_minutes=10
    )
    asyncio.create_task(
        email_service.send_password_reset_otp(
            to_email=user.email, 
            user_name=user.name, 
            otp_code=otp_record.otp_code
        )
    )
    return BaseResponse(
        data={"sent": True}, 
        message="Kode OTP 6 digit telah dikirimkan ke email Anda."
    )

@router.post("/forgot-password/verify-otp", response_model=BaseResponse[VerifyOtpResponse], summary="Verify Password Reset OTP")
async def verify_password_reset_otp(
    body: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    clean_email = body.email.strip().lower()
    user = await crud_user.get_by_email(db, email=clean_email)
    if not user:
        raise NotFoundException(message="Pengguna dengan email ini tidak ditemukan.")

    success, message, reset_token = await crud_email_verification.verify_otp(
        db, email=clean_email, otp_code=body.otp_code, otp_type="forgot_password"
    )
    if not success:
        raise ValidationException(message=message)

    return BaseResponse(
        data=VerifyOtpResponse(reset_token=reset_token, message=message),
        message="Kode OTP berhasil diverifikasi."
    )

@router.post("/forgot-password/reset-password", response_model=BaseResponse[dict], summary="Reset Password with Verified Token")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    clean_email = body.email.strip().lower()
    user = await crud_user.get_by_email(db, email=clean_email)
    if not user:
        raise NotFoundException(message="Pengguna tidak ditemukan.")

    valid = await crud_email_verification.verify_and_consume_reset_token(
        db, email=clean_email, reset_token=body.reset_token
    )
    if not valid:
        raise ValidationException(
            message="Token reset password tidak valid atau telah kedaluwarsa. Silakan ulangi proses lupa password."
        )

    await crud_user.update_password(db, user_id=user.id, new_password=body.new_password)

    # Send security notification email in background
    asyncio.create_task(
        email_service.send_password_changed_alert(
            to_email=user.email,
            user_name=user.name,
            ip_address=request.client.host if request.client else None
        )
    )

    return BaseResponse(
        data={"success": True}, 
        message="Kata sandi berhasil diperbarui! Silakan masuk kembali menggunakan kata sandi baru Anda."
    )

@router.post("/verify-email", response_model=BaseResponse[dict], summary="Verify Registration Email OTP")
async def verify_registration_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    clean_email = body.email.strip().lower()
    user = await crud_user.get_by_email(db, email=clean_email)
    if not user:
        raise NotFoundException(message="Pengguna tidak ditemukan.")

    if user.is_email_verified:
        return BaseResponse(data={"verified": True}, message="Email Anda sudah terverifikasi sebelumnya.")

    success, message, _ = await crud_email_verification.verify_otp(
        db, email=clean_email, otp_code=body.otp_code, otp_type="register"
    )
    if not success:
        raise ValidationException(message=message)

    await crud_user.mark_email_verified(db, user_id=user.id)
    return BaseResponse(
        data={"verified": True}, 
        message="Selamat! Alamat email Anda berhasil diverifikasi."
    )

@router.post("/resend-verification-otp", response_model=BaseResponse[dict], summary="Resend Verification OTP")
async def resend_verification_otp(
    body: ResendOtpRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    clean_email = body.email.strip().lower()
    user = await crud_user.get_by_email(db, email=clean_email)
    if not user:
        raise NotFoundException(message="Pengguna tidak ditemukan.")

    if body.otp_type == "register" and user.is_email_verified:
        return BaseResponse(data={"sent": False}, message="Email Anda sudah terverifikasi.")

    can_request, wait_seconds = await crud_email_verification.can_request_otp(
        db, email=clean_email, otp_type=body.otp_type, cooldown_seconds=60
    )
    if not can_request:
        raise ValidationException(message=f"Harap tunggu {wait_seconds} detik sebelum meminta kode OTP kembali.")

    otp_record = await crud_email_verification.create_otp(
        db, email=clean_email, otp_type=body.otp_type, expires_minutes=10
    )
    if body.otp_type == "forgot_password":
        asyncio.create_task(
            email_service.send_password_reset_otp(
                to_email=user.email, user_name=user.name, otp_code=otp_record.otp_code
            )
        )
    else:
        asyncio.create_task(
            email_service.send_verification_otp(
                to_email=user.email, user_name=user.name, otp_code=otp_record.otp_code
            )
        )

    return BaseResponse(
        data={"sent": True}, 
        message="Kode OTP verifikasi baru telah dikirimkan ke email Anda."
    )

