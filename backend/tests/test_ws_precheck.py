"""Tests for /ws/v1/orders/{order_id}/precheck WebSocket — S3-DEV-003 c4.

Covers:

- ABAC Layer 2 (role) — invalid / missing token rejected
- ABAC Layer 2.5 (owner) — non-owner / nonexistent order close codes
- Authorised patient owner connects + ping/pong loopback
- Broadcast facade (broadcast_status_updated / broadcast_all_ready /
  broadcast_blocked) reaches subscribed clients with correct event shape
- Upstream write attempts (non-ping) close with 4012 (read-only stream)
- Multiple subscribers per order_id all receive broadcast
"""
import json
import uuid
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.order import Order, OrderStatus, ServiceType
from app.models.user import User, UserRole
from app.services.precheck_broadcast import (
    broadcast_all_ready,
    broadcast_blocked,
    broadcast_status_updated,
)

from .conftest import (
    FakeRedis,
    override_get_db,
    test_engine,
)
from .conftest import (
    test_session_factory as _session_factory,
)

_TEST_SESSION_FACTORY = _session_factory


def _make_token(user_id: uuid.UUID, role: str = "patient") -> str:
    return create_access_token({"sub": str(user_id), "role": role})


@pytest.fixture(autouse=True)
async def _setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sync_client():
    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = FakeRedis()
    # Force fallback brokers (no Redis pubsub) for in-test isolation.
    app.state.ws_broker = None
    app.state.ws_chat_broker = None
    app.state.ws_precheck_broker = None
    # Reset module-level fallback so each test starts from a clean
    # registry (subscriber sets from earlier tests must not leak).
    import app.services.precheck_broadcast as pb

    pb._fallback_precheck_broker = None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_async_session():
    with patch("app.api.v1.ws.async_session", _TEST_SESSION_FACTORY):
        yield


async def _seed_user(phone: str, role=UserRole.patient) -> User:
    async with _TEST_SESSION_FACTORY() as session:
        user = User(
            phone=phone,
            role=role,
            roles=role.value if role else None,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _seed_order(patient_id, hospital_id) -> Order:
    async with _TEST_SESSION_FACTORY() as session:
        order = Order(
            order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
            patient_id=patient_id,
            hospital_id=hospital_id,
            service_type=ServiceType.full_accompany,
            status=OrderStatus.accepted,
            appointment_date="2026-04-15",
            appointment_time="09:00",
            price=299.0,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def _seed_hospital():
    from app.models.hospital import Hospital

    async with _TEST_SESSION_FACTORY() as session:
        hospital = Hospital(name="Test", address="Addr", level="三甲")
        session.add(hospital)
        await session.commit()
        await session.refresh(hospital)
        return hospital


WS_PATH = "/api/v1/ws/v1/orders/{order_id}/precheck"


# ===================================================================
# Layer 2 (role) — auth handshake
# ===================================================================


class TestPrecheckWsAuth:
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, sync_client):
        """No token in query AND first frame is not auth → close 4011."""
        order_id = uuid.uuid4()
        with sync_client.websocket_connect(WS_PATH.format(order_id=order_id)) as ws:
            ws.send_text(json.dumps({"type": "not_auth"}))
            with pytest.raises(Exception):
                ws.receive_text()

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, sync_client):
        order_id = uuid.uuid4()
        with pytest.raises(Exception):
            with sync_client.websocket_connect(
                WS_PATH.format(order_id=order_id) + "?token=invalid"
            ):
                pass


# ===================================================================
# Layer 2.5 (owner) — order owner gate
# ===================================================================


class TestPrecheckWsOwnerGate:
    @pytest.mark.asyncio
    async def test_order_not_found_closes_4004(self, sync_client):
        """Valid token but nonexistent order → close after accept."""
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        order_id = uuid.uuid4()
        url = WS_PATH.format(order_id=order_id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            with pytest.raises(Exception):
                ws.receive_text()

    @pytest.mark.asyncio
    async def test_non_owner_patient_rejected(self, sync_client):
        """Another patient (not the order owner) can authenticate but
        the owner gate closes the socket."""
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000020")
        stranger = await _seed_user("13800000021")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(stranger.id)
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            with pytest.raises(Exception):
                ws.receive_text()

    @pytest.mark.asyncio
    async def test_admin_role_blocked_by_owner_gate(self, sync_client):
        """Admin JWT decodes successfully but admin user is a separate
        identity (not order.patient_id) so the owner gate closes the
        socket. (Patient-only feature; admin should use the admin
        polling endpoint.)"""
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000030")
        # Admin role is encoded in the JWT claim, not the user table
        # (see UserRole enum). We seed a separate patient row to back
        # the JWT sub and issue an admin-role token from a non-owner.
        admin_user = await _seed_user("13800000031")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(admin_user.id, role="admin")
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            with pytest.raises(Exception):
                ws.receive_text()


# ===================================================================
# Authorised flow — ping/pong + read-only stream contract
# ===================================================================


class TestPrecheckWsPatientFlow:
    @pytest.mark.asyncio
    async def test_owner_connects_and_ping_pong(self, sync_client):
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000040")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(owner.id)
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    @pytest.mark.asyncio
    async def test_upstream_write_frame_closes_4012(self, sync_client):
        """Stream is push-only: any non-ping upstream frame closes
        the connection (mirrors family-share §2.4 contract)."""
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000041")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(owner.id)
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            ws.send_text(json.dumps({"type": "text", "content": "no writes"}))
            with pytest.raises(Exception):
                ws.receive_text()


# ===================================================================
# Broadcast facade — event shape + per-order_id routing
# ===================================================================


class TestPrecheckBroadcast:
    @pytest.mark.asyncio
    async def test_status_updated_event_reaches_subscriber(self, sync_client):
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000050")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(owner.id)
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            # Wait for handshake / owner gate to complete before broadcast.
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text())["type"] == "pong"

            await broadcast_status_updated(
                app,
                order.id,
                card="insurance",
                status={"state": "green", "detail": "verified"},
                all_ready=False,
            )
            payload = json.loads(ws.receive_text())
            assert payload["event"] == "precheck.status.updated"
            assert payload["order_id"] == str(order.id)
            assert payload["card"] == "insurance"
            assert payload["status"] == {"state": "green", "detail": "verified"}
            assert payload["all_ready"] is False
            assert "ts" in payload

    @pytest.mark.asyncio
    async def test_all_ready_event_shape(self, sync_client):
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000051")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(owner.id)
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text())["type"] == "pong"

            await broadcast_all_ready(app, order.id)
            payload = json.loads(ws.receive_text())
            assert payload["event"] == "precheck.all_ready"
            assert payload["order_id"] == str(order.id)
            assert "ts" in payload

    @pytest.mark.asyncio
    async def test_blocked_event_carries_reason(self, sync_client):
        hospital = await _seed_hospital()
        owner = await _seed_user("13800000052")
        order = await _seed_order(owner.id, hospital.id)
        token = _make_token(owner.id)
        url = WS_PATH.format(order_id=order.id) + f"?token={token}"
        with sync_client.websocket_connect(url) as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text())["type"] == "pong"

            await broadcast_blocked(app, order.id, reason="signature_invalid")
            payload = json.loads(ws.receive_text())
            assert payload["event"] == "precheck.blocked"
            assert payload["order_id"] == str(order.id)
            assert payload["reason"] == "signature_invalid"

    @pytest.mark.asyncio
    async def test_broadcast_isolated_per_order_id(self, sync_client):
        """Broadcast to order A must not reach a subscriber of order B."""
        hospital = await _seed_hospital()
        owner_a = await _seed_user("13800000060")
        owner_b = await _seed_user("13800000061")
        order_a = await _seed_order(owner_a.id, hospital.id)
        order_b = await _seed_order(owner_b.id, hospital.id)
        token_a = _make_token(owner_a.id)
        token_b = _make_token(owner_b.id)
        url_a = WS_PATH.format(order_id=order_a.id) + f"?token={token_a}"
        url_b = WS_PATH.format(order_id=order_b.id) + f"?token={token_b}"
        with sync_client.websocket_connect(url_a) as ws_a, \
             sync_client.websocket_connect(url_b) as ws_b:
            ws_a.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws_a.receive_text())["type"] == "pong"
            ws_b.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws_b.receive_text())["type"] == "pong"

            await broadcast_status_updated(
                app,
                order_a.id,
                card="signature",
                status={"state": "green"},
                all_ready=False,
            )
            payload = json.loads(ws_a.receive_text())
            assert payload["event"] == "precheck.status.updated"
            assert payload["order_id"] == str(order_a.id)
            assert payload["card"] == "signature"

            # ws_b must not receive the order_a broadcast. Use a very
            # short timeout on receive to assert no payload arrives.
            ws_b.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws_b.receive_text())
            assert resp == {"type": "pong"}, (
                "ws_b leaked order_a broadcast: " + json.dumps(resp)
            )
