import asyncio
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger("app.email_service")

class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.sender_email = settings.EMAILS_FROM_EMAIL
        self.sender_name = settings.EMAILS_FROM_NAME

    def _send_sync(self, to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> bool:
        """
        Synchronous SMTP sender intended to be dispatched via asyncio.to_thread.
        """
        # 1. Fallback simulation if no password is configured
        if not self.smtp_password or self.smtp_password.strip() == "":
            logger.info(
                f"\n{'='*65}\n"
                f"📧 [EMAIL-SIMULATION MODE - SMTP PASSWORD NOT SET]\n"
                f"To: {to_email}\n"
                f"Subject: {subject}\n"
                f"{'-'*65}\n"
                f"Content:\n{text_body or html_body[:300]}...\n"
                f"{'='*65}\n"
            )
            return True

        # 2. Real SMTP delivery
        try:
            print(f"📧 [EmailService] Connecting to SMTP {self.smtp_host}:{self.smtp_port} to send to {to_email}...", flush=True)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = to_email

            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                if settings.SMTP_TLS:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            print(f"✅ [EmailService] Email successfully sent to {to_email} via Google SMTP (Subject: {subject})", flush=True)
            logger.info(f"✅ Email successfully sent to {to_email} via Google SMTP (Subject: {subject})")
            return True
        except Exception as e:
            print(f"❌ [EmailService] Failed to send email to {to_email} via SMTP: {e}", flush=True)
            logger.error(f"❌ Failed to send email to {to_email} via SMTP: {e}")
            # Fallback log in case of connection or authentication errors
            logger.info(
                f"\n{'='*65}\n"
                f"📧 [EMAIL-FALLBACK LOG (SMTP Error: {e})]\n"
                f"To: {to_email}\n"
                f"Subject: {subject}\n"
                f"{'-'*65}\n"
                f"Content:\n{text_body or html_body[:300]}...\n"
                f"{'='*65}\n"
            )
            return False

    async def send_email(self, to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> bool:
        """
        Asynchronously sends an email without blocking the event loop.
        """
        return await asyncio.to_thread(self._send_sync, to_email, subject, html_body, text_body)

    # -------------------------------------------------------------
    # High-level templates
    # -------------------------------------------------------------

    def _render_base_template(self, title: str, content_html: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    background-color: #f4f6f8;
                    margin: 0;
                    padding: 24px;
                    color: #212529;
                }}
                .container {{
                    max-width: 560px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 14px;
                    overflow: hidden;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
                    border: 1px solid #e9ecef;
                }}
                .header {{
                    background: linear-gradient(135deg, #0f5132 0%, #198754 100%);
                    color: #ffffff;
                    padding: 28px 24px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 22px;
                    letter-spacing: 0.5px;
                }}
                .header p {{
                    margin: 4px 0 0 0;
                    font-size: 13px;
                    opacity: 0.85;
                }}
                .content {{
                    padding: 32px 28px;
                }}
                .otp-box {{
                    text-align: center;
                    margin: 28px 0;
                }}
                .otp-code {{
                    font-family: 'Courier New', Courier, monospace;
                    font-size: 34px;
                    font-weight: 800;
                    letter-spacing: 8px;
                    color: #0f5132;
                    background: #e8f5e9;
                    padding: 14px 28px;
                    border-radius: 10px;
                    display: inline-block;
                    border: 1.5px dashed #2e7d32;
                }}
                .alert-box {{
                    background: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 14px;
                    border-radius: 6px;
                    margin: 20px 0;
                    font-size: 13px;
                    color: #664d03;
                }}
                .info-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                    font-size: 13.5px;
                }}
                .info-table td {{
                    padding: 8px 12px;
                    border-bottom: 1px solid #f1f3f5;
                }}
                .info-table td.label {{
                    color: #6c757d;
                    width: 35%;
                    font-weight: 500;
                }}
                .footer {{
                    background: #f8f9fa;
                    padding: 20px 24px;
                    text-align: center;
                    font-size: 12px;
                    color: #6c757d;
                    border-top: 1px solid #e9ecef;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>TERRA GIS</h1>
                    <p>Sistem Pemetaan Geospasial & Manajemen Data Lapangan</p>
                </div>
                <div class="content">
                    {content_html}
                </div>
                <div class="footer">
                    &copy; {datetime.now(timezone.utc).year} Terra GIS Platform. Seluruh hak cipta dilindungi.<br>
                    Email ini dikirim secara otomatis oleh sistem keamanan Terra GIS.
                </div>
            </div>
        </body>
        </html>
        """

    async def send_verification_otp(self, to_email: str, user_name: str, otp_code: str) -> bool:
        subject = f"Kode Verifikasi Registrasi Akun Terra GIS [{otp_code}]"
        content_html = f"""
            <h2 style="margin-top:0; color:#198754; font-size:18px;">Halo, {user_name}!</h2>
            <p style="font-size:14px; line-height:1.6; color:#495057;">
                Terima kasih telah mendaftar di <strong>Terra GIS</strong>. Untuk mengaktifkan akun Anda dan melindungi keamanan data, masukkan kode verifikasi 6 digit berikut ke dalam aplikasi:
            </p>
            <div class="otp-box">
                <div class="otp-code">{otp_code}</div>
            </div>
            <p style="font-size:13px; color:#6c757d; line-height:1.5;">
                ⏳ Kode ini berlaku selama <strong>10 menit</strong>. Jangan bagikan kode ini kepada siapa pun termasuk pihak yang mengatasnamakan Terra GIS.
            </p>
        """
        text_body = f"Halo {user_name},\n\nKode verifikasi akun Terra GIS Anda adalah: {otp_code}\nKode ini berlaku selama 10 menit.\n\nSalam,\nTim Terra GIS"
        html = self._render_base_template("Verifikasi Akun Terra GIS", content_html)
        return await self.send_email(to_email, subject, html, text_body)

    async def send_password_reset_otp(self, to_email: str, user_name: str, otp_code: str) -> bool:
        subject = f"Kode Verifikasi Reset Password Terra GIS [{otp_code}]"
        content_html = f"""
            <h2 style="margin-top:0; color:#dc3545; font-size:18px;">Permintaan Reset Password</h2>
            <p style="font-size:14px; line-height:1.6; color:#495057;">
                Halo <strong>{user_name}</strong>, kami menerima permintaan untuk mereset kata sandi akun Terra GIS Anda. Silakan masukkan kode OTP berikut pada aplikasi:
            </p>
            <div class="otp-box">
                <div class="otp-code" style="color:#b02a37; background:#f8d7da; border-color:#dc3545;">{otp_code}</div>
            </div>
            <div class="alert-box">
                ⚠️ <strong>Peringatan Keamanan:</strong> Kode berlaku selama <strong>10 menit</strong>. Jika Anda tidak merasa melakukan permintaan ini, abaikan email ini dan akun Anda akan tetap aman.
            </div>
        """
        text_body = f"Halo {user_name},\n\nKode OTP untuk reset password Terra GIS Anda adalah: {otp_code}\nKode berlaku 10 menit.\nJika Anda tidak meminta ini, abaikan email ini.\n\nTim Terra GIS"
        html = self._render_base_template("Reset Password Terra GIS", content_html)
        return await self.send_email(to_email, subject, html, text_body)

    async def send_login_alert(
        self,
        to_email: str,
        user_name: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        login_time: Optional[datetime] = None,
        login_method: str = "Google SSO"
    ) -> bool:
        formatted_time = (login_time or datetime.now(timezone.utc)).strftime("%d %b %Y, %H:%M:%S UTC")
        subject = f"Pemberitahuan Masuk Baru ke Akun Terra GIS ({login_method})"
        method_badge = (
            f'<span style="background:#e8f0fe; color:#1967d2; font-weight:600; padding:3px 8px; border-radius:4px; font-size:12px;">{login_method}</span>'
            if "google" in login_method.lower() else
            f'<span style="background:#f1f3f4; color:#3c4043; font-weight:600; padding:3px 8px; border-radius:4px; font-size:12px;">{login_method}</span>'
        )
        content_html = f"""
            <h2 style="margin-top:0; color:#0d6efd; font-size:18px;">Notifikasi Masuk (Login) Baru</h2>
            <p style="font-size:14px; line-height:1.6; color:#495057;">
                Halo <strong>{user_name}</strong>, akun Anda baru saja berhasil masuk ke sistem Terra GIS. Berikut adalah rincian aktivitas login:
            </p>
            <table class="info-table">
                <tr>
                    <td class="label">Metode Masuk:</td>
                    <td>{method_badge}</td>
                </tr>
                <tr>
                    <td class="label">Waktu Masuk:</td>
                    <td><strong>{formatted_time}</strong></td>
                </tr>
                <tr>
                    <td class="label">Alamat IP:</td>
                    <td><code>{ip_address or 'Tidak diketahui'}</code></td>
                </tr>
                <tr>
                    <td class="label">Perangkat:</td>
                    <td>{user_agent or 'Aplikasi Mobile / Web'}</td>
                </tr>
            </table>
            <div class="alert-box">
                🛡️ Jika ini memang Anda, tidak ada tindakan lanjutan yang perlu dilakukan. Namun jika Anda tidak merasa melakukan aktivitas masuk ini, segera periksa keamanan akun Anda atau hubungi admin di <strong>sdev67035@gmail.com</strong>.
            </div>
        """
        text_body = f"Halo {user_name},\n\nAkun Terra GIS Anda baru saja masuk ({login_method}) pada {formatted_time} dari IP {ip_address or '-'}.\nJika ini bukan Anda, segera amankan akun Anda.\n\nTim Terra GIS"
        html = self._render_base_template("Notifikasi Masuk Baru", content_html)
        return await self.send_email(to_email, subject, html, text_body)

    async def send_password_changed_alert(
        self,
        to_email: str,
        user_name: str,
        ip_address: Optional[str] = None
    ) -> bool:
        formatted_time = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")
        subject = "Keamanan Akun: Kata Sandi Terra GIS Berhasil Diubah"
        content_html = f"""
            <h2 style="margin-top:0; color:#198754; font-size:18px;">Kata Sandi Berhasil Diperbarui</h2>
            <p style="font-size:14px; line-height:1.6; color:#495057;">
                Halo <strong>{user_name}</strong>, kata sandi akun Terra GIS Anda telah berhasil diperbarui pada <strong>{formatted_time}</strong>.
            </p>
            <div class="alert-box">
                🔒 Semua sesi sebelumnya tetap dilindungi. Jika Anda tidak merasa melakukan perubahan ini, segera hubungi dukungan teknis Terra GIS di <strong>sdev67035@gmail.com</strong>.
            </div>
        """
        text_body = f"Halo {user_name},\n\nKata sandi akun Terra GIS Anda telah berhasil diperbarui pada {formatted_time}.\nJika ini bukan Anda, hubungi dukungan teknis kami.\n\nTim Terra GIS"
        html = self._render_base_template("Password Berhasil Diubah", content_html)
        return await self.send_email(to_email, subject, html, text_body)

    async def send_group_invite_notification(
        self,
        to_email: str,
        invited_user_name: str,
        owner_name: str,
        owner_email: str,
        group_name: str,
        deeplink_url: str,
        app_scheme_url: str = "terragis://group"
    ) -> bool:
        subject = f"Undangan Bergabung ke Paket Bersama Terra GIS - {group_name}"
        content_html = f"""
            <h2 style="margin-top:0; color:#198754; font-size:18px;">Undangan Paket Bersama (Team)</h2>
            <p style="font-size:14px; line-height:1.6; color:#495057;">
                Halo <strong>{invited_user_name}</strong>, Anda telah ditambahkan oleh <strong>{owner_name}</strong> ({owner_email}) ke dalam <strong>{group_name}</strong> di platform <strong>Terra GIS</strong>.
            </p>
            <table class="info-table">
                <tr>
                    <td class="label">Nama Grup:</td>
                    <td><strong>{group_name}</strong></td>
                </tr>
                <tr>
                    <td class="label">Pemilik Grup:</td>
                    <td>{owner_name} ({owner_email})</td>
                </tr>
                <tr>
                    <td class="label">Status Akses:</td>
                    <td><span style="background:#e8f5e9; color:#0f5132; font-weight:600; padding:3px 8px; border-radius:4px; font-size:12px;">Aktif (Paket Bersama)</span></td>
                </tr>
                <tr>
                    <td class="label">Fitur Termasuk:</td>
                    <td>Pemetaan Geospasial, MBTiles Offline, GPS Tracking, Geotagging, & Ekspor Data</td>
                </tr>
            </table>

            <div style="text-align: center; margin: 28px 0 20px 0;">
                <a href="{deeplink_url}" style="background: linear-gradient(135deg, #0f5132 0%, #198754 100%); color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 10px; font-weight: bold; font-size: 15px; display: inline-block; box-shadow: 0 4px 12px rgba(25, 135, 84, 0.3);">
                    Buka Aplikasi Terra GIS
                </a>
            </div>

            <div style="text-align: center; font-size: 13px; color: #6c757d; margin-bottom: 20px;">
                Jika tombol di atas tidak merespon di ponsel Anda, <a href="{app_scheme_url}" style="color: #198754; font-weight: 600;">klik di sini untuk membuka langsung (terragis://)</a>.
            </div>

            <div class="alert-box">
                ℹ️ <strong>Informasi:</strong> Akun Anda secara otomatis mendapatkan hak akses penuh mengikuti status aktif langganan pemilik grup. Anda tidak perlu membayar biaya langganan tambahan.
            </div>
        """
        text_body = (
            f"Halo {invited_user_name},\n\n"
            f"Anda telah ditambahkan oleh {owner_name} ({owner_email}) ke dalam {group_name} di Terra GIS.\n\n"
            f"Buka aplikasi Terra GIS melalui tautan ini:\n{deeplink_url}\n"
            f"Atau buka langsung via aplikasi: {app_scheme_url}\n\n"
            f"Salam,\nTim Terra GIS"
        )
        html = self._render_base_template("Undangan Paket Bersama", content_html)
        return await self.send_email(to_email, subject, html, text_body)

email_service = EmailService()

