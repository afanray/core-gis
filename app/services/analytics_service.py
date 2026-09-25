import time
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.crud_analytics import crud_analytics

class AnalyticsService:
    def __init__(self, cache_ttl_seconds: int = 15):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def _get_cache(self, key: str) -> Optional[Any]:
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = (time.time(), data)

    def invalidate_cache(self):
        self._cache.clear()

    async def get_overview(self, db: AsyncSession, use_cache: bool = True) -> Dict[str, Any]:
        if use_cache:
            cached = self._get_cache("overview")
            if cached:
                return cached

        data = await crud_analytics.get_overview(db)
        self._set_cache("overview", data)
        return data

    async def get_monthly_trends(self, db: AsyncSession, use_cache: bool = True):
        if use_cache:
            cached = self._get_cache("monthly_trends")
            if cached:
                return cached

        data = await crud_analytics.get_monthly_trends(db)
        self._set_cache("monthly_trends", data)
        return data

    async def get_product_stats(self, db: AsyncSession, use_cache: bool = True):
        if use_cache:
            cached = self._get_cache("product_stats")
            if cached:
                return cached

        data = await crud_analytics.get_product_stats(db)
        self._set_cache("product_stats", data)
        return data

    async def get_status_distribution(self, db: AsyncSession, use_cache: bool = True):
        if use_cache:
            cached = self._get_cache("status_distribution")
            if cached:
                return cached

        data = await crud_analytics.get_status_distribution(db)
        self._set_cache("status_distribution", data)
        return data

analytics_service = AnalyticsService()
