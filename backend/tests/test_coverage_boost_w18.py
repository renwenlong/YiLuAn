"""W18-prep coverage boost: push residual gaps from 96% -> ~98%.

Covers small, hard-to-reach branches in:
- app/api/v1/ws.py (fallback brokers, push helper, chat content edge cases)
- app/api/v1/users.py (switch-role multi-role token issuance)
- app/api/v1/payment_callback.py (auto-refund failure branches)
- app/services/notification.py (broadcast service_type branch)
- app/services/order.py (defensive 404 helpers + role-guard branches)
- app/dependencies.py (UnauthorizedException paths)
- app/services/providers/payment/wechat.py (credentialed httpx branches)
- app/database.py (get_db generator)
- app/tasks/log_retention.py (skip-on-lock branch)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

from app.core.security import create_access_token
from app.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.models.hospital import Hospital
from app.models.notification import NotificationType
from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment
from app.models.user import User, UserRole

from .conftest import test_session_factory


pytestmark = pytest.mark.asyncio


# ============================================================================
# app/api/v1/ws.py – fallback brokers + push helper
# ============================================================================
class TestWsFallbackBrokers:
    async def test_fallback_broker_created_when_app_state_missing(self):
        """No ws_broker on app.state -> fallback broker created and cached."""
        import app.api.v1.ws as ws_mod

        # Reset module-level fallback so we exercise creation branch
        ws_mod._fallback_broker = None
        fake_app = SimpleNamespace(state=SimpleNamespace())
        b1 = ws_mod._get_or_create_broker(fake_app)
        b2 = ws_mod._get_or_create_broker(fake_app)
        assert b1 is b2  # cached
        assert b1._started is True

    async def test_fallback_chat_broker_created_when_app_state_missing(self):
        """No ws_chat_broker on app.state -> fallback chat broker created."""
        import app.api.v1.ws as ws_mod

        ws_mod._fallback_chat_broker = None
        fake_app = SimpleNamespace(state=SimpleNamespace())
        b1 = ws_mod._get_or_create_chat_broker(fake_app)
        b2 = ws_mod._get_or_create_chat_broker(fake_app)
        assert b1 is b2
        assert b1._started is True

    async def test_push_notification_to_user_uses_broker(self):
        """push_notification_to_user delegates to broker.push_to_user."""
        import app.api.v1.ws as ws_mod

        fake_broker = MagicMock()
        fake_broker.push_to_user = AsyncMock()
        with patch.object(ws_mod, "_get_or_create_broker", return_value=fake_broker):
            uid = uuid.uuid4()
            await ws_mod.push_notification_to_user(
                SimpleNamespace(state=SimpleNamespace()),
                uid,
                {"hello": "world"},
            )
        fake_broker.push_to_user.assert_awaited_once_with(uid, {"hello": "world"})


# ============================================================================
# app/api/v1/users.py – switch_role full token issuance
# ============================================================================
class TestUsersSwitchRoleFullPath:
    async def test_switch_role_returns_tokens_when_allowed(self, client):
        """User with multiple roles -> switch returns access + refresh tokens."""
        async with test_session_factory() as session:
            u = User(
                phone="13800200001",
                role=UserRole.patient,
                roles="patient,companion",
                is_active=True,
            )
            session.add(u)
            await session.commit()
            await session.refresh(u)

        token = create_access_token({"sub": str(u.id), "role": "patient"})
        resp = await client.post(
            "/api/v1/users/me/switch-role",
            json={"role": "companion"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["user"]["role"] == "companion"


# ============================================================================
# app/api/v1/payment_callback.py – auto-refund failure branches
# ============================================================================
class TestPaymentCallbackAutoRefundBranches:
    async def _seed_paid_expired_order(self, trade_no: str):
        async with test_session_factory() as session:
            patient = User(phone=f"139002{trade_no[-5:]}", role=UserRole.patient, is_active=True)
            hospital = Hospital(name="X", province="P", city="C", district="D", address="A")
            session.add_all([patient, hospital])
            await session.flush()
            order_no = f"YLA{uuid.uuid4().hex[:12].upper()}"
            order = Order(
                order_number=order_no,
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.expired,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=100.0,
            )
            session.add(order)
            await session.flush()
            payment = Payment(
                order_id=order.id,
                user_id=patient.id,
                amount=100.0,
                status="pending",
                payment_type="pay",
                trade_no=trade_no,
            )
            session.add(payment)
            await session.commit()
            return order_no

    async def test_auto_refund_bad_request_logged(self, client):
        """Late callback on expired order: create_refund raises BadRequest -> error logged, callback OK."""
        from app.services.payment_service import PaymentService

        order_no = await self._seed_paid_expired_order("TXNAR1")
        body = json.dumps(
            {"transaction_id": "TXNAR1", "out_trade_no": order_no, "trade_state": "SUCCESS"}
        ).encode()

        with patch.object(
            PaymentService,
            "create_refund",
            AsyncMock(side_effect=BadRequestException("dup refund")),
        ):
            r = await client.post("/api/v1/payments/wechat/callback", content=body)
        assert r.status_code == 200

    async def test_auto_refund_unexpected_exception_logged(self, client):
        """Late callback: create_refund raises generic Exception -> error logged, callback OK."""
        from app.services.payment_service import PaymentService

        order_no = await self._seed_paid_expired_order("TXNAR2")
        body = json.dumps(
            {"transaction_id": "TXNAR2", "out_trade_no": order_no, "trade_state": "SUCCESS"}
        ).encode()

        with patch.object(
            PaymentService,
            "create_refund",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            r = await client.post("/api/v1/payments/wechat/callback", content=body)
        assert r.status_code == 200

    async def test_refund_callback_outer_exception_returns_fail(self, client):
        """Refund callback: handle_refund_callback raises -> outer except -> FAIL."""
        from app.services.payment_service import PaymentService

        with patch.object(
            PaymentService,
            "handle_refund_callback",
            AsyncMock(side_effect=RuntimeError("kaboom")),
        ):
            body = json.dumps(
                {"out_refund_no": "RFEXC", "out_trade_no": "OXX", "refund_status": "SUCCESS"}
            ).encode()
            r = await client.post(
                "/api/v1/payments/wechat/refund-callback", content=body
            )
        assert r.status_code == 200
        assert r.json()["code"] == "FAIL"


# ============================================================================
# app/services/notification.py – broadcast SERVICE_TYPE_LABELS branch
# ============================================================================
class TestNotificationBroadcast:
    async def test_notify_new_order_broadcast(self):
        """Broadcast notification creates one row per companion id."""
        from app.services.notification import NotificationService

        async with test_session_factory() as session:
            patient = User(phone="13800300001", role=UserRole.patient, is_active=True)
            companion1 = User(phone="13800300002", role=UserRole.companion, is_active=True)
            companion2 = User(phone="13800300003", role=UserRole.companion, is_active=True)
            hospital = Hospital(name="H", province="P", city="C", district="D", address="A")
            session.add_all([patient, companion1, companion2, hospital])
            await session.flush()
            order = Order(
                order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.created,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                hospital_name="H",
                price=100.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)

            svc = NotificationService(session)
            ns = await svc.notify_new_order_broadcast(order, [companion1.id, companion2.id])
            assert len(ns) == 2
            assert all(n.type == NotificationType.new_order for n in ns)


# ============================================================================
# app/services/order.py – defensive 404 + role-guard branches
# ============================================================================
class TestOrderServiceGuards:
    async def test_get_order_or_404_raises(self):
        from app.services.order import OrderService

        async with test_session_factory() as session:
            svc = OrderService(session)
            with pytest.raises(NotFoundException):
                await svc._get_order_or_404(uuid.uuid4())

    async def test_get_order_for_update_or_404_raises(self):
        from app.services.order import OrderService

        async with test_session_factory() as session:
            svc = OrderService(session)
            with pytest.raises(NotFoundException):
                await svc._get_order_for_update_or_404(uuid.uuid4())

    async def test_get_order_patient_not_owner_forbidden(self):
        from app.services.order import OrderService

        async with test_session_factory() as session:
            owner = User(phone="13800400001", role=UserRole.patient, is_active=True)
            stranger = User(phone="13800400002", role=UserRole.patient, is_active=True)
            hospital = Hospital(name="H", province="P", city="C", district="D", address="A")
            session.add_all([owner, stranger, hospital])
            await session.flush()
            order = Order(
                order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
                patient_id=owner.id,
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
            svc = OrderService(session)
            with pytest.raises(ForbiddenException):
                await svc.get_order(order.id, stranger)

    async def test_cancel_companion_not_owner(self):
        from app.services.order import OrderService

        async with test_session_factory() as session:
            patient = User(phone="13800400005", role=UserRole.patient, is_active=True)
            comp_owner = User(phone="13800400006", role=UserRole.companion, is_active=True)
            comp_other = User(phone="13800400007", role=UserRole.companion, is_active=True)
            hospital = Hospital(name="H", province="P", city="C", district="D", address="A")
            session.add_all([patient, comp_owner, comp_other, hospital])
            await session.flush()
            order = Order(
                order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
                patient_id=patient.id,
                companion_id=comp_owner.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.accepted,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=100.0,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            svc = OrderService(session)
            with pytest.raises(ForbiddenException):
                await svc.cancel_order(order.id, comp_other)


# ============================================================================
# app/dependencies.py – UnauthorizedException branches
# ============================================================================
class TestDependenciesAuth:
    async def test_invalid_token_type(self, client):
        """A refresh token presented as Bearer -> 'Invalid token type'."""
        from app.core.security import create_refresh_token

        token = create_refresh_token({"sub": str(uuid.uuid4())})
        r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    async def test_token_malformed_subject(self, client):
        """Token with non-UUID 'sub' -> 'malformed subject'."""
        import jwt
        from app.config import settings

        payload = {
            "sub": "not-a-uuid",
            "role": "patient",
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    async def test_token_user_not_found(self, client):
        """Valid token but user does not exist -> 'User not found'."""
        token = create_access_token({"sub": str(uuid.uuid4()), "role": "patient"})
        r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


# ============================================================================
# app/services/providers/payment/wechat.py – credentialed httpx branches
# ============================================================================
class TestWechatProviderCredentialedPaths:
    def _make_with_creds(self, monkeypatch, tmp_path):
        from app.config import settings as s
        from app.services.providers.payment.wechat import WechatPaymentProvider

        # Write a dummy private key file (RSA path will fall through except -> "sign_error")
        pk = tmp_path / "key.pem"
        pk.write_bytes(b"not-a-real-key")
        monkeypatch.setattr(s, "wechat_pay_mch_id", "1234567890", raising=False)
        monkeypatch.setattr(s, "wechat_pay_api_key_v3", "v3key", raising=False)
        monkeypatch.setattr(s, "wechat_app_id", "wxAppX", raising=False)
        monkeypatch.setattr(s, "wechat_pay_cert_serial", "SERIAL01", raising=False)
        monkeypatch.setattr(s, "wechat_pay_private_key_path", str(pk), raising=False)
        monkeypatch.setattr(s, "wechat_pay_notify_url", "https://example.com/cb", raising=False)
        monkeypatch.setattr(s, "wechat_pay_platform_cert_path", "", raising=False)
        return WechatPaymentProvider()

    async def test_create_order_http_path_success(self, monkeypatch, tmp_path):
        """Credentialed create_order -> httpx POST mocked 200 -> sign_params returned."""
        from app.services.providers.payment.base import OrderDTO
        import httpx

        prov = self._make_with_creds(monkeypatch, tmp_path)

        mock_resp = MagicMock(spec=Response)
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"prepay_id": "wx_pp_123"})
        mock_resp.text = ""

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None, timeout=None):
                return mock_resp

        with patch.object(httpx, "AsyncClient", return_value=_MockClient()):
            res = await prov.create_order(
                OrderDTO(
                    order_number="YLREAL1",
                    amount_yuan=12.5,
                    description="d",
                    openid="oid",
                )
            )
        assert res["prepay_id"] == "wx_pp_123"
        assert res["sign_params"]["package"] == "prepay_id=wx_pp_123"

    async def test_create_order_http_path_failure(self, monkeypatch, tmp_path):
        """Credentialed create_order -> httpx 400 -> BadRequestException."""
        from app.services.providers.payment.base import OrderDTO
        import httpx

        prov = self._make_with_creds(monkeypatch, tmp_path)

        mock_resp = MagicMock(spec=Response)
        mock_resp.status_code = 400
        mock_resp.json = MagicMock(return_value={})
        mock_resp.text = "bad request"

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return mock_resp

        with patch.object(httpx, "AsyncClient", return_value=_MockClient()):
            with pytest.raises(BadRequestException):
                await prov.create_order(
                    OrderDTO(
                        order_number="YLREAL2",
                        amount_yuan=10.0,
                        description="d",
                        openid="oid",
                    )
                )

    async def test_refund_http_path_success(self, monkeypatch, tmp_path):
        from app.services.providers.payment.base import RefundDTO
        import httpx

        prov = self._make_with_creds(monkeypatch, tmp_path)

        mock_resp = MagicMock(spec=Response)
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(
            return_value={"out_refund_no": "RF1", "status": "SUCCESS"}
        )
        mock_resp.text = ""

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return mock_resp

        with patch.object(httpx, "AsyncClient", return_value=_MockClient()):
            res = await prov.refund(
                RefundDTO(
                    refund_id="RF1",
                    trade_no="TX1",
                    total_yuan=10.0,
                    refund_yuan=5.0,
                )
            )
        assert res["refund_id"] == "RF1"
        assert res["status"] == "success"

    async def test_refund_http_path_failure(self, monkeypatch, tmp_path):
        from app.services.providers.payment.base import RefundDTO
        import httpx

        prov = self._make_with_creds(monkeypatch, tmp_path)

        mock_resp = MagicMock(spec=Response)
        mock_resp.status_code = 500
        mock_resp.json = MagicMock(return_value={})
        mock_resp.text = "err"

        class _MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **k):
                return mock_resp

        with patch.object(httpx, "AsyncClient", return_value=_MockClient()):
            with pytest.raises(BadRequestException):
                await prov.refund(
                    RefundDTO(
                        refund_id="RF2",
                        trade_no="TX2",
                        total_yuan=10.0,
                        refund_yuan=5.0,
                    )
                )

    async def test_load_platform_cert_load_failure(self, monkeypatch, tmp_path):
        """Bad cert file -> BadRequestException 'load failed' branch."""
        from app.services.providers.payment.wechat import (
            _platform_cert_cache,
            WechatPaymentProvider,
        )
        from app.config import settings as s

        bad = tmp_path / "bad.pem"
        bad.write_bytes(b"this is not a real pem certificate")
        monkeypatch.setattr(s, "wechat_pay_platform_cert_path", str(bad), raising=False)
        prov = WechatPaymentProvider()

        # Clear cache to force fresh load
        _platform_cert_cache.clear()

        with pytest.raises(BadRequestException, match="加载失败"):
            prov._load_platform_cert("SOME_SERIAL")

    async def test_rsa_sign_with_invalid_key_returns_sign_error(
        self, monkeypatch, tmp_path
    ):
        """Invalid PEM file -> _rsa_sign returns 'sign_error'."""
        from app.services.providers.payment.wechat import WechatPaymentProvider
        from app.config import settings as s

        bad = tmp_path / "bad-key.pem"
        bad.write_bytes(b"not-a-key")
        monkeypatch.setattr(s, "wechat_pay_private_key_path", str(bad), raising=False)
        prov = WechatPaymentProvider()
        sig = prov._rsa_sign("hello")
        assert sig == "sign_error"


# ============================================================================
# app/database.py – production get_db generator path
# ============================================================================
class TestDatabaseGetDb:
    async def test_get_db_yields_session(self, monkeypatch):
        """get_db() yields a session and closes cleanly."""
        import app.database as db_mod
        from .conftest import test_session_factory

        monkeypatch.setattr(db_mod, "async_session", test_session_factory)
        gen = db_mod.get_db()
        session = await gen.__anext__()
        assert session is not None
        # Trigger commit + close path via finalization
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    async def test_get_db_rollback_on_exception(self, monkeypatch):
        """Exception inside the with-block -> rollback path."""
        import app.database as db_mod
        from .conftest import test_session_factory

        monkeypatch.setattr(db_mod, "async_session", test_session_factory)
        gen = db_mod.get_db()
        await gen.__anext__()
        with pytest.raises(RuntimeError):
            await gen.athrow(RuntimeError("boom"))


# ============================================================================
# app/tasks/log_retention.py – skip-on-lock branch
# ============================================================================
class TestLogRetentionSkipOnLock:
    async def test_cleanup_payment_callback_skipped_when_lock_held(self, monkeypatch):
        """Lock not acquired -> returns status='skipped'."""
        from app.tasks import log_retention as lr

        # Fake lock context manager that reports acquired=False
        class _Lock:
            acquired = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(lr, "acquire_scheduler_lock", lambda **kw: _Lock())
        monkeypatch.setattr(lr, "async_session", test_session_factory)
        result = await lr.cleanup_payment_callback_log(app=None)
        assert result["status"] == "skipped"

    async def test_cleanup_sms_send_log_skipped_when_lock_held(self, monkeypatch):
        from app.tasks import log_retention as lr

        class _Lock:
            acquired = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(lr, "acquire_scheduler_lock", lambda **kw: _Lock())
        monkeypatch.setattr(lr, "async_session", test_session_factory)
        result = await lr.cleanup_sms_send_log(app=None)
        assert result["status"] == "skipped"

    async def test_cleanup_payment_callback_outer_exception_branch(self, monkeypatch):
        """Inner DB ops raise -> outer except -> status='error'."""
        from app.tasks import log_retention as lr

        def _raise_lock(**kw):
            raise RuntimeError("lock infra down")

        monkeypatch.setattr(lr, "acquire_scheduler_lock", _raise_lock)
        monkeypatch.setattr(lr, "async_session", test_session_factory)
        result = await lr.cleanup_payment_callback_log(app=None)
        assert result["status"] == "error"

    async def test_cleanup_sms_send_log_outer_exception_branch(self, monkeypatch):
        from app.tasks import log_retention as lr

        def _raise_lock(**kw):
            raise RuntimeError("lock infra down")

        monkeypatch.setattr(lr, "acquire_scheduler_lock", _raise_lock)
        monkeypatch.setattr(lr, "async_session", test_session_factory)
        result = await lr.cleanup_sms_send_log(app=None)
        assert result["status"] == "error"
