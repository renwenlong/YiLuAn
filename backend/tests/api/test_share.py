"""REST endpoint tests for ADR-0036 / S2-DEV-002 family share flows.

Covers acceptance criteria:
- AC#1: 6 endpoints all return per spec (mounted + 2xx happy path)
- AC#2: POST returns share_token + share_url + active cap auto-revoke
- AC#3 (spec only — WS close 4013 lives in S2-DEV-003)
- AC#4: exchange_session — expired/revoked → 401
- AC#5: GET /shares/session/order — desensitized payload + scope gating
- AC#6: scope=progress_only → can_view_images=False (AC#21 hook for 403)
- AC#7: OpenAPI schema mounted (covered indirectly via test_openapi_paths)
- AC#8: ≥12 functional cases (this file ships 12)

Negative-flow security tests (Top1 §3.5) live in
``tests/services/test_share_security.py`` under ``pytest -m share_security``
(刻晴 S2-TEST-002 owns those).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models import Hospital, Order, OrderShareToken, User
from app.models.order import OrderStatus, ServiceType
from app.models.user import UserRole
from app.services.share import (
    SHARE_SESSION_TOKEN_TYPE,
    decode_share_session,
)
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def order_with_owner(authenticated_client: AsyncClient):
    """Create an order owned by ``authenticated_client._test_user``."""
    owner: User = authenticated_client._test_user  # type: ignore[attr-defined]
    async with test_session_factory() as session:
        hospital = Hospital(
            id=uuid.uuid4(), name=f"H-{uuid.uuid4().hex[:6]}"
        )
        session.add(hospital)
        await session.flush()
        order = Order(
            id=uuid.uuid4(),
            order_number=f"YLA-{uuid.uuid4().hex[:10].upper()}",
            patient_id=owner.id,
            hospital_id=hospital.id,
            companion_id=None,
            service_type=ServiceType.full_accompany,
            status=OrderStatus.in_progress,
            appointment_date="2026-06-01",
            appointment_time="09:00",
            price=Decimal("299.00"),
            patient_name="张小明",
            hospital_name=hospital.name,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


@pytest.fixture
async def other_user_client(client, seed_user):
    """A second authenticated client used for cross-owner negative tests."""
    user = await seed_user(phone="13511110000", role=UserRole.patient)
    token = create_access_token({"sub": str(user.id), "role": "patient"})
    client2 = client
    # Mutate shared client by *swapping* headers per call — but pytest gives
    # one client per test, so we hand back a small wrapper.
    class _OtherClient:
        def __init__(self, base: AsyncClient, hdr: dict[str, str]):
            self._base = base
            self._hdr = hdr

        async def post(self, *a, **kw):
            kw.setdefault("headers", {}).update(self._hdr)
            return await self._base.post(*a, **kw)

        async def get(self, *a, **kw):
            kw.setdefault("headers", {}).update(self._hdr)
            return await self._base.get(*a, **kw)

        async def delete(self, *a, **kw):
            kw.setdefault("headers", {}).update(self._hdr)
            return await self._base.delete(*a, **kw)

    return _OtherClient(client2, {"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# AC#2: POST /orders/{id}/shares — happy path + active cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_returns_token_and_url(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    r = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["share_scope"] == "full"
    assert len(data["share_token"]) == 32
    assert data["share_url"] == f"https://m.yiluan.cn/s/{data['share_token']}"
    assert data["share_active_count"] == 1
    assert data["share_revoked_at"] is None


@pytest.mark.asyncio
async def test_create_share_active_cap_auto_revokes_oldest(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    tokens = []
    for _ in range(4):
        r = await authenticated_client.post(
            f"/api/v1/orders/{order_with_owner.id}/shares",
            json={"share_scope": "full"},
        )
        assert r.status_code == 201
        tokens.append(r.json())

    # The 4th call must have triggered auto-revoke; active_count caps at 3.
    assert tokens[-1]["share_active_count"] == 3

    list_r = await authenticated_client.get(
        f"/api/v1/orders/{order_with_owner.id}/shares"
    )
    assert list_r.status_code == 200
    assert list_r.json()["share_active_count"] == 3


# ---------------------------------------------------------------------------
# AC#3: cross-owner forbidden (Top1 §3.5 #3 hint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_by_non_owner_forbidden(
    other_user_client, order_with_owner: Order
):
    r = await other_user_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE — owner can revoke; idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_share_marks_revoked_and_is_idempotent(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token_id = create.json()["id"]

    r1 = await authenticated_client.delete(
        f"/api/v1/orders/{order_with_owner.id}/shares/{token_id}"
    )
    assert r1.status_code == 204
    # second delete is a no-op (idempotent), not 404.
    r2 = await authenticated_client.delete(
        f"/api/v1/orders/{order_with_owner.id}/shares/{token_id}"
    )
    assert r2.status_code == 204

    # the active list should now show 0 entries.
    list_r = await authenticated_client.get(
        f"/api/v1/orders/{order_with_owner.id}/shares"
    )
    assert list_r.json()["share_active_count"] == 0


@pytest.mark.asyncio
async def test_revoke_unknown_token_returns_404(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    r = await authenticated_client.delete(
        f"/api/v1/orders/{order_with_owner.id}/shares/{uuid.uuid4()}"
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# AC#4: exchange_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_session_with_wx_openid_returns_jwt(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]

    r = await authenticated_client.post(
        f"/api/v1/shares/{token}/session",
        json={"wx_openid": "wx-openid-1"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["order_id"] == str(order_with_owner.id)
    assert data["share_scope"] == "full"
    payload = decode_share_session(data["share_session"])
    assert payload["type"] == SHARE_SESSION_TOKEN_TYPE
    assert payload["aud"] == "share"  # ADR-0036 §3.5 #5 follow-up
    assert payload["acc"] == "wx-openid-1"


@pytest.mark.asyncio
async def test_exchange_session_with_invalid_token_returns_401(
    authenticated_client: AsyncClient,
):
    r = await authenticated_client.post(
        "/api/v1/shares/nope-not-a-real-token/session",
        json={"wx_openid": "wx-openid-1"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_exchange_session_with_revoked_token_returns_401(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]
    token_id = create.json()["id"]
    # Revoke through the owner endpoint.
    await authenticated_client.delete(
        f"/api/v1/orders/{order_with_owner.id}/shares/{token_id}"
    )
    r = await authenticated_client.post(
        f"/api/v1/shares/{token}/session", json={"wx_openid": "wx-openid-1"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_exchange_session_missing_auth_proof_returns_401(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]
    r = await authenticated_client.post(
        f"/api/v1/shares/{token}/session", json={}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# S2-DEV-011: iOS/H5 OTP fallback 端到端 (send-otp → exchange with phone+otp)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_otp_then_exchange_with_phone_otp(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]
    phone = "13800019999"

    # 1. request OTP (mock SMS provider always ok)
    sent = await authenticated_client.post(
        f"/api/v1/shares/{token}/otp", json={"phone": phone}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["masked_phone"] == "138****9999"

    # 2. pull the code straight out of the (fake) redis store
    from app.main import app as _app
    from app.services.share_otp import _CODE_KEY, _phone_hash

    code = await _app.state.redis.get(
        _CODE_KEY.format(token=token, phash=_phone_hash(phone))
    )
    assert code

    # 3. exchange phone+otp → share_session JWT with phone-hash accessor
    r = await authenticated_client.post(
        f"/api/v1/shares/{token}/session",
        json={"phone": phone, "otp": code},
    )
    assert r.status_code == 200, r.text
    payload = decode_share_session(r.json()["share_session"])
    assert payload["acc"].startswith("phone:")


@pytest.mark.asyncio
async def test_exchange_with_wrong_otp_returns_401(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]
    phone = "13800018888"
    await authenticated_client.post(
        f"/api/v1/shares/{token}/otp", json={"phone": phone}
    )
    r = await authenticated_client.post(
        f"/api/v1/shares/{token}/session",
        json={"phone": phone, "otp": "000000"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_send_otp_token_daily_cap_429(
    authenticated_client: AsyncClient, order_with_owner: Order
):
    from app.config import settings

    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]
    phone = "13800017777"
    for _ in range(settings.share_otp_token_daily_cap):
        ok = await authenticated_client.post(
            f"/api/v1/shares/{token}/otp", json={"phone": phone}
        )
        assert ok.status_code == 200
    over = await authenticated_client.post(
        f"/api/v1/shares/{token}/otp", json={"phone": phone}
    )
    assert over.status_code == 429


# ---------------------------------------------------------------------------
# AC#5/#6: GET /shares/session/order — desensitized view + scope gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_share_session_order_returns_masked_view(
    authenticated_client: AsyncClient, client, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "full"},
    )
    token = create.json()["share_token"]
    sess = await authenticated_client.post(
        f"/api/v1/shares/{token}/session",
        json={"wx_openid": "wx-openid-2"},
    )
    share_jwt = sess.json()["share_session"]

    # Use a *fresh* request with the share_session bearer so we don't leak
    # the owner's access token into the family-viewer call.
    r = await client.get(
        "/api/v1/shares/session/order",
        headers={"Authorization": f"Bearer {share_jwt}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order_id"] == str(order_with_owner.id)
    assert body["patient_name_masked"] == "张**"
    assert "patient_phone" not in body  # PII not leaked (§2.5)
    assert body["can_view_images"] is True
    assert body["can_view_ai_summary"] is True
    assert body["share_scope"] == "full"


@pytest.mark.asyncio
async def test_get_share_session_order_scope_progress_only_hides_images(
    authenticated_client: AsyncClient, client, order_with_owner: Order
):
    create = await authenticated_client.post(
        f"/api/v1/orders/{order_with_owner.id}/shares",
        json={"share_scope": "progress_only"},
    )
    token = create.json()["share_token"]
    sess = await authenticated_client.post(
        f"/api/v1/shares/{token}/session",
        json={"wx_openid": "wx-openid-3"},
    )
    share_jwt = sess.json()["share_session"]

    r = await client.get(
        "/api/v1/shares/session/order",
        headers={"Authorization": f"Bearer {share_jwt}"},
    )
    body = r.json()
    assert body["share_scope"] == "progress_only"
    assert body["can_view_images"] is False
    assert body["can_view_ai_summary"] is False


@pytest.mark.asyncio
async def test_get_share_session_order_rejects_access_token(
    authenticated_client: AsyncClient, client, order_with_owner: Order
):
    """An access JWT must NOT be usable on the family-viewer endpoint
    (the ``type`` claim differs — Top1 §3.5 #5)."""
    owner = authenticated_client._test_user  # type: ignore[attr-defined]
    access_jwt = create_access_token({"sub": str(owner.id), "role": "patient"})
    r = await client.get(
        "/api/v1/shares/session/order",
        headers={"Authorization": f"Bearer {access_jwt}"},
    )
    assert r.status_code == 401
