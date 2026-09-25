import pytest
from httpx import AsyncClient
from app.crud.crud_user import crud_user
from app.crud.crud_email_verification import crud_email_verification
from app.schemas.auth import UserCreate

@pytest.mark.asyncio
async def test_registration_and_email_verification_flow(client: AsyncClient, db_session):
    # 1. Register a new user
    reg_payload = {
        "email": "new_surveyor@terragis.io",
        "name": "New Surveyor",
        "password": "Password123!"
    }
    response = await client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["requires_verification"] is True

    # 2. Check that user was created with is_email_verified = False
    user = await crud_user.get_by_email(db_session, email="new_surveyor@terragis.io")
    assert user is not None
    assert user.is_email_verified is False

    # 3. Retrieve the generated OTP from database
    otp_record = await crud_email_verification.get_active_otp if hasattr(crud_email_verification, "get_active_otp") else None
    # Verify using direct query
    from sqlalchemy.future import select
    from app.models.email_verification import EmailVerification
    res = await db_session.execute(
        select(EmailVerification).where(
            EmailVerification.email == "new_surveyor@terragis.io",
            EmailVerification.otp_type == "register",
            EmailVerification.is_used == False
        )
    )
    otp_obj = res.scalars().first()
    assert otp_obj is not None
    assert len(otp_obj.otp_code) == 6

    # 4. Attempt verification with WRONG OTP
    verify_res_wrong = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": "new_surveyor@terragis.io", "otp_code": "000000"}
    )
    assert verify_res_wrong.status_code == 422
    assert "tidak cocok" in verify_res_wrong.json()["error"]["message"].lower()

    # 5. Verify with CORRECT OTP
    verify_res_correct = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": "new_surveyor@terragis.io", "otp_code": otp_obj.otp_code}
    )
    assert verify_res_correct.status_code == 200
    assert verify_res_correct.json()["data"]["verified"] is True

    # Verify user is now marked verified in DB
    await db_session.refresh(user)
    assert user.is_email_verified is True


@pytest.mark.asyncio
async def test_forgot_password_and_reset_flow(client: AsyncClient, db_session):
    # 1. Create a user to reset password
    user = await crud_user.create(
        db_session,
        obj_in=UserCreate(
            email="reset_me@terragis.io",
            name="Reset Tester",
            password="OriginalPassword123!",
            role="user",
            is_email_verified=True
        )
    )

    # 2. Request forgot password OTP
    req_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"email": "reset_me@terragis.io"}
    )
    assert req_res.status_code == 200
    assert req_res.json()["data"]["sent"] is True

    # Check rate limit on immediate re-request
    cooldown_res = await client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"email": "reset_me@terragis.io"}
    )
    assert cooldown_res.status_code == 422
    assert "detik" in cooldown_res.json()["error"]["message"].lower()

    # 3. Retrieve OTP from DB
    from sqlalchemy.future import select
    from app.models.email_verification import EmailVerification
    res = await db_session.execute(
        select(EmailVerification).where(
            EmailVerification.email == "reset_me@terragis.io",
            EmailVerification.otp_type == "forgot_password",
            EmailVerification.is_used == False
        )
    )
    otp_obj = res.scalars().first()
    assert otp_obj is not None

    # 4. Verify OTP and obtain reset_token
    verify_res = await client.post(
        "/api/v1/auth/forgot-password/verify-otp",
        json={"email": "reset_me@terragis.io", "otp_code": otp_obj.otp_code}
    )
    assert verify_res.status_code == 200
    reset_token = verify_res.json()["data"]["reset_token"]
    assert reset_token is not None
    assert len(reset_token) > 10

    # 5. Reset password using reset_token
    reset_res = await client.post(
        "/api/v1/auth/forgot-password/reset-password",
        json={
            "email": "reset_me@terragis.io",
            "reset_token": reset_token,
            "new_password": "NewSecurePassword2026!"
        }
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["data"]["success"] is True

    # 6. Verify old password fails
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset_me@terragis.io", "password": "OriginalPassword123!"}
    )
    assert old_login.status_code == 401

    # 7. Verify new password succeeds
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset_me@terragis.io", "password": "NewSecurePassword2026!"}
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()["data"]

    # 8. Token reuse attempt should be rejected
    reuse_res = await client.post(
        "/api/v1/auth/forgot-password/reset-password",
        json={
            "email": "reset_me@terragis.io",
            "reset_token": reset_token,
            "new_password": "AnotherPassword123!"
        }
    )
    assert reuse_res.status_code == 422


@pytest.mark.asyncio
async def test_resend_verification_otp_and_login_flag(client: AsyncClient, db_session):
    # 1. Register a user
    email = "resend_tester@terragis.io"
    reg_payload = {
        "email": email,
        "name": "Resend Tester",
        "password": "Password123!"
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201

    # 2. Login should indicate requires_verification = True
    login_res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    assert login_res.json()["data"]["requires_verification"] is True

    # 3. Resend verification OTP (expect cooldown or success)
    resend_cooldown = await client.post("/api/v1/auth/resend-verification-otp", json={
        "email": email,
        "otp_type": "register"
    })
    # Since registration just created an OTP, rate limit may trigger
    assert resend_cooldown.status_code in [200, 422]

