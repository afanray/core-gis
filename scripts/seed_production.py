import asyncio
import os
import sys
import uuid
from sqlalchemy import select

# Ensure parent directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine, AsyncSessionLocal, Base
from app.models.user import User
from app.models.product import Product
from app.core.security import get_password_hash

async def seed_production():
    print("=" * 60)
    print("🌱 [Terra GIS] Memulai Seeding Default Database Production...")
    print("=" * 60)

    # 1. Pastikan semua tabel sudah dibuat di database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # ==========================================
        # 1. SEED DEFAULT ADMIN & SUPERADMIN USERS
        # ==========================================
        print("\n👤 Menyiapkan Akun Default Superadmin & Admin...")
        
        default_superadmin_email = os.getenv("ADMIN_EMAIL", "admin@terragis.io").strip()
        default_superadmin_pass = os.getenv("ADMIN_PASSWORD", "AdminPassword123!").strip()
        
        default_staff_email = os.getenv("STAFF_EMAIL", "staff@terragis.io").strip()
        default_staff_pass = os.getenv("STAFF_PASSWORD", "StaffPassword123!").strip()

        users_to_seed = [
            {
                "email": default_superadmin_email,
                "name": "Super Admin Terra GIS",
                "password": default_superadmin_pass,
                "role": "superadmin"
            },
            {
                "email": default_staff_email,
                "name": "Staff Admin Terra GIS",
                "password": default_staff_pass,
                "role": "admin"
            }
        ]

        for u in users_to_seed:
            result = await session.execute(select(User).where(User.email == u["email"]))
            existing_user = result.scalars().first()

            if existing_user:
                existing_user.role = u["role"]
                existing_user.is_active = True
                existing_user.is_email_verified = True
                existing_user.hashed_password = get_password_hash(u["password"])
                print(f"  🔄 Diperbarui: {u['role'].upper()} -> {u['email']}")
            else:
                new_user = User(
                    id=str(uuid.uuid4()),
                    email=u["email"],
                    name=u["name"],
                    hashed_password=get_password_hash(u["password"]),
                    role=u["role"],
                    is_active=True,
                    login_type="email",
                    is_email_verified=True
                )
                session.add(new_user)
                print(f"  ➕ Dibuat Baru: {u['role'].upper()} -> {u['email']}")

        # ==========================================
        # 2. SEED DEFAULT SUBSCRIPTION PRODUCTS
        # ==========================================
        print("\n📦 Menyiapkan Paket Produk Langganan (Subscription Products)...")

        products_data = [
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

        for p_data in products_data:
            result = await session.execute(select(Product).where(Product.id == p_data["id"]))
            existing_product = result.scalars().first()

            if existing_product:
                existing_product.title = p_data["title"]
                existing_product.description = p_data["description"]
                existing_product.amount = p_data["amount"]
                existing_product.original_amount = p_data["original_amount"]
                existing_product.discount_percent = p_data["discount_percent"]
                existing_product.currency = p_data["currency"]
                existing_product.billing_period = p_data["billing_period"]
                existing_product.trial_days = p_data["trial_days"]
                existing_product.google_play_product_id = p_data["google_play_product_id"]
                existing_product.is_active = p_data["is_active"]
                print(f"  🔄 Diperbarui: {p_data['title']} (Rp {p_data['amount']:,.0f})")
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
                print(f"  ➕ Dibuat Baru: {p_data['title']} (Rp {p_data['amount']:,.0f})")

        await session.commit()

    print("\n" + "=" * 60)
    print("✅ SEEDING PRODUCTION SELESAI DENGAN SUKSES!")
    print("=" * 60)
    print("\n📌 KREDENSIAL LOGIN DEFAULT:")
    print("------------------------------------------------------------")
    print(f"👑 Superadmin : {default_superadmin_email}")
    print(f"🔑 Password   : {default_superadmin_pass}")
    print("------------------------------------------------------------")
    print(f"🛡️  Staff Admin: {default_staff_email}")
    print(f"🔑 Password   : {default_staff_pass}")
    print("------------------------------------------------------------")
    print("💡 Catatan: Harap ganti password default setelah login pertama kali.\n")

if __name__ == "__main__":
    asyncio.run(seed_production())
