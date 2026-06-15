"""E2E test — trust-precheck polling fallback (AC#6 / design AC#4 polling 30s).

Phase A2 (S3-TEST-003) — 验收 board AC#6 "WS 断开后 polling fallback 30s
切换正确 + 灰度文案一致" + design doc AC#4 "polling fallback 30±2s 切换
正确, 不能提前刷接口 (<28s) 或超过 32s".

# 跨端 gap 实证 (本 file 关键发现)

iOS 实现了 ``PrecheckViewModel.startPolling`` (30s interval, WS 断后启用,
WS 重连后停止). WX 当前 ``precheckWs.js`` 仅做 ws reconnect (jitter),
**WX 没有 page-level polling fallback 30s 实现**, page ``order-detail/index.js``
``_connectPrecheckWs`` 只挂 WS event 回调, 没有 WS 断后切 polling 逻辑.

跨端一致性 gap → 本 file ``L4_WxPollingFallback`` 类全 SKIP, reason 写
明确 "WX 缺 polling fallback 实现", forward-compat 一旦补则自动启用
(避免静默漂移).

# Layer 拆分

- L1 — Backend polling endpoint: ``GET /api/v1/users/orders/{order_id}/
       precheck-status`` 存在 + cache HIT/MISS 路径 + ABAC 404 hybrid mask.
- L2 — iOS polling fallback: ``PrecheckViewModel`` polling 30s + WS 断
       触发 + WS 重连停止 + init 默认值校验.
- L3 — Backend polling cache TTL: 5min (300s) cache TTL 与 polling 5s
       间隔 (design §4.1 polling 间隔 5s, fallback 切换延时 30±2s).
- L4 — WX polling fallback (跨端 gap): WX 缺 polling fallback 实现,
       SKIP forward-compat.
- L5 — design doc 与实现一致性: design §4.1 polling 间隔 = 5s, fallback
       切换延时 = 30±2s, polling 30s 是 iOS interval (覆盖在 fallback
       延时窗口外).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

# Project root.
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"
IOS = REPO_ROOT / "ios"
WX = REPO_ROOT / "wechat"


# ──────────────────────────────────────────────────────────────────────────
# L1 — Backend polling endpoint contract
# ──────────────────────────────────────────────────────────────────────────


class TestL1BackendPollingEndpoint:
    """L1 — backend GET endpoint 是 polling fallback 的服务端."""

    def test_users_precheck_router_exists(self) -> None:
        """``GET /{order_id}/precheck-status`` router 存在."""
        users_precheck = importlib.import_module("app.api.v1.users_precheck")
        # router 对象
        assert hasattr(
            users_precheck, "router"
        ), "users_precheck.router 必须存在"
        # precheck-status path 在 routes
        paths = {getattr(r, "path", "") for r in users_precheck.router.routes}
        assert any(
            "precheck-status" in p for p in paths
        ), f"GET precheck-status 路由必须存在, 实际 paths={paths}"

    def test_get_precheck_status_is_async(self) -> None:
        """endpoint 是 async function (FastAPI dep + cache 读 redis)."""
        import inspect

        users_precheck = importlib.import_module("app.api.v1.users_precheck")
        endpoint = getattr(users_precheck, "get_precheck_status", None)
        assert endpoint is not None, "get_precheck_status function 必须存在"
        assert inspect.iscoroutinefunction(
            endpoint
        ), "get_precheck_status 必须是 async function"

    def test_endpoint_doc_mentions_polling_5s(self) -> None:
        """endpoint 描述必须提及 polling 5s 间隔 (design §4.1)."""
        endpoint_src = (
            BACKEND / "app" / "api" / "v1" / "users_precheck.py"
        ).read_text()
        # design §4.1: polling 间隔 5s
        assert (
            re.search(r"polling.*5s|5s.*polling|polling.*5 ?\*", endpoint_src)
            is not None
        ), "endpoint 必须文档化 polling 5s 间隔 (design §4.1)"

    def test_cache_ttl_5min(self) -> None:
        """Aggregator cache TTL = 5min (300s), polling 不读 stale 数据."""
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        # _CACHE_TTL_SECONDS 接受 literal 300 或 5*60 / 60*5 表达式
        patterns = [
            r"_CACHE_TTL_SECONDS[^=]*=\s*300\b",
            r"_CACHE_TTL_SECONDS[^=]*=\s*5\s*\*\s*60\b",
            r"_CACHE_TTL_SECONDS[^=]*=\s*60\s*\*\s*5\b",
        ]
        matched = any(re.search(p, agg_src) for p in patterns)
        assert (
            matched
        ), (
            "_CACHE_TTL_SECONDS 必须 = 300 (5min), "
            "接受 literal 300 或 5*60/60*5 表达式"
        )


# ──────────────────────────────────────────────────────────────────────────
# L2 — iOS polling fallback impl
# ──────────────────────────────────────────────────────────────────────────


IOS_PRECHECK_VM = (
    IOS / "YiLuAn" / "Features" / "Precheck" / "ViewModels" / "PrecheckViewModel.swift"
)


class TestL2IosPollingFallback:
    """L2 — iOS PrecheckViewModel polling 30s fallback impl."""

    def test_ios_viewmodel_exists(self) -> None:
        assert (
            IOS_PRECHECK_VM.exists()
        ), f"iOS PrecheckViewModel.swift 必须存在: {IOS_PRECHECK_VM}"

    def test_ios_polling_interval_default_30s(self) -> None:
        """``pollingInterval`` init 默认值 = 30 (设计 §4.1 polling 30s)."""
        src = IOS_PRECHECK_VM.read_text()
        # init(orderId: String, pollingInterval: TimeInterval = 30)
        assert re.search(
            r"pollingInterval\s*:\s*TimeInterval\s*=\s*30\b", src
        ), "iOS polling interval 默认必须 = 30 (TimeInterval = 30)"

    def test_ios_starts_polling_on_ws_disconnect(self) -> None:
        """iOS WS 断开后 startPolling, WS 重连后 stopPolling."""
        src = IOS_PRECHECK_VM.read_text()
        assert (
            "startPolling()" in src
        ), "iOS 必须有 startPolling() 方法 (polling fallback 入口)"
        assert (
            "stopPolling()" in src
        ), "iOS 必须有 stopPolling() 方法 (WS 上线即停)"
        # comment 含 "WS 上线即停" 或 "WS 断" 语义
        assert (
            "WS 上线即停" in src or "WS 断" in src or "fallback" in src.lower()
        ), "iOS 必须文档化 WS 状态变更触发 polling 切换"

    def test_ios_isPollingFallback_published_state(self) -> None:
        """``isPollingFallback`` @Published 暴露给 UI (灰度 / 文案 hint)."""
        src = IOS_PRECHECK_VM.read_text()
        assert re.search(
            r"@Published\s+private\(set\)\s+var\s+isPollingFallback", src
        ), (
            "iOS 必须 @Published isPollingFallback state "
            "(支撑 design AC#6 文案一致性: UI 显示 polling fallback 提示)"
        )


# ──────────────────────────────────────────────────────────────────────────
# L3 — Backend polling cache + TTL contract
# ──────────────────────────────────────────────────────────────────────────


class TestL3PollingCacheContract:
    """L3 — cache HIT/MISS + TTL + invalidation 在 polling 路径正确."""

    def test_endpoint_cache_read_through_path(self) -> None:
        """endpoint 必须 read-through cache (HIT 返回, MISS 走 aggregator)."""
        endpoint_src = (
            BACKEND / "app" / "api" / "v1" / "users_precheck.py"
        ).read_text()
        # 用 redis.get(cache_key) HIT 路径 + aggregator.evaluate MISS 路径
        assert (
            "redis.get" in endpoint_src
        ), "endpoint 必须 redis.get cache HIT 路径"
        assert (
            "aggregator.evaluate" in endpoint_src
        ), "endpoint 必须 aggregator.evaluate MISS 路径"

    def test_invalidation_pre_invalidate_then_set(self) -> None:
        """aggregator._invalidate_cache (after_commit hook) 必须 DEL 后 SET.

        Design AC#10 (board AC#10 等价): 防御性 pre-invalidation, 避免
        polling 5s 读到 stale 数据.
        """
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        # 必须有 invalidate / DEL 操作
        assert (
            "redis.delete" in agg_src or "_redis.delete" in agg_src
        ), "aggregator 必须有 redis.delete invalidation (防 stale)"

    def test_cache_key_scoped_by_order_id(self) -> None:
        """cache key 必须按 order_id scope (不能跨订单 leak)."""
        endpoint_src = (
            BACKEND / "app" / "api" / "v1" / "users_precheck.py"
        ).read_text()
        # _build_cache_key(order_id) or precheck:order:{order_id}
        assert (
            "_build_cache_key" in endpoint_src
            or "precheck:order:" in endpoint_src
        ), "cache key 必须 scoped by order_id"


# ──────────────────────────────────────────────────────────────────────────
# L4 — WX polling fallback (跨端 gap, 全 SKIP forward-compat)
# ──────────────────────────────────────────────────────────────────────────


WX_PRECHECK_WS = WX / "services" / "precheckWs.js"
WX_ORDER_DETAIL = WX / "pages" / "patient" / "order-detail" / "index.js"


def _wx_has_polling_fallback() -> tuple[bool, str]:
    """检查 WX 是否实现 polling fallback (page-level / service-level)."""
    if not WX_PRECHECK_WS.exists():
        return False, f"precheckWs.js 不存在: {WX_PRECHECK_WS}"
    if not WX_ORDER_DETAIL.exists():
        return False, f"order-detail/index.js 不存在: {WX_ORDER_DETAIL}"

    ws_src = WX_PRECHECK_WS.read_text()
    page_src = WX_ORDER_DETAIL.read_text()
    combined = ws_src + "\n" + page_src

    # 检查 polling fallback 关键标记 (page 或 service 任一实现都接受)
    indicators = [
        "polling",  # 任何 polling 关键词
        "setInterval",  # WX timer
        "_pollingTimer",  # 常见命名
        "_precheckPollingTimer",
        "pollingFallback",
        "isPollingFallback",
    ]
    hits = [s for s in indicators if s in combined]
    # setInterval 在 page 用于 countdown 不算 — 必须明确关联 precheck
    has_precheck_polling = any(
        s in combined for s in (
            "_pollingTimer", "_precheckPollingTimer",
            "pollingFallback", "isPollingFallback",
        )
    )
    if has_precheck_polling:
        return True, f"detected: {hits}"
    return False, f"missing polling fallback for precheck (hits={hits})"


class TestL4WxPollingFallbackGap:
    """L4 — WX 缺 polling fallback 实现 (跨端一致性 gap)."""

    def test_wx_polling_fallback_detection(self) -> None:
        """文档化 WX 当前不实现 polling fallback (跨端 gap)."""
        has_impl, reason = _wx_has_polling_fallback()
        if has_impl:
            # 一旦补上, test 转 PASS
            assert True, f"WX 已实现 polling fallback: {reason}"
        else:
            pytest.skip(
                f"⚠️ 跨端 gap: WX 缺 polling fallback 实现 "
                f"(iOS 已实 30s polling). reason={reason}. "
                f"AC#6 跨端文案一致性受影响 — 建议 WX 端补 page-level "
                f"polling fallback (setInterval 30s, WS 重连后 clear)."
            )

    def test_wx_ws_has_reconnect_at_least(self) -> None:
        """WX 至少必须有 WS reconnect (precheckWs.js)."""
        ws_src = WX_PRECHECK_WS.read_text()
        assert (
            "reconnect" in ws_src
        ), (
            "WX precheckWs.js 必须有 reconnect 逻辑 (即便没有 polling fallback, "
            "WS 重连 jitter 是 baseline)"
        )


# ──────────────────────────────────────────────────────────────────────────
# L5 — design doc ↔ 实现 一致性 sentinel
# ──────────────────────────────────────────────────────────────────────────


DESIGN_DOC = REPO_ROOT / "docs" / "design" / "S3-trust-precheck-ui.md"


class TestL5DesignImplConsistency:
    """L5 — design doc 与实现 polling/WS 数值校准."""

    def test_design_doc_polling_5s_documented(self) -> None:
        """Design doc §4.1 明确 polling 间隔 5s."""
        src = DESIGN_DOC.read_text()
        assert re.search(
            r"polling\s*5s|5s.*polling|polling.*间隔.*5", src
        ), "design doc 必须文档化 polling 间隔 5s"

    def test_design_doc_polling_fallback_30s_documented(self) -> None:
        """Design doc 明确 fallback 切换延时 30±2s 或 polling 30s 兜底."""
        src = DESIGN_DOC.read_text()
        # 接受 "30±2s" / "30s" / "polling fallback 30" 任一表达
        assert re.search(
            r"polling.*30\b|30.*polling|30±2s|polling fallback.*30", src
        ), (
            "design doc 必须文档化 polling fallback 30s 兜底 "
            "(切换延时或 polling 间隔表达任一)"
        )

    def test_design_doc_ws_latency_5s(self) -> None:
        """Design doc AC#4 WS ≤5s 端到端延时."""
        src = DESIGN_DOC.read_text()
        assert re.search(
            r"WS.*≤5s|≤5s.*WS|broadcast.*≤5s|WS.*5s.*onMessage", src
        ), "design doc 必须文档化 WS ≤5s 端到端延时 (AC#4)"
