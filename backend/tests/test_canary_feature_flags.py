"""S2-OPS-011 灰度门 feature flag 单测（纯单元测试，不走 TestClient）

3 个 flag 拦截点直接调路由函数 + 断言抛 ServiceUnavailableException：
- create_share (FEATURE_SHARE_F2_ENABLED + READONLY_SHARE_SESSIONS)
- exchange_session (READONLY_SHARE_SESSIONS)
- websocket_share (READONLY_SHARE_SESSIONS, close 4015)

不走 FastAPI TestClient 避免 lifespan / auth / DI 顺序问题——这些 flag
是路由函数体首行检查，单测断言就抛即可，full HTTP 路径走集成测试。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.share import create_share, exchange_session
from app.config import settings
from app.exceptions import ServiceUnavailableException
from app.schemas.share import (
    CreateShareRequest,
    ExchangeSessionRequest,
)


# ---------------------------------------------------------------------------
# 默认 flag 值（向后兼容）
# ---------------------------------------------------------------------------


def test_default_flags_do_not_block_share_endpoints():
    """settings 默认值：feature_share_f2_enabled=True / readonly=False
    不应改变现有行为。"""
    assert settings.feature_share_f2_enabled is True
    assert settings.readonly_share_sessions is False


# ---------------------------------------------------------------------------
# create_share: FEATURE_SHARE_F2_ENABLED 拦截
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_raises_503_when_f2_disabled():
    """FEATURE_SHARE_F2_ENABLED=false 时 create_share 抛
    ServiceUnavailableException + SHARE_F2_DISABLED."""
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_session = MagicMock()

    with patch.object(settings, "feature_share_f2_enabled", False):
        with pytest.raises(ServiceUnavailableException) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_F2_DISABLED"


# ---------------------------------------------------------------------------
# create_share: READONLY_SHARE_SESSIONS 拦截（即使 F2 开着也拒）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_raises_503_when_readonly_on_even_with_f2_enabled():
    """READONLY_SHARE_SESSIONS=true 时即使 F2 开着 create_share 也拒。"""
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_session = MagicMock()

    with patch.object(settings, "feature_share_f2_enabled", True), \
         patch.object(settings, "readonly_share_sessions", True):
        with pytest.raises(ServiceUnavailableException) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_SESSIONS_READONLY"


# ---------------------------------------------------------------------------
# exchange_session: READONLY_SHARE_SESSIONS 拦截
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_session_raises_503_when_readonly_on():
    """READONLY_SHARE_SESSIONS=true 时 exchange_session 抛
    ServiceUnavailableException + SHARE_SESSIONS_READONLY。"""
    body = ExchangeSessionRequest(phone="13800000001", otp="123456")
    fake_session = MagicMock()
    fake_redis = MagicMock()

    with patch.object(settings, "readonly_share_sessions", True):
        with pytest.raises(ServiceUnavailableException) as exc_info:
            await exchange_session(
                token="a" * 40,
                body=body,
                session=fake_session,
                redis=fake_redis,
            )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_SESSIONS_READONLY"


# ---------------------------------------------------------------------------
# F2 关闭但 readonly 关闭，create_share 应通过 flag 拦截层（进入业务逻辑）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_passes_flags_when_both_default():
    """flags 默认值时 create_share 应通过 flag 拦截层进入业务（业务里因 mock
    session/user 会 fail，但**不是因 503 flag**——证明 flag 不拦了）。"""
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_session = MagicMock()

    with patch.object(settings, "feature_share_f2_enabled", True), \
         patch.object(settings, "readonly_share_sessions", False):
        with pytest.raises(Exception) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )
        # 异常**不能是** ServiceUnavailableException（因为 flag 没拦）
        assert not isinstance(exc_info.value, ServiceUnavailableException)


# ---------------------------------------------------------------------------
# WS share readonly close 4015 — 用 mock websocket 直接调
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_share_close_4015_when_readonly_on():
    """READONLY_SHARE_SESSIONS=true 时 websocket_share 在 accept 前 close 4015。"""
    from app.api.v1.ws import websocket_share

    fake_ws = MagicMock()
    fake_ws.accept = AsyncMock()
    fake_ws.close = AsyncMock()

    with patch.object(settings, "readonly_share_sessions", True):
        await websocket_share(websocket=fake_ws, token="a" * 40)

    # 直接 close 4015，不 accept
    fake_ws.close.assert_called_once()
    args, kwargs = fake_ws.close.call_args
    code = kwargs.get("code", args[0] if args else None)
    reason = kwargs.get("reason", args[1] if len(args) > 1 else None)
    assert code == 4015
    assert reason == "SHARE_SESSIONS_READONLY"
    # 不能调 accept
    fake_ws.accept.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_share_passes_when_readonly_off():
    """READONLY_SHARE_SESSIONS=false 时 websocket_share 应正常 accept。
    （之后会进入 share_auth_handshake，由于 mock 不发帧会卡——这里只验 accept 调用了）"""
    from app.api.v1 import ws as ws_module

    fake_ws = MagicMock()
    fake_ws.accept = AsyncMock()
    fake_ws.close = AsyncMock()

    # mock share_auth_handshake 返回 None 让函数提前 return
    with patch.object(settings, "readonly_share_sessions", False), \
         patch.object(ws_module, "_share_auth_handshake", AsyncMock(return_value=None)):
        await ws_module.websocket_share(websocket=fake_ws, token="a" * 40)

    # accept 被调，close 不被调（或被调但不是 4015）
    fake_ws.accept.assert_called_once()
    # 即使 close 被调（因 _share_auth_handshake 返回 None 后 return，handshake 自己不 close）
    # 应该没有 close 4015 调用
    for call in fake_ws.close.call_args_list:
        args, kwargs = call
        code = kwargs.get("code", args[0] if args else None)
        assert code != 4015, "readonly=false 不应 close 4015"
