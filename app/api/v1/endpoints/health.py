from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.common import BaseResponse

router = APIRouter()

@router.get("/health", response_model=BaseResponse[dict], summary="System Health Check")
async def health_check(db: AsyncSession = Depends(get_db)):
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return BaseResponse(
        data={
            "status": "online" if db_status == "ok" else "degraded",
            "database": db_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "Terra GIS Dashboard Backend API",
            "version": "1.0.0"
        }
    )
