from typing import List
from pydantic import BaseModel

class AnalyticsOverviewOut(BaseModel):
    totalSupport: float
    totalCount: int
    currentMonthSupport: float
    averageSupport: float

class MonthlyTrendItem(BaseModel):
    month: str  # e.g., "Jan", "Feb"
    year: int   # e.g., 2026
    totalSupport: float
    totalCount: int

class ProductStatItem(BaseModel):
    productId: str
    label: str
    count: int
    sum: float

class StatusDistributionItem(BaseModel):
    status: str
    count: int
    percentage: float
