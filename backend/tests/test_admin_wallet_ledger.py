"""
Admin Wallet Ledger API tests — D-050 manual adjustment + read endpoint.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)
from app.services.wallet_ledger_writer import WalletLedgerWriter
from tests.conftest import test_session_factory

TOKEN_HEADERS = {"X-Admin-Token": "dev-admin-token"}
OP_A = {**TOKEN_HEADERS, "X-Admin-Operator": "ops-alice"}


@pytest.mark.asyncio
class TestManualAdjustmentAuth:
    async def test_no_token_422(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "1.00", "reason": "x"},
        )
        assert r.status_code == 422

    async def test_no_operator_header_422(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=TOKEN_HEADERS,
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "1.00", "reason": "x"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
class TestManualAdjustmentHappyPath:
    async def test_in_adjustment_appends_ledger_and_audit(
        self, client: AsyncClient
    ):
        user_id = uuid.uuid4()
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={
                "user_id": str(user_id),
                "direction": "in",
                "amount": "12.34",
                "reason": "客诉补偿 ORDER-1234",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["operator"] == "ops-alice"
        assert body["direction"] == "in"
        assert body["amount"] == "12.34"
        assert body["provider_txn_id"].startswith("ADJ-ops-alice-")

        # Ledger row exists
        async with test_session_factory() as s:
            rows = (
                await s.execute(
                    select(WalletLedger).where(WalletLedger.user_id == user_id)
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].reason == WalletLedgerReason.adjust
            assert rows[0].direction == WalletLedgerDirection.in_
            assert rows[0].amount == Decimal("12.34")

            # Audit log row exists
            audits = (
                await s.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == rows[0].id
                    )
                )
            ).scalars().all()
            assert len(audits) == 1
            assert audits[0].action == "wallet_ledger_manual_adjust"
            assert audits[0].operator == "ops-alice"

    async def test_out_adjustment_works(self, client: AsyncClient):
        user_id = uuid.uuid4()
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(user_id), "direction": "out",
                  "amount": "5.00", "reason": "demo reset"},
        )
        assert r.status_code == 200
        assert r.json()["direction"] == "out"


@pytest.mark.asyncio
class TestManualAdjustmentValidation:
    async def test_amount_zero_rejected(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "0", "reason": "x"},
        )
        assert r.status_code == 400

    async def test_amount_negative_rejected(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "-1", "reason": "x"},
        )
        assert r.status_code == 400

    async def test_invalid_amount_string_rejected(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "abc", "reason": "x"},
        )
        assert r.status_code == 400

    async def test_invalid_direction_rejected(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(uuid.uuid4()), "direction": "sideways",
                  "amount": "1", "reason": "x"},
        )
        assert r.status_code == 422

    async def test_empty_reason_rejected(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "1", "reason": ""},
        )
        assert r.status_code == 422

    async def test_reason_too_long_rejected(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/admin/wallet-ledger/adjustments",
            headers=OP_A,
            json={"user_id": str(uuid.uuid4()), "direction": "in",
                  "amount": "1", "reason": "x" * 501},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
class TestListUserLedger:
    async def test_list_empty_returns_zero(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/admin/wallet-ledger/{uuid.uuid4()}",
            headers=TOKEN_HEADERS,
        )
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    async def test_list_returns_rows_newest_first(self, client: AsyncClient):
        user_id = uuid.uuid4()
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            await w.record_pay_success(
                user_id=user_id, order_id=None,
                provider_txn_id="L-1", amount=Decimal("10"),
            )
            await w.record_refund_success(
                user_id=user_id, order_id=None,
                provider_txn_id="L-1", amount=Decimal("10"),
            )
            await s.commit()

        r = await client.get(
            f"/api/v1/admin/wallet-ledger/{user_id}", headers=TOKEN_HEADERS
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    async def test_filter_by_reason(self, client: AsyncClient):
        user_id = uuid.uuid4()
        async with test_session_factory() as s:
            w = WalletLedgerWriter(s)
            await w.record_pay_success(
                user_id=user_id, order_id=None,
                provider_txn_id="F-PAY", amount=Decimal("5"),
            )
            await w.record_manual_adjustment(
                user_id=user_id, order_id=None,
                amount=Decimal("3"), direction=WalletLedgerDirection.in_,
                operator="ops-alice", reason="补",
            )
            await s.commit()

        r = await client.get(
            f"/api/v1/admin/wallet-ledger/{user_id}?reason=adjust",
            headers=TOKEN_HEADERS,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["reason"] == "adjust"
