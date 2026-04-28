"""
WalletService.get_summary integration tests — D-050 follow-up.

Goal: prove that once production write paths are wired and a companion
has ledger rows, ``get_summary`` reads from the ledger (not the
legacy OrderRepository.sum_earnings_by_companion fallback).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.user import UserRole
from app.models.wallet_ledger import WalletLedgerDirection
from app.services.wallet import WalletService
from app.services.wallet_ledger_writer import WalletLedgerWriter
from tests.conftest import test_session_factory


@pytest.mark.asyncio
class TestGetSummaryLedgerSource:
    async def test_companion_with_ledger_uses_ledger_sum(self, seed_user):
        companion = await seed_user(phone="13900000401", role=UserRole.companion)
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            await w.record_pay_success(
                user_id=companion.id, order_id=None,
                provider_txn_id="LDG-1", amount=Decimal("199.00"),
            )
            await w.record_pay_success(
                user_id=companion.id, order_id=None,
                provider_txn_id="LDG-2", amount=Decimal("50.50"),
            )
            await w.record_refund_success(
                user_id=companion.id, order_id=None,
                provider_txn_id="LDG-1", amount=Decimal("99.00"),
            )
            await s.commit()

        async with test_session_factory() as s:
            summary = await WalletService(s).get_summary(companion)

        # 199 + 50.50 - 99 = 150.50
        assert summary["balance"] == Decimal("150.50")
        assert summary["total_income"] == Decimal("150.50")
        assert summary["withdrawn"] == Decimal("0.00")

    async def test_companion_with_empty_ledger_falls_back(self, seed_user):
        """No ledger row → fallback to legacy OrderRepository aggregation (returns 0)."""
        companion = await seed_user(phone="13900000402", role=UserRole.companion)
        async with test_session_factory() as s:
            summary = await WalletService(s).get_summary(companion)
        # No orders + no ledger → fallback returns 0
        assert summary["balance"] == Decimal("0.00")

    async def test_non_companion_returns_zeros(self, seed_user):
        patient = await seed_user(phone="13800000401", role=UserRole.patient)
        async with test_session_factory() as s:
            summary = await WalletService(s).get_summary(patient)
        assert summary["balance"] == Decimal("0.00")
        assert summary["total_income"] == Decimal("0.00")

    async def test_adjust_in_increases_balance(self, seed_user):
        companion = await seed_user(phone="13900000403", role=UserRole.companion)
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            await w.record_manual_adjustment(
                user_id=companion.id, order_id=None,
                amount=Decimal("25"), direction=WalletLedgerDirection.in_,
                operator="ops", reason="客诉补偿",
            )
            await s.commit()

        async with test_session_factory() as s:
            summary = await WalletService(s).get_summary(companion)
        assert summary["balance"] == Decimal("25.00")

    async def test_adjust_out_decreases_balance(self, seed_user):
        companion = await seed_user(phone="13900000404", role=UserRole.companion)
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            await w.record_pay_success(
                user_id=companion.id, order_id=None,
                provider_txn_id="LDG-A", amount=Decimal("100"),
            )
            await w.record_manual_adjustment(
                user_id=companion.id, order_id=None,
                amount=Decimal("30"), direction=WalletLedgerDirection.out,
                operator="ops", reason="财务对账修复",
            )
            await s.commit()

        async with test_session_factory() as s:
            summary = await WalletService(s).get_summary(companion)
        assert summary["balance"] == Decimal("70.00")
