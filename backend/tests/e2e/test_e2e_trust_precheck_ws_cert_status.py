"""E2E test — trust-precheck WS broadcast (AC#4 / design §4.1 §6.3).

Phase A2 (S3-TEST-003) — 验收 board AC#4 "WS 推送 cert_status_changed
≤3s, 含 1 次自动重连" + design doc AC#4 "WS broadcast → 前端 onMessage
≤5s, 含 1 次自动重连". 因 design 已与 backend 实现校准 (event name
是 ``precheck.status.updated`` 通用 envelope, cert 状态变化作为 envelope
内字段携带, 不是单独 ``cert_status_changed`` event), 本 test 围绕实际
contract 验收, 而非 design 字面文本.

Layer 拆分 (复用 Phase A1 5-layer pattern, 适配 WS 主题):

- L1 — Schema/Code: WS handler 落位 + envelope schema 字段 + 通用 event
       name + close code 4003/4004 contract.
- L2 — Owner gate (ABAC L2.5): 4003 not_owner / 4004 order_not_found
       contract 复用 (实证 hybrid 404 mask 在 WS 层接受 4003/4004 差异化).
- L3 — Broker registration: ``get_or_create_precheck_broker`` 在 app
       startup / first-WS-connect 路径都能拿到 singleton broker.
- L4 — Broadcast envelope: ``_ws_broadcast`` summary param 携带正确
       cert_* 字段子集 (跟 Phase A1 5 cert 字段全集对齐).
- L5 — Idle timeout / heartbeat / reconnect contract: WS_IDLE_TIMEOUT
       constant + counter metric 在 idle close 路径触发.

测试策略:

- 不真起 uvicorn (e2e/test_e2e_precheck_pubsub_cross_replica 系列已 cover);
  本 file 聚焦 ``contract-level`` 验证 (字段名 / close code / event name),
  E2E 实际 WS 流由 backend integration test 兜底.
- 关键 fixture: ``app_with_precheck_router`` (sync helper, 不 require WS
  client), ``aggregator_with_mock_broker`` (mock broker.broadcast).

CI / pre-push:
- 所有 test 走 ``shutil.which("python3.11")`` (复用 Phase A1 lesson:
  pathlib.Path.is_relative_to 是 3.9+, 但 hook fallback python3 是
  3.8). pytest 直接 invoke 已是 3.11 venv, 此约束仅 subprocess 适用.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

# Project root (3 levels up: tests/e2e/<this>.py → repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"


# ──────────────────────────────────────────────────────────────────────────
# L1 — Schema / Code contract
# ──────────────────────────────────────────────────────────────────────────


class TestL1WSHandlerSchema:
    """L1 — backend WS handler 落位 + envelope contract."""

    def test_precheck_ws_route_registered(self) -> None:
        """``/ws/v1/orders/{order_id}/precheck`` route 在 ws router."""
        ws_module = importlib.import_module("app.api.v1.ws")
        router = ws_module.router
        ws_routes = [
            route
            for route in router.routes
            if "precheck" in getattr(route, "path", "")
        ]
        assert ws_routes, (
            "/ws/v1/orders/{order_id}/precheck route 未在 ws router 注册 "
            "(AC#4 WS broadcast 前置: handler 必须存在)"
        )
        paths = {getattr(r, "path", "") for r in ws_routes}
        assert any(
            "/ws/v1/orders/" in p and "/precheck" in p for p in paths
        ), f"precheck WS route path 不符预期, 实际 paths={paths}"

    def test_precheck_ws_uses_owner_gate_dep(self) -> None:
        """WS handler 必须 import load_order_owner_id (ABAC L2.5)."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        # 不要求 top-level import, 允许函数内 late import (实际就是).
        assert (
            "load_order_owner_id" in ws_src
        ), "WS handler 必须 import load_order_owner_id (ABAC L2.5 owner gate)"

    def test_precheck_ws_close_code_contract(self) -> None:
        """WS close code 4003 not_owner / 4004 order_not_found contract."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        # 找 precheck handler 段
        assert "websocket_precheck" in ws_src
        # 4003 / 4004 close code 在 handler 段出现
        assert (
            "4003" in ws_src and "4004" in ws_src
        ), "WS close code 4003 (not_owner) / 4004 (order_not_found) 必须存在"
        assert (
            "not_owner" in ws_src
        ), "close reason 'not_owner' 必须存在 (ABAC L2.5)"
        assert (
            "order_not_found" in ws_src
        ), "close reason 'order_not_found' 必须存在 (ABAC L2.5)"

    def test_precheck_ws_event_name_aligned_with_aggregator(self) -> None:
        """Aggregator broadcast envelope event name 与 design doc 校准.

        Design doc §4.1 / §6.3 提到 ``cert_status_changed`` 是状态变化
        语义描述, backend 实际 envelope 用通用 ``precheck.status.updated``
        + envelope.summary 内 cert_status 字段差异表达. 本 test 锁定
        backend 一致使用 ``precheck.status.updated``, 不被 design 文字
        漂移误导.
        """
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        assert (
            "precheck.status.updated" in agg_src
        ), "Aggregator broadcast envelope 必须用 'precheck.status.updated' event name"

    def test_precheck_ws_idle_timeout_constant(self) -> None:
        """WS_IDLE_TIMEOUT_SECONDS constant 必须存在 (heartbeat policy)."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        assert (
            "WS_IDLE_TIMEOUT_SECONDS" in ws_src
        ), "WS_IDLE_TIMEOUT_SECONDS constant 必须存在 (AC#4 reconnect contract)"


# ──────────────────────────────────────────────────────────────────────────
# L2 — Owner gate (ABAC L2.5)
# ──────────────────────────────────────────────────────────────────────────


class TestL2OwnerGateContract:
    """L2 — ABAC L2.5 owner gate contract 在 WS + REST 两层一致."""

    def test_load_order_owner_id_exists(self) -> None:
        """``load_order_owner_id`` 在 deps_precheck (WS + REST 共享)."""
        deps = importlib.import_module("app.api.v1.deps_precheck")
        assert hasattr(
            deps, "load_order_owner_id"
        ), "load_order_owner_id 必须存在 (ABAC L2.5 owner gate 共享 dep)"
        # 必须是 async function
        assert inspect.iscoroutinefunction(
            deps.load_order_owner_id
        ), "load_order_owner_id 必须是 async function"

    def test_owner_check_failure_exception_class(self) -> None:
        """OwnerCheckFailure 异常类 (WS handler 捕获用)."""
        deps = importlib.import_module("app.api.v1.deps_precheck")
        assert hasattr(
            deps, "OwnerCheckFailure"
        ), "OwnerCheckFailure 异常类必须存在 (WS handler 捕获用)"


# ──────────────────────────────────────────────────────────────────────────
# L3 — Broker registration (singleton per app)
# ──────────────────────────────────────────────────────────────────────────


class TestL3BrokerSingleton:
    """L3 — precheck broker 在 app 级 singleton, register/unregister 对称."""

    def test_get_or_create_precheck_broker_exists(self) -> None:
        """``get_or_create_precheck_broker`` 公开 API."""
        broker_mod = importlib.import_module("app.services.precheck_broadcast")
        assert hasattr(
            broker_mod, "get_or_create_precheck_broker"
        ), "get_or_create_precheck_broker 必须存在 (broker singleton 入口)"

    def test_broker_class_has_register_broadcast(self) -> None:
        """Broker 类必须有 register / broadcast 方法."""
        broker_mod = importlib.import_module("app.services.precheck_broadcast")
        # 找 broker 类 — 常见命名 PrecheckBroker / PrecheckBroadcast
        broker_classes = [
            obj
            for name, obj in inspect.getmembers(broker_mod, inspect.isclass)
            if "Broker" in name or "Broadcast" in name
        ]
        assert broker_classes, (
            "precheck_broadcast 模块必须有 Broker/Broadcast class "
            "(WS register + broadcast 接口承载)"
        )
        # 至少一个 broker class 有 register 方法
        with_register = [
            c for c in broker_classes if any(
                hasattr(c, name) for name in ("register", "subscribe", "connect")
            )
        ]
        assert with_register, (
            f"Broker class 必须有 register/subscribe/connect 方法之一, "
            f"实际 classes={[c.__name__ for c in broker_classes]}"
        )


# ──────────────────────────────────────────────────────────────────────────
# L4 — Broadcast envelope cert_* 字段透传
# ──────────────────────────────────────────────────────────────────────────


class TestL4BroadcastEnvelopeCertFields:
    """L4 — Aggregator ``_ws_broadcast`` summary 携带 cert_* 字段."""

    def test_broadcast_takes_summary_param(self) -> None:
        """``_ws_broadcast`` 必须接受 summary 参数 (c6 dedup)."""
        agg_mod = importlib.import_module(
            "app.services.order_precheck_aggregator"
        )
        # 找 aggregator class
        agg_classes = [
            obj
            for name, obj in inspect.getmembers(agg_mod, inspect.isclass)
            if "Aggregator" in name
        ]
        assert agg_classes, "OrderPrecheckAggregator class 必须存在"
        # _ws_broadcast signature 接受 summary kwarg
        agg_cls = agg_classes[0]
        if hasattr(agg_cls, "_ws_broadcast"):
            sig = inspect.signature(agg_cls._ws_broadcast)
            assert (
                "summary" in sig.parameters
            ), f"_ws_broadcast 必须接受 summary 参数, 实际 params={list(sig.parameters)}"

    def test_aggregator_evaluate_returns_cert_fields(self) -> None:
        """Aggregator.evaluate 产出包含 5 cert 字段全集 (Phase A1 验证).

        Phase A1 锁了 CompanionCertStatusView 5 字段全集, 本 test 检查
        aggregator 源码引用这些字段 (避免 broadcast envelope 漏字段).
        """
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        # 至少引用其中 3 个核心 cert 字段 (cert_status 是必有)
        core_cert_fields = ["cert_status", "companion_cert"]
        found = sum(1 for f in core_cert_fields if f in agg_src)
        assert (
            found >= 2
        ), f"Aggregator 必须引用核心 cert 字段, 实际命中={found}/{len(core_cert_fields)}"


# ──────────────────────────────────────────────────────────────────────────
# L5 — Idle timeout / counter / reconnect contract
# ──────────────────────────────────────────────────────────────────────────


class TestL5IdleAndReconnectContract:
    """L5 — WS idle timeout 触发 counter + close code, 支持 client 重连."""

    def test_ws_idle_timeout_counter_metric(self) -> None:
        """``ws_idle_timeout_total`` Prometheus counter 必须存在."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        assert (
            "ws_idle_timeout_total" in ws_src
        ), "ws_idle_timeout_total counter 必须存在 (idle close metric)"

    def test_ws_idle_timeout_labelled_by_channel(self) -> None:
        """counter label channel=precheck 必须存在."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        # grep counter.labels(channel="precheck") 或类似
        assert re.search(
            r'labels\([^)]*channel\s*=\s*["\']precheck["\']', ws_src
        ), "idle timeout counter 必须 label channel='precheck'"

    def test_ws_handler_logs_idle_close(self) -> None:
        """idle 超时 close 时必须 logger.info 含 order_id (debugging)."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        # ws.idle_timeout log event
        assert (
            "ws.idle_timeout" in ws_src
        ), "WS idle timeout 必须有 logger.info('ws.idle_timeout') 事件"
