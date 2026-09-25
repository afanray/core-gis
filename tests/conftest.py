import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.models import User, Product, Transaction
from app.core.security import get_password_hash, create_access_token

# Use an in-memory SQLite database for test isolation
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True
)

TestAsyncSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        # Seed test superadmin
        superadmin = User(
            id="test-superadmin-id",
            email="admin@terragis.io",
            name="Super Admin",
            hashed_password=get_password_hash("AdminPassword123!"),
            role="superadmin",
            is_active=True,
            is_email_verified=True
        )
        # Seed test admin
        staff = User(
            id="test-admin-id",
            email="staff@terragis.io",
            name="Staff Admin",
            hashed_password=get_password_hash("StaffPassword123!"),
            role="admin",
            is_active=True,
            is_email_verified=True
        )
        # Seed test inactive user
        inactive = User(
            id="test-inactive-id",
            email="inactive@terragis.io",
            name="Inactive User",
            hashed_password=get_password_hash("Password123!"),
            role="admin",
            is_active=False
        )
        session.add_all([superadmin, staff, inactive])

        # Seed test products
        product = Product(
            id="support_10000",
            title="Dukungan Rp10.000 (Kopi)",
            description="Dukungan Kopi",
            amount=10000,
            currency="IDR",
            is_active=True
        )
        trial_product = Product(
            id="terragis_sub_trial",
            title="Uji Coba Gratis",
            description="Akses penuh seluruh fitur Terra GIS selama masa uji coba gratis",
            amount=0.0,
            currency="IDR",
            billing_period="trial",
            trial_days=7,
            is_active=True
        )
        session.add_all([product, trial_product])

        # Seed test transaction
        tx = Transaction(
            id="TX-TEST-001",
            product_id="support_10000",
            name="Dukungan Rp10.000",
            amount=10000,
            currency="IDR",
            status="Success",
            user_name="Budi Santoso",
            user_email="budi.santoso@gmail.com"
        )
        session.add(tx)

        await session.commit()
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()

@pytest.fixture
def superadmin_token():
    return create_access_token(subject="test-superadmin-id")

@pytest.fixture
def admin_token():
    return create_access_token(subject="test-admin-id")

@pytest.fixture
def auth_headers(superadmin_token):
    return {"Authorization": f"Bearer {superadmin_token}"}
