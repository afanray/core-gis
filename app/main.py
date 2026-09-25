import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

from app.core.config import settings
from app.core.database import engine, Base
from app.core.error_handlers import register_exception_handlers
from app.api.v1.api import api_router

tags_metadata = [
    {
        "name": "Health",
        "description": "System health, database connectivity, and uptime metrics.",
    },
    {
        "name": "Authentication",
        "description": "OAuth2 JWT Login, profile retrieval (`/me`), token refresh, and session logout.",
    },
    {
        "name": "Analytics",
        "description": "Aggregated revenue stats, monthly performance trends, product distribution, and status metrics.",
    },
    {
        "name": "Transactions",
        "description": "Full transaction management: paginated lists, status/date filtering, detail lookup, status updates, creation, deletion, and CSV export.",
    },
    {
        "name": "Products",
        "description": "CRUD management for donation product packages (10k, 25k, 50k, 100k, custom).",
    },
    {
        "name": "Admins Management",
        "description": "Role-Based Access Control (RBAC) and administrator account management (Superadmin only).",
    },
]

from sqlalchemy import text
import app.models  # ensure models are loaded

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables & missing columns on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        migration_queries = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR DEFAULT 'trial';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMP WITH TIME ZONE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_plan_id VARCHAR;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS purchase_token VARCHAR;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_type VARCHAR DEFAULT 'email';",
        ]
        for q in migration_queries:
            try:
                await conn.execute(text(q))
            except Exception:
                pass
    yield
    # Cleanup on shutdown
    await engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
# 🌍 Terra GIS Dashboard Backend API

Welcome to the **Terra GIS Dashboard Backend API documentation**.

### Key Features:
* 🔐 **OAuth2 JWT Authentication** with Role-Based Access Control (`superadmin`, `admin`, `viewer`).
* 📊 **High-Performance Analytics** with indexed queries and TTL caching.
* 💳 **Donation & Payment Management** supporting full transaction log filtering, status updates, and CSV exports.
* 🛠 **Standardized Error Responses**: All non-2xx responses deliver structured JSON error objects.
* 🚀 **Async Processing**: Built with FastAPI, SQLAlchemy 2.0 Async, and Pydantic v2.
    """,
    openapi_tags=tags_metadata,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Register CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register GZip Compression Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Register Custom Exception Handlers for strict error contract
register_exception_handlers(app)

# Include V1 API Routes
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "Welcome to Terra GIS Dashboard API. Visit /docs for OpenAPI documentation.",
        "docs": "/docs",
        "redoc": "/redoc"
    }
