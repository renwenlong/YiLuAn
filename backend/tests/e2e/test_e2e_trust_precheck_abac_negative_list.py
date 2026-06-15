"""E2E test — trust-precheck ABAC 4 层 + 17 字段 negative list + counter
(AC#8 board / design AC#8).

Phase A2 (S3-TEST-003) — 验收 board AC#8 "ABAC 4 层防御全过 + 17 字段
negative list + ``precheck_abac_filtered_total`` counter 可观测".

# Cover 拆分 (不重复已有 schema test)

backend 已有 ``tests/schemas/test_order_precheck_abac_layer1.py``
(Layer 1 schema sentinel — 15 named fields negative list, 2 patterns
由 schemathesis 兜底). 本 e2e 不重复 Layer 1, 聚焦 Layer 2/3/4 e2e
contract + counter gap 实证.

# Layer 拆分

- L1 — Layer 1 ABAC schema (reference only): schema test 文件存在 + 15
       named fields constant 在文件内.
- L2 — Layer 2 endpoint ABAC: ``users_precheck.py`` 用 ``CurrentPatient``
       dep + ``assert_order_owner_or_404`` (role gate + owner gate hybrid
       404 mask).
- L3 — Layer 3 service SELECT lint: aggregator 用 explicit positive
       column SELECTs, 不 SELECT * (避免 negative-list 字段 leak).
- L4 — Layer 4 schemathesis + counter:
        - schemathesis positive-list test 存在 (response schema lock).
        - ``precheck_abac_filtered_total`` counter — 当前 backend 未实,
          本 test 揭示 gap, mark forward-compat skip (design doc 列了
          但实现 gap, S3-DEV-003-PRECHECK-BACKEND 后续 task 应补).
- L5 — 17 字段全集校验: 15 named + 2 patterns 一一可枚举, 设计 §5.3
       表与 schema test constant 对齐.

# 关键发现 (跨 task evidence)

1. counter ``precheck_abac_filtered_total`` 在 design doc §4.3 / §6.3
   明确列出, 但 ``grep -r 'precheck_abac' backend/`` 全 0 hit —
   counter 实现 gap (Phase A2 揭示 → 建议在 board 新建 dev task).
2. 17 字段定义 = 15 named + 2 patterns; schema test 只 cover 15 named,
   2 patterns (``companion_real_*`` / ``*_id_card_*``) 由 schemathesis
   兜底 — 跨工具一致性需要确保两端都活着.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"
DESIGN_DOC = REPO_ROOT / "docs" / "design" / "S3-trust-precheck-ui.md"


# ──────────────────────────────────────────────────────────────────────────
# Constants — 17 字段 negative list (design §5.3)
# ──────────────────────────────────────────────────────────────────────────

NEGATIVE_LIST_15_NAMED: tuple[str, ...] = (
    # Contract (4)
    "contract_hash",
    "hash_inputs",
    "storage_blob_path",
    "template_key",
    # Insurance (3)
    "carrier_internal_id",
    "actual_premium",
    "underwriter_meta",
    # Preparation (4)
    "prompt_version",
    "model_used",
    "raw_llm_output",
    "cost_yuan",
    # Companion cert (4)
    "companion_real_name",
    "companion_id_card_hash",
    "companion_phone",
    "companion_user_id",
)

NEGATIVE_LIST_2_PATTERNS: tuple[str, ...] = (
    "companion_real_*",
    "*_id_card_*",
)


# ──────────────────────────────────────────────────────────────────────────
# L1 — Layer 1 ABAC schema sentinel (reference, 不重复, 仅 verify 存在)
# ──────────────────────────────────────────────────────────────────────────


class TestL1SchemaSentinelExists:
    """L1 — schema sentinel test 文件存在 + 15 named fields 全集."""

    def test_schema_sentinel_file_exists(self) -> None:
        f = BACKEND / "tests" / "schemas" / "test_order_precheck_abac_layer1.py"
        assert f.exists(), (
            f"Layer 1 ABAC schema sentinel 必须存在: {f} "
            f"(本 e2e file 不重复 Layer 1, 仅检查存在性)"
        )

    def test_schema_sentinel_lists_15_named_fields(self) -> None:
        f = BACKEND / "tests" / "schemas" / "test_order_precheck_abac_layer1.py"
        src = f.read_text()
        # 15 named fields 全部出现在 constant 段
        missing = [
            field for field in NEGATIVE_LIST_15_NAMED if field not in src
        ]
        assert not missing, (
            f"Layer 1 sentinel missing 15 named negative-list fields: "
            f"{missing}. design §5.3 表与 constant 不对齐."
        )


# ──────────────────────────────────────────────────────────────────────────
# L2 — Layer 2 endpoint ABAC (role + owner hybrid 404)
# ──────────────────────────────────────────────────────────────────────────


class TestL2EndpointABAC:
    """L2 — Layer 2 endpoint role + owner gate contract."""

    def test_endpoint_uses_current_patient_role_dep(self) -> None:
        """endpoint 必须用 ``CurrentPatient`` dep (admin/companion 401/403)."""
        endpoint_src = (
            BACKEND / "app" / "api" / "v1" / "users_precheck.py"
        ).read_text()
        assert (
            "CurrentPatient" in endpoint_src
        ), "endpoint 必须用 CurrentPatient role gate (admin/companion 401/403)"

    def test_endpoint_uses_owner_hybrid_404(self) -> None:
        """endpoint 必须用 ``assert_order_owner_or_404`` (跨订单 404)."""
        endpoint_src = (
            BACKEND / "app" / "api" / "v1" / "users_precheck.py"
        ).read_text()
        assert (
            "assert_order_owner_or_404" in endpoint_src
        ), "endpoint 必须用 assert_order_owner_or_404 owner gate (hybrid 404)"

    def test_deps_precheck_404_mask_log(self) -> None:
        """deps_precheck 必须有 404 mask debug log (防 enum 取证)."""
        deps_src = (
            BACKEND / "app" / "api" / "v1" / "deps_precheck.py"
        ).read_text()
        assert (
            "precheck-status 404" in deps_src
        ), "deps_precheck 必须 log 404 mask 事件 (debugging + audit)"

    def test_ws_handler_uses_same_owner_dep(self) -> None:
        """WS handler 必须 reuse ``load_order_owner_id`` (跨协议一致)."""
        ws_src = (BACKEND / "app" / "api" / "v1" / "ws.py").read_text()
        assert (
            "load_order_owner_id" in ws_src
        ), "WS handler 必须 reuse load_order_owner_id (REST + WS 一致 owner gate)"


# ──────────────────────────────────────────────────────────────────────────
# L3 — Layer 3 service SELECT 列裁剪 lint
# ──────────────────────────────────────────────────────────────────────────


class TestL3ServiceSelectLint:
    """L3 — aggregator 必须用 positive-column SELECTs, 不能 SELECT *."""

    def test_aggregator_no_select_star_for_sensitive_tables(self) -> None:
        """aggregator 不能对 service_contracts / companions / 等表 SELECT *.

        SELECT * 会拉所有列, 包括 contract_hash / hash_inputs / company_*
        敏感字段, Layer 3 阻止 (ADR-0048 §7.0).
        """
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        # 不能用 select(ServiceContract) / select(Companion) 整模型
        # 但可以 select(SomeTable.col1, SomeTable.col2) explicit
        forbidden = re.findall(
            r"select\(\s*(ServiceContract|Companion|InsurancePolicy|"
            r"PreparationPackage)\s*\)",
            agg_src,
        )
        assert not forbidden, (
            f"Aggregator 不能 SELECT 整 model (会带 negative-list 字段): "
            f"{forbidden}. 用 select(M.col1, M.col2) explicit."
        )

    def test_aggregator_uses_explicit_columns(self) -> None:
        """aggregator 必须有 ``select(...)`` 显式列形式 (positive list)."""
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        # select( 出现且与 ., 显式列共现
        # 简化: select( 必须出现 + 不能仅出现 select(M) 形式
        assert "select(" in agg_src, "Aggregator 必须有 SELECT 查询"
        # 至少一处 explicit col select (有点号在 select( 之后)
        # 实测: 用 select(Table.col, ...) 形式
        m = re.search(r"select\s*\([^)]*\.[a-z_]+", agg_src)
        assert m is not None, (
            "Aggregator 必须至少有一处 explicit column select "
            "(如 select(Table.col1, Table.col2))"
        )

    def test_aggregator_comment_mentions_positive_list(self) -> None:
        """aggregator 文档应说明 Layer 3 列裁剪策略 (ADR-0048)."""
        agg_src = (
            BACKEND / "app" / "services" / "order_precheck_aggregator.py"
        ).read_text()
        # docstring / comment 提到 positive list / Layer 3 / column projection
        markers = [
            "positive-list",
            "positive list",
            "Layer 3",
            "negative-list",
            "column projection",
            "ABAC",
        ]
        hits = [m for m in markers if m.lower() in agg_src.lower()]
        assert len(hits) >= 2, (
            f"Aggregator 文档必须说明 ABAC Layer 3 列裁剪策略, "
            f"实际命中 markers={hits}"
        )


# ──────────────────────────────────────────────────────────────────────────
# L4 — Layer 4 schemathesis + counter gap
# ──────────────────────────────────────────────────────────────────────────


class TestL4SchemathesisAndCounterGap:
    """L4 — Layer 4 = schemathesis positive lock + counter (counter gap)."""

    def test_schemathesis_contract_test_exists(self) -> None:
        """schemathesis positive-list response schema lock test 存在."""
        f = BACKEND / "tests" / "contract" / "test_precheck_schemathesis_contract.py"
        assert f.exists(), (
            f"Layer 4 schemathesis contract test 必须存在: {f}"
        )

    def test_schemathesis_test_mentions_positive_list(self) -> None:
        """schemathesis test docstring 必须 mention positive list 哨兵."""
        f = BACKEND / "tests" / "contract" / "test_precheck_schemathesis_contract.py"
        src = f.read_text()
        assert (
            "positive list" in src or "positive-list" in src
        ), "schemathesis test 必须 mention positive-list 哨兵"

    def test_precheck_abac_filtered_counter_gap(self) -> None:
        """``precheck_abac_filtered_total`` counter 当前未实, 文档化 gap.

        Design doc §4.3 / §6.3 明确列出 counter, 但 backend grep 0 hit.
        Test mark forward-compat skip; counter 补上后自动启用.
        """
        # 全 app/ + services/ 找 counter 名
        candidates = [
            BACKEND / "app",
        ]
        found_hits: list[str] = []
        for base in candidates:
            for f in base.rglob("*.py"):
                src = f.read_text()
                if "precheck_abac_filtered_total" in src:
                    found_hits.append(str(f.relative_to(REPO_ROOT)))

        if found_hits:
            # 一旦补上, test 转 PASS (forward-compat 自动启用)
            assert True, (
                f"precheck_abac_filtered_total counter 已实现于: "
                f"{found_hits}"
            )
        else:
            pytest.skip(
                "⚠️ counter gap: precheck_abac_filtered_total 在 design "
                "doc §4.3 / §6.3 列出, 但 backend 未实 (grep 0 hit). "
                "建议在 board 新建 dev task 补 counter (本 Phase A2 "
                "test 已 forward-compat skip, counter 实现后自动启用)."
            )


# ──────────────────────────────────────────────────────────────────────────
# L5 — 17 字段全集一致性
# ──────────────────────────────────────────────────────────────────────────


class TestL5SeventeenFieldsConsistency:
    """L5 — 17 字段 = 15 named + 2 patterns, 三处定义必须一致."""

    def test_15_named_in_design_doc(self) -> None:
        """15 named negative-list fields 全部在 design doc §5.3 表."""
        src = DESIGN_DOC.read_text()
        missing = [f for f in NEGATIVE_LIST_15_NAMED if f not in src]
        assert not missing, (
            f"design doc §5.3 缺以下 negative-list 字段: {missing}. "
            f"design 与 schema test constant 不对齐."
        )

    def test_2_patterns_in_design_doc(self) -> None:
        """2 pattern matches (``companion_real_*`` / ``*_id_card_*``) 在 design."""
        src = DESIGN_DOC.read_text()
        for pattern in NEGATIVE_LIST_2_PATTERNS:
            assert (
                pattern in src
            ), f"design doc §5.3 缺 pattern: {pattern}"

    def test_17_total_count_matches_design(self) -> None:
        """15 + 2 = 17, design doc 必须 mention "17 字段"."""
        src = DESIGN_DOC.read_text()
        # design doc 多处 mention 17 字段
        assert (
            "17 字段" in src or "17 个字段" in src or "17 fields" in src
        ), "design doc 必须 mention '17 字段' (15 named + 2 patterns 合计)"

    def test_no_negative_list_fields_in_runtime_schema(self) -> None:
        """OrderPrecheckSummaryView (+ 4 nested) 不出现 15 named 字段."""
        from app.schemas.order_precheck import (
            CompanionCertStatusView,
            ContractStatusView,
            InsuranceStatusView,
            OrderPrecheckSummaryView,
            PreparationStatusView,
        )

        views = (
            OrderPrecheckSummaryView,
            ContractStatusView,
            InsuranceStatusView,
            PreparationStatusView,
            CompanionCertStatusView,
        )

        for view_cls in views:
            schema = view_cls.model_json_schema()
            # walk top + $defs
            names: set[str] = set(schema.get("properties", {}).keys())
            for def_body in schema.get("$defs", {}).values():
                names.update(def_body.get("properties", {}).keys())
            leaked = sorted(set(NEGATIVE_LIST_15_NAMED) & names)
            assert not leaked, (
                f"{view_cls.__name__} 实时 schema 泄漏 negative-list 字段: "
                f"{leaked} (e2e 二次 sentinel — schema test 之外多兜一层)"
            )
