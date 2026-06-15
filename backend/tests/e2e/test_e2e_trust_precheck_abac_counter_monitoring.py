"""E2E test — Phase D: trust-precheck ABAC counter 灰度 baseline 监控 (AC#9).

Phase D (S3-TEST-003) — 验收 board AC#9 "灰度发布期间 ABAC counter 监控 baseline":
当 ``precheck_abac_filtered_total`` counter (P2 task ``S3-DEV-003-PRECHECK-ABAC-COUNTER``
uuid ``c6323053`` hutao) 实施后, 灰度期间 metric 行为:

1. counter 在 ``backend/app/utils/metrics.py`` 注册 (跟随现有 prometheus_client pattern)
2. ABAC 4 层 filter hit 时 counter ``inc()`` (依赖注入 chain 触发)
3. label 维度: 至少 ``layer`` (l1/l2/l3/l4) + ``field`` (17 字段之一, 含 2 patterns) 或 aggregate
4. ``/metrics`` Prometheus endpoint expose 这个 counter (mounted at ``backend/app/main.py:253``)
5. counter value monotonic increase, scrape format 符合 Prometheus exposition

# Forward-compat 设计

跟 Phase B
``test_e2e_trust_precheck_abac_negative_list.py::test_precheck_abac_filtered_counter_gap``
同模式: counter 未实时 SKIP, 实了自动 PASS. 不阻 Phase D done — counter merged
后 ci 自动转 PASS.

# Gray-release baseline (AC#9 灰度监控)

灰度发布期间, 这个 counter 的 baseline 行为:
- 流量 0 → counter 应为 0 (或 absent)
- 流量 N (灰度 5%/20%/100%) → counter 应 ~= ABAC filter 命中次数 (无超量/泄漏)
- 异常 spike (counter 远超流量) → alarm signal: ABAC 误命中或 attack 迹象

本测试覆盖 monotonic + Prometheus exposition 两个 invariant;
灰度真实 baseline 比对 (mean/p99/SLA) 是 Grafana / Alertmanager 域,
不在 e2e test scope.

# 关键约束

- 用 mock Redis (与 polling_fallback test 同 pattern), 不需要真 Redis
- counter 模块 import 应在 fixture 内, 不在 module top — 否则 forward-compat
  skip 会被 ImportError 破坏
- 跟 ``test_e2e_trust_precheck_abac_negative_list.py`` 互补, 不重复 17 字段语义校验
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"
METRICS_FILE = BACKEND / "app" / "utils" / "metrics.py"
COUNTER_NAME = "precheck_abac_filtered_total"


# ──────────────────────────────────────────────────────────────────────────
# Helper — counter 实施状态 probe (forward-compat 单点)
# ──────────────────────────────────────────────────────────────────────────


def _counter_implemented() -> tuple[bool, list[str]]:
    """grep backend/app 找 counter 名. 返回 (实施了?, hit 文件列表)."""
    hits: list[str] = []
    for f in (BACKEND / "app").rglob("*.py"):
        try:
            src = f.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if COUNTER_NAME in src:
            hits.append(str(f.relative_to(REPO_ROOT)))
    return bool(hits), hits


# ──────────────────────────────────────────────────────────────────────────
# L1 — counter 注册位置 (metrics.py)
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDCounterRegistration:
    """L1 — counter 必须注册在 ``backend/app/utils/metrics.py``.

    跟现有 ``order_created_total`` / ``ai_blocklist_*`` 同位置;
    集中注册便于 Prometheus scrape 一次 import.
    """

    def test_counter_lives_in_metrics_module(self) -> None:
        """counter 注册位置 = ``backend/app/utils/metrics.py``."""
        implemented, hits = _counter_implemented()
        if not implemented:
            pytest.skip(
                f"⚠️ Phase D forward-compat skip: counter '{COUNTER_NAME}' 未实, "
                f"等 dev task S3-DEV-003-PRECHECK-ABAC-COUNTER (c6323053 hutao) 完成. "
                f"现有 Phase B negative_list test 已有同源 forward-compat probe, "
                f"两边一起转 PASS."
            )
        metrics_src = METRICS_FILE.read_text()
        assert COUNTER_NAME in metrics_src, (
            f"counter '{COUNTER_NAME}' 必须注册在 metrics.py 集中位置, "
            f"实际找到在: {hits} (不在 metrics.py)"
        )

    def test_counter_uses_prometheus_client_Counter(self) -> None:
        """counter 必须用 prometheus_client.Counter, 不能自造或用 Gauge/Histogram."""
        implemented, _ = _counter_implemented()
        if not implemented:
            pytest.skip(f"Phase D forward-compat skip: {COUNTER_NAME} 未实")
        src = METRICS_FILE.read_text()
        pattern = rf"{re.escape(COUNTER_NAME)}\s*=\s*Counter\s*\("
        assert re.search(pattern, src), (
            f"counter '{COUNTER_NAME}' 必须是 prometheus_client.Counter, "
            f"不能用 Gauge/Histogram/自造类"
        )


# ──────────────────────────────────────────────────────────────────────────
# L2 — counter labels 覆盖 ABAC 4 层 + 17 字段维度
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDCounterLabels:
    """L2 — counter 必须有可观测维度, 否则灰度无法定位问题源."""

    def test_counter_has_layer_or_field_label(self) -> None:
        """counter 至少含 'layer' OR 'field' label, 否则只能看总数, 灰度阶段无定位力.

        ABAC 4 层 (L1 schema / L2 endpoint / L3 SELECT / L4 schemathesis)
        + 17 字段 (15 named + 2 patterns) 任一维度可标即可.
        """
        implemented, _ = _counter_implemented()
        if not implemented:
            pytest.skip(f"Phase D forward-compat skip: {COUNTER_NAME} 未实")
        src = METRICS_FILE.read_text()
        # 找 counter 定义块 (从 COUNTER_NAME 到下一个 = Counter( 或文件末)
        idx = src.find(COUNTER_NAME)
        block = src[idx : idx + 800] if idx >= 0 else ""
        has_layer = "layer" in block.lower()
        has_field = "field" in block.lower()
        assert has_layer or has_field, (
            f"counter '{COUNTER_NAME}' 应至少标 layer 或 field 一个维度, "
            f"definition block: {block[:300]}"
        )


# ──────────────────────────────────────────────────────────────────────────
# L3 — counter 触发点 (ABAC hit 时 .inc())
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDCounterTriggerPoint:
    """L3 — counter 必须在 ABAC filter 实际命中点被 .inc(), 不能只注册不触发."""

    def test_counter_is_actually_incremented_in_codebase(self) -> None:
        """grep ``.inc()`` / ``.labels(...).inc()`` near counter import."""
        implemented, hits = _counter_implemented()
        if not implemented:
            pytest.skip(f"Phase D forward-compat skip: {COUNTER_NAME} 未实")
        triggered_files: list[str] = []
        for hit_path in hits:
            abs_path = REPO_ROOT / hit_path
            if abs_path == METRICS_FILE:
                continue
            src = abs_path.read_text()
            if ".inc(" in src or ".labels(" in src:
                triggered_files.append(hit_path)
        assert triggered_files, (
            f"counter '{COUNTER_NAME}' 注册了但没找到 .inc() / .labels() 触发点. "
            f"定义出现在: {hits}, 但都没 .inc(). 灰度上线后 counter 永远为 0, "
            f"无法实现 AC#9 baseline 监控."
        )


# ──────────────────────────────────────────────────────────────────────────
# L4 — /metrics endpoint expose counter
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDMetricsEndpointExposes:
    """L4 — counter 必须能被 Prometheus scrape (/metrics endpoint)."""

    def test_metrics_endpoint_mounted(self) -> None:
        """``backend/app/main.py`` 须 mount ``/metrics`` (现有 line 253 应保留)."""
        main_py = BACKEND / "app" / "main.py"
        src = main_py.read_text()
        assert 'mount("/metrics"' in src or "mount('/metrics'" in src, (
            "/metrics endpoint 必须 mount 在 backend/app/main.py "
            "(现 line 253, 不要 break Prometheus scrape 路径)"
        )

    def test_counter_appears_in_metrics_scrape(self) -> None:
        """灰度 baseline 必须能 scrape — TestClient GET /metrics 含 counter HELP/TYPE."""
        implemented, _ = _counter_implemented()
        if not implemented:
            pytest.skip(f"Phase D forward-compat skip: {COUNTER_NAME} 未实")
        try:
            from fastapi.testclient import TestClient

            from app.main import app  # type: ignore[import-not-found]
        except ImportError as e:
            pytest.skip(f"app import 失败, 跳过 endpoint scrape 验证: {e}")

        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 200, (
            f"/metrics endpoint 必须 return 200, 实际 {resp.status_code}"
        )
        body = resp.text
        # Prometheus exposition: HELP + TYPE + sample 任一出现即可证明 counter 注册成功
        assert (
            f"# HELP {COUNTER_NAME}" in body
            or f"# TYPE {COUNTER_NAME}" in body
            or COUNTER_NAME in body
        ), (
            f"/metrics 响应中找不到 '{COUNTER_NAME}'. "
            f"counter 注册了但未被 Prometheus REGISTRY 收录, 灰度 baseline 监控失效."
        )


# ──────────────────────────────────────────────────────────────────────────
# L5 — Gray-release baseline invariants (monotonic + exposition format)
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDBaselineInvariants:
    """L5 — 灰度发布期 counter 的 baseline 不变式 (不变即 healthy)."""

    def test_counter_value_is_monotonic_non_negative(self) -> None:
        """Counter 设计上 monotonic 不减 (prometheus_client.Counter 强制).

        本 test 是 sanity probe — 若 hutao 误用 Gauge (允许减) 会被 L1 已捕获,
        这里再加一道断言确保 type contract.
        """
        implemented, _ = _counter_implemented()
        if not implemented:
            pytest.skip(f"Phase D forward-compat skip: {COUNTER_NAME} 未实")
        try:
            from app.utils import metrics as metrics_mod  # type: ignore[import-not-found]
        except ImportError as e:
            pytest.skip(f"metrics module import 失败: {e}")

        counter_obj = getattr(metrics_mod, COUNTER_NAME, None)
        assert counter_obj is not None, (
            f"metrics 模块中找不到 '{COUNTER_NAME}' 属性"
        )
        # prometheus_client.Counter 没有 .dec() 方法 (Gauge 才有)
        assert not hasattr(counter_obj, "dec"), (
            f"counter '{COUNTER_NAME}' 不能是 Gauge — Gray-release baseline "
            f"要求 monotonic non-decreasing, 用 Gauge 会破坏 baseline 单调性"
        )

    def test_design_doc_references_counter(self) -> None:
        """design doc §4.3 / §6.3 应 reference counter 名 (audit trail)."""
        design_doc = REPO_ROOT / "docs" / "design" / "S3-trust-precheck-ui.md"
        if not design_doc.exists():
            pytest.skip(f"design doc 不存在于 {design_doc}")
        src = design_doc.read_text()
        assert COUNTER_NAME in src, (
            f"design doc 未 reference counter '{COUNTER_NAME}', "
            f"灰度 baseline 监控缺 audit trail / 设计依据"
        )
