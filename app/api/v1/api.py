from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, 
    transactions, 
    analytics, 
    products, 
    admins, 
    health,
    webhooks,
    payments,
    group
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(admins.router, prefix="/admins", tags=["Admins Management"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks & Real-Time Developer Notifications"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments & Gateway"])
api_router.include_router(group.router, prefix="/group", tags=["Subscription Group (Paket Bersama)"])


