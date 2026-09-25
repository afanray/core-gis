import asyncio
import random
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine, Base, AsyncSessionLocal
from app.models import User, Product, Transaction
from app.core.security import get_password_hash

INDONESIAN_NAMES = [
    "Aditya Pratama", "Budi Santoso", "Dewi Lestari", "Eko Prasetyo", "Fitriani",
    "Hendra Wijaya", "Indah Permatasari", "Joko Susilo", "Kartika Sari", "Lukman Hakim",
    "Mega Utami", "Novi Ariyanti", "Oki Rahardjo", "Putri Wulandari", "Rian Hidayat",
    "Siti Aminah", "Taufik Hidayat", "Wahyu Hidayat", "Yudi Setiawan", "Zainal Abidin",
    "Amalia Putri", "Bambang Pamungkas", "Citra Kirana", "Dian Sastrowardoyo", "Ervan Kurniawan",
    "Farhan Halim", "Gita Gutawa", "Herianto", "Ika Nurjanah", "Joni Iskandar"
]

def get_random_name():
    return random.choice(INDONESIAN_NAMES)

def get_email_from_name(name: str):
    clean = name.lower().replace(" ", ".")
    provider = random.choice(["gmail.com", "yahoo.com", "outlook.com", "terragis.io"])
    return f"{clean}@{provider}"

async def seed_database():
    print("🌱 Starting Database Seeding...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # 1. Seed Users (Admins)
        admin = User(
            email="admin@terragis.io",
            name="Super Admin",
            hashed_password=get_password_hash("AdminPassword123!"),
            role="superadmin",
            is_active=True
        )
        staff = User(
            email="staff@terragis.io",
            name="Staff Admin",
            hashed_password=get_password_hash("StaffPassword123!"),
            role="admin",
            is_active=True
        )
        session.add(admin)
        session.add(staff)

        # 2. Seed Products
        products = [
            Product(id="support_10000", title="Dukungan Rp10.000 (Kopi)", description="Dukungan setara secangkir kopi", amount=10000, currency="IDR", is_active=True),
            Product(id="support_25000", title="Dukungan Rp25.000 (Camilan)", description="Dukungan setara camilan tim", amount=25000, currency="IDR", is_active=True),
            Product(id="support_50000", title="Dukungan Rp50.000 (Makan Siang)", description="Dukungan setara makan siang developer", amount=50000, currency="IDR", is_active=True),
            Product(id="support_100000", title="Dukungan Rp100.000 (Premium)", description="Dukungan premium pengembangan fitur GIS", amount=100000, currency="IDR", is_active=True),
        ]
        for p in products:
            session.add(p)

        # 3. Seed Transactions
        transactions = []
        current_id = 1000

        def add_tx(product_id: str, title: str, amount: float, status: str, month: int, day: int):
            nonlocal current_id
            name = get_random_name()
            email = get_email_from_name(name)
            year = 2026
            hour = random.randint(8, 20)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            dt = datetime(year, month + 1, day, hour, minute, second, tzinfo=timezone.utc)

            transactions.append(
                Transaction(
                    id=f"TX-{current_id}",
                    product_id=product_id,
                    name=title,
                    amount=amount,
                    currency="IDR",
                    status=status,
                    user_name=name,
                    user_email=email,
                    order_id=f"GPA.{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(10000,99999)}",
                    purchase_token=f"token_{current_id}_{random.randint(10000,99999)}",
                    created_at=dt
                )
            )
            current_id += 1

        # July distribution (month = 6, i.e., July)
        for _ in range(100):
            add_tx("support_10000", "Dukungan Rp10.000", 10000, "Success", 6, random.randint(1, 22))
        for _ in range(90):
            add_tx("support_25000", "Dukungan Rp25.000", 25000, "Success", 6, random.randint(1, 22))
        for _ in range(10):
            add_tx("support_50000", "Dukungan Rp50.000", 50000, "Success", 6, random.randint(1, 22))
        for _ in range(5):
            add_tx("support_100000", "Dukungan Rp100.000", 100000, "Success", 6, random.randint(1, 22))

        # Other months distribution
        other_months = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11]
        for i in range(530):
            m = other_months[i % len(other_months)]
            add_tx("support_10000", "Dukungan Rp10.000", 10000, "Success", m, random.randint(1, 28))

        for i in range(424):
            m = other_months[i % len(other_months)]
            add_tx("support_25000", "Dukungan Rp25.000", 25000, "Success", m, random.randint(1, 28))

        for i in range(66):
            m = other_months[i % len(other_months)]
            add_tx("support_50000", "Dukungan Rp50.000", 50000, "Success", m, random.randint(1, 28))

        for i in range(20):
            m = other_months[i % len(other_months)]
            add_tx("support_100000", "Dukungan Rp100.000", 100000, "Success", m, random.randint(1, 28))

        # Non-successful transactions
        statuses = ["Pending", "Failed", "Cancelled"]
        counts = [60, 40, 35]
        prods = [
            ("support_10000", "Dukungan Rp10.000", 10000),
            ("support_25000", "Dukungan Rp25.000", 25000),
            ("support_50000", "Dukungan Rp50.000", 50000),
            ("support_100000", "Dukungan Rp100.000", 100000)
        ]

        for s_idx, st in enumerate(statuses):
            c = counts[s_idx]
            for _ in range(c):
                p_id, p_title, p_val = random.choice(prods)
                m = random.randint(0, 11)
                add_tx(p_id, p_title, p_val, st, m, random.randint(1, 28))

        for tx in transactions:
            session.add(tx)

        await session.commit()
        print(f"✅ Seeding Complete! Inserted 2 Admins, 4 Products, and {len(transactions)} Transactions.")

if __name__ == "__main__":
    asyncio.run(seed_database())
