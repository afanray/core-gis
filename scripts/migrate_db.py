import asyncio
import sys
import os
from sqlalchemy import text

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine, AsyncSessionLocal, Base
import app.models
from app.models import Product
from app.crud.crud_product import crud_product

async def migrate():
    print("🔄 Running Database Migrations...")
    async with engine.begin() as conn:
        # Create all tables from metadata (including user_subscriptions & login_histories)
        await conn.run_sync(Base.metadata.create_all)

        # Alter users table: ensure login_type and is_email_verified exist, remove duplicate subscription columns
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS login_type VARCHAR DEFAULT 'email';"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN DEFAULT TRUE;"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS subscription_status;"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS trial_ends_at;"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS subscription_ends_at;"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS active_plan_id;"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS purchase_token;"))

        # Alter user_subscriptions table: ensure group_id exists, drop unique user_id constraint to allow 1-to-many (active + queued)
        await conn.execute(text("ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS group_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE user_subscriptions DROP CONSTRAINT IF EXISTS uq_user_sub_user_id;"))
        await conn.execute(text("DROP INDEX IF EXISTS uq_user_sub_user_id;"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_sub_status ON user_subscriptions (user_id, status);"))

        # Alter products table
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS billing_period VARCHAR DEFAULT 'monthly';"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS trial_days INTEGER DEFAULT 7;"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS google_play_product_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS original_amount FLOAT;"))
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS discount_percent INTEGER DEFAULT 0;"))

    print("✅ Schema Columns & Tables Migrated Successfully!")

    # Seed/Update exact 3 subscription products requested
    async with AsyncSessionLocal() as session:
        sub_products = [
            {
                "id": "terragis_sub_monthly",
                "title": "Paket Perbulan",
                "description": "Akses penuh fitur Terra GIS per bulan dengan promo 7 hari uji coba gratis",
                "amount": 49000.0,
                "original_amount": 49000.0,
                "discount_percent": 0,
                "currency": "IDR",
                "billing_period": "monthly",
                "trial_days": 7,
                "google_play_product_id": "terragis_sub_monthly",
                "is_active": True
            },
            {
                "id": "terragis_sub_yearly",
                "title": "Paket Pertahun",
                "description": "Akses penuh fitur Terra GIS per tahun (Promo Hemat 74%)",
                "amount": 150000.0,
                "original_amount": 588000.0,
                "discount_percent": 74,
                "currency": "IDR",
                "billing_period": "yearly",
                "trial_days": 7,
                "google_play_product_id": "terragis_sub_yearly",
                "is_active": True
            },
            {
                "id": "terragis_sub_lifetime",
                "title": "Paket Selamanya",
                "description": "Sekali bayar untuk akses seumur hidup tanpa batas (Promo Hemat 70%)",
                "amount": 350000.0,
                "original_amount": 1200000.0,
                "discount_percent": 70,
                "currency": "IDR",
                "billing_period": "lifetime",
                "trial_days": 7,
                "google_play_product_id": "terragis_sub_lifetime",
                "is_active": True
            },
            {
                "id": "terragis_sub_group",
                "title": "Paket Bersama (5 User)",
                "description": "Langganan 1 tahun untuk 5 pengguna (1 Akun Utama + 4 Anggota Tim). Undang anggota menggunakan email.",
                "amount": 500000.0,
                "original_amount": 750000.0,
                "discount_percent": 33,
                "currency": "IDR",
                "billing_period": "group",
                "trial_days": 7,
                "google_play_product_id": "terragis_sub_group",
                "is_active": True
            },
            {
                "id": "terragis_sub_trial",
                "title": "Uji Coba Gratis",
                "description": "Akses penuh seluruh fitur Terra GIS selama masa uji coba gratis",
                "amount": 0.0,
                "original_amount": 0.0,
                "discount_percent": 0,
                "currency": "IDR",
                "billing_period": "trial",
                "trial_days": 7,
                "google_play_product_id": None,
                "is_active": True
            }
        ]

        for p_data in sub_products:
            existing = await crud_product.get_by_id(session, id=p_data["id"])
            if existing:
                existing.title = p_data["title"]
                existing.description = p_data["description"]
                existing.amount = p_data["amount"]
                existing.original_amount = p_data["original_amount"]
                existing.discount_percent = p_data["discount_percent"]
                existing.billing_period = p_data["billing_period"]
                existing.trial_days = p_data["trial_days"]
                existing.google_play_product_id = p_data["google_play_product_id"]
                existing.is_active = p_data["is_active"]
                print(f"🔄 Updated Subscription Product: {p_data['title']} (Rp {p_data['amount']:,.0f})")
            else:
                p = Product(
                    id=p_data["id"],
                    title=p_data["title"],
                    description=p_data["description"],
                    amount=p_data["amount"],
                    original_amount=p_data["original_amount"],
                    discount_percent=p_data["discount_percent"],
                    currency=p_data["currency"],
                    billing_period=p_data["billing_period"],
                    trial_days=p_data["trial_days"],
                    google_play_product_id=p_data["google_play_product_id"],
                    is_active=p_data["is_active"]
                )
                session.add(p)
                print(f"➕ Created Subscription Product: {p_data['title']} (Rp {p_data['amount']:,.0f})")

        await session.commit()
    print("✅ Subscription Products Seeded & Updated Successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
