"""Regression tests for C-12 / TD-MSG-04 / TD-MSG-01.

Covers the new behaviour landed in the WS unification:
- ChatService.send_message_via_ws (service-layer, no broker)
- nonce dedup returns the same outcome (no duplicate persist)
- WS idle timeout → 4002 close + ws_idle_timeout_total counter increments
- unauthorised participant rejected (regression of pre-flight check)
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.chat_message import MessageType
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.user import User, UserRole
from app.services.chat import ChatService

from .conftest import FakeRedis, override_get_db, test_engine, test_session_factory


def _make_token(user_id: uuid.UUID) -> str:
    return create_access_token({"sub": str(user_id), "role": "patient"})


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
    app.state.ws_broker = None
    app.state.ws_chat_broker = None
    with TestClient(app, raise_server_exceptions=False) as c:
        # Override AFTER lifespan runs (lifespan calls init_redis(), which in
        # CI environments without a real Redis would replace our FakeRedis with
        # a client that fails to connect on the first SETNX).
        app.state.redis = FakeRedis()
        app.state.ws_broker = None
        app.state.ws_chat_broker = None
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_async_session():
    with patch("app.api.v1.ws.async_session", test_session_factory):
        yield


async def _seed_user(phone: str, role: UserRole = UserRole.patient) -> User:
    async with test_session_factory() as session:
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


async def _seed_hospital() -> Hospital:
    async with test_session_factory() as session:
        h = Hospital(name="Test", address="Addr", level="三甲")
        session.add(h)
        await session.commit()
        await session.refresh(h)
        return h


async def _seed_order(patient_id, hospital_id, companion_id=None) -> Order:
    async with test_session_factory() as session:
        order = Order(
            order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
            patient_id=patient_id,
            hospital_id=hospital_id,
            companion_id=companion_id,
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


# ----------------------------------------------------------------------
# Service-layer unit tests
# ----------------------------------------------------------------------
class TestChatServiceWs:
    @pytest.mark.asyncio
    async def test_send_message_via_chat_service(self):
        hospital = await _seed_hospital()
        patient = await _seed_user("13800200001")
        order = await _seed_order(patient.id, hospital.id)

        async with test_session_factory() as session:
            svc = ChatService(session)
            msg, payload, dup = await svc.send_message_via_ws(
                order_id=order.id,
                sender_id=patient.id,
                content="hello via service",
                msg_type=MessageType.text,
            )

        assert dup is False
        assert msg is not None
        assert payload["content"] == "hello via service"
        assert payload["sender_id"] == str(patient.id)
        assert payload["order_id"] == str(order.id)
        assert payload["type"] == "text"
        assert "id" in payload and "created_at" in payload

    @pytest.mark.asyncio
    async def test_nonce_dedup_returns_duplicate_flag(self):
        hospital = await _seed_hospital()
        patient = await _seed_user("13800200002")
        order = await _seed_order(patient.id, hospital.id)
        redis = FakeRedis()
        nonce = "nonce-abc-123"

        async with test_session_factory() as session:
            svc = ChatService(session)
            msg1, payload1, dup1 = await svc.send_message_via_ws(
                order_id=order.id,
                sender_id=patient.id,
                content="first",
                msg_type=MessageType.text,
                nonce=nonce,
                redis=redis,
            )

        async with test_session_factory() as session:
            svc = ChatService(session)
            msg2, payload2, dup2 = await svc.send_message_via_ws(
                order_id=order.id,
                sender_id=patient.id,
                content="first",
                msg_type=MessageType.text,
                nonce=nonce,
                redis=redis,
            )

        assert dup1 is False and msg1 is not None
        assert dup2 is True and msg2 is None and payload2 == {}

    @pytest.mark.asyncio
    async def test_unauthorized_sender_rejected(self):
        from app.exceptions import ForbiddenException

        hospital = await _seed_hospital()
        patient = await _seed_user("13800200003")
        outsider = await _seed_user("13800200004")
        order = await _seed_order(patient.id, hospital.id)

        async with test_session_factory() as session:
            svc = ChatService(session)
            with pytest.raises(ForbiddenException):
                await svc.send_message_via_ws(
                    order_id=order.id,
                    sender_id=outsider.id,
                    content="sneaky",
                    msg_type=MessageType.text,
                )

    @pytest.mark.asyncio
    async def test_empty_content_returns_no_message(self):
        hospital = await _seed_hospital()
        patient = await _seed_user("13800200005")
        order = await _seed_order(patient.id, hospital.id)

        async with test_session_factory() as session:
            svc = ChatService(session)
            msg, payload, dup = await svc.send_message_via_ws(
                order_id=order.id,
                sender_id=patient.id,
                content="   ",
                msg_type=MessageType.text,
            )
        assert msg is None and payload == {} and dup is False


# ----------------------------------------------------------------------
# WS-level integration tests (TestClient)
# ----------------------------------------------------------------------
class TestWsIdleTimeoutAndNonce:
    @pytest.mark.asyncio
    async def test_ws_idle_timeout_disconnects_chat(self, sync_client):
        """Patch idle timeout to 0.2s — the server should close the socket
        before any frame is sent."""
        hospital = await _seed_hospital()
        patient = await _seed_user("13800201010")
        order = await _seed_order(patient.id, hospital.id)
        token = _make_token(patient.id)

        from app.utils.metrics import ws_idle_timeout_total

        before = ws_idle_timeout_total.labels(channel="chat")._value.get()

        with patch("app.api.v1.ws.WS_IDLE_TIMEOUT_SECONDS", 0.2):
            with sync_client.websocket_connect(
                f"/api/v1/ws/chat/{order.id}?token={token}"
            ) as ws:
                # Don't send anything; receive a close from server-side timeout.
                with pytest.raises(Exception):
                    while True:
                        ws.receive_text()

        after = ws_idle_timeout_total.labels(channel="chat")._value.get()
        assert after >= before + 1

    @pytest.mark.asyncio
    async def test_ws_idle_timeout_disconnects_notifications(self, sync_client):
        user_id = uuid.uuid4()
        token = _make_token(user_id)

        from app.utils.metrics import ws_idle_timeout_total

        before = ws_idle_timeout_total.labels(channel="notifications")._value.get()

        with patch("app.api.v1.ws.WS_IDLE_TIMEOUT_SECONDS", 0.2):
            with sync_client.websocket_connect(
                f"/api/v1/ws/notifications?token={token}"
            ) as ws:
                with pytest.raises(Exception):
                    while True:
                        ws.receive_text()

        after = ws_idle_timeout_total.labels(channel="notifications")._value.get()
        assert after >= before + 1

    @pytest.mark.asyncio
    async def test_ws_chat_nonce_dedup_short_circuits_broadcast(self, sync_client):
        """Send same nonce twice → only one broadcast frame received."""
        hospital = await _seed_hospital()
        patient = await _seed_user("13800201020")
        order = await _seed_order(patient.id, hospital.id)
        token = _make_token(patient.id)

        with sync_client.websocket_connect(
            f"/api/v1/ws/chat/{order.id}?token={token}"
        ) as ws:
            ws.send_text(json.dumps({
                "type": "text",
                "content": "dedupe me",
                "nonce": "n-dedupe-1",
            }))
            first = json.loads(ws.receive_text())
            assert first["content"] == "dedupe me"
            assert first.get("nonce") == "n-dedupe-1"

            # Send the same nonce again.
            ws.send_text(json.dumps({
                "type": "text",
                "content": "dedupe me",
                "nonce": "n-dedupe-1",
            }))
            # Then send a ping; we should receive a pong, NOT a second broadcast.
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp.get("type") == "pong"
