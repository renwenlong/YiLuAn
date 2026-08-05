# ruff: noqa: I001 -- network guard must import before application modules.
import uuid
from typing import AsyncGenerator

# S3-OPS-TEST-NO-OUTBOUND-NETWORK-GUARD:
# Import before application modules so test collection/import, session fixtures
# and test bodies all default to zero real outbound network. Import has the
# deliberate side effect of installing the process-wide socket/DNS guard.
from tests import network_guard as _network_guard

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.rate_limit import limiter as _rate_limiter
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

# Re-export hooks instead of loading the already-imported module as a plugin;
# this keeps early installation without pytest's duplicate-import warning.
pytest_configure = _network_guard.pytest_configure
pytest_runtest_protocol = _network_guard.pytest_runtest_protocol


# ---------------------------------------------------------------------------
# Fake Redis (dict-based mock)
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._sets: dict[str, set[str]] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = str(value)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = str(value)

    async def delete(self, *keys: str) -> int:
        # Real redis-py accepts varargs; tests previously only passed one.
        removed = 0
        for key in keys:
            if key in self._store:
                self._store.pop(key, None)
                removed += 1
            if key in self._zsets:
                self._zsets.pop(key, None)
                removed += 1
            if key in self._sets:
                self._sets.pop(key, None)
                removed += 1
        return removed

    async def close(self) -> None:
        self._store.clear()
        self._zsets.clear()
        self._sets.clear()

    # redis>=5 renamed close → aclose for the async client. Mirror it so
    # FastAPI lifespan shutdown (which calls app.state.redis.aclose()) works.
    async def aclose(self) -> None:
        await self.close()

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

    async def zrangebyscore(
        self,
        key: str,
        min_score: float,
        max_score: float,
        withscores: bool = False,
    ) -> list:
        zset = self._zsets.get(key)
        if not zset:
            return []
        items = [(m, s) for m, s in zset.items() if min_score <= s <= max_score]
        items.sort(key=lambda kv: kv[1])
        if withscores:
            return items
        return [m for m, _ in items]

    # --- SET commands (refresh-token jti whitelist) ----------------------
    async def sadd(self, key: str, *members: str) -> int:
        s = self._sets.setdefault(key, set())
        added = 0
        for m in members:
            if m not in s:
                s.add(m)
                added += 1
        return added

    async def srem(self, key: str, *members: str) -> int:
        s = self._sets.get(key)
        if not s:
            return 0
        removed = 0
        for m in members:
            if m in s:
                s.discard(m)
                removed += 1
        if not s:
            self._sets.pop(key, None)
        return removed

    async def sismember(self, key: str, member: str) -> bool:
        return member in self._sets.get(key, set())

    async def smembers(self, key: str):
        return set(self._sets.get(key, set()))

    # --- pipeline (executed sequentially) --------------------------------
    def pipeline(self):
        return _FakeRedisPipeline(self)


class _FakeRedisPipeline:
    """Best-effort sync-then-async pipeline shim.

    redis-py's pipeline queues commands synchronously and awaits the whole
    batch on ``execute()``. We mirror that surface by recording (method,
    args, kwargs) tuples and replaying them via ``getattr`` on the underlying
    FakeRedis instance.
    """

    def __init__(self, client: "FakeRedis"):
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def _record(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return _record

    async def execute(self):
        results = []
        for name, args, kwargs in self._ops:
            fn = getattr(self._client, name)
            results.append(await fn(*args, **kwargs))
        self._ops.clear()
        return results


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
def _current_alembic_head() -> str | None:
    try:
        from pathlib import Path as _P

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg_paths = [_P("alembic.ini"), _P(__file__).resolve().parents[1] / "alembic.ini"]
        cfg_path = next((p for p in cfg_paths if p.exists()), None)
        if cfg_path is None:
            return None
        return ScriptDirectory.from_config(Config(str(cfg_path))).get_heads()[0]
    except Exception:
        return None


_ALEMBIC_HEAD = _current_alembic_head()


@pytest.fixture(autouse=True)
async def setup_database():
    from sqlalchemy import text as _text

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Mirror what `alembic upgrade head` would leave in a real DB so the
        # /readiness alembic check passes against the SQLite test DB.
        if _ALEMBIC_HEAD:
            await conn.execute(
                _text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(64) PRIMARY KEY)"
                )
            )
            await conn.execute(_text("DELETE FROM alembic_version"))
            await conn.execute(
                _text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": _ALEMBIC_HEAD},
            )
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def _seed_service_packages(setup_database, request):
    """S2-REQ-003-P3: 所有 test 需要 service_packages 档位 (create_order 会查).

    跳过自带 service_packages CRUD 测试文件以免 code unique 冲突。
    跳过 PG_SMOKE=1 (独立 PG 路径 + 不走 SQLite test_session_factory)。
    """
    import os
    if os.environ.get("PG_SMOKE") == "1":
        yield
        return
    skip_files = {
        "test_service_package_p1.py",
        "test_admin_service_packages.py",
        "test_models_pg_smoke.py",
    }
    if request.node.fspath.basename in skip_files:
        yield
        return
    from decimal import Decimal

    from app.models.service_package import ServicePackage as _SP
    async with test_session_factory() as session:
        for code, name, price, sort in [
            ("full_accompany", "全程陪诊", Decimal("299.00"), 10),
            ("half_accompany", "半程陪诊", Decimal("199.00"), 20),
            ("errand", "跑腿代办", Decimal("149.00"), 30),
        ]:
            session.add(_SP(
                code=code, name=name, price=price,
                sort_order=sort, is_active=True,
            ))
        await session.commit()
    yield


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture(autouse=True)
def _set_contract_pseudonym_salt(monkeypatch):
    """S3-DEV-001 / ADR-0046 §3.2: contract hash compute requires a salt.

    Production must set ``CONTRACT_PSEUDONYM_SALT`` (high-entropy random).
    Tests need a deterministic salt so any code path that calls
    ``compute_patient_pseudonym_hash`` (e.g. via accept_order →
    ContractService.request_generation) does not raise
    ``ContractPseudonymSaltMissingError`` and breaks unrelated tests.
    """
    test_salt = "test-salt-not-for-production-2cQ8mP4xJ9zR5"
    monkeypatch.setenv("CONTRACT_PSEUDONYM_SALT", test_salt)
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "contract_pseudonym_salt", test_salt)


@pytest.fixture(autouse=True)
def _disable_prompt_versions_validator(monkeypatch):
    """S3-DEV-002-PROMPT-VERSIONING AC#3 test isolation.

    The production lifespan runs ``validate_prompt_versions_on_startup``
    (DB ↔ git source-of-truth check).  Most tests use ``Base.metadata.create_all``
    on an in-memory SQLite and seed no ``prompt_versions`` rows, which would
    trivially pass.  But tests that seed rows for unrelated assertions
    (e.g. PreparationPackage FK fixture) would trip the validator the
    moment they boot via ``TestClient`` (lifespan runs).  Default-off in
    tests, opt-in via dedicated fixture in startup-validator suites.
    """
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "prompt_versions_validate_on_startup", False)


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """W1-S3: route-level @limiter.limit decorators are now in production code
    paths (orders writes, auth refresh/login). The slowapi Limiter is stateful
    and shared across requests; in the test suite all calls come from the same
    ASGI client IP, which would trip 30/min within a few hundred-call tests.

    We disable the limiter globally for the suite and re-enable it explicitly
    in tests that assert rate-limit behaviour.
    """
    prev = _rate_limiter.enabled
    _rate_limiter.enabled = False
    try:
        yield
    finally:
        _rate_limiter.enabled = prev


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
async def companion_client(client, seed_user, seed_companion_profile) -> AsyncClient:
    user = await seed_user(phone="13700137000", role=UserRole.companion)
    # 默认为陪诊师 seed 一条 verified profile，使接单/start 等需要
    # verified 审核的流程在测试中默认可走。seed_companion_profile 是 idempotent 的，
    # 测试内部再次调用也不会冲突。需要测试未审核的场景，使用专门的测试方法或 token 启新用户。
    await seed_companion_profile(user_id=user.id)
    token = create_access_token({"sub": str(user.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"
    client._test_user = user  # type: ignore[attr-defined]
    return client


@pytest.fixture
async def verified_companion_client(client, seed_user, seed_companion_profile) -> AsyncClient:
    """Alias/explicit form of ``companion_client`` for readability."""
    user = await seed_user(phone="13700137000", role=UserRole.companion)
    await seed_companion_profile(user_id=user.id)
    token = create_access_token({"sub": str(user.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"
    client._test_user = user  # type: ignore[attr-defined]
    return client


@pytest.fixture
async def admin_client(client, seed_user) -> AsyncClient:
    """Client authenticated as an admin user.

    Sends both a JWT (legacy fixture support) and the ``X-Admin-Token``
    header used by the new B4 admin endpoints.
    """
    async with test_session_factory() as session:
        user = User(phone="13600136000", roles="admin,patient", is_active=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": "admin"})
    client.headers["Authorization"] = f"Bearer {token}"
    client.headers["X-Admin-Token"] = "dev-admin-token"
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
            # Idempotent: if a profile already exists for this user, reuse it and
            # merge in the requested fields. This lets fixtures that pre-seed a
            # profile (e.g. companion_client) coexist with individual tests that
            # call seed_companion_profile explicitly.
            from sqlalchemy import select as _select
            existing = (
                await session.execute(
                    _select(CompanionProfile).where(CompanionProfile.user_id == user_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.real_name = real_name
                existing.verification_status = verification_status
                for k, v in kwargs.items():
                    setattr(existing, k, v)
                await session.commit()
                await session.refresh(existing)
                return existing
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
                patient_name=kwargs.pop("patient_name", "测试患者"),
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
