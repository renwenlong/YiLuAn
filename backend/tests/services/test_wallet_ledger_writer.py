"""
Wallet ledger writer — unit tests covering pay / refund / manual adjust paths.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)
from app.services.wallet_ledger_writer import (
    LedgerWriteResult,
    WalletLedgerWriter,
)
from sqlalchemy import select
from tests.conftest import test_session_factory


@pytest.mark.asyncio
class TestRecordPaySuccess:
    async def test_appends_in_pay_row(self):
        async with test_session_factory() as s:
            uid = uuid.uuid4()
            r = await WalletLedgerWriter(s).record_pay_success(
                user_id=uid,
                order_id=uuid.uuid4(),
                provider_txn_id="W-PAY-001",
                amount=Decimal("199.00"),
            )
            await s.commit()
            assert r.written
            row = (await s.execute(select(WalletLedger).where(WalletLedger.id == r.ledger_id))).scalar_one()
            assert row.direction == WalletLedgerDirection.in_
            assert row.reason == WalletLedgerReason.pay
            assert row.amount == Decimal("199.00")

    async def test_idempotent_duplicate_skips_silently(self):
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            uid = uuid.uuid4()
            r1 = await w.record_pay_success(
                user_id=uid, order_id=None,
                provider_txn_id="DUP-1", amount=Decimal("10.00"),
            )
            r2 = await w.record_pay_success(
                user_id=uid, order_id=None,
                provider_txn_id="DUP-1", amount=Decimal("10.00"),
            )
            await s.commit()
            assert r1.written is True
            assert r2.written is False
            assert r2.skipped_reason == "duplicate"
            assert r2.ledger_id == r1.ledger_id

    async def test_skips_empty_provider_txn_id(self):
        async with test_session_factory() as s:
            r = await WalletLedgerWriter(s).record_pay_success(
                user_id=uuid.uuid4(),
                order_id=None,
                provider_txn_id="",
                amount=Decimal("1.00"),
            )
            assert r.written is False
            assert r.skipped_reason == "empty_provider_txn_id"

    async def test_quantizes_amount_to_2_decimals(self):
        async with test_session_factory() as s:
            r = await WalletLedgerWriter(s).record_pay_success(
                user_id=uuid.uuid4(), order_id=None,
                provider_txn_id="Q-1", amount=Decimal("1.005"),
            )
            await s.commit()
            row = (await s.execute(select(WalletLedger).where(WalletLedger.id == r.ledger_id))).scalar_one()
            # 1.005 quantize ROUND_HALF_EVEN → 1.00 on Python default
            assert row.amount in (Decimal("1.00"), Decimal("1.01"))


@pytest.mark.asyncio
class TestRecordRefundSuccess:
    async def test_appends_out_refund_row(self):
        async with test_session_factory() as s:
            uid = uuid.uuid4()
            r = await WalletLedgerWriter(s).record_refund_success(
                user_id=uid, order_id=uuid.uuid4(),
                provider_txn_id="R-001", amount=Decimal("50.00"),
            )
            await s.commit()
            assert r.written
            row = (await s.execute(select(WalletLedger).where(WalletLedger.id == r.ledger_id))).scalar_one()
            assert row.direction == WalletLedgerDirection.out
            assert row.reason == WalletLedgerReason.refund

    async def test_pay_and_refund_share_provider_id_but_different_direction(self):
        """Same trade_no can appear once per direction (pay in / refund out)."""
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            uid = uuid.uuid4()
            r1 = await w.record_pay_success(
                user_id=uid, order_id=None,
                provider_txn_id="SAME-1", amount=Decimal("100"),
            )
            r2 = await w.record_refund_success(
                user_id=uid, order_id=None,
                provider_txn_id="SAME-1", amount=Decimal("100"),
            )
            await s.commit()
            assert r1.written and r2.written
            assert r1.ledger_id != r2.ledger_id


@pytest.mark.asyncio
class TestRecordManualAdjustment:
    async def test_happy_path_appends_adjust_row(self):
        async with test_session_factory() as s:
            r = await WalletLedgerWriter(s).record_manual_adjustment(
                user_id=uuid.uuid4(),
                order_id=None,
                amount=Decimal("12.34"),
                direction=WalletLedgerDirection.in_,
                operator="ops-alice",
                reason="客诉补偿",
            )
            await s.commit()
            assert r.written
            row = (await s.execute(select(WalletLedger).where(WalletLedger.id == r.ledger_id))).scalar_one()
            assert row.reason == WalletLedgerReason.adjust
            assert row.provider_txn_id.startswith("ADJ-ops-alice-")

    async def test_rejects_zero_amount(self):
        async with test_session_factory() as s:
            with pytest.raises(ValueError, match="amount must be > 0"):
                await WalletLedgerWriter(s).record_manual_adjustment(
                    user_id=uuid.uuid4(), order_id=None,
                    amount=Decimal("0"),
                    direction=WalletLedgerDirection.in_,
                    operator="ops-alice", reason="x",
                )

    async def test_rejects_negative_amount(self):
        async with test_session_factory() as s:
            with pytest.raises(ValueError):
                await WalletLedgerWriter(s).record_manual_adjustment(
                    user_id=uuid.uuid4(), order_id=None,
                    amount=Decimal("-1"),
                    direction=WalletLedgerDirection.in_,
                    operator="ops-alice", reason="x",
                )

    async def test_rejects_empty_operator(self):
        async with test_session_factory() as s:
            with pytest.raises(ValueError, match="operator"):
                await WalletLedgerWriter(s).record_manual_adjustment(
                    user_id=uuid.uuid4(), order_id=None,
                    amount=Decimal("1"),
                    direction=WalletLedgerDirection.in_,
                    operator="   ", reason="x",
                )

    async def test_rejects_empty_reason(self):
        async with test_session_factory() as s:
            with pytest.raises(ValueError, match="reason"):
                await WalletLedgerWriter(s).record_manual_adjustment(
                    user_id=uuid.uuid4(), order_id=None,
                    amount=Decimal("1"),
                    direction=WalletLedgerDirection.in_,
                    operator="ops", reason="",
                )

    async def test_operator_too_long_rejected(self):
        async with test_session_factory() as s:
            with pytest.raises(ValueError, match="<= 64"):
                await WalletLedgerWriter(s).record_manual_adjustment(
                    user_id=uuid.uuid4(), order_id=None,
                    amount=Decimal("1"),
                    direction=WalletLedgerDirection.in_,
                    operator="x" * 65, reason="ok",
                )

    async def test_explicit_provider_txn_id_used_verbatim(self):
        async with test_session_factory() as s:
            r = await WalletLedgerWriter(s).record_manual_adjustment(
                user_id=uuid.uuid4(), order_id=None,
                amount=Decimal("1"),
                direction=WalletLedgerDirection.out,
                operator="ops", reason="ok",
                provider_txn_id="EXPLICIT-KEY",
            )
            await s.commit()
            row = (await s.execute(select(WalletLedger).where(WalletLedger.id == r.ledger_id))).scalar_one()
            assert row.provider_txn_id == "EXPLICIT-KEY"
            assert row.direction == WalletLedgerDirection.out
