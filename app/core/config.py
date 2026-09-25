from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    PROJECT_NAME: str = "Terra GIS Dashboard API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # JWT Auth Configuration
    SECRET_KEY: str = "TERRA_GIS_SECRET_KEY_SUPER_SECURE_JWT_2026_TOKEN_KEY"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    # Database Configuration
    DATABASE_URL: str = "postgresql+asyncpg://postgres:1234567890@localhost:5436/be-terralium"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "terragis_db"

    # CORS Origins
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "https://terra-gis.web.app",
        "https://core.gis.terralium.tech",
        "https://terralium.tech",
    ]

    # Google Play In-App Billing Configuration
    ANDROID_PACKAGE_NAME: str = "com.terralium.terragis"
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "credentials.json"

    # DOKU Payment Gateway Configuration
    DOKU_CLIENT_ID: str = "BRN-0266-1790264635586"
    DOKU_SECRET_KEY: str = "SK-kDBxrrukEBtlXUHed7Sv"
    DOKU_IS_PRODUCTION: bool = False
    DOKU_API_URL: str = "https://api-sandbox.doku.com"

    # Midtrans Payment Gateway Configuration
    MIDTRANS_MERCHANT_ID: str = "G881325537"
    MIDTRANS_CLIENT_KEY: str = "SB-Mid-client-ne3Orm4LdJA3yygc"
    MIDTRANS_SERVER_KEY: str = "SB-Mid-server-McrTVbIis-Ib-JmB8awVKVG1"
    MIDTRANS_IS_PRODUCTION: bool = False
    MIDTRANS_SNAP_URL: str = "https://app.sandbox.midtrans.com/snap/v1/transactions"

    # SMTP Google Email Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "sdev67035@gmail.com"
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    EMAILS_FROM_EMAIL: str = "sdev67035@gmail.com"
    EMAILS_FROM_NAME: str = "Terra GIS Support"

    # Deep Linking Configuration
    APP_WEB_BASE_URL: str = "https://core.gis.terralium.tech"
    APP_DEEP_LINK_SCHEME: str = "terragis"

settings = Settings()
