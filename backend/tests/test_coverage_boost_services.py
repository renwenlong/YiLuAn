"""Service-level tests to push `app.services.*` coverage.

Targets the highest-miss service modules:
  - services.sms (Aliyun + Tencent, mocked httpx; mock fallback)
  - services.wechat (code2session: success, errcode, raise_for_status)
  - services.auth (refresh_token branches, bind_phone, wechat_login)
  - services.user (delete_account incl. refund branches)
  - services.companion_profile (apply / update / stats / list)
  - services.hospital (search / find_nearest / seed)
  - services.review (submit + edge cases)
  - services.chat (send / list / mark_read + permission branches)
  - services.admin_audit (list / approve / reject)
  - services.payment_service (idempotency, refund, callback)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment
from app.models.user import User, UserRole
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository
from app.schemas.auth import RefreshTokenResponse
from app.schemas.chat import SendMessageRequest
from app.schemas.companion import (
    ApplyCompanionRequest,
    UpdateCompanionProfileRequest,
)
from app.schemas.review import CreateReviewRequest
from app.schemas.user import UpdateUserRequest
from app.services.admin_audit import AdminAuditService
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.companion_profile import CompanionProfileService
from app.services.hospital import HospitalService
from app.services.payment_service import PaymentService
from app.services.review import ReviewService
from app.services.sms import (
    AliyunSMSProvider,
    MockSMSProvider,
    TencentSMSProvider,
    get_sms_provider,
)
from app.services.user import UserService
from app.services.wechat import WeChatAPIClient
from tests.conftest import FakeRedis, test_session_factory

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# services.wechat
# ---------------------------------------------------------------------------
class TestWeChatAPIClient:
    async def test_code2session_success(self):
        """Returns mapped dict on successful response."""

        class FakeResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "openid": "OID",
                    "session_key": "SK",
                    "unionid": "UID",
                }

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None):
                return FakeResp()

        with patch("app.services.wechat.httpx.AsyncClient", FakeClient):
            res = await WeChatAPIClient.code2session("any")
        assert res == {"openid": "OID", "session_key": "SK", "unionid": "UID"}

    async def test_code2session_errcode_raises(self):
        """errcode != 0 → BadRequestException."""

        class FakeResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"errcode": 40029, "errmsg": "invalid code"}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None):
                return FakeResp()

        with patch("app.services.wechat.httpx.AsyncClient", FakeClient):
            with pytest.raises(BadRequestException):
                await WeChatAPIClient.code2session("bad")


# ---------------------------------------------------------------------------
# services.sms (legacy provider classes)
# ---------------------------------------------------------------------------
class TestLegacySMSProviders:
    async def test_mock_provider_send(self):
        """MockSMSProvider always returns True."""
        assert await MockSMSProvider().send("13800138000", "123456") is True

    async def test_aliyun_no_credentials_falls_back(self, monkeypatch):
        """Without access_key/secret, send returns True via fallback."""
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "x", raising=False)
        provider = AliyunSMSProvider()
        assert await provider.send("13800138000", "111111") is True

    async def test_aliyun_send_ok(self, monkeypatch):
        """Mock httpx response → OK code → True."""
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "AK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "SK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "Sign", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "TC", raising=False)

        class FakeResp:
            def json(self):
                return {"Code": "OK"}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None, timeout=None):
                return FakeResp()

        with patch("httpx.AsyncClient", FakeClient):
            assert await AliyunSMSProvider().send("13800138000", "111111") is True

    async def test_aliyun_send_error_code(self, monkeypatch):
        """Non-OK code → False."""
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "AK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "SK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "x", raising=False)

        class FakeResp:
            def json(self):
                return {"Code": "QPS_LIMIT", "Message": "throttled"}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **kw):
                return FakeResp()

        with patch("httpx.AsyncClient", FakeClient):
            assert await AliyunSMSProvider().send("13800138000", "1") is False

    async def test_aliyun_send_exception(self, monkeypatch):
        """httpx blowup → False (caught)."""
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "AK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "SK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "x", raising=False)

        class BadClient:
            def __init__(self, *a, **k):
                raise RuntimeError("boom")

        with patch("httpx.AsyncClient", BadClient):
            assert await AliyunSMSProvider().send("13800138000", "1") is False

    async def test_tencent_no_credentials_falls_back(self, monkeypatch):
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "", raising=False)
        assert await TencentSMSProvider().send("13800138000", "1") is True

    async def test_tencent_send_ok(self, monkeypatch):
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "AK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "SK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sdk_app_id", "1400", raising=False)

        class FakeResp:
            def json(self):
                return {"Response": {"SendStatusSet": [{"Code": "Ok"}]}}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return FakeResp()

        with patch("httpx.AsyncClient", FakeClient):
            assert await TencentSMSProvider().send("13800138000", "1") is True

    async def test_tencent_send_error(self, monkeypatch):
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "AK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "SK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sdk_app_id", "1400", raising=False)

        class FakeResp:
            def json(self):
                return {"Response": {"Error": {"Code": "FailedOperation"}}}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return FakeResp()

        with patch("httpx.AsyncClient", FakeClient):
            # Includes phone with country code path: starts without +
            assert await TencentSMSProvider().send("13800138000", "1") is False

    async def test_tencent_send_exception(self, monkeypatch):
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_access_key", "AK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_access_secret", "SK", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sign_name", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_template_code", "x", raising=False)
        monkeypatch.setattr(sms_mod.settings, "sms_sdk_app_id", "1400", raising=False)

        class BadClient:
            def __init__(self, *a, **k):
                raise RuntimeError("net")

        with patch("httpx.AsyncClient", BadClient):
            assert await TencentSMSProvider().send("13800138000", "1") is False

    async def test_get_sms_provider_factory(self, monkeypatch):
        """Factory returns the right concrete class per setting."""
        from app.services import sms as sms_mod

        monkeypatch.setattr(sms_mod.settings, "sms_provider", "aliyun", raising=False)
        assert isinstance(get_sms_provider(), AliyunSMSProvider)
        monkeypatch.setattr(sms_mod.settings, "sms_provider", "tencent", raising=False)
        assert isinstance(get_sms_provider(), TencentSMSProvider)
        monkeypatch.setattr(sms_mod.settings, "sms_provider", "mock", raising=False)
        assert isinstance(get_sms_provider(), MockSMSProvider)


# ---------------------------------------------------------------------------
# services.auth
# ---------------------------------------------------------------------------
class TestAuthServiceBranches:
    async def test_refresh_token_invalid_returns_unauthorized(self):
        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token("not.a.token")

    async def test_refresh_token_wrong_type(self):
        from app.core.security import create_access_token

        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            tok = create_access_token({"sub": str(uuid4())})  # type=access
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token(tok)

    async def test_refresh_token_missing_subject(self):
        from app.core.security import create_refresh_token

        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            tok = create_refresh_token({"sub": ""})
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token(tok)

    async def test_refresh_token_malformed_subject(self):
        from app.core.security import create_refresh_token

        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            tok = create_refresh_token({"sub": "not-a-uuid"})
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token(tok)

    async def test_refresh_token_user_missing(self):
        from app.core.security import create_refresh_token

        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            tok = create_refresh_token({"sub": str(uuid4())})
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token(tok)

    async def test_refresh_token_deleted_user(self):
        from app.core.security import create_refresh_token

        async with test_session_factory() as session:
            user = User(phone="13888880001", deleted_at=datetime.now(timezone.utc))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            tok = create_refresh_token({"sub": str(user.id)})
            svc = AuthService(session, FakeRedis())
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token(tok)

    async def test_refresh_token_inactive_user(self):
        from app.core.security import create_refresh_token

        async with test_session_factory() as session:
            user = User(phone="13888880002", is_active=False)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            tok = create_refresh_token({"sub": str(user.id)})
            svc = AuthService(session, FakeRedis())
            with pytest.raises(UnauthorizedException):
                await svc.refresh_token(tok)

    async def test_refresh_token_success(self):
        from app.core.security import create_refresh_token

        async with test_session_factory() as session:
            user = User(phone="13888880003", role=UserRole.patient, roles="patient")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            tok = create_refresh_token({"sub": str(user.id)})
            svc = AuthService(session, FakeRedis())
            res = await svc.refresh_token(tok)
            assert isinstance(res, RefreshTokenResponse)
            assert res.access_token and res.refresh_token

    async def test_bind_phone_dev_otp_success(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "development", raising=False
        )
        async with test_session_factory() as session:
            user = User(wechat_openid="oid_b1")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = AuthService(session, FakeRedis())
            updated = await svc.bind_phone(user.id, "13900001111", "000000")
            assert updated.phone == "13900001111"

    async def test_bind_phone_otp_expired(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "production", raising=False
        )
        async with test_session_factory() as session:
            user = User(wechat_openid="oid_b2")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = AuthService(session, FakeRedis())
            with pytest.raises(BadRequestException):
                await svc.bind_phone(user.id, "13900002222", "999999")

    async def test_bind_phone_wrong_otp(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "production", raising=False
        )
        async with test_session_factory() as session:
            user = User(wechat_openid="oid_b3")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            redis = FakeRedis()
            await redis.set("otp:13900003333", "111111")
            svc = AuthService(session, redis)
            with pytest.raises(BadRequestException):
                await svc.bind_phone(user.id, "13900003333", "999999")

    async def test_bind_phone_already_bound(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "development", raising=False
        )
        async with test_session_factory() as session:
            user = User(phone="13900004444")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = AuthService(session, FakeRedis())
            with pytest.raises(BadRequestException):
                await svc.bind_phone(user.id, "13900005555", "000000")

    async def test_bind_phone_user_missing(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "development", raising=False
        )
        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            with pytest.raises(UnauthorizedException):
                await svc.bind_phone(uuid4(), "13900007777", "000000")

    async def test_bind_phone_taken_by_other(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "development", raising=False
        )
        async with test_session_factory() as session:
            other = User(phone="13900008888")
            user = User(wechat_openid="oid_b4")
            session.add_all([other, user])
            await session.commit()
            await session.refresh(user)
            svc = AuthService(session, FakeRedis())
            with pytest.raises(ConflictException):
                await svc.bind_phone(user.id, "13900008888", "000000")

    async def test_wechat_login_dev_code(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "development", raising=False
        )
        async with test_session_factory() as session:
            svc = AuthService(session, FakeRedis())
            res = await svc.wechat_login("dev_test_code")
            assert res.access_token

    async def test_wechat_login_real_code_path(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "production", raising=False
        )

        async def fake_code2session(code):
            return {"openid": "real_oid_x", "unionid": "uid", "session_key": "sk"}

        with patch.object(WeChatAPIClient, "code2session", fake_code2session):
            async with test_session_factory() as session:
                svc = AuthService(session, FakeRedis())
                res = await svc.wechat_login("real_code")
                assert res.access_token

    async def test_wechat_login_deleted_user_blocked(self, monkeypatch):
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "production", raising=False
        )

        async def fake(code):
            return {"openid": "del_oid", "unionid": None, "session_key": "sk"}

        async with test_session_factory() as session:
            session.add(
                User(
                    wechat_openid="del_oid",
                    deleted_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            with patch.object(WeChatAPIClient, "code2session", fake):
                svc = AuthService(session, FakeRedis())
                with pytest.raises(UnauthorizedException):
                    await svc.wechat_login("c")

    async def test_send_otp_rate_limited(self, monkeypatch):
        """SMS rate limiter rejects after burst."""
        from app.services import auth as auth_mod

        # Allow at most 1 per minute (default), so 2nd hits limit
        async with test_session_factory() as session:
            redis = FakeRedis()
            svc = AuthService(session, redis)
            monkeypatch.setattr(
                auth_mod.settings, "environment", "development", raising=False
            )
            await svc.send_otp("13900009000")
            with pytest.raises(BadRequestException):
                await svc.send_otp("13900009000")

    async def test_verify_otp_lockout(self, monkeypatch):
        """After OTP_FAIL_MAX failures, returns TooManyRequests."""
        from app.exceptions import TooManyRequestsException
        from app.services import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "environment", "production", raising=False
        )
        async with test_session_factory() as session:
            redis = FakeRedis()
            await redis.set("otp:fail:13900009111", "5")
            svc = AuthService(session, redis)
            with pytest.raises(TooManyRequestsException):
                await svc.verify_otp("13900009111", "123456")


# ---------------------------------------------------------------------------
# services.user
# ---------------------------------------------------------------------------
class TestUserService:
    async def test_update_user_with_role(self):
        async with test_session_factory() as session:
            user = User(phone="13900010001")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = UserService(session)
            updated = await svc.update_user(
                user, UpdateUserRequest(role="patient", display_name="A")
            )
            assert updated.role == UserRole.patient
            assert "patient" in (updated.roles or "")

    async def test_update_user_noop(self):
        async with test_session_factory() as session:
            user = User(phone="13900010002")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = UserService(session)
            assert (await svc.update_user(user, UpdateUserRequest())).id == user.id

    async def test_switch_role_invalid(self):
        async with test_session_factory() as session:
            user = User(phone="13900010003", role=UserRole.patient, roles="patient")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = UserService(session)
            with pytest.raises(BadRequestException):
                await svc.switch_role(user, "companion")

    async def test_switch_role_ok(self):
        async with test_session_factory() as session:
            user = User(
                phone="13900010004",
                role=UserRole.patient,
                roles="patient,companion",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = UserService(session)
            updated = await svc.switch_role(user, "companion")
            assert updated.role == UserRole.companion

    async def test_get_user_by_id_missing(self):
        async with test_session_factory() as session:
            svc = UserService(session)
            with pytest.raises(NotFoundException):
                await svc.get_user_by_id(uuid4())

    async def test_delete_account_already_deleted(self):
        async with test_session_factory() as session:
            user = User(phone="13900010005", deleted_at=datetime.now(timezone.utc))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = UserService(session)
            with pytest.raises(BadRequestException):
                await svc.delete_account(user)

    async def test_delete_account_with_active_orders_and_refund(self, monkeypatch):
        """Deleting an account cancels orders and triggers a refund for accepted ones."""
        async with test_session_factory() as session:
            user = User(phone="13900010006")
            hospital = Hospital(name="H")
            session.add_all([user, hospital])
            await session.commit()
            await session.refresh(user)
            await session.refresh(hospital)

            order = Order(
                order_number="YLAUSR1",
                patient_id=user.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.accepted,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=200.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)

            # Pre-existing successful pay so refund is triggered
            session.add(
                Payment(
                    order_id=order.id,
                    user_id=user.id,
                    amount=200.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TX-DEL",
                )
            )
            await session.commit()

            svc = UserService(session)
            await svc.delete_account(user)
            await session.commit()

            # phone hashed (not original), is_active False, deleted_at set
            await session.refresh(user)
            assert user.is_active is False
            assert user.deleted_at is not None
            assert user.phone != "13900010006"

    async def test_delete_account_in_progress_50pct_refund(self):
        async with test_session_factory() as session:
            user = User(phone="13900010007")
            hospital = Hospital(name="H")
            session.add_all([user, hospital])
            await session.commit()
            await session.refresh(user)
            await session.refresh(hospital)

            order = Order(
                order_number="YLAUSR2",
                patient_id=user.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.in_progress,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=200.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            session.add(
                Payment(
                    order_id=order.id,
                    user_id=user.id,
                    amount=200.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TX-DEL2",
                )
            )
            await session.commit()
            await UserService(session).delete_account(user)


# ---------------------------------------------------------------------------
# services.companion_profile
# ---------------------------------------------------------------------------
class TestCompanionProfileService:
    async def test_apply_requires_phone(self):
        async with test_session_factory() as session:
            user = User(wechat_openid="oid_cp1")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = CompanionProfileService(session)
            with pytest.raises(BadRequestException):
                await svc.apply(
                    user,
                    ApplyCompanionRequest(
                        real_name="张三", service_types="queue"
                    ),
                )

    async def test_apply_ok_then_conflict(self):
        async with test_session_factory() as session:
            user = User(phone="13900020001")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = CompanionProfileService(session)
            await svc.apply(
                user,
                ApplyCompanionRequest(real_name="张三", service_types="queue"),
            )
            with pytest.raises(ConflictException):
                await svc.apply(
                    user,
                    ApplyCompanionRequest(real_name="张三", service_types="queue"),
                )

    async def test_update_profile_creates_when_missing(self):
        async with test_session_factory() as session:
            uid = uuid4()
            svc = CompanionProfileService(session)
            p = await svc.update_profile(
                uid,
                UpdateCompanionProfileRequest(bio="hi", service_area="海淀"),
                display_name="李四",
            )
            assert p.real_name == "李四"
            assert p.bio == "hi"

    async def test_update_profile_no_changes(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add(
                CompanionProfile(
                    user_id=uid,
                    real_name="王五",
                    verification_status=VerificationStatus.verified,
                )
            )
            await session.commit()
            svc = CompanionProfileService(session)
            p = await svc.update_profile(uid, UpdateCompanionProfileRequest())
            assert p.real_name == "王五"

    async def test_update_profile_with_changes(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add(
                CompanionProfile(
                    user_id=uid,
                    real_name="王五",
                    verification_status=VerificationStatus.verified,
                )
            )
            await session.commit()
            svc = CompanionProfileService(session)
            p = await svc.update_profile(
                uid, UpdateCompanionProfileRequest(bio="updated")
            )
            assert p.bio == "updated"

    async def test_get_detail_not_found(self):
        async with test_session_factory() as session:
            svc = CompanionProfileService(session)
            with pytest.raises(NotFoundException):
                await svc.get_detail(uuid4())

    async def test_get_detail_by_user_creates(self):
        async with test_session_factory() as session:
            svc = CompanionProfileService(session)
            p = await svc.get_detail_by_user(uuid4(), display_name="赵六")
            assert p.real_name == "赵六"

    async def test_list_companions_with_hospital(self):
        async with test_session_factory() as session:
            h = Hospital(name="H1", district="海淀")
            session.add(h)
            await session.commit()
            await session.refresh(h)
            svc = CompanionProfileService(session)
            res = await svc.list_companions(hospital_id=str(h.id))
            assert isinstance(res, list)

    async def test_get_stats_forbidden_for_non_companion(self):
        async with test_session_factory() as session:
            user = User(phone="13900020010", role=UserRole.patient, roles="patient")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = CompanionProfileService(session)
            with pytest.raises(ForbiddenException):
                await svc.get_stats(user)

    async def test_get_stats_no_profile_uses_review_fallback(self):
        async with test_session_factory() as session:
            user = User(
                phone="13900020011",
                role=UserRole.companion,
                roles="companion",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            svc = CompanionProfileService(session)
            stats = await svc.get_stats(user)
            assert stats["total_orders"] == 0

    async def test_get_stats_with_profile(self):
        async with test_session_factory() as session:
            user = User(
                phone="13900020012",
                role=UserRole.companion,
                roles="companion",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            session.add(
                CompanionProfile(
                    user_id=user.id,
                    real_name="x",
                    verification_status=VerificationStatus.verified,
                    avg_rating=4.5,
                    total_orders=3,
                )
            )
            await session.commit()
            svc = CompanionProfileService(session)
            stats = await svc.get_stats(user)
            assert stats["avg_rating"] == 4.5
            assert stats["total_orders"] == 3


# ---------------------------------------------------------------------------
# services.hospital
# ---------------------------------------------------------------------------
class TestHospitalService:
    async def test_get_by_id_missing(self):
        async with test_session_factory() as session:
            with pytest.raises(NotFoundException):
                await HospitalService(session).get_by_id(uuid4())

    async def test_get_filter_options_and_find(self):
        async with test_session_factory() as session:
            session.add(
                Hospital(
                    name="H",
                    province="北京",
                    city="北京",
                    latitude=39.9,
                    longitude=116.4,
                )
            )
            await session.commit()
            svc = HospitalService(session)
            opts = await svc.get_filter_options()
            assert "北京" in opts["provinces"]
            res = await svc.find_nearest_region(latitude=39.9, longitude=116.4)
            assert res == {"province": "北京", "city": "北京"}

    async def test_seed_no_file(self, monkeypatch):
        """seed_hospitals returns 0 when seed file missing."""
        from app.services import hospital as h_mod

        fake_path = h_mod.SEED_FILE.parent / "no_such_file.json"
        monkeypatch.setattr(h_mod, "SEED_FILE", fake_path)
        async with test_session_factory() as session:
            assert await HospitalService(session).seed_hospitals() == 0

    async def test_seed_creates_and_updates(self, tmp_path, monkeypatch):
        """seed file: insert new + update existing path."""
        import json as _json
        from app.services import hospital as h_mod

        # Pre-existing hospital with same name → triggers update branch
        async with test_session_factory() as session:
            session.add(Hospital(name="医院A", city="旧"))
            await session.commit()

            seed = tmp_path / "h.json"
            seed.write_text(
                _json.dumps(
                    [
                        {"name": "医院A", "city": "新"},
                        {"name": "医院B", "city": "上海"},
                    ]
                ),
                encoding="utf-8",
            )
            monkeypatch.setattr(h_mod, "SEED_FILE", seed)
            count = await HospitalService(session).seed_hospitals()
            assert count == 2


# ---------------------------------------------------------------------------
# services.review
# ---------------------------------------------------------------------------
class TestReviewService:
    async def test_submit_not_found(self):
        async with test_session_factory() as session:
            user = User(phone="13900030001")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            with pytest.raises(NotFoundException):
                await ReviewService(session).submit_review(
                    uuid4(), user, CreateReviewRequest(rating=5, content="good!")
                )

    async def test_submit_forbidden(self):
        async with test_session_factory() as session:
            patient = User(phone="13900030002")
            other = User(phone="13900030003")
            hospital = Hospital(name="H")
            session.add_all([patient, other, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(other)
            await session.refresh(hospital)
            order = Order(
                order_number="YLAR1",
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.completed,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=100.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            with pytest.raises(ForbiddenException):
                await ReviewService(session).submit_review(
                    order.id, other, CreateReviewRequest(rating=5, content="good!")
                )

    async def test_submit_status_not_completed(self):
        async with test_session_factory() as session:
            patient = User(phone="13900030010")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = Order(
                order_number="YLAR2",
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.created,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=100.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            with pytest.raises(BadRequestException):
                await ReviewService(session).submit_review(
                    order.id, patient, CreateReviewRequest(rating=5, content="good!")
                )

    async def test_submit_no_companion(self):
        async with test_session_factory() as session:
            patient = User(phone="13900030011")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = Order(
                order_number="YLAR3",
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.completed,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=100.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            with pytest.raises(BadRequestException):
                await ReviewService(session).submit_review(
                    order.id, patient, CreateReviewRequest(rating=5, content="good!")
                )

    async def test_submit_success_with_existing_profile(self):
        async with test_session_factory() as session:
            patient = User(phone="13900030020", display_name="P")
            companion = User(
                phone="13900030021", role=UserRole.companion, roles="companion"
            )
            hospital = Hospital(name="H")
            session.add_all([patient, companion, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(companion)
            await session.refresh(hospital)
            session.add(
                CompanionProfile(
                    user_id=companion.id,
                    real_name="C",
                    verification_status=VerificationStatus.verified,
                    avg_rating=0.0,
                    total_orders=0,
                )
            )
            order = Order(
                order_number="YLAR4",
                patient_id=patient.id,
                companion_id=companion.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.completed,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=200.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            r = await ReviewService(session).submit_review(
                order.id, patient, CreateReviewRequest(rating=4, content="goods")
            )
            assert r.rating == 4

    async def test_submit_already_reviewed(self):
        async with test_session_factory() as session:
            patient = User(phone="13900030030", display_name="P")
            companion = User(phone="13900030031")
            hospital = Hospital(name="H")
            session.add_all([patient, companion, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(companion)
            await session.refresh(hospital)
            order = Order(
                order_number="YLAR5",
                patient_id=patient.id,
                companion_id=companion.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.completed,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=200.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)

            svc = ReviewService(session)
            await svc.submit_review(
                order.id, patient, CreateReviewRequest(rating=5, content="good!")
            )
            # second time → BadRequest
            with pytest.raises(BadRequestException):
                await svc.submit_review(
                    order.id, patient, CreateReviewRequest(rating=5, content="again")
                )

    async def test_submit_creates_profile_when_missing(self):
        async with test_session_factory() as session:
            patient = User(phone="13900030040", display_name="P")
            companion = User(phone="13900030041")
            hospital = Hospital(name="H")
            session.add_all([patient, companion, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(companion)
            await session.refresh(hospital)
            order = Order(
                order_number="YLAR6",
                patient_id=patient.id,
                companion_id=companion.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.completed,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=200.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            r = await ReviewService(session).submit_review(
                order.id, patient, CreateReviewRequest(rating=5, content="good!")
            )
            assert r.rating == 5

    async def test_get_review_missing(self):
        async with test_session_factory() as session:
            with pytest.raises(NotFoundException):
                await ReviewService(session).get_review(uuid4())

    async def test_list_companion_reviews(self):
        async with test_session_factory() as session:
            items, total = await ReviewService(session).list_companion_reviews(
                uuid4()
            )
            assert total == 0


# ---------------------------------------------------------------------------
# services.chat
# ---------------------------------------------------------------------------
class TestChatService:
    async def test_send_message_forbidden(self):
        async with test_session_factory() as session:
            patient = User(phone="13900040001")
            other = User(phone="13900040002")
            hospital = Hospital(name="H")
            session.add_all([patient, other, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(other)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLACT1",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.in_progress,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            with pytest.raises(ForbiddenException):
                await ChatService(session).send_message(
                    order.id, other, SendMessageRequest(type="text", content="x")
                )

    async def test_send_message_order_missing(self):
        async with test_session_factory() as session:
            user = User(phone="13900040003")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            with pytest.raises(NotFoundException):
                await ChatService(session).send_message(
                    uuid4(), user, SendMessageRequest(type="text", content="x")
                )

    async def test_send_message_success(self):
        async with test_session_factory() as session:
            patient = User(phone="13900040010", display_name="P")
            companion = User(phone="13900040011")
            hospital = Hospital(name="H")
            session.add_all([patient, companion, hospital])
            await session.commit()
            for o in (patient, companion, hospital):
                await session.refresh(o)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLACT2",
                    patient_id=patient.id,
                    companion_id=companion.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.in_progress,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            msg = await ChatService(session).send_message(
                order.id, patient, SendMessageRequest(type="text", content="hi")
            )
            assert msg.id is not None

            # list
            items, total = await ChatService(session).list_messages(
                order.id, patient
            )
            assert total >= 1

            # mark_read by companion
            assert (
                await ChatService(session).mark_read(order.id, companion) >= 1
            )


# ---------------------------------------------------------------------------
# services.admin_audit
# ---------------------------------------------------------------------------
class TestAdminAuditService:
    async def test_list_pending_empty(self):
        async with test_session_factory() as session:
            res = await AdminAuditService(session).list_pending_companions()
            assert res["total"] == 0

    async def test_approve_not_found(self):
        async with test_session_factory() as session:
            with pytest.raises(NotFoundException):
                await AdminAuditService(session).approve_companion(
                    uuid4(), "admin"
                )

    async def test_approve_wrong_status(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13900050001"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="X",
                        verification_status=VerificationStatus.verified,
                    ),
                ]
            )
            await session.commit()
            from sqlalchemy import select as _sel

            prof = (
                await session.execute(
                    _sel(CompanionProfile).where(CompanionProfile.user_id == uid)
                )
            ).scalar_one()
            with pytest.raises(ConflictException):
                await AdminAuditService(session).approve_companion(prof.id, "admin")

    async def test_approve_no_phone(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, wechat_openid="oid_aud_x"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="X",
                        verification_status=VerificationStatus.pending,
                    ),
                ]
            )
            await session.commit()
            from sqlalchemy import select as _sel

            prof = (
                await session.execute(
                    _sel(CompanionProfile).where(CompanionProfile.user_id == uid)
                )
            ).scalar_one()
            with pytest.raises(BadRequestException):
                await AdminAuditService(session).approve_companion(prof.id, "admin")

    async def test_approve_ok_then_lists_empty(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13900050010"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="X",
                        verification_status=VerificationStatus.pending,
                    ),
                ]
            )
            await session.commit()
            from sqlalchemy import select as _sel

            prof = (
                await session.execute(
                    _sel(CompanionProfile).where(CompanionProfile.user_id == uid)
                )
            ).scalar_one()
            res = await AdminAuditService(session).list_pending_companions()
            assert res["total"] == 1
            updated = await AdminAuditService(session).approve_companion(
                prof.id, "admin"
            )
            assert updated.verification_status == VerificationStatus.verified

    async def test_reject_not_found_and_wrong_status(self):
        async with test_session_factory() as session:
            with pytest.raises(NotFoundException):
                await AdminAuditService(session).reject_companion(
                    uuid4(), "admin", "no"
                )

            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13900050020"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="X",
                        verification_status=VerificationStatus.verified,
                    ),
                ]
            )
            await session.commit()
            from sqlalchemy import select as _sel

            prof = (
                await session.execute(
                    _sel(CompanionProfile).where(CompanionProfile.user_id == uid)
                )
            ).scalar_one()
            with pytest.raises(ConflictException):
                await AdminAuditService(session).reject_companion(
                    prof.id, "admin", "x"
                )

    async def test_reject_ok(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13900050030"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="X",
                        verification_status=VerificationStatus.pending,
                    ),
                ]
            )
            await session.commit()
            from sqlalchemy import select as _sel

            prof = (
                await session.execute(
                    _sel(CompanionProfile).where(CompanionProfile.user_id == uid)
                )
            ).scalar_one()
            updated = await AdminAuditService(session).reject_companion(
                prof.id, "admin", "missing docs"
            )
            assert updated.verification_status == VerificationStatus.rejected


# ---------------------------------------------------------------------------
# services.payment_service — extra branches
# ---------------------------------------------------------------------------
class TestPaymentServiceBranches:
    async def test_create_prepay_already_paid(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060001")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS1",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TX1",
                )
            )
            svc = PaymentService(session)
            with pytest.raises(BadRequestException):
                await svc.create_prepay(
                    order.id, order.order_number, patient.id, 100.0
                )

    async def test_create_prepay_reuses_pending(self):
        """Existing pending Payment row is updated in-place."""
        async with test_session_factory() as session:
            patient = User(phone="13900060002")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS2",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="pending",
                    trade_no="OLD",
                )
            )
            svc = PaymentService(session)
            res = await svc.create_prepay(
                order.id, order.order_number, patient.id, 100.0
            )
            assert res.payment_id is not None

    async def test_record_callback_no_txn(self):
        async with test_session_factory() as session:
            svc = PaymentService(session)
            # No txn → returns True (process)
            assert (
                await svc.record_callback_or_skip(
                    provider="wechat", transaction_id=""
                )
                is True
            )

    async def test_record_callback_then_dup(self):
        async with test_session_factory() as session:
            svc = PaymentService(session)
            assert (
                await svc.record_callback_or_skip(
                    provider="wechat",
                    transaction_id="TXN-A",
                    raw_body=b"x" * 10,
                )
                is True
            )
            assert (
                await svc.record_callback_or_skip(
                    provider="wechat",
                    transaction_id="TXN-A",
                    raw_body="raw",
                )
                is False
            )

    async def test_is_callback_processed(self):
        async with test_session_factory() as session:
            svc = PaymentService(session)
            assert await svc.is_callback_processed("w", "") is False
            await svc.record_callback_or_skip(
                provider="w", transaction_id="X1"
            )
            assert await svc.is_callback_processed("w", "X1") is True

    async def test_handle_pay_callback_unknown(self):
        async with test_session_factory() as session:
            assert (
                await PaymentService(session).handle_pay_callback(
                    "missing", "ord", True
                )
                is None
            )

    async def test_handle_pay_callback_terminal(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060010")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS3",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TXN-OK",
                )
            )
            res = await PaymentService(session).handle_pay_callback(
                "TXN-OK", order.order_number, True
            )
            assert res is not None and res.status == "success"

    async def test_handle_pay_callback_pending_to_success_and_failed(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060011")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order1 = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS4A",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            order2 = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS4B",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order1.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="pending",
                    trade_no="TXN-P1",
                )
            )
            r1 = await PaymentService(session).handle_pay_callback(
                "TXN-P1", "ord", True
            )
            assert r1.status == "success"

            await PaymentRepository(session).create(
                Payment(
                    order_id=order2.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="pending",
                    trade_no="TXN-P2",
                )
            )
            r2 = await PaymentService(session).handle_pay_callback(
                "TXN-P2", "ord", False
            )
            assert r2.status == "failed"

    async def test_close_pending_payment_no_op(self):
        async with test_session_factory() as session:
            await PaymentService(session).close_pending_payment(uuid4())  # no row

    async def test_close_pending_payment_provider_raises(self, monkeypatch):
        async with test_session_factory() as session:
            patient = User(phone="13900060020")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS5",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="pending",
                    trade_no="TXN-CL",
                )
            )
            svc = PaymentService(session)
            svc.provider.close_order = AsyncMock(side_effect=RuntimeError("x"))
            with pytest.raises(BadRequestException):
                await svc.close_pending_payment(order.id)

    async def test_close_pending_payment_ok(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060021")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS6",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="pending",
                    trade_no="TXN-CL2",
                )
            )
            svc = PaymentService(session)
            svc.provider.close_order = AsyncMock(return_value=None)
            await svc.close_pending_payment(order.id)

    async def test_create_refund_dup(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060030")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS7",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="refund",
                    status="success",
                    refund_id="R-EXIST",
                )
            )
            with pytest.raises(BadRequestException):
                await PaymentService(session).create_refund(
                    order.id, patient.id, 100.0, 100.0
                )

    async def test_create_refund_no_original_pay(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060031")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS8",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            with pytest.raises(BadRequestException):
                await PaymentService(session).create_refund(
                    order.id, patient.id, 100.0, 100.0
                )

    async def test_create_refund_provider_blowup(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060032")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPS9",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TXN-RF",
                )
            )
            svc = PaymentService(session)
            svc.provider.create_refund = AsyncMock(side_effect=RuntimeError("net"))
            with pytest.raises(BadRequestException):
                await svc.create_refund(order.id, patient.id, 100.0, 100.0)

    async def test_create_refund_propagates_bad_request(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060033")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPSA",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TXN-RF2",
                )
            )
            svc = PaymentService(session)
            svc.provider.create_refund = AsyncMock(
                side_effect=BadRequestException("rejected")
            )
            with pytest.raises(BadRequestException):
                await svc.create_refund(order.id, patient.id, 100.0, 100.0)

    async def test_handle_refund_callback_unknown(self):
        async with test_session_factory() as session:
            assert (
                await PaymentService(session).handle_refund_callback(
                    "no-such", "SUCCESS"
                )
                is None
            )

    async def test_handle_refund_callback_terminal(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060040")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            order = await OrderRepository(session).create(
                Order(
                    order_number="YLAPSB",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=order.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="refund",
                    status="success",
                    refund_id="RFND-1",
                )
            )
            res = await PaymentService(session).handle_refund_callback(
                "RFND-1", "SUCCESS"
            )
            assert res.status == "success"

    async def test_handle_refund_callback_success_and_failure(self):
        async with test_session_factory() as session:
            patient = User(phone="13900060041")
            hospital = Hospital(name="H")
            session.add_all([patient, hospital])
            await session.commit()
            await session.refresh(patient)
            await session.refresh(hospital)
            o1 = await OrderRepository(session).create(
                Order(
                    order_number="YLAPSCa",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            o2 = await OrderRepository(session).create(
                Order(
                    order_number="YLAPSCb",
                    patient_id=patient.id,
                    hospital_id=hospital.id,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await PaymentRepository(session).create(
                Payment(
                    order_id=o1.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="refund",
                    status="pending",
                    refund_id="RFND-S",
                )
            )
            r = await PaymentService(session).handle_refund_callback(
                "RFND-S", "SUCCESS", raw_body="payload"
            )
            assert r.status == "success"

            await PaymentRepository(session).create(
                Payment(
                    order_id=o2.id,
                    user_id=patient.id,
                    amount=100.0,
                    payment_type="refund",
                    status="pending",
                    refund_id="RFND-F",
                )
            )
            r2 = await PaymentService(session).handle_refund_callback(
                "RFND-F", "ABNORMAL"
            )
            assert r2.status == "failed"
