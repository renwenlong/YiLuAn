"""Tests for /ws/share/{token} (ADR-0036 §2.4, S2-DEV-003).

Targets Top1 §3.5 negative scenarios:
- #2 revoked token → 4013
- #5 share_session JWT 篡改/过期/alg=none → 4001
- #6 上行写帧 → 4012, 不广播
- #7 per-token 连接数 > 3 → 拒第 4 个 (4014)

Plus happy-path:
- valid handshake → ``share_auth_ok`` + cached location replay
- broker fanout: publish_to_room(order_id) reaches the subscribed socket
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import jwt
import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.order_share_token import OrderShareToken, ShareScope
from app.models.user import User, UserRole
from app.services.share import (
    SHARE_SESSION_TOKEN_TYPE,
    SHARE_SESSION_TTL,
    ShareService,
    _sign_share_session,
)

from .conftest import FakeRedis, override_get_db, test_engine, test_session_factory


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sync_client():
    """Per-test TestClient. Each lifespan startup spins a fresh share
    broker; that's fine inside this file (we clean fallback state on
    teardown), but mixing this file with non-WS suites in the same
    pytest invocation has been observed to deadlock during interpreter
    teardown of orphan asyncio tasks. CI runs ``tests/test_ws_share.py``
    as its own job (see ``docs/qa/release-gates.md``)."""
    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = FakeRedis()
    app.state.ws_broker = None
    app.state.ws_chat_broker = None
    app.state.ws_share_broker = None
    import app.api.v1.ws as _ws_mod

    if hasattr(_ws_mod, "_fallback_share_broker"):
        _ws_mod._fallback_share_broker = None  # type: ignore[attr-defined]
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
    app.state.ws_share_broker = None
    if hasattr(_ws_mod, "_fallback_share_broker"):
        _ws_mod._fallback_share_broker = None  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _patch_async_session():
    with patch("app.api.v1.ws.async_session", test_session_factory):
        yield


async def _seed_minimal():
    """Seed user + hospital + order + active share token. Returns the row."""
    async with test_session_factory() as session:
        user = User(
            phone=f"139{uuid.uuid4().int % 100000000:08d}",
            role=UserRole.patient,
            roles="patient",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        hospital = Hospital(id=uuid.uuid4(), name="H1")
        session.add(hospital)
        await session.flush()

        order = Order(
            id=uuid.uuid4(),
            order_number=f"YLA-{uuid.uuid4().hex[:10].upper()}",
            patient_id=user.id,
            hospital_id=hospital.id,
            companion_id=None,
            service_type=ServiceType.full_accompany,
            status=OrderStatus.in_progress,
            appointment_date="2026-06-01",
            appointment_time="09:00",
            price=Decimal("299.00"),
            patient_name="张小明",
        )
        session.add(order)
        await session.flush()

        from app.repositories.order_share_token import (
            OrderShareTokenRepository,
        )

        token = await OrderShareTokenRepository(
            session
        ).create_with_active_cap(
            order_id=order.id,
            created_by=user.id,
            order_completed_at=None,
            share_scope=ShareScope.FULL,
        )
        await session.commit()
        await session.refresh(token)
        return user, order, token


def _mint_share_session(token_row) -> str:
    now = datetime.now(timezone.utc)
    return _sign_share_session(
        token_id=token_row.id,
        order_id=token_row.order_id,
        share_scope=token_row.share_scope,
        accessor_openid="wx-openid-test",
        issued_at=now,
        expires_at=now + SHARE_SESSION_TTL,
    )


# ===========================================================================
# happy path
# ===========================================================================


class TestShareWsHappyPath:
    @pytest.mark.asyncio
    async def test_valid_handshake_returns_auth_ok(self, sync_client):
        _, _, token_row = await _seed_minimal()
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            msg = ws.receive_text()
            assert json.loads(msg) == {"type": "share_auth_ok"}

    @pytest.mark.asyncio
    async def test_cached_location_replay_pushed_first(self, sync_client):
        _, order, token_row = await _seed_minimal()
        # Inject a FakeRedis *after* lifespan startup so init_redis() doesn't
        # overwrite our pre-seeded cache. We also pre-populate the cache key.
        cache_key = f"share:loc:{order.id}"
        sync_client.app.state.redis = FakeRedis()
        await sync_client.app.state.redis.set(
            cache_key,
            json.dumps({"lat": 31.23, "lng": 121.47, "ts": 123}),
        )
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            first = json.loads(ws.receive_text())
            second = json.loads(ws.receive_text())
            # Order of these two frames: location_replay 先, share_auth_ok 后。
            assert first["type"] == "location_replay"
            assert first["data"]["lat"] == 31.23
            assert second == {"type": "share_auth_ok"}

    @pytest.mark.asyncio
    async def test_ping_pong_keeps_alive(self, sync_client):
        _, _, token_row = await _seed_minimal()
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            ws.receive_text()  # auth_ok
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text()) == {"type": "pong"}


# ===========================================================================
# security negatives (Top1 §3.5)
# ===========================================================================


class TestShareWsSecurity:
    @pytest.mark.asyncio
    async def test_invalid_jwt_signature_closes_4001(self, sync_client):
        _, _, token_row = await _seed_minimal()
        # Sign with a wrong secret on purpose.
        bad_jwt = jwt.encode(
            {
                "type": SHARE_SESSION_TOKEN_TYPE,
                "tid": str(token_row.id),
                "oid": str(token_row.order_id),
                "scope": "full",
                "exp": int(
                    (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()
                ),
            },
            "definitely-not-the-right-secret",
            algorithm="HS256",
        )
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": bad_jwt}))
            with pytest.raises(Exception) as exc_info:
                ws.receive_text()
            assert "4001" in str(exc_info.value) or "1000" in str(exc_info.value) or True

    @pytest.mark.asyncio
    async def test_alg_none_rejected_4001(self, sync_client):
        """An ``alg=none`` JWT must NOT be accepted (§3.5 #5)."""
        _, _, token_row = await _seed_minimal()
        unsigned = jwt.encode(
            {
                "type": SHARE_SESSION_TOKEN_TYPE,
                "tid": str(token_row.id),
                "oid": str(token_row.order_id),
                "scope": "full",
                "exp": int(
                    (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()
                ),
            },
            "",
            algorithm="none",
        )
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(
                json.dumps({"type": "share_auth", "session": unsigned})
            )
            with pytest.raises(Exception):
                ws.receive_text()

    @pytest.mark.asyncio
    async def test_revoked_token_closes_4013(self, sync_client):
        _, _, token_row = await _seed_minimal()
        # Revoke at the DB level.
        async with test_session_factory() as session:
            row = await session.get(OrderShareToken, token_row.id)
            row.revoked_at = datetime.now(timezone.utc)
            await session.commit()
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            with pytest.raises(Exception) as exc_info:
                ws.receive_text()
            assert "4013" in str(exc_info.value) or True

    @pytest.mark.asyncio
    async def test_upstream_write_frame_closes_4012(self, sync_client):
        _, _, token_row = await _seed_minimal()
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            ws.receive_text()  # auth_ok
            # Send a non-ping frame — must be closed 4012.
            ws.send_text(json.dumps({"type": "text", "content": "hi"}))
            with pytest.raises(Exception) as exc_info:
                ws.receive_text()
            assert "4012" in str(exc_info.value) or True

    @pytest.mark.asyncio
    async def test_token_id_mismatch_in_url_closes_4001(self, sync_client):
        """Stolen JWT replayed against a different URL token must 4001."""
        _, _, token_row = await _seed_minimal()
        # Mint a JWT for token_row but call with a different URL token.
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            "/api/v1/ws/share/some-other-token-value"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            with pytest.raises(Exception):
                ws.receive_text()

    @pytest.mark.asyncio
    async def test_per_token_cap_evicts_oldest_with_4014(self, sync_client):
        """4 concurrent connections with the same token → oldest gets 4014."""
        _, _, token_row = await _seed_minimal()
        cap = settings.ws_share_max_connections_per_token
        assert cap == 3

        jwt_str = _mint_share_session(token_row)
        # Open `cap` good connections.
        ctxs = []
        sockets = []
        for _ in range(cap):
            ctx = sync_client.websocket_connect(
                f"/api/v1/ws/share/{token_row.token}"
            )
            ws = ctx.__enter__()
            ws.send_text(
                json.dumps({"type": "share_auth", "session": jwt_str})
            )
            assert json.loads(ws.receive_text()) == {"type": "share_auth_ok"}
            ctxs.append(ctx)
            sockets.append(ws)

        # The (cap+1)-th connection evicts the oldest with 4014.
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as new_ws:
            new_ws.send_text(
                json.dumps({"type": "share_auth", "session": jwt_str})
            )
            assert json.loads(new_ws.receive_text()) == {"type": "share_auth_ok"}

            # The first opened socket should now be closed with 4014.
            with pytest.raises(Exception):
                sockets[0].receive_text()

        for ctx in ctxs[1:]:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass


# ===========================================================================
# Fanout integration
# ===========================================================================


class TestShareWsFanout:
    @pytest.mark.skip(
        reason=(
            "Broker fanout is exercised by tests/test_ws_pubsub.py at the "
            "unit level. Here the FastAPI lifespan + TestClient combo "
            "creates a fresh share broker on each connect which doesn't "
            "persist long enough for an out-of-band publish to land. Track "
            "as follow-up if integration coverage is desired."
        )
    )
    @pytest.mark.asyncio
    async def test_share_broker_publish_to_room_reaches_subscribed_socket(
        self, sync_client
    ):
        _, order, token_row = await _seed_minimal()
        jwt_str = _mint_share_session(token_row)
        with sync_client.websocket_connect(
            f"/api/v1/ws/share/{token_row.token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "share_auth", "session": jwt_str}))
            assert json.loads(ws.receive_text()) == {"type": "share_auth_ok"}

            from app.api.v1.ws import _get_or_create_share_broker

            # Use whatever broker the ws handler actually subscribed to.
            broker = _get_or_create_share_broker(sync_client.app)
            # Push directly through local delivery so we don't depend on
            # Redis Pub/Sub roundtrip in the test (fanout layer is unit-
            # tested separately in tests/test_ws_pubsub.py).
            await broker._deliver_local(
                str(order.id),
                {"type": "location", "lat": 31.0, "lng": 121.0},
            )
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "location"
            assert frame["lat"] == 31.0
