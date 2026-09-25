from typing import Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.analytics import (
    AnalyticsOverviewOut, 
    MonthlyTrendItem, 
    ProductStatItem, 
    StatusDistributionItem
)
from app.schemas.common import BaseResponse
from app.api.deps import get_current_active_admin
from app.models.user import User
from app.services.analytics_service import analytics_service

router = APIRouter()

@router.get("/overview", response_model=BaseResponse[AnalyticsOverviewOut], summary="Get Analytics Overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    data = await analytics_service.get_overview(db)
    return BaseResponse(data=AnalyticsOverviewOut(**data))

@router.get("/monthly", response_model=BaseResponse[List[MonthlyTrendItem]], summary="Get Monthly Support Trends")
async def get_monthly_trends(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    data = await analytics_service.get_monthly_trends(db)
    return BaseResponse(data=[MonthlyTrendItem(**item) for item in data])

@router.get("/products", response_model=BaseResponse[List[ProductStatItem]], summary="Get Product Breakdown Stats")
async def get_product_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    data = await analytics_service.get_product_stats(db)
    return BaseResponse(data=[ProductStatItem(**item) for item in data])

@router.get("/status-distribution", response_model=BaseResponse[List[StatusDistributionItem]], summary="Get Status Distribution")
async def get_status_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
) -> Any:
    data = await analytics_service.get_status_distribution(db)
    return BaseResponse(data=[StatusDistributionItem(**item) for item in data])
