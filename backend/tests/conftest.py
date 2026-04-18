import uuid
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.chat_message import ChatMessage, MessageType
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.device_token import DeviceToken
from app.models.hospital import Hospital
from app.models.notification import Notification, NotificationType
from app.models.order import Order, OrderStatus, ServiceType
from app.models.patient_profile import PatientProfile
from app.models.payment import Payment
from app.models.review import Review
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Fake Redis (dict-based mock)
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = str(value)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = str(value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._zsets.pop(key, None)

    async def close(self) -> None:
        self._store.clear()
        self._zsets.clear()

    async def ping(self) -> bool:
        return True

    # --- minimal extras used by SMSRateLimiter / similar -----------------
    async def incr(self, key: str) -> int:
        try:
            current = int(self._store.get(key, "0"))
        except (TypeError, ValueError):
            current = 0
        current += 1
        self._store[key] = str(current)
        return current

    async def expire(self, key: str, ttl: int) -> bool:
        # TTL not enforced in tests; just signal success if key exists.
        return key in self._store or key in self._zsets

    async def ttl(self, key: str) -> int:
        # Tests don't depend on the actual TTL countdown.
        return 60 if key in self._store else -2

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        zset = self._zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = float(score)
        return added

    async def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        zset = self._zsets.get(key)
        if not zset:
            return 0
        to_remove = [m for m, s in zset.items() if min_score <= s <= max_score]
        for m in to_remove:
            zset.pop(m, None)
        return len(to_remove)


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
            role_val = role.value if isinstance(role, UserRole) else role
            roles = role_val if role else None
            user = User(phone=phone, role=role, roles=roles, is_active=is_active)
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
            role_val = role.value if isinstance(role, UserRole) else role
            roles = role_val if role else None
            user = User(wechat_openid=openid, role=role, roles=roles, is_active=is_active)
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
async def admin_client(client, seed_user) -> AsyncClient:
    """Client authenticated as an admin user."""
    async with test_session_factory() as session:
        user = User(phone="13600136000", roles="admin,patient", is_active=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": "admin"})
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


@pytest.fixture
def seed_payment():
    async def _seed(
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        amount: float = 299.0,
        payment_type: str = "pay",
        status: str = "success",
    ) -> Payment:
        async with test_session_factory() as session:
            payment = Payment(
                order_id=order_id,
                user_id=user_id,
                amount=amount,
                payment_type=payment_type,
                status=status,
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            return payment

    return _seed


@pytest.fixture
def seed_review():
    async def _seed(
        order_id: uuid.UUID,
        patient_id: uuid.UUID,
        companion_id: uuid.UUID,
        *,
        rating: int = 5,
        content: str = "很好的服务",
        **kwargs,
    ) -> Review:
        async with test_session_factory() as session:
            review = Review(
                order_id=order_id,
                patient_id=patient_id,
                companion_id=companion_id,
                rating=rating,
                content=content,
                **kwargs,
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            return review

    return _seed


@pytest.fixture
def seed_chat_message():
    async def _seed(
        order_id: uuid.UUID,
        sender_id: uuid.UUID,
        *,
        content: str = "Hello",
        msg_type: MessageType = MessageType.text,
        **kwargs,
    ) -> ChatMessage:
        async with test_session_factory() as session:
            message = ChatMessage(
                order_id=order_id,
                sender_id=sender_id,
                type=msg_type,
                content=content,
                **kwargs,
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    return _seed


@pytest.fixture
def seed_notification():
    async def _seed(
        user_id: uuid.UUID,
        *,
        type: NotificationType = NotificationType.system,
        title: str = "Test Notification",
        body: str = "Test body",
        **kwargs,
    ) -> Notification:
        async with test_session_factory() as session:
            notification = Notification(
                user_id=user_id,
                type=type,
                title=title,
                body=body,
                **kwargs,
            )
            session.add(notification)
            await session.commit()
            await session.refresh(notification)
            return notification

    return _seed


@pytest.fixture
def seed_device_token():
    async def _seed(
        user_id: uuid.UUID,
        *,
        token: str = "test_device_token_001",
        device_type: str = "ios",
        **kwargs,
    ) -> DeviceToken:
        async with test_session_factory() as session:
            device = DeviceToken(
                user_id=user_id,
                token=token,
                device_type=device_type,
                **kwargs,
            )
            session.add(device)
            await session.commit()
            await session.refresh(device)
            return device

    return _seed
