"""
Payment callback **阻断级**（blocker）tests — P1-7 / Action #7.

These scenarios complement ``test_payment_callback_idempotency.py``.
Each one represents a real-world edge case that, if the test fails,
should be treated as a release blocker:

  A1. 乱序回调           —— refund SUCCESS arrives before pay SUCCESS,
                            terminal state must not be flipped back.
  A2. 跨订单串号         —— transaction_id of order A delivered against
                            order B's out_trade_no — must be rejected.
  A3. 超大延迟回调       —— pay SUCCESS arrives after the order has been
                            expired/cancelled. Pay row must NOT silently
                            re-activate the order; refund row stays.
  A4. 签名替换攻击       —— legit signature path + tampered amount/body —
                            verifier MUST cover the entire body.
  A5. provider 切换       —— a (mock, txn=X) log row must NOT block a
                            (wechat, txn=X) row from being inserted —
                            ``provider`` is part of the unique key.

Constraints
-----------
* Only adds tests; never touches business code.
* Findings of real bugs are recorded in ``docs/TECH_DEBT.md`` rather
  than fixed inline (per task spec).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.exceptions import BadRequestException
from app.models.order import OrderStatus
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from app.services.payment_service import PaymentService
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _callback_body(out_trade_no: str, transaction_id: str, trade_state: str = "SUCCESS") -> bytes:
    return (
        f'{{"out_trade_no": "{out_trade_no}", '
        f'"transaction_id": "{transaction_id}", '
        f'"trade_state": "{trade_state}"}}'
    ).encode()


# ---------------------------------------------------------------------------
# A1. Out-of-order callbacks — refund-then-pay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOutOfOrderCallback:
    """If a refund-style callback (or terminal failure) arrives, then a
    *late* SUCCESS pay callback for the same trade_no shows up, the
    Payment row's terminal state must not be reverted to ``success``.

    The PaymentService defensively short-circuits when status is in
    {success, failed} — we explicitly verify that contract here.
    """

    async def test_late_pay_success_after_failed_does_not_revert(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")

        # Force the pay row into "failed" terminal state (e.g. the
        # provider eventually told us the user abandoned the flow).
        async with test_session_factory() as s:
            row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            row.status = "failed"
            trade_no = row.trade_no
            await s.commit()

        # A LATE success callback now arrives for the same trade_no.
        body = _callback_body(trade_no, trade_no, "SUCCESS")
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        # Endpoint always 200s towards the PSP.
        assert resp.status_code == 200

        # State must remain failed — terminal-state guard in
        # PaymentService.handle_pay_callback.
        async with test_session_factory() as s:
            row_after = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
        assert row_after.status == "failed", (
            "Late SUCCESS callback must NOT overwrite a terminal 'failed' "
            "state (would silently double-charge the user from the order's "
            "perspective)."
        )


# ---------------------------------------------------------------------------
# A2. Cross-order transaction-id contamination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCrossOrderContamination:
    """Order A is paid (trade_no=TXA). A buggy/malicious caller posts a
    callback that *claims* to be TXA but lists Order B's out_trade_no.

    The current implementation routes purely by ``trade_no`` (which
    correctly belongs to Order A). Order B's row must be untouched.
    """

    async def test_cross_order_callback_does_not_touch_other_order(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order_a = await seed_order(user.id, hospital.id)
        order_b = await seed_order(user.id, hospital.id)

        # Pay both — each gets its own trade_no.
        await authenticated_client.post(f"/api/v1/orders/{order_a.id}/pay")
        await authenticated_client.post(f"/api/v1/orders/{order_b.id}/pay")

        async with test_session_factory() as s:
            pay_a = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order_a.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            pay_b = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order_b.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            tx_a, tx_b = pay_a.trade_no, pay_b.trade_no
            assert tx_a != tx_b
            # Force pay_a back to pending so we can detect a wrongful flip
            # to "success" caused by routing the cross-order callback.
            pay_a.status = "pending"
            pay_b.status = "pending"
            await s.commit()

        # Hostile callback: transaction_id of A, but out_trade_no of B.
        body = _callback_body(
            out_trade_no=order_b.order_number,
            transaction_id=tx_a,
            trade_state="SUCCESS",
        )
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

        # Routing key is trade_no (== tx_a) — so order A's payment may
        # legitimately flip to success. Order B MUST NOT be touched.
        async with test_session_factory() as s:
            pay_b_after = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order_b.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
        assert pay_b_after.status == "pending", (
            "Cross-order contamination: callback with TXA but out_trade_no=B "
            "must not flip Order B's payment status."
        )


# ---------------------------------------------------------------------------
# A3. Late callback after order is expired/cancelled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLateCallbackAfterExpiredOrder:
    """If the order has already been marked ``expired`` by the scheduled
    job and a SUCCESS callback finally arrives, the order must not be
    silently re-activated. The pay record's *terminal* state guards
    against this; we additionally assert that the order itself remains
    expired (i.e. no implicit accept/in_progress flip).
    """

    async def test_callback_after_expired_does_not_reactivate(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")

        # TD-PAY-01 (now active): the scheduler runs while the pay row is
        # still pending and the order is past its expires_at. The new
        # contract is that check_expired_orders marks the pay row 'failed'
        # itself — no manual fixture pre-flip is needed any more.
        from datetime import datetime, timedelta, timezone as _tz
        async with test_session_factory() as s:
            from app.models.order import Order as OrderModel
            row_o = (
                await s.execute(
                    select(OrderModel).where(OrderModel.id == order.id)
                )
            ).scalar_one()
            row_o.expires_at = datetime.now(_tz.utc) - timedelta(hours=1)
            row_pay = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            trade_no = row_pay.trade_no
            # Mock provider returns success immediately; force the row
            # back to pending so we can exercise the scheduler path.
            row_pay.status = "pending"
            await s.commit()

        async with test_session_factory() as s:
            from app.services.order import OrderService
            svc = OrderService(s)
            await svc.check_expired_orders()
            await s.commit()

        # Late SUCCESS callback arrives.
        body = _callback_body(trade_no, trade_no, "SUCCESS")
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

        async with test_session_factory() as s:
            from app.models.order import Order as OrderModel
            row_o = (
                await s.execute(
                    select(OrderModel).where(OrderModel.id == order.id)
                )
            ).scalar_one()
            row_pay = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()

        assert row_o.status == OrderStatus.expired, (
            "Order in expired state must NEVER be flipped back by a late "
            "pay callback."
        )
        assert row_pay.status == "failed", (
            "check_expired_orders must mark the pay row 'failed' when the "
            "order expires (TD-PAY-01)."
        )

    async def test_callback_after_expired_is_logged_for_audit(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """Even when state is not flipped, the late callback must leave
        an audit row so ops can later trigger a manual refund.
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")

        async with test_session_factory() as s:
            from app.models.order import Order as OrderModel
            row_o = (
                await s.execute(
                    select(OrderModel).where(OrderModel.id == order.id)
                )
            ).scalar_one()
            row_o.status = OrderStatus.expired
            row_pay = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            trade_no = row_pay.trade_no
            await s.commit()

        late_txn = f"LATE_AUDIT_{trade_no}"
        body = _callback_body(trade_no, late_txn, "SUCCESS")
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

        async with test_session_factory() as s:
            log = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == late_txn
                    )
                )
            ).scalar_one_or_none()
        assert log is not None, (
            "Late callback must persist an audit row even if no business "
            "state change happened."
        )


# ---------------------------------------------------------------------------
# A4. Tampered-body / signature-replacement attack
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSignatureCoversFullBody:
    """If a real (production) verifier ever ignores a portion of the
    body (e.g. the ``amount`` field), an attacker can lift a legitimate
    signature and substitute a smaller refund amount. The contract here
    is: ``verify_callback`` must fail closed on ANY body mutation.

    We model this by using a verifier that:
      * accepts the original body (legit signature).
      * raises on the tampered body (signature mismatch).

    If this test ever starts passing without raising, the contract is
    being violated — release blocker.
    """

    async def test_tampered_body_must_be_rejected(
        self,
        authenticated_client: AsyncClient,
    ):
        legit_body = b'{"out_trade_no":"YLA-A4","transaction_id":"TX-A4","trade_state":"SUCCESS","amount":29900}'
        tampered_body = legit_body.replace(b'"amount":29900', b'"amount":1')
        assert tampered_body != legit_body

        # Verifier mock: only the *exact* legit body validates; anything
        # else raises (this is what a real HMAC verifier would do).
        async def strict_verify(headers, body):
            if body != legit_body:
                raise BadRequestException("微信回调签名验证失败")
            import json as _json
            return _json.loads(body.decode())

        with patch(
            "app.services.providers.payment.mock.MockPaymentProvider.verify_callback",
            side_effect=strict_verify,
        ):
            resp = await authenticated_client.post(
                "/api/v1/payments/wechat/callback",
                content=tampered_body,
                headers={"content-type": "application/json"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "FAIL", (
            "Tampered body must yield code=FAIL — verifier must hash the "
            "ENTIRE request body, not a subset."
        )

        # And no idempotency log row should have been written.
        async with test_session_factory() as s:
            logs = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.out_trade_no == "YLA-A4"
                    )
                )
            ).scalars().all()
        assert logs == [], (
            "Rejected (bad-sig) callbacks must NOT leak audit rows — "
            "otherwise an attacker can poison the idempotency table."
        )


# ---------------------------------------------------------------------------
# A5. Provider switch: same txn id under different providers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestProviderIsPartOfIdempotencyKey:
    """The migration day from mock → wechat: a ``(mock, TXN_X)`` log row
    pre-existing in the DB must NOT be misread as a duplicate of an
    incoming ``(wechat, TXN_X)`` callback. Provider is part of the
    composite uniqueness key.
    """

    async def test_same_txn_under_different_providers_both_processed(self):
        async with test_session_factory() as s:
            svc = PaymentService(s)
            txn = "TXN_PROVIDER_SWAP_001"

            ok_mock = await svc.record_callback_or_skip(
                provider="mock",
                transaction_id=txn,
                callback_type="pay",
                out_trade_no="YLA-PSWAP-001",
                raw_body=b"{}",
            )
            ok_wechat = await svc.record_callback_or_skip(
                provider="wechat",
                transaction_id=txn,
                callback_type="pay",
                out_trade_no="YLA-PSWAP-001",
                raw_body=b"{}",
            )
            await s.commit()

        assert ok_mock is True
        assert ok_wechat is True, (
            "(provider, transaction_id) must be the composite uniqueness "
            "key — same txn id under a different provider is a brand new "
            "callback and MUST be processed."
        )

        async with test_session_factory() as s:
            rows = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == txn
                    )
                )
            ).scalars().all()
        providers = sorted(r.provider for r in rows)
        assert providers == ["mock", "wechat"]

    async def test_same_provider_same_txn_is_blocked(self):
        """Sanity check the inverse — within a single provider, dup is dup."""
        async with test_session_factory() as s:
            svc = PaymentService(s)
            txn = "TXN_PROVIDER_SAME_002"

            ok1 = await svc.record_callback_or_skip(
                provider="wechat",
                transaction_id=txn,
                callback_type="pay",
                out_trade_no="YLA-PSAME-002",
                raw_body=b"{}",
            )
            ok2 = await svc.record_callback_or_skip(
                provider="wechat",
                transaction_id=txn,
                callback_type="pay",
                out_trade_no="YLA-PSAME-002",
                raw_body=b"{}",
            )
            await s.commit()

        assert ok1 is True
        assert ok2 is False


# ---------------------------------------------------------------------------
# T3 (W1 P0). Callbacks after the user has been soft-deleted (GDPR purge / 注销)
# ---------------------------------------------------------------------------
#
# Regression for W1 P0:  the legal/account-deletion flow soft-deletes a User
# (sets ``deleted_at``).  WeChat callbacks for that user's orders, however,
# may still arrive **days later** (refund queues lag, settlement retries,
# operator-initiated replays).  The pay / refund callback path must:
#
#   * NOT crash with ``AttributeError`` / ``NoResultFound`` because the User
#     row is logically gone.
#   * Still mutate the Payment row's terminal state honestly so finance can
#     reconcile.
#   * Be safely idempotent when the **same** callback is replayed.
#
# Implementation note:  ``PaymentService.handle_pay_callback`` /
# ``handle_refund_callback`` operate purely on ``payments.user_id`` (UUID) and
# never load the User ORM row, so soft-deletion should be transparent.  This
# regression test pins that contract so a future refactor that joins User
# into the callback path immediately turns red.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCallbackAfterUserPurge:
    """W1 P0: pay / refund callbacks arriving after the user was soft-deleted
    must still update the Payment row safely and idempotently.
    """

    @staticmethod
    async def _purge_user(user_id):
        """Soft-delete the user 7 days in the past."""
        from datetime import datetime, timedelta, timezone as _tz
        from app.models.user import User as _User
        async with test_session_factory() as s:
            row = (
                await s.execute(select(_User).where(_User.id == user_id))
            ).scalar_one()
            row.deleted_at = datetime.now(_tz.utc) - timedelta(days=7)
            row.is_active = False
            await s.commit()

    async def test_pay_callback_after_user_purged_updates_payment(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """Case 1: order paid -> user soft-deleted -> 7d later pay SUCCESS
        callback arrives. Payment row must move to 'success' without
        raising; no User row is required by the callback path.
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")

        # Force the pay row back to ``pending`` so the late callback has
        # something to mutate (mock provider would otherwise mark it
        # ``success`` synchronously).
        async with test_session_factory() as s:
            row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            row.status = "pending"
            trade_no = row.trade_no
            await s.commit()

        # User is purged (account 注销) before the callback arrives.
        await self._purge_user(user.id)

        body = _callback_body(trade_no, trade_no, "SUCCESS")
        # Must not raise.  The endpoint always 200s towards the PSP.
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json().get("code") == "SUCCESS"

        async with test_session_factory() as s:
            row_after = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
        assert row_after.status == "success", (
            "Pay callback arriving after the user was soft-deleted must "
            "still flip the payment row to 'success' (no User join in the "
            "callback path)."
        )

    async def test_refund_callback_after_user_purged_updates_payment(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """Case 2: order paid + cancelled + refund issued -> user
        soft-deleted -> 7d later refund SUCCESS callback arrives.
        Refund row must reach 'success' (idempotent against missing user).
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Pay -> cancel (cancel auto-creates the refund record;
        # see test_orders.py::test_refund_cancelled_order). Then we just
        # need to flip the refund row back to ``pending`` so the late
        # callback has a transition to make.
        pay_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/pay"
        )
        assert pay_resp.status_code == 200
        cancel_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel"
        )
        assert cancel_resp.status_code == 200

        async with test_session_factory() as s:
            refund_row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                    )
                )
            ).scalar_one()
            # Force back to pending to exercise the callback's mutation.
            refund_row.status = "pending"
            refund_id = refund_row.refund_id
            await s.commit()
        assert refund_id, "refund_id must be set after create_refund"

        # User is purged before the refund callback arrives.
        await self._purge_user(user.id)

        body = (
            f'{{"refund_id":"{refund_id}","out_refund_no":"{refund_id}",'
            f'"refund_status":"SUCCESS","transaction_id":"TXN_REFUND_{refund_id}"}}'
        ).encode()
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        # Endpoint must answer the PSP with 200 even if the row is gone.
        assert resp.status_code == 200

        async with test_session_factory() as s:
            row_after = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                    )
                )
            ).scalar_one()
        assert row_after.status == "success", (
            "Refund callback arriving after the user was soft-deleted "
            "must still flip the refund row to 'success'."
        )

    async def test_duplicate_callback_after_user_purged_is_idempotent(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """Case 3: same pay-SUCCESS callback is delivered twice after the
        user was purged. Second delivery must be a safe no-op:
          * 200 to the PSP
          * exactly ONE PaymentCallbackLog row (the unique key holds)
          * Payment row stays 'success' (no double-ledger).
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")

        async with test_session_factory() as s:
            row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            row.status = "pending"
            trade_no = row.trade_no
            await s.commit()

        await self._purge_user(user.id)

        txn = trade_no  # routing key for handle_pay_callback
        body = _callback_body(trade_no, txn, "SUCCESS")
        resp1 = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        resp2 = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        async with test_session_factory() as s:
            logs = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == txn
                    )
                )
            ).scalars().all()
            row_after = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()

        assert len(logs) == 1, (
            f"Duplicate callback after user purge must dedupe via the "
            f"(provider, transaction_id) unique key — got {len(logs)} rows."
        )
        assert row_after.status == "success", (
            "Replayed callback must not flip the terminal success state."
        )
