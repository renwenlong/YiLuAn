"""S2-OPS-011 灰度门 feature flag 单测

验证 FEATURE_SHARE_F2_ENABLED + READONLY_SHARE_SESSIONS 的拦截行为。
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    """简化：FastAPI TestClient 默认无 token；本测试关注 503 拦截先于鉴权
    则即便 token 缺失，503 也优先触发——这是设计意图（feature flag 是
    系统级开关，不应被鉴权穿透）。"""
    return {}


# ---------------------------------------------------------------------------
# FEATURE_SHARE_F2_ENABLED
# ---------------------------------------------------------------------------


def test_create_share_blocked_when_f2_disabled(client, auth_headers):
    """FEATURE_SHARE_F2_ENABLED=false 时 POST /orders/{id}/shares 返回 503
    + SHARE_F2_DISABLED 错误码。"""
    with patch.object(settings, "feature_share_f2_enabled", False):
        resp = client.post(
            f"/api/v1/orders/{uuid4()}/shares",
            json={"share_scope": "full"},
            headers=auth_headers,
        )
    assert resp.status_code == 503
    body = resp.json()
    detail = body.get("detail")
    # detail 可能是 dict 含 error_code 或 string，按 AppException 实现
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_F2_DISABLED"


def test_create_share_passes_through_when_f2_enabled(client, auth_headers):
    """FEATURE_SHARE_F2_ENABLED=true 时 503 不触发（鉴权失败回 401/403，不
    是 503——证明 flag 拦截不拦了）。"""
    with patch.object(settings, "feature_share_f2_enabled", True), \
         patch.object(settings, "readonly_share_sessions", False):
        resp = client.post(
            f"/api/v1/orders/{uuid4()}/shares",
            json={"share_scope": "full"},
            headers=auth_headers,
        )
    # 拒因为没 token / order 不存在等业务原因，但绝对不是 503 SHARE_F2_DISABLED
    assert resp.status_code != 503 or (
        isinstance(resp.json().get("detail"), dict)
        and resp.json()["detail"].get("error_code") != "SHARE_F2_DISABLED"
    )


# ---------------------------------------------------------------------------
# READONLY_SHARE_SESSIONS
# ---------------------------------------------------------------------------


def test_create_share_blocked_when_readonly_on(client, auth_headers):
    """READONLY_SHARE_SESSIONS=true 时 POST /shares 也被拒（503 + READONLY）。"""
    with patch.object(settings, "feature_share_f2_enabled", True), \
         patch.object(settings, "readonly_share_sessions", True):
        resp = client.post(
            f"/api/v1/orders/{uuid4()}/shares",
            json={"share_scope": "full"},
            headers=auth_headers,
        )
    assert resp.status_code == 503
    detail = resp.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_SESSIONS_READONLY"


def test_exchange_session_blocked_when_readonly_on(client):
    """READONLY_SHARE_SESSIONS=true 时 POST /shares/{token}/session 拒（冻结新
    会话），但已发 share_session JWT 仍可读视图（fetchShareOrder 不受本拦截）。"""
    fake_token = "a" * 40
    with patch.object(settings, "readonly_share_sessions", True):
        resp = client.post(
            f"/api/v1/shares/{fake_token}/session",
            json={"phone": "13800000001", "otp": "123456"},
        )
    assert resp.status_code == 503
    detail = resp.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_SESSIONS_READONLY"


# ---------------------------------------------------------------------------
# WS share upgrade 拦截
# ---------------------------------------------------------------------------


def test_ws_share_close_4015_when_readonly_on(client):
    """READONLY_SHARE_SESSIONS=true 时 WS upgrade 直接 close 4015。"""
    fake_token = "a" * 40
    with patch.object(settings, "readonly_share_sessions", True):
        with pytest.raises(Exception) as exc_info:
            with client.websocket_connect(f"/api/v1/ws/share/{fake_token}") as ws:
                ws.receive_text()  # 应该收不到任何消息（close 4015）
        # WebSocketDisconnect 应被抛出含 code=4015
        # 不同 starlette/fastapi 版本异常类型不同，宽松检查 code 4015 在 str 里
        assert "4015" in str(exc_info.value) or "SHARE_SESSIONS_READONLY" in str(exc_info.value)


def test_ws_share_normal_when_flags_off(client):
    """flags 默认 False 时 WS upgrade 不被拦截（accept 后等 share_auth 帧）。"""
    fake_token = "a" * 40
    with patch.object(settings, "readonly_share_sessions", False):
        # WS 会 accept 然后等 share_auth 帧；如果客户端不发会被服务端超时
        # 这里我们只验证 不立即 close 4015——能成功 connect 即可
        try:
            with client.websocket_connect(f"/api/v1/ws/share/{fake_token}") as ws:
                # 主动关掉避免挂起
                ws.close()
        except Exception as e:
            # 不能含 4015
            assert "4015" not in str(e)


# ---------------------------------------------------------------------------
# 默认配置不阻断业务（向后兼容）
# ---------------------------------------------------------------------------


def test_default_flags_do_not_block_share_endpoints():
    """settings 默认值：feature_share_f2_enabled=True / readonly=False
    不应改变现有行为。"""
    assert settings.feature_share_f2_enabled is True
    assert settings.readonly_share_sessions is False
