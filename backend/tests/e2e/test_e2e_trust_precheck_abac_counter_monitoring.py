"""E2E test — Phase D: trust-precheck ABAC counter 灰度 baseline 监控 (AC#9).

S3-TEST-003 Phase D — board AC#9 "灰度发布期间 ABAC counter 监控 baseline".

依赖 dev task ``S3-DEV-003-PRECHECK-ABAC-COUNTER`` (c6323053 hutao P2 done)
已实施 ``precheck_abac_filtered_total`` counter (PR #319 f302fdc merged
06-15 14:54Z), Phase D 转 hard contract (无 forward-compat skip).

# Hutao 实际实施 (与 board AC#2 完全一致)

- module: ``backend/app/observability/precheck_abac_metrics.py``
  (新建独立 observability 模块, **不在** business-metrics ``utils/metrics.py``;
  per-feature observability 子模块是合理设计, 不阻塞)
- Python 常量: ``PRECHECK_ABAC_FILTERED_TOTAL`` (大写)
- Prometheus name: ``precheck_abac_filtered_total``
- labels (AC#2 强制): ``endpoint`` / ``user_role`` / ``filter_reason``
- 触发点: ``backend/app/api/v1/deps_precheck.py`` L132 + L150
  (assert_order_owner_or_404 deny 分支 .labels(...).inc())
- multi-import 防呆: ``_get_or_create_counter`` wrapper (REGISTRY 检查)

# Phase D 验收契约 (5 L)

| L | 验收 |
|---|---|
| L1 | counter 存在且 module 路径明确 (新 observability 模块亦可) |
| L2 | label dim ⊇ {endpoint, user_role, filter_reason} (AC#2) |
| L3 | 触发点存在: deps_precheck.py 有 .labels(...).inc() |
| L4 | /metrics endpoint expose counter (Prometheus scrape format) |
| L5 | Counter type (非 Gauge) + design doc audit trail |

# Lesson §94 反案 #61 candidate (改回结论)

旧假设 "test 先写硬契约约束 dev" 错 — 当 ADR / board AC 已明,
dev 实施合理时 test 必须跟随 spec, 不能用 test 内未明的假设
(L1 module 路径、L2 label 名) 反推 dev. 14:54Z 我犯此错,
5 个 case 全 FAIL, 改用 AC#2 + ADR-0048 实际 spec 重写.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"

# Hutao 实施路径 (AC#5: grep ≥ 5 hits 已验)
METRICS_MODULE = BACKEND / "app" / "observability" / "precheck_abac_metrics.py"
TRIGGER_MODULE = BACKEND / "app" / "api" / "v1" / "deps_precheck.py"

PROM_NAME = "precheck_abac_filtered_total"
PY_CONST = "PRECHECK_ABAC_FILTERED_TOTAL"

# AC#2 强制 label schema
REQUIRED_LABELS = {"endpoint", "user_role", "filter_reason"}


# ──────────────────────────────────────────────────────────────────────────
# L1 — counter 模块存在
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDCounterModuleExists:
    """L1 — counter 模块文件存在 + Python 常量 + Prometheus name 都齐."""

    def test_metrics_module_file_exists(self) -> None:
        """``backend/app/observability/precheck_abac_metrics.py`` 必须存在."""
        assert METRICS_MODULE.exists(), (
            f"counter 模块 {METRICS_MODULE} 不存在 — "
            f"hutao S3-DEV-003-PRECHECK-ABAC-COUNTER 是否回滚?"
        )

    def test_python_constant_defined(self) -> None:
        """Python 模块顶层应定义 ``PRECHECK_ABAC_FILTERED_TOTAL`` 常量."""
        src = METRICS_MODULE.read_text()
        # 允许多行赋值: 用 regex 找 assignment
        pattern = rf"\b{re.escape(PY_CONST)}\b\s*[:=]"
        assert re.search(pattern, src), (
            f"Python 常量 '{PY_CONST}' 必须在 {METRICS_MODULE.name} 定义"
        )

    def test_prometheus_metric_name_present(self) -> None:
        """Prometheus metric name 字符串 ``precheck_abac_filtered_total`` 必须在源码."""
        src = METRICS_MODULE.read_text()
        assert PROM_NAME in src, (
            f"Prometheus name '{PROM_NAME}' 不在 {METRICS_MODULE.name}"
        )


# ──────────────────────────────────────────────────────────────────────────
# L2 — labels 维度严格 = AC#2 spec
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDCounterLabelsAC2:
    """L2 — labels schema 必须 ⊇ AC#2 强制集合 {endpoint, user_role, filter_reason}.

    AC#2 原文: "label dimensions {endpoint, user_role, filter_reason} 实施完整"
    """

    def test_all_required_labels_in_source(self) -> None:
        """3 个 AC#2 label name 字符串必须在 counter 模块出现."""
        src = METRICS_MODULE.read_text()
        missing = [lbl for lbl in REQUIRED_LABELS if lbl not in src]
        assert not missing, (
            f"AC#2 强制 label 缺失: {missing}; "
            f"必须在 {METRICS_MODULE.name} 出现 (作为 labelnames 列表 / 常量)"
        )

    def test_counter_runtime_labels_match_spec(self) -> None:
        """Runtime import counter, 检查 ._labelnames ⊇ AC#2 集合."""
        try:
            from app.observability.precheck_abac_metrics import (  # type: ignore[import-not-found]
                PRECHECK_ABAC_FILTERED_TOTAL,
            )
        except ImportError as e:
            pytest.fail(
                f"counter 模块 import 失败: {e}; "
                f"AC#3 注册到 Prometheus registry 受阻"
            )

        actual_labels = set(PRECHECK_ABAC_FILTERED_TOTAL._labelnames)  # type: ignore[attr-defined]
        missing = REQUIRED_LABELS - actual_labels
        assert not missing, (
            f"counter runtime labels 缺 AC#2 强制项: {missing}; "
            f"实际 labels: {actual_labels}"
        )


# ──────────────────────────────────────────────────────────────────────────
# L3 — 触发点 (deps_precheck.py .labels(...).inc())
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDTriggerPoint:
    """L3 — counter 必须在 ABAC deny 分支被 .labels(...).inc()."""

    def test_trigger_module_exists(self) -> None:
        """``backend/app/api/v1/deps_precheck.py`` 必须存在."""
        assert TRIGGER_MODULE.exists(), (
            f"触发模块 {TRIGGER_MODULE} 不存在"
        )

    def test_import_counter_in_trigger_module(self) -> None:
        """deps_precheck.py 必须从 observability 模块 import counter."""
        src = TRIGGER_MODULE.read_text()
        assert "from app.observability.precheck_abac_metrics import" in src, (
            "deps_precheck.py 必须 import precheck_abac_metrics 模块"
        )
        assert PY_CONST in src, (
            f"deps_precheck.py 必须 import {PY_CONST} 常量"
        )

    def test_counter_labels_inc_pattern(self) -> None:
        """deps_precheck.py 必须有 ``.labels(...).inc()`` 链式调用 (>= 1 处)."""
        src = TRIGGER_MODULE.read_text()
        # 找 PRECHECK_ABAC_FILTERED_TOTAL.labels( ... pattern
        pattern = rf"{re.escape(PY_CONST)}\.labels\("
        matches = re.findall(pattern, src)
        assert matches, (
            f"deps_precheck.py 找不到 {PY_CONST}.labels(...) 调用; "
            f"AC#1 'ABAC filter 出口 increment counter' 未实施"
        )
        # 应至少有 2 处 (order_not_found + abac_owner_mismatch 两个分支)
        assert len(matches) >= 2, (
            f"AC#2 filter_reason 至少 2 种 (order_not_found / abac_owner_mismatch), "
            f"应至少 2 处 .labels() 调用, 实际 {len(matches)}"
        )

    def test_both_filter_reasons_triggered(self) -> None:
        """两种 filter_reason 都应在 deps_precheck.py 触发."""
        src = TRIGGER_MODULE.read_text()
        for reason_const in (
            "FILTER_REASON_ORDER_NOT_FOUND",
            "FILTER_REASON_ABAC_OWNER_MISMATCH",
        ):
            assert reason_const in src, (
                f"filter_reason 常量 '{reason_const}' 未在 deps_precheck.py 使用; "
                f"AC#4 单测 3 场景 (通过/拒绝/降级) coverage 受损"
            )


# ──────────────────────────────────────────────────────────────────────────
# L4 — /metrics endpoint expose counter
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDMetricsEndpointExpose:
    """L4 — /metrics scrape 必须含 counter (AC#3)."""

    def test_metrics_endpoint_mounted_in_main(self) -> None:
        """``backend/app/main.py`` 须 mount /metrics endpoint."""
        main_py = BACKEND / "app" / "main.py"
        src = main_py.read_text()
        assert 'mount("/metrics"' in src or "mount('/metrics'" in src, (
            "/metrics endpoint 必须 mount, AC#3 Prometheus scrape 路径"
        )

    def test_counter_appears_in_metrics_scrape(self) -> None:
        """灰度 baseline 必须能 scrape — TestClient GET /metrics 含 counter."""
        try:
            from fastapi.testclient import TestClient

            from app.main import app  # type: ignore[import-not-found]
        except ImportError as e:
            pytest.fail(f"app import 失败: {e}; AC#3 scrape 路径受阻")

        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 200, (
            f"/metrics 必须 return 200, 实际 {resp.status_code}"
        )
        body = resp.text
        assert PROM_NAME in body, (
            f"/metrics scrape 找不到 '{PROM_NAME}'; "
            f"counter 注册了但未被 Prometheus REGISTRY 收录, "
            f"AC#9 灰度 baseline 监控失效"
        )

    def test_metrics_endpoint_has_help_and_type(self) -> None:
        """Prometheus exposition 格式: HELP + TYPE meta 必须存在 (AC#3 完整 scrape format)."""
        try:
            from fastapi.testclient import TestClient

            from app.main import app  # type: ignore[import-not-found]
        except ImportError as e:
            pytest.fail(f"app import 失败: {e}")

        client = TestClient(app)
        body = client.get("/metrics").text
        assert f"# HELP {PROM_NAME}" in body, (
            f"/metrics 缺 HELP meta for '{PROM_NAME}', Prometheus format 不完整"
        )
        assert f"# TYPE {PROM_NAME} counter" in body, (
            "/metrics 缺 TYPE meta 或 type 不是 counter; "
            "AC#5 Counter (非 Gauge/Histogram) 类型不正确"
        )


# ──────────────────────────────────────────────────────────────────────────
# L5 — Gray-release baseline invariants (Counter type + audit trail)
# ──────────────────────────────────────────────────────────────────────────


class TestPhaseDBaselineInvariants:
    """L5 — 灰度发布期 counter 的 baseline 不变式."""

    def test_counter_is_prometheus_counter_not_gauge(self) -> None:
        """counter 必须是 prometheus_client.Counter (monotonic), 不能 Gauge."""
        try:
            from app.observability.precheck_abac_metrics import (  # type: ignore[import-not-found]
                PRECHECK_ABAC_FILTERED_TOTAL,
            )
        except ImportError as e:
            pytest.fail(f"counter import 失败: {e}")

        # Counter 没 .dec() (Gauge 才有), 灰度 baseline 要求 monotonic
        assert not hasattr(PRECHECK_ABAC_FILTERED_TOTAL, "dec"), (
            f"{PY_CONST} 不能是 Gauge — Gray-release baseline 要求 monotonic "
            f"non-decreasing, Gauge 会破坏单调性"
        )

        # 类型字符串验证
        type_str = str(type(PRECHECK_ABAC_FILTERED_TOTAL))
        assert "Counter" in type_str, (
            f"{PY_CONST} 类型应含 'Counter', 实际 {type_str}"
        )

    def test_counter_can_increment_with_labels(self) -> None:
        """smoke test: counter.labels(...).inc() 可调用且数值递增."""
        try:
            from app.observability.precheck_abac_metrics import (  # type: ignore[import-not-found]
                ENDPOINT_PRECHECK_STATUS,
                FILTER_REASON_ABAC_OWNER_MISMATCH,
                PRECHECK_ABAC_FILTERED_TOTAL,
                USER_ROLE_PATIENT,
            )
        except ImportError as e:
            pytest.fail(f"counter / 常量 import 失败: {e}")

        labeled = PRECHECK_ABAC_FILTERED_TOTAL.labels(
            endpoint=ENDPOINT_PRECHECK_STATUS,
            user_role=USER_ROLE_PATIENT,
            filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
        )
        before = labeled._value.get()  # type: ignore[attr-defined]
        labeled.inc()
        after = labeled._value.get()  # type: ignore[attr-defined]
        assert after == before + 1, (
            f"counter inc() 应 +1, 实际 before={before} after={after}"
        )

    def test_design_doc_references_counter(self) -> None:
        """design doc §4.3 / §6.3 应 reference counter 名 (audit trail)."""
        design_doc = REPO_ROOT / "docs" / "design" / "S3-trust-precheck-ui.md"
        if not design_doc.exists():
            pytest.skip(f"design doc 不存在: {design_doc}")
        src = design_doc.read_text()
        assert PROM_NAME in src, (
            f"design doc 未 reference '{PROM_NAME}'; 缺 audit trail / 设计依据"
        )
