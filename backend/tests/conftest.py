import uuid
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
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
