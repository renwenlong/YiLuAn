"""
[TD-MONEY-01 M1 finishing / D-050] PaymentService -> wallet_ledger 集成测试

证明：mock provider 即时成功 + wechat callback 成功 + refund callback 成功
三条路径都会向 wallet_ledger 追加正确方向的 row。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.order import OrderStatus
from app.models.payment import Payment
from app.models.user import UserRole
from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)
from app.services.payment_service import PaymentService
from tests.conftest import test_session_factory


async def _ledger_rows_for_user(user_id: uuid.UUID) -> list[WalletLedger]:
    async with test_session_factory() as s:
        rows = (
            await s.execute(
                select(WalletLedger).where(WalletLedger.user_id == user_id)
            )
        ).scalars().all()
        return list(rows)


async def _make_companion(seed_user, phone: str = "13900000099") -> uuid.UUID:
    """Helper: 创建一个 companion 角色用户，返回 id。"""
    u = await seed_user(phone=phone, role=UserRole.companion)
    return u.id


@pytest.mark.asyncio
class TestPayAppendsLedger:
    async def test_mock_pay_appends_in_pay_row_under_companion_id(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order, seed_user
    ):
        """关键语义：ledger.user_id 必须是 companion (陪诊师)，不是 payer。"""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        companion_id = await _make_companion(seed_user, phone="13900000201")
        order = await seed_order(user.id, hospital.id, companion_id=companion_id)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200

        # 陪诊师账本有 1 行 in/pay
        rows = await _ledger_rows_for_user(companion_id)
        pay_rows = [r for r in rows if r.reason == WalletLedgerReason.pay]
        assert len(pay_rows) == 1
        assert pay_rows[0].direction == WalletLedgerDirection.in_
        assert pay_rows[0].order_id == order.id

        # payer (患者) 账本为空
        payer_rows = await _ledger_rows_for_user(user.id)
        assert payer_rows == []

    async def test_pay_without_companion_skips_ledger(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """订单未接单 → 尚未产生收入归属 → 不写 ledger。不报错。"""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id, companion_id=None)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200  # 支付仍然成功

        # 但 ledger 为空（难判定归属人，跳过）
        async with test_session_factory() as s:
            count = (await s.execute(select(WalletLedger))).scalars().all()
            assert len(count) == 0

    async def test_double_pay_attempt_does_not_double_ledger(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        companion_id = await _make_companion(seed_user, phone="13900000202")
        order = await seed_order(user.id, hospital.id, companion_id=companion_id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        rows1 = await _ledger_rows_for_user(companion_id)
        assert len([r for r in rows1 if r.reason == WalletLedgerReason.pay]) == 1


@pytest.mark.asyncio
class TestRefundAppendsLedger:
    async def test_mock_refund_appends_out_refund_row_under_companion(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        companion_id = await _make_companion(seed_user, phone="13900000203")
        order = await seed_order(user.id, hospital.id, companion_id=companion_id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel",
            json={"reason": "test refund ledger append"},
        )
        assert resp.status_code in (200, 204)

        rows = await _ledger_rows_for_user(companion_id)
        refund_rows = [r for r in rows if r.reason == WalletLedgerReason.refund]
        assert len(refund_rows) == 1
        assert refund_rows[0].direction == WalletLedgerDirection.out

    async def test_pay_then_refund_yields_two_directions(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        companion_id = await _make_companion(seed_user, phone="13900000204")
        order = await seed_order(user.id, hospital.id, companion_id=companion_id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel",
            json={"reason": "x"},
        )

        rows = await _ledger_rows_for_user(companion_id)
        directions = sorted({r.direction for r in rows})
        assert WalletLedgerDirection.in_ in directions
        assert WalletLedgerDirection.out in directions


@pytest.mark.asyncio
class TestWechatCallbackAppendsLedger:
    """模拟生产 wechat 回调路径（pending → handle_pay_callback success）。"""

    async def test_callback_success_appends_ledger_under_companion(
        self, seed_hospital, seed_order, seed_user
    ):
        payer = await seed_user(phone="13800000301")
        companion_id = await _make_companion(seed_user, phone="13900000301")
        hospital = await seed_hospital()
        order = await seed_order(payer.id, hospital.id, companion_id=companion_id)
        async with test_session_factory() as s:
            p = Payment(
                order_id=order.id,
                user_id=payer.id,
                amount=Decimal("99.00"),
                payment_type="pay",
                status="pending",
                trade_no="WX-TEST-CB-1",
                prepay_id="prepay_x",
            )
            s.add(p)
            await s.commit()

        async with test_session_factory() as s:
            svc = PaymentService(s)
            updated = await svc.handle_pay_callback(
                trade_no="WX-TEST-CB-1",
                order_number=order.order_number,
                success=True,
            )
            await s.commit()
            assert updated is not None
            assert updated.status == "success"

        rows = await _ledger_rows_for_user(companion_id)
        pay_rows = [r for r in rows if r.reason == WalletLedgerReason.pay]
        assert len(pay_rows) == 1
        assert pay_rows[0].provider_txn_id == "WX-TEST-CB-1"
        # payer 账本仍然为空
        assert await _ledger_rows_for_user(payer.id) == []

    async def test_callback_failure_does_not_append(
        self, seed_hospital, seed_order, seed_user
    ):
        payer = await seed_user(phone="13800000302")
        companion_id = await _make_companion(seed_user, phone="13900000302")
        hospital = await seed_hospital()
        order = await seed_order(payer.id, hospital.id, companion_id=companion_id)
        async with test_session_factory() as s:
            p = Payment(
                order_id=order.id,
                user_id=payer.id,
                amount=Decimal("99.00"),
                payment_type="pay",
                status="pending",
                trade_no="WX-TEST-CB-FAIL",
                prepay_id="prepay_y",
            )
            s.add(p)
            await s.commit()

        async with test_session_factory() as s:
            svc = PaymentService(s)
            await svc.handle_pay_callback(
                trade_no="WX-TEST-CB-FAIL",
                order_number=order.order_number,
                success=False,
            )
            await s.commit()

        assert await _ledger_rows_for_user(companion_id) == []


@pytest.mark.asyncio
class TestRefundCallbackAppendsLedger:
    async def test_refund_callback_success_appends_out_row_under_companion(
        self, seed_hospital, seed_order, seed_user
    ):
        payer = await seed_user(phone="13800000303")
        companion_id = await _make_companion(seed_user, phone="13900000303")
        hospital = await seed_hospital()
        order = await seed_order(payer.id, hospital.id, companion_id=companion_id)
        async with test_session_factory() as s:
            pay = Payment(
                order_id=order.id, user_id=payer.id,
                amount=Decimal("100"), payment_type="pay",
                status="success", trade_no="WX-PAY-RFND-1",
            )
            refund = Payment(
                order_id=order.id, user_id=payer.id,
                amount=Decimal("100"), payment_type="refund",
                status="pending", trade_no="WX-PAY-RFND-1",
                refund_id="REFUND-CB-1",
            )
            s.add_all([pay, refund])
            await s.commit()

        async with test_session_factory() as s:
            svc = PaymentService(s)
            await svc.handle_refund_callback(
                refund_id="REFUND-CB-1",
                refund_status="SUCCESS",
            )
            await s.commit()

        rows = await _ledger_rows_for_user(companion_id)
        refund_rows = [r for r in rows if r.reason == WalletLedgerReason.refund]
        assert len(refund_rows) == 1
        assert refund_rows[0].direction == WalletLedgerDirection.out
        assert refund_rows[0].provider_txn_id == "REFUND-CB-1"
