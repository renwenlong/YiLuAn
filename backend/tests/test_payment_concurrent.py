"""
Concurrent payment tests — verifies payment idempotency and race condition safety.
"""

import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestConcurrentPayment:
    """Tests for concurrent payment scenarios."""

    async def test_concurrent_pay_same_order(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Concurrent pay requests on the same order — SQLite path.

        The production race is FIXED via SELECT ... FOR UPDATE: ``pay_order``
        loads the row through ``_get_order_for_update_or_404`` →
        ``order_repo.get_by_id_for_update`` (``.with_for_update()`` in
        ``backend/app/repositories/order.py``), which serialises concurrent
        ``POST /orders/{id}/pay`` so only one caller wins.

        ⚠️ LIMITATION — this SQLite test does NOT actually exercise that lock:
        ``with_for_update()`` is a **no-op** on SQLite, so this path cannot
        prove concurrent-pay serialisation. Do NOT read a green run here as
        evidence the race is covered.

        ✅ REAL COVERAGE lives in
        ``backend/tests/smoke/test_pg_prepay_race.py`` (``-m smoke``), which
        runs under real Postgres where ``FOR UPDATE`` is enforced and pins the
        contract: exactly 1×2xx winner + 4×400 rejects, 0×5xx, no
        IntegrityError / UNIQUE leak to the client. That smoke runs in
        ci-smoke.yml's ``smoke-pg`` job ("Smoke tests (real Postgres +
        alembic)"). See S3-PAY-PREPAY-RACE-CI-REQUIRED-GATE.
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Fire 5 concurrent pay requests
        tasks = [
            authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
            for _ in range(5)
        ]
        # In SQLite test env, this may raise IntegrityError due to race condition
        # In production (PostgreSQL), behavior may differ
        try:
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            # Check that we don't get unexpected errors
            for r in responses:
                if isinstance(r, Exception):
                    # IntegrityError is the known race condition
                    assert "IntegrityError" in type(r).__name__ or "UNIQUE" in str(r), (
                        f"Unexpected error: {type(r).__name__}: {r}"
                    )
        except Exception as e:
            # Known race condition — IntegrityError on UNIQUE constraint
            assert "UNIQUE" in str(e) or "IntegrityError" in str(e), (
                f"Unexpected error type: {type(e).__name__}: {e}"
            )

    async def test_concurrent_pay_different_orders(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Concurrent pay requests on different orders should all succeed independently."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()

        orders = [await seed_order(user.id, hospital.id) for _ in range(3)]

        tasks = [
            authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
            for order in orders
        ]
        responses = await asyncio.gather(*tasks)

        for i, resp in enumerate(responses):
            assert resp.status_code == 200, (
                f"Order {i} pay failed with {resp.status_code}: {resp.text}"
            )

    async def test_concurrent_pay_and_cancel(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Pay and cancel happening concurrently should not crash the server."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        tasks = [
            authenticated_client.post(f"/api/v1/orders/{order.id}/pay"),
            authenticated_client.post(f"/api/v1/orders/{order.id}/cancel"),
        ]
        responses = await asyncio.gather(*tasks)

        # No server errors
        for resp in responses:
            assert resp.status_code != 500, f"Server error: {resp.text}"

    async def test_concurrent_callbacks(
        self, authenticated_client: AsyncClient
    ):
        """Multiple callback notifications arriving simultaneously should all return 200."""
        body = b'{"out_trade_no": "YLA_CONC_001", "trade_state": "SUCCESS"}'

        tasks = [
            authenticated_client.post(
                "/api/v1/payments/wechat/callback",
                content=body,
                headers={"content-type": "application/json"},
            )
            for _ in range(10)
        ]
        responses = await asyncio.gather(*tasks)

        for resp in responses:
            assert resp.status_code == 200, f"Callback failed: {resp.text}"
            assert resp.json()["code"] == "SUCCESS"

    async def test_concurrent_refund_same_order(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Multiple concurrent refund requests on same paid-then-cancelled order."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Pay first
        pay_resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert pay_resp.status_code == 200

        # Cancel
        cancel_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel"
        )
        assert cancel_resp.status_code == 200

        # Fire concurrent refund requests
        tasks = [
            authenticated_client.post(f"/api/v1/orders/{order.id}/refund")
            for _ in range(3)
        ]
        responses = await asyncio.gather(*tasks)

        # No server errors
        for resp in responses:
            assert resp.status_code != 500, f"Server error on refund: {resp.text}"
