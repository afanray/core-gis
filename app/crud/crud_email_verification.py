import uuid
import secrets
from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, and_

from app.models.email_verification import EmailVerification

class CRUDEmailVerification:
    @staticmethod
    def generate_otp() -> str:
        """Generates a secure 6-digit numeric OTP code."""
        return f"{secrets.randbelow(900000) + 100000}"

    async def can_request_otp(
        self,
        db: AsyncSession,
        email: str,
        otp_type: str,
        cooldown_seconds: int = 60
    ) -> Tuple[bool, int]:
        """
        Rate limiting: prevents requesting another OTP within cooldown_seconds.
        Returns (allowed: bool, remaining_seconds: int).
        """
        clean_email = email.strip().lower()
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(EmailVerification)
            .where(
                and_(
                    EmailVerification.email == clean_email,
                    EmailVerification.otp_type == otp_type
                )
            )
            .order_by(desc(EmailVerification.created_at))
        )
        latest = result.scalars().first()
        if not latest:
            return True, 0

        created_tz = latest.created_at if latest.created_at.tzinfo else latest.created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_tz).total_seconds()
        if elapsed < cooldown_seconds:
            return False, int(cooldown_seconds - elapsed)

        return True, 0

    async def create_otp(
        self,
        db: AsyncSession,
        email: str,
        otp_type: str,
        expires_minutes: int = 10
    ) -> EmailVerification:
        clean_email = email.strip().lower()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_minutes)

        # Invalidate previous unused OTPs for this email and type
        prev_result = await db.execute(
            select(EmailVerification).where(
                and_(
                    EmailVerification.email == clean_email,
                    EmailVerification.otp_type == otp_type,
                    EmailVerification.is_used == False
                )
            )
        )
        for prev in prev_result.scalars().all():
            prev.is_used = True

        otp_code = self.generate_otp()
        verification = EmailVerification(
            email=clean_email,
            otp_code=otp_code,
            otp_type=otp_type,
            expires_at=expires_at,
            attempts=0,
            is_used=False
        )
        db.add(verification)
        await db.commit()
        await db.refresh(verification)
        return verification

    async def verify_otp(
        self,
        db: AsyncSession,
        email: str,
        otp_code: str,
        otp_type: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Verifies the 6-digit OTP code.
        Returns (success: bool, message: str, reset_token: Optional[str]).
        """
        clean_email = email.strip().lower()
        clean_otp = otp_code.strip()
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(EmailVerification)
            .where(
                and_(
                    EmailVerification.email == clean_email,
                    EmailVerification.otp_type == otp_type,
                    EmailVerification.is_used == False
                )
            )
            .order_by(desc(EmailVerification.created_at))
        )
        record = result.scalars().first()
        if not record:
            return False, "Kode OTP tidak valid atau belum diminta.", None

        # Check maximum attempts (anti-brute-force)
        if record.attempts >= 5:
            record.is_used = True
            await db.commit()
            return False, "Batas maksimal percobaan salah (5x) tercapai. Silakan minta kode OTP baru.", None

        # Check expiration
        expires_tz = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
        if now > expires_tz:
            record.is_used = True
            await db.commit()
            return False, "Kode OTP telah kedaluwarsa. Silakan minta kode baru.", None

        # Check OTP match
        if record.otp_code != clean_otp:
            record.attempts += 1
            await db.commit()
            remaining = 5 - record.attempts
            return False, f"Kode OTP tidak cocok. Sisa percobaan: {remaining} kali.", None

        # Success
        reset_token = None
        if otp_type == "forgot_password":
            reset_token = uuid.uuid4().hex
            record.reset_token = reset_token
            # Leave is_used=False until password reset completes
        else:
            record.is_used = True

        await db.commit()
        await db.refresh(record)
        return True, "Verifikasi kode OTP berhasil.", reset_token

    async def verify_and_consume_reset_token(
        self,
        db: AsyncSession,
        email: str,
        reset_token: str
    ) -> bool:
        """
        Validates temporary reset token and marks it consumed.
        """
        clean_email = email.strip().lower()
        clean_token = reset_token.strip()
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(EmailVerification)
            .where(
                and_(
                    EmailVerification.email == clean_email,
                    EmailVerification.reset_token == clean_token,
                    EmailVerification.otp_type == "forgot_password",
                    EmailVerification.is_used == False
                )
            )
        )
        record = result.scalars().first()
        if not record:
            return False

        # Verify not expired (within 15 minutes of creation)
        created_tz = record.created_at if record.created_at.tzinfo else record.created_at.replace(tzinfo=timezone.utc)
        if (now - created_tz).total_seconds() > 900:  # 15 mins
            record.is_used = True
            await db.commit()
            return False

        record.is_used = True
        await db.commit()
        return True

crud_email_verification = CRUDEmailVerification()
