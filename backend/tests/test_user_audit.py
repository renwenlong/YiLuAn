"""S3-DEV-001-USER-AUDIT tests — UserAuditService 5 acceptance scenarios.

ADR-0047 §3.5 acceptance:
1) migration + 2 indexes (verified via Base.metadata.create_all)
2) 3 actions 全落库 (contract_acceptance_clicked / contract_viewed / insurance_terms_viewed)
3) user_agent + client_ip 必填, 反代提取真实 IP
4) admin 操作不进此表 (走 AdminAuditService)
5) 单测: 勾选写库 + 缺失 IP 兜底 (missing_ip=True)
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.admin_audit_log import AdminAuditLog
from app.models.user_audit_log import UserAuditAction, UserAuditLog
from app.services.user_audit import (
    FALLBACK_CLIENT_IP,
    FALLBACK_USER_AGENT,
    UserAuditService,
    extract_real_client_ip,
    extract_user_agent,
)

# ---------------------------------------------------------------------------
# Isolated in-memory SQLite engine (avoid conftest entanglement)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """独立 in-memory SQLite session, 与 conftest 全局 fixture 物理隔离"""
    # 全部 model 必须在 Base.metadata.create_all 前已 import (avoid 表缺失)
    import app.models  # noqa: F401  (register all models with Base)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()

    await engine.dispose()



# ---------------------------------------------------------------------------
# Fake Request helper (FastAPI Request 构造较重 — 用 Mock 模拟最小 API)
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, host: str | None = None):
        self.host = host


class _FakeRequest:
    """FastAPI Request 最小 mock — 只暴露 user_audit.py 用到的 headers + client"""

    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        client_host: str | None = None,
    ):
        self.headers = headers or {}
        self.client = _FakeClient(client_host) if client_host is not None else None


# ---------------------------------------------------------------------------
# Tests: IP 提取优先级 (X-Forwarded-For > X-Real-IP > request.client > fallback)
# ---------------------------------------------------------------------------


class TestExtractRealClientIP:
    """ADR-0047 §3.5 acceptance #3: 反代提取真实 IP, 4 级 fallback"""

    def test_xff_first_priority(self):
        """X-Forwarded-For 首个 IP 优先 (反代 chain 左起)"""
        req = _FakeRequest(
            headers={"X-Forwarded-For": "203.0.113.42, 10.0.0.1, 192.168.1.1"},
            client_host="127.0.0.1",
        )
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "203.0.113.42"
        assert missing is False

    def test_xff_single_ip_no_comma(self):
        """X-Forwarded-For 单 IP (无逗号 chain)"""
        req = _FakeRequest(
            headers={"X-Forwarded-For": "198.51.100.7"},
            client_host="127.0.0.1",
        )
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "198.51.100.7"
        assert missing is False

    def test_xri_fallback_when_no_xff(self):
        """X-Real-IP 作为 X-Forwarded-For 缺失时的 fallback"""
        req = _FakeRequest(
            headers={"X-Real-IP": "203.0.113.99"},
            client_host="127.0.0.1",
        )
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "203.0.113.99"
        assert missing is False

    def test_request_client_when_no_proxy_headers(self):
        """无反代 header 时取 request.client.host (直连场景)"""
        req = _FakeRequest(client_host="192.0.2.50")
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "192.0.2.50"
        assert missing is False

    def test_fallback_when_no_client_no_headers(self):
        """全缺失 → 写 0.0.0.0 + missing_ip=True (PIPL 取证仍必须写库)"""
        req = _FakeRequest()
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == FALLBACK_CLIENT_IP
        assert ip == "0.0.0.0"
        assert missing is True

    def test_empty_xff_falls_through_to_xri(self):
        """X-Forwarded-For 空值不算 (空字符串)"""
        req = _FakeRequest(
            headers={"X-Forwarded-For": "", "X-Real-IP": "203.0.113.1"},
        )
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "203.0.113.1"
        assert missing is False

    def test_xff_with_whitespace_around_first(self):
        """X-Forwarded-For 首个 IP 带空格 → strip 处理"""
        req = _FakeRequest(headers={"X-Forwarded-For": "  198.51.100.7  , 10.0.0.1"})
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "198.51.100.7"
        assert missing is False

    def test_ipv6_supported(self):
        """支持 IPv6 (45 字符列 String 足够)"""
        req = _FakeRequest(
            headers={"X-Forwarded-For": "2001:db8:85a3::8a2e:370:7334"},
        )
        ip, missing = extract_real_client_ip(req)  # type: ignore[arg-type]
        assert ip == "2001:db8:85a3::8a2e:370:7334"
        assert missing is False


class TestExtractUserAgent:
    def test_normal_ua(self):
        req = _FakeRequest(headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        assert extract_user_agent(req) == "Mozilla/5.0 (compatible)"  # type: ignore[arg-type]

    def test_missing_ua_fallback(self):
        req = _FakeRequest()
        assert extract_user_agent(req) == FALLBACK_USER_AGENT  # type: ignore[arg-type]
        assert extract_user_agent(req) == "unknown"  # type: ignore[arg-type]

    def test_empty_ua_fallback(self):
        req = _FakeRequest(headers={"User-Agent": "   "})
        assert extract_user_agent(req) == FALLBACK_USER_AGENT  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: UserAuditService 3 actions 入库 + acceptance #2/#5
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def patient_user(db_session: AsyncSession):
    """创建独立测试用户 (隔离 conftest 全局 user 影响)"""
    from app.models.user import User, UserRole

    user = User(
        id=uuid.uuid4(),
        phone=f"139{uuid.uuid4().hex[:8]}",
        role=UserRole.patient,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def sample_order(db_session: AsyncSession, patient_user):
    """最小 order_id mock — 用随机 UUID, SQLite 不检 FK constraint。

    不需实际 Order 行实例 (Order 字段太多, 与本测试无关)。本测试仅验 UserAuditService 入库逻辑,
    order_id 只作为 metadata 志记。
    """

    class _OrderRef:
        id = uuid.uuid4()

    return _OrderRef()


class TestUserAuditServiceRecord:
    """AC#2 + AC#5: 3 actions 入库 + 缺失 IP 兜底"""

    @pytest.mark.asyncio
    async def test_record_contract_acceptance_clicked_full_metadata(
        self, db_session: AsyncSession, patient_user, sample_order
    ):
        """AC#2 + AC#5: 勾选合同写库 + user_agent + client_ip + template_version"""
        service = UserAuditService(db_session)
        req = _FakeRequest(
            headers={
                "X-Forwarded-For": "203.0.113.42",
                "User-Agent": "Mozilla/5.0 Test",
            }
        )
        log = await service.record_contract_acceptance_clicked(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
            template_version="v1.0.0",
        )
        assert log.action == UserAuditAction.contract_acceptance_clicked.value
        assert log.user_id == patient_user.id
        assert log.order_id == sample_order.id
        assert log.client_ip == "203.0.113.42"
        assert log.user_agent == "Mozilla/5.0 Test"
        assert log.audit_metadata == {"template_version": "v1.0.0"}

    @pytest.mark.asyncio
    async def test_record_contract_viewed(
        self, db_session: AsyncSession, patient_user, sample_order
    ):
        """AC#2: 查看合同 PDF 入库"""
        service = UserAuditService(db_session)
        req = _FakeRequest(
            headers={"X-Real-IP": "198.51.100.7", "User-Agent": "iOS App 1.0"}
        )
        log = await service.record_contract_viewed(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
        )
        assert log.action == UserAuditAction.contract_viewed.value
        assert log.client_ip == "198.51.100.7"
        assert log.user_agent == "iOS App 1.0"

    @pytest.mark.asyncio
    async def test_record_insurance_terms_viewed_no_order(
        self, db_session: AsyncSession, patient_user
    ):
        """AC#2: 查看保障条款无 order 场景 (营销页)"""
        service = UserAuditService(db_session)
        req = _FakeRequest(client_host="192.0.2.10")
        log = await service.record_insurance_terms_viewed(
            user_id=patient_user.id,
            order_id=None,
            request=req,  # type: ignore[arg-type]
        )
        assert log.action == UserAuditAction.insurance_terms_viewed.value
        assert log.order_id is None
        assert log.client_ip == "192.0.2.10"

    @pytest.mark.asyncio
    async def test_record_missing_ip_writes_fallback(
        self, db_session: AsyncSession, patient_user, sample_order
    ):
        """AC#5: 缺失 IP 写 0.0.0.0 + metadata.missing_ip=True (PIPL 取证仍必须写库)"""
        service = UserAuditService(db_session)
        # 无任何 header + 无 client → 全 fallback
        req = _FakeRequest()
        log = await service.record_contract_acceptance_clicked(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
            template_version="v1.0.0",
        )
        assert log.client_ip == FALLBACK_CLIENT_IP
        assert log.client_ip == "0.0.0.0"
        assert log.user_agent == FALLBACK_USER_AGENT
        assert log.audit_metadata["missing_ip"] is True
        # metadata 同时保留其他字段
        assert log.audit_metadata.get("template_version") == "v1.0.0"

    @pytest.mark.asyncio
    async def test_three_actions_persist_distinct_rows(
        self, db_session: AsyncSession, patient_user, sample_order
    ):
        """AC#2: 3 actions 全落库 → 3 行独立"""
        service = UserAuditService(db_session)
        req = _FakeRequest(
            headers={
                "X-Forwarded-For": "203.0.113.1",
                "User-Agent": "Test UA",
            }
        )

        await service.record_contract_acceptance_clicked(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
            template_version="v1.0.0",
        )
        await service.record_contract_viewed(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
        )
        await service.record_insurance_terms_viewed(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
        )

        rows = (
            (
                await db_session.execute(
                    select(UserAuditLog)
                    .where(UserAuditLog.user_id == patient_user.id)
                    .order_by(UserAuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )
        actions = [r.action for r in rows]
        assert UserAuditAction.contract_acceptance_clicked.value in actions
        assert UserAuditAction.contract_viewed.value in actions
        assert UserAuditAction.insurance_terms_viewed.value in actions
        assert len(rows) == 3


class TestAdminAuditNotImpactedByUserAudit:
    """AC#4: admin 操作不进此表, 走 admin_audit_logs (物理隔离哨兵)"""

    @pytest.mark.asyncio
    async def test_user_audit_does_not_create_admin_audit_rows(
        self, db_session: AsyncSession, patient_user, sample_order
    ):
        """3 user actions 全跑后 admin_audit_logs 应仍为空"""
        service = UserAuditService(db_session)
        req = _FakeRequest(
            headers={"X-Forwarded-For": "203.0.113.1", "User-Agent": "Test"}
        )
        await service.record_contract_acceptance_clicked(
            user_id=patient_user.id,
            order_id=sample_order.id,
            request=req,  # type: ignore[arg-type]
            template_version="v1.0.0",
        )

        admin_rows = (
            (await db_session.execute(select(AdminAuditLog))).scalars().all()
        )
        # user_audit 不应该写 admin_audit_logs
        assert len(admin_rows) == 0

        user_rows = (
            (await db_session.execute(select(UserAuditLog))).scalars().all()
        )
        assert len(user_rows) == 1


class TestUserAuditLogSchemaSentinel:
    """AC#1: schema 哨兵 — user_agent + client_ip 是 NOT NULL"""

    @pytest.mark.asyncio
    async def test_user_agent_required(self, db_session: AsyncSession, patient_user):
        """直接 instantiate UserAuditLog 缺 user_agent 应该 raise"""
        from sqlalchemy.exc import IntegrityError

        log = UserAuditLog(
            user_id=patient_user.id,
            order_id=None,
            action=UserAuditAction.insurance_terms_viewed.value,
            audit_metadata={},
            # 故意不给 user_agent
            client_ip="0.0.0.0",
        )
        db_session.add(log)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_client_ip_required(self, db_session: AsyncSession, patient_user):
        from sqlalchemy.exc import IntegrityError

        log = UserAuditLog(
            user_id=patient_user.id,
            order_id=None,
            action=UserAuditAction.insurance_terms_viewed.value,
            audit_metadata={},
            user_agent="Test",
            # 故意不给 client_ip
        )
        db_session.add(log)
        with pytest.raises(IntegrityError):
            await db_session.flush()
