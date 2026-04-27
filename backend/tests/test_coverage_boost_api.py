"""Push API + provider coverage further (payment callbacks, hospitals,
notifications, users, admin, wechat provider).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment
from app.models.user import User, UserRole
from tests.conftest import test_session_factory

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# api/v1/notifications.py – device-token endpoints
# ---------------------------------------------------------------------------
class TestNotificationsAPI:
    async def test_list_unread_count(self, authenticated_client, seed_notification):
        """List + unread_count endpoint paths."""
        await seed_notification(user_id=authenticated_client._test_user.id)
        r = await authenticated_client.get("/api/v1/notifications")
        assert r.status_code == 200
        r2 = await authenticated_client.get("/api/v1/notifications/unread-count")
        assert r2.status_code == 200
        assert r2.json()["count"] >= 1

    async def test_mark_one_and_all_read(
        self, authenticated_client, seed_notification
    ):
        n = await seed_notification(user_id=authenticated_client._test_user.id)
        r = await authenticated_client.post(f"/api/v1/notifications/{n.id}/read")
        assert r.status_code == 200
        r2 = await authenticated_client.post("/api/v1/notifications/read-all")
        assert r2.status_code == 200

    async def test_register_and_dedupe_device_token(self, authenticated_client):
        body = {"token": "tk_x_001", "device_type": "ios"}
        r = await authenticated_client.post(
            "/api/v1/notifications/device-token", json=body
        )
        assert r.status_code == 200
        # second identical → returns existing record (no error)
        r2 = await authenticated_client.post(
            "/api/v1/notifications/device-token", json=body
        )
        assert r2.status_code == 200

    async def test_unregister_device_token(self, authenticated_client):
        await authenticated_client.post(
            "/api/v1/notifications/device-token",
            json={"token": "tk_x_002", "device_type": "android"},
        )
        r = await authenticated_client.request(
            "DELETE",
            "/api/v1/notifications/device-token",
            json={"token": "tk_x_002"},
        )
        assert r.status_code == 200
        assert r.json() == {"success": True}


# ---------------------------------------------------------------------------
# api/v1/hospitals.py
# ---------------------------------------------------------------------------
class TestHospitalsAPI:
    async def test_search_uses_cache_on_second_hit(self, client, seed_hospital):
        """Second identical search hits the cached branch."""
        await seed_hospital(name="协和", province="北京", city="北京")
        url = "/api/v1/hospitals?keyword=协和&page=1&page_size=10"
        r1 = await client.get(url)
        r2 = await client.get(url)  # served from FakeRedis cache
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["total"] == r2.json()["total"]

    async def test_filters_endpoint(self, client, seed_hospital):
        await seed_hospital(province="北京", city="北京")
        r = await client.get("/api/v1/hospitals/filters?province=北京")
        assert r.status_code == 200

    async def test_nearest_region_no_data(self, client):
        r = await client.get(
            "/api/v1/hospitals/nearest-region?latitude=39.9&longitude=116.4"
        )
        assert r.status_code == 200
        assert r.json() == {"province": None, "city": None}

    async def test_nearest_region_found(self, client, seed_hospital):
        await seed_hospital(
            province="北京", city="北京", latitude=39.9, longitude=116.4
        )
        r = await client.get(
            "/api/v1/hospitals/nearest-region?latitude=39.9&longitude=116.4"
        )
        assert r.status_code == 200
        assert r.json()["province"] == "北京"

    async def test_seed_endpoint(self, client):
        r = await client.post("/api/v1/hospitals/seed")
        assert r.status_code == 200
        assert "seeded" in r.json()


# ---------------------------------------------------------------------------
# api/v1/users.py
# ---------------------------------------------------------------------------
class TestUsersAPI:
    async def test_get_me_and_update_me(self, authenticated_client):
        r = await authenticated_client.get("/api/v1/users/me")
        assert r.status_code == 200
        r2 = await authenticated_client.put(
            "/api/v1/users/me", json={"display_name": "Aaa"}
        )
        assert r2.status_code == 200
        assert r2.json()["display_name"] == "Aaa"

    async def test_switch_role_requires_multi_role(self, authenticated_client):
        r = await authenticated_client.post(
            "/api/v1/users/me/switch-role", json={"role": "companion"}
        )
        # patient-only user → 400
        assert r.status_code == 400

    async def test_delete_account(self, authenticated_client):
        r = await authenticated_client.delete("/api/v1/users/me")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# api/v1/admin/__init__.py – admin endpoints
# ---------------------------------------------------------------------------
class TestAdminAPI:
    async def test_non_admin_no_token_returns_422(self, authenticated_client):
        """Patient hitting admin endpoint without X-Admin-Token → 422."""
        r = await authenticated_client.get("/api/v1/admin/orders")
        assert r.status_code == 422

    async def test_admin_list_orders(self, admin_client):
        r = await admin_client.get("/api/v1/admin/orders")
        assert r.status_code == 200
        assert "items" in r.json()

    async def test_admin_list_users(self, admin_client):
        r = await admin_client.get("/api/v1/admin/users?page=1&page_size=10")
        assert r.status_code == 200

    async def test_admin_force_status_not_found(self, admin_client):
        r = await admin_client.post(
            f"/api/v1/admin/orders/{uuid4()}/force-status",
            json={"status": "expired", "reason": "test"},
        )
        assert r.status_code == 404

    async def test_admin_force_status_invalid(self, admin_client, seed_hospital, seed_order):
        async with test_session_factory() as session:
            patient = User(phone="13900090001")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id, status=OrderStatus.created)
        r = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            json={"status": "BAD", "reason": "test"},
        )
        assert r.status_code == 400

    async def test_admin_force_status_ok(self, admin_client, seed_hospital, seed_order):
        async with test_session_factory() as session:
            patient = User(phone="13900090002")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id, status=OrderStatus.created)
        r = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            json={"status": "expired", "reason": "test"},
        )
        assert r.status_code == 200
        assert r.json()["new_status"] == "expired"

    async def test_admin_refund_not_found(self, admin_client):
        r = await admin_client.post(
            f"/api/v1/admin/orders/{uuid4()}/refund",
            json={"amount": "1.00", "reason": "test"},
        )
        assert r.status_code == 404

    async def test_admin_refund_ok(
        self, admin_client, seed_hospital, seed_order, seed_payment
    ):
        async with test_session_factory() as session:
            patient = User(phone="13900090003")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id, hospital.id, status=OrderStatus.completed, price=200.0
        )
        await seed_payment(
            order.id, patient.id, amount=200.0, status="success"
        )
        r = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            json={"amount": "100.00", "reason": "test"},
        )
        assert r.status_code == 200
        assert r.json()["refund_amount"] == "100.00"

    async def test_admin_refund_failure(
        self, admin_client, seed_hospital, seed_order
    ):
        async with test_session_factory() as session:
            patient = User(phone="13900090004")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id, hospital.id, status=OrderStatus.completed, price=200.0
        )
        # No prior pay → refund fails
        r = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            json={"amount": "50.00", "reason": "test"},
        )
        assert r.status_code == 400

    async def test_disable_enable_user(self, admin_client):
        async with test_session_factory() as session:
            u = User(phone="13900090005")
            session.add(u)
            await session.commit()
            await session.refresh(u)
        r = await admin_client.post(
            f"/api/v1/admin/users/{u.id}/disable",
            json={"reason": "test"},
        )
        assert r.status_code == 200
        r2 = await admin_client.post(f"/api/v1/admin/users/{u.id}/enable")
        assert r2.status_code == 200
        # Not-found branch
        r3 = await admin_client.post(
            f"/api/v1/admin/users/{uuid4()}/disable",
            json={"reason": "test"},
        )
        assert r3.status_code == 404
        r4 = await admin_client.post(f"/api/v1/admin/users/{uuid4()}/enable")
        assert r4.status_code == 404


# ---------------------------------------------------------------------------
# api/v1/payment_callback.py – wechat / refund callbacks
# ---------------------------------------------------------------------------
class TestPaymentCallbackAPI:
    async def test_pay_callback_missing_trade_no(self, client):
        """Empty body → mock provider verify returns {} → no trade_no → success."""
        r = await client.post("/api/v1/payments/wechat/callback", content=b"")
        assert r.status_code == 200

    async def test_pay_callback_full_flow(
        self, client, seed_hospital, seed_order, seed_payment
    ):
        """Mock provider parses JSON body; record + handle_pay_callback executed."""
        async with test_session_factory() as session:
            patient = User(phone="13900100001")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id, hospital.id, status=OrderStatus.created, price=100.0
        )
        await seed_payment(
            order.id, patient.id, amount=100.0, status="pending"
        )
        # Patch the trade_no after creation so callback can locate it
        async with test_session_factory() as session:
            from sqlalchemy import update as _upd
            await session.execute(
                _upd(Payment).where(Payment.order_id == order.id).values(
                    trade_no="TXNCB1"
                )
            )
            await session.commit()

        body = json.dumps(
            {
                "transaction_id": "TXNCB1",
                "out_trade_no": order.order_number,
                "trade_state": "SUCCESS",
            }
        ).encode()
        r1 = await client.post("/api/v1/payments/wechat/callback", content=body)
        assert r1.status_code == 200
        # duplicate
        r2 = await client.post("/api/v1/payments/wechat/callback", content=body)
        assert r2.status_code == 200

    async def test_pay_callback_late_after_expire_triggers_refund(
        self, client, seed_hospital, seed_order, seed_payment
    ):
        """Order already expired but payment now succeeds → auto-refund branch."""
        async with test_session_factory() as session:
            patient = User(phone="13900100002")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id, hospital.id, status=OrderStatus.expired, price=100.0
        )
        await seed_payment(
            order.id, patient.id, amount=100.0, status="pending"
        )
        async with test_session_factory() as session:
            from sqlalchemy import update as _upd
            await session.execute(
                _upd(Payment).where(Payment.order_id == order.id).values(
                    trade_no="TXNCB2"
                )
            )
            await session.commit()
        body = json.dumps(
            {
                "transaction_id": "TXNCB2",
                "out_trade_no": order.order_number,
                "trade_state": "SUCCESS",
            }
        ).encode()
        r = await client.post("/api/v1/payments/wechat/callback", content=body)
        assert r.status_code == 200

    async def test_pay_callback_verify_rejected(self, client):
        """verify_callback raises BadRequest → fail_response."""
        from app.exceptions import BadRequestException
        from app.services.payment_service import MockPaymentProvider

        with patch.object(
            MockPaymentProvider,
            "verify_callback",
            AsyncMock(side_effect=BadRequestException("bad sig")),
        ):
            r = await client.post(
                "/api/v1/payments/wechat/callback", content=b"{}"
            )
        assert r.status_code == 200
        assert r.json()["code"] == "FAIL"

    async def test_pay_callback_unhandled_exc(self, client):
        """Provider raises non-BadRequest → fail_response (outer except)."""
        from app.services.payment_service import MockPaymentProvider

        with patch.object(
            MockPaymentProvider,
            "verify_callback",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            r = await client.post(
                "/api/v1/payments/wechat/callback", content=b"{}"
            )
        assert r.status_code == 200
        assert r.json()["code"] == "FAIL"

    async def test_refund_callback_missing_id(self, client):
        r = await client.post(
            "/api/v1/payments/wechat/refund-callback", content=b"{}"
        )
        assert r.status_code == 200

    async def test_refund_callback_full(self, client, seed_hospital, seed_order, seed_payment):
        async with test_session_factory() as session:
            patient = User(phone="13900100003")
            session.add(patient)
            await session.commit()
            await session.refresh(patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id, hospital.id, status=OrderStatus.completed, price=100.0
        )
        await seed_payment(
            order.id,
            patient.id,
            amount=100.0,
            payment_type="refund",
            status="pending",
        )
        async with test_session_factory() as session:
            from sqlalchemy import update as _upd
            await session.execute(
                _upd(Payment).where(Payment.order_id == order.id).values(
                    refund_id="RF-CB1"
                )
            )
            await session.commit()
        body = json.dumps(
            {
                "out_refund_no": "RF-CB1",
                "out_trade_no": order.order_number,
                "refund_status": "SUCCESS",
            }
        ).encode()
        r = await client.post(
            "/api/v1/payments/wechat/refund-callback", content=body
        )
        assert r.status_code == 200
        # duplicate
        r2 = await client.post(
            "/api/v1/payments/wechat/refund-callback", content=body
        )
        assert r2.status_code == 200

    async def test_refund_callback_verify_rejected(self, client):
        from app.exceptions import BadRequestException
        from app.services.payment_service import MockPaymentProvider

        with patch.object(
            MockPaymentProvider,
            "verify_callback",
            AsyncMock(side_effect=BadRequestException("nope")),
        ):
            r = await client.post(
                "/api/v1/payments/wechat/refund-callback", content=b"{}"
            )
        assert r.status_code == 200 and r.json()["code"] == "FAIL"


# ---------------------------------------------------------------------------
# WeChat payment provider – sign / mock / decrypt branches
# ---------------------------------------------------------------------------
class TestWechatPaymentProvider:
    def _make(self, monkeypatch, **kw):
        from app.config import settings as s
        from app.services.providers.payment.wechat import WechatPaymentProvider

        for k, v in kw.items():
            monkeypatch.setattr(s, k, v, raising=False)
        return WechatPaymentProvider()

    async def test_create_order_mock_path(self, monkeypatch):
        """No credentials → mock prepay payload."""
        from app.services.providers.payment.base import OrderDTO

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="",
            wechat_pay_api_key_v3="",
            wechat_app_id="wxApp",
            wechat_pay_cert_serial="",
            wechat_pay_private_key_path="",
            wechat_pay_notify_url="",
            wechat_pay_platform_cert_path="",
        )
        res = await prov.create_order(
            OrderDTO(
                order_number="YLAQQ1",
                amount_yuan=10.0,
                description="d",
                openid="oid",
            )
        )
        assert res["status"] == "success"
        assert res["sign_params"]["appId"] == "wxApp"

    async def test_refund_mock_path(self, monkeypatch):
        from app.services.providers.payment.base import RefundDTO

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="",
            wechat_pay_api_key_v3="",
        )
        r = await prov.refund(
            RefundDTO(
                refund_id="RID-1",
                trade_no="TX-1",
                total_yuan=10.0,
                refund_yuan=5.0,
            )
        )
        assert r == {"refund_id": "RID-1", "status": "success"}

    async def test_verify_callback_mock_json_path(self, monkeypatch):
        prov = self._make(
            monkeypatch, wechat_pay_mch_id="", wechat_pay_api_key_v3=""
        )
        out = await prov.verify_callback({}, b'{"a": 1}')
        assert out == {"a": 1}

    async def test_verify_callback_mock_invalid_json(self, monkeypatch):
        prov = self._make(
            monkeypatch, wechat_pay_mch_id="", wechat_pay_api_key_v3=""
        )
        out = await prov.verify_callback({}, b"not-json")
        assert out["verified"] is True

    async def test_query_not_implemented(self, monkeypatch):
        from app.services.providers.payment.base import OrderDTO

        prov = self._make(
            monkeypatch, wechat_pay_mch_id="", wechat_pay_api_key_v3=""
        )
        with pytest.raises(NotImplementedError):
            await prov.query(
                OrderDTO(
                    order_number="x",
                    amount_yuan=1.0,
                    description="d",
                    openid="o",
                )
            )

    async def test_close_order_mock(self, monkeypatch):
        prov = self._make(
            monkeypatch, wechat_pay_mch_id="", wechat_pay_api_key_v3=""
        )
        assert await prov.close_order("X") == {"status": "success"}

    async def test_close_order_with_creds_not_implemented(self, monkeypatch):
        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
        )
        with pytest.raises(NotImplementedError):
            await prov.close_order("X")

    async def test_verify_signature_missing_headers(self, monkeypatch):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
        )
        with pytest.raises(BadRequestException):
            await prov.verify_callback({}, b"{}")

    async def test_verify_signature_bad_timestamp_format(self, monkeypatch):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
        )
        headers = {
            "wechatpay-timestamp": "abc",
            "wechatpay-nonce": "n",
            "wechatpay-signature": "x",
            "wechatpay-serial": "s",
        }
        with pytest.raises(BadRequestException):
            await prov.verify_callback(headers, b"{}")

    async def test_verify_signature_replay(self, monkeypatch):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
        )
        headers = {
            "wechatpay-timestamp": "1",
            "wechatpay-nonce": "n",
            "wechatpay-signature": "x",
            "wechatpay-serial": "s",
        }
        with pytest.raises(BadRequestException):
            await prov.verify_callback(headers, b"{}")

    async def test_load_platform_cert_no_path(self, monkeypatch):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
            wechat_pay_platform_cert_path="",
        )
        with pytest.raises(BadRequestException):
            prov._load_platform_cert("serial1")

    async def test_load_platform_cert_missing_file(self, monkeypatch, tmp_path):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
            wechat_pay_platform_cert_path=str(tmp_path / "no_such.pem"),
        )
        with pytest.raises(BadRequestException):
            prov._load_platform_cert("serial-missing")

    async def test_decrypt_resource_missing_ciphertext(self, monkeypatch):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
        )
        with pytest.raises(BadRequestException):
            prov._decrypt_resource({"ciphertext": "", "nonce": "n"})

    async def test_decrypt_resource_bad_key_len(self, monkeypatch):
        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="short",
        )
        with pytest.raises(BadRequestException):
            prov._decrypt_resource(
                {"ciphertext": "AAAA", "nonce": "n", "associated_data": ""}
            )

    async def test_decrypt_resource_decrypt_fail(self, monkeypatch):
        import base64

        from app.exceptions import BadRequestException

        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
        )
        with pytest.raises(BadRequestException):
            prov._decrypt_resource(
                {
                    "ciphertext": base64.b64encode(b"not-a-real-cipher").decode(),
                    "nonce": "abcdefghijkl",
                    "associated_data": "",
                }
            )

    async def test_rsa_sign_no_key(self, monkeypatch):
        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="",
            wechat_pay_api_key_v3="",
            wechat_pay_private_key_path="",
        )
        assert prov._rsa_sign("msg") == "mock_rsa_signature"

    async def test_rsa_sign_load_failure(self, monkeypatch):
        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
            wechat_pay_private_key_path="/nope/key.pem",
        )
        assert prov._rsa_sign("msg") == "sign_error"

    async def test_build_auth_header(self, monkeypatch):
        prov = self._make(
            monkeypatch,
            wechat_pay_mch_id="MCH",
            wechat_pay_api_key_v3="K" * 32,
            wechat_pay_cert_serial="CERT",
        )
        h = prov._build_auth_header("POST", "/x", {"a": 1})
        assert "WECHATPAY2-SHA256-RSA2048" in h["Authorization"]
        assert h["Content-Type"] == "application/json"
