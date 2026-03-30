import uuid
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.patient_profile import PatientProfile
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Fake Redis (dict-based mock)
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = str(value)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = str(value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def close(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# Test Database (SQLite async in-memory)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
async def client(fake_redis) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def seed_user():
    async def _seed(
        phone: str = "13800138000",
        role: UserRole | None = None,
        is_active: bool = True,
    ) -> User:
        async with test_session_factory() as session:
            user = User(phone=phone, role=role, is_active=is_active)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return _seed


@pytest.fixture
def seed_wechat_user():
    async def _seed(
        openid: str = "test_openid_001",
        role: UserRole | None = None,
        is_active: bool = True,
    ) -> User:
        async with test_session_factory() as session:
            user = User(wechat_openid=openid, role=role, is_active=is_active)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return _seed


@pytest.fixture
async def wechat_client(client, seed_wechat_user) -> AsyncClient:
    user = await seed_wechat_user(openid="test_openid_auth")
    token = create_access_token({"sub": str(user.id), "role": None})
    client.headers["Authorization"] = f"Bearer {token}"
    client._test_user = user  # type: ignore[attr-defined]
    return client


@pytest.fixture
async def authenticated_client(client, seed_user) -> AsyncClient:
    user = await seed_user(phone="13800138000", role=UserRole.patient)
    token = create_access_token({"sub": str(user.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"
    client._test_user = user  # type: ignore[attr-defined]
    return client


@pytest.fixture
async def no_role_client(client, seed_user) -> AsyncClient:
    user = await seed_user(phone="13900139000", role=None)
    token = create_access_token({"sub": str(user.id), "role": None})
    client.headers["Authorization"] = f"Bearer {token}"
    client._test_user = user  # type: ignore[attr-defined]
    return client


@pytest.fixture
async def companion_client(client, seed_user) -> AsyncClient:
    user = await seed_user(phone="13700137000", role=UserRole.companion)
    token = create_access_token({"sub": str(user.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"
    client._test_user = user  # type: ignore[attr-defined]
    return client


@pytest.fixture
def seed_patient_profile():
    async def _seed(user_id: uuid.UUID, **kwargs) -> PatientProfile:
        async with test_session_factory() as session:
            profile = PatientProfile(user_id=user_id, **kwargs)
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile

    return _seed


@pytest.fixture
def seed_companion_profile():
    async def _seed(
        user_id: uuid.UUID,
        real_name: str = "测试陪诊师",
        verification_status: VerificationStatus = VerificationStatus.verified,
        **kwargs,
    ) -> CompanionProfile:
        async with test_session_factory() as session:
            profile = CompanionProfile(
                user_id=user_id,
                real_name=real_name,
                verification_status=verification_status,
                **kwargs,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile

    return _seed


@pytest.fixture
def seed_hospital():
    async def _seed(
        name: str = "测试医院",
        address: str = "北京市测试区",
        level: str = "三甲",
        **kwargs,
    ) -> Hospital:
        async with test_session_factory() as session:
            hospital = Hospital(name=name, address=address, level=level, **kwargs)
            session.add(hospital)
            await session.commit()
            await session.refresh(hospital)
            return hospital

    return _seed


@pytest.fixture
def seed_order():
    async def _seed(
        patient_id: uuid.UUID,
        hospital_id: uuid.UUID,
        *,
        companion_id: uuid.UUID | None = None,
        service_type: ServiceType = ServiceType.full_accompany,
        status: OrderStatus = OrderStatus.created,
        **kwargs,
    ) -> Order:
        async with test_session_factory() as session:
            order = Order(
                order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
                patient_id=patient_id,
                hospital_id=hospital_id,
                companion_id=companion_id,
                service_type=service_type,
                status=status,
                appointment_date=kwargs.pop("appointment_date", "2026-04-15"),
                appointment_time=kwargs.pop("appointment_time", "09:00"),
                price=kwargs.pop("price", 299.0),
                **kwargs,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            return order

    return _seed
