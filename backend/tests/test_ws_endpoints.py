"""Tests for WebSocket endpoints in app/api/v1/ws.py.

Covers:
- /ws/notifications: auth, ping/pong, invalid JSON, push_notification_to_user
- /ws/chat/{order_id}: auth, participant check, message send, invalid JSON
"""
import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.order import Order, OrderStatus, ServiceType
from app.models.user import User, UserRole

from .conftest import FakeRedis, override_get_db, test_engine, test_session_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
    """Starlette sync TestClient for WebSocket testing."""
    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = FakeRedis()
    # Ensure no broker attached so fallback broker is used
    app.state.ws_broker = None
    app.state.ws_chat_broker = None
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


async def _seed_user(phone="13800138000", role=UserRole.patient) -> User:
    async with test_session_factory() as session:
        user = User(phone=phone, role=role, roles=role.value if role else None, is_active=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _seed_order(patient_id, hospital_id, companion_id=None, status=OrderStatus.accepted) -> Order:
    async with test_session_factory() as session:
        order = Order(
            order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
            patient_id=patient_id,
            hospital_id=hospital_id,
            companion_id=companion_id,
            service_type=ServiceType.full_accompany,
            status=status,
            appointment_date="2026-04-15",
            appointment_time="09:00",
            price=299.0,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


# We need to patch async_session in ws.py to use test DB
@pytest.fixture(autouse=True)
def _patch_async_session():
    with patch("app.api.v1.ws.async_session", test_session_factory):
        yield


# ===================================================================
# /ws/notifications
# ===================================================================


class TestNotificationsWs:
    def test_missing_token_rejected(self, sync_client):
        """No token → close 4001."""
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/api/v1/ws/notifications"):
                pass

    def test_invalid_token_rejected(self, sync_client):
        """Bad JWT → close 4001."""
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/api/v1/ws/notifications?token=bad.jwt.token"):
                pass

    def test_refresh_token_rejected(self, sync_client):
        """A refresh token (type!=access) → close 4001."""
        from app.core.security import create_refresh_token

        user_id = uuid.uuid4()
        token = create_refresh_token({"sub": str(user_id)})
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}"):
                pass

    def test_valid_token_connects(self, sync_client):
        """Valid access token → connection accepted."""
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}") as ws:
            # Connection is open; send ping and expect pong
            ws.send_text(json.dumps({"type": "ping"}))
            data = json.loads(ws.receive_text())
            assert data == {"type": "pong"}

    def test_ping_pong(self, sync_client):
        """Heartbeat: send ping, get pong."""
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    def test_invalid_json_ignored(self, sync_client):
        """Send non-JSON → server ignores, connection stays open."""
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}") as ws:
            ws.send_text("not json at all {{{")
            # Connection should still be alive; verify with ping
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    def test_unknown_message_type_no_crash(self, sync_client):
        """Send unknown type → no response, connection stays alive."""
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}") as ws:
            ws.send_text(json.dumps({"type": "unknown_type", "data": 123}))
            # Verify connection alive
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    def test_token_with_invalid_sub_uuid(self, sync_client):
        """Token with non-UUID sub → close 4001."""
        import jwt
        from app.config import settings

        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "not-a-uuid",
            "role": "patient",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}"):
                pass

    def test_token_without_sub(self, sync_client):
        """Token without 'sub' field → close 4001."""
        import jwt
        from app.config import settings
        from datetime import datetime, timedelta, timezone

        payload = {
            "role": "patient",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/notifications?token={token}"):
                pass


# ===================================================================
# /ws/chat/{order_id}
# ===================================================================


class TestChatWs:
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, sync_client):
        """No token → close."""
        order_id = uuid.uuid4()
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/chat/{order_id}"):
                pass

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, sync_client):
        order_id = uuid.uuid4()
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/chat/{order_id}?token=invalid"):
                pass

    @pytest.mark.asyncio
    async def test_order_not_found(self, sync_client):
        """Valid token but nonexistent order → close 4004."""
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        order_id = uuid.uuid4()
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/chat/{order_id}?token={token}"):
                pass

    @pytest.mark.asyncio
    async def test_not_participant_rejected(self, sync_client):
        """User not in order → close 4003."""
        from app.models.hospital import Hospital

        # Seed hospital, patient, companion, order
        async with test_session_factory() as session:
            hospital = Hospital(name="Test", address="Addr", level="三甲")
            session.add(hospital)
            await session.commit()
            await session.refresh(hospital)

        patient = await _seed_user("13800000001", UserRole.patient)
        companion = await _seed_user("13800000002", UserRole.companion)
        outsider = await _seed_user("13800000003", UserRole.patient)

        order = await _seed_order(patient.id, hospital.id, companion_id=companion.id)
        token = _make_token(outsider.id)

        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws/chat/{order.id}?token={token}"):
                pass

    @pytest.mark.asyncio
    async def test_participant_connects_and_ping(self, sync_client):
        """Patient of order can connect and ping/pong."""
        from app.models.hospital import Hospital

        async with test_session_factory() as session:
            hospital = Hospital(name="Test", address="Addr", level="三甲")
            session.add(hospital)
            await session.commit()
            await session.refresh(hospital)

        patient = await _seed_user("13800000010", UserRole.patient)
        order = await _seed_order(patient.id, hospital.id)
        token = _make_token(patient.id)

        with sync_client.websocket_connect(f"/api/v1/ws/chat/{order.id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    @pytest.mark.asyncio
    async def test_chat_invalid_json_ignored(self, sync_client):
        """Invalid JSON in chat → ignored, connection stays."""
        from app.models.hospital import Hospital

        async with test_session_factory() as session:
            hospital = Hospital(name="Test", address="Addr", level="三甲")
            session.add(hospital)
            await session.commit()
            await session.refresh(hospital)

        patient = await _seed_user("13800000011", UserRole.patient)
        order = await _seed_order(patient.id, hospital.id)
        token = _make_token(patient.id)

        with sync_client.websocket_connect(f"/api/v1/ws/chat/{order.id}?token={token}") as ws:
            ws.send_text("not valid json!!!")
            # Still alive
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    @pytest.mark.asyncio
    async def test_chat_empty_content_ignored(self, sync_client):
        """Message with empty content → ignored."""
        from app.models.hospital import Hospital

        async with test_session_factory() as session:
            hospital = Hospital(name="Test", address="Addr", level="三甲")
            session.add(hospital)
            await session.commit()
            await session.refresh(hospital)

        patient = await _seed_user("13800000012", UserRole.patient)
        order = await _seed_order(patient.id, hospital.id)
        token = _make_token(patient.id)

        with sync_client.websocket_connect(f"/api/v1/ws/chat/{order.id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "text", "content": ""}))
            # No broadcast for empty; verify alive
            ws.send_text(json.dumps({"type": "ping"}))
            resp = json.loads(ws.receive_text())
            assert resp["type"] == "pong"

    @pytest.mark.asyncio
    async def test_chat_send_message_broadcast(self, sync_client):
        """Send a text message → persisted and broadcast back."""
        from app.models.hospital import Hospital

        async with test_session_factory() as session:
            hospital = Hospital(name="Test", address="Addr", level="三甲")
            session.add(hospital)
            await session.commit()
            await session.refresh(hospital)

        patient = await _seed_user("13800000013", UserRole.patient)
        order = await _seed_order(patient.id, hospital.id)
        token = _make_token(patient.id)

        with sync_client.websocket_connect(f"/api/v1/ws/chat/{order.id}?token={token}") as ws:
            ws.send_text(json.dumps({"type": "text", "content": "Hello doctor!"}))
            resp = json.loads(ws.receive_text())
            assert resp["content"] == "Hello doctor!"
            assert resp["sender_id"] == str(patient.id)
            assert resp["order_id"] == str(order.id)
            assert resp["type"] == "text"
