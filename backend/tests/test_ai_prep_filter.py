"""Tests for AI prep filter (S3-DEV-002-KEYWORD-FILTER / ADR-0048 §4).

# Coverage map

- AC#1: yml 落 docs/medical-content/ + 6 大分类 (verify load + 数量)
- AC#2: backend 启动加载 + module-level cache (verify load_blocklist 工作 + snapshot)
- AC#3: 双层 hit 检测 (filter_input L1 / filter_output L2 + 各分类 hit + metric incr)
- AC#5: ai_blocklist_viewed audit_log + admin_id + category_filter (test_admin_api 部分)

注: AC#4 admin-v2 read-only 前端测试在 admin-v2 单元测试范畴, 此处仅测 backend API endpoint.
"""
from __future__ import annotations

import pytest

from app.services.ai_prep_filter import (
    _DEFAULT_YML_PATH,
    AIPrepKeywordFilter,
    FilterLayer,
    FilterResult,
    get_blocklist_snapshot,
    get_blocklist_version,
    load_blocklist,
)


@pytest.fixture(autouse=True)
def _reset_blocklist():
    """每个 test 走 default yml (repo 根)."""
    load_blocklist()


# ---------------------------------------------------------------------------
# AC#1: yml 落 docs/medical-content/ + 6 大分类
# ---------------------------------------------------------------------------


class TestBlocklistYmlLoaded:
    """Verify yml 文件落档 + 6 大分类 (PRD §4.4 AC-4)."""

    def test_yml_exists_at_default_path(self):
        assert _DEFAULT_YML_PATH.exists(), (
            f"prohibited-keywords.yml not at {_DEFAULT_YML_PATH}; "
            "must be at docs/medical-content/prohibited-keywords.yml"
        )

    def test_yml_has_version(self):
        assert get_blocklist_version() == "1.0.0"

    def test_yml_has_six_categories(self):
        snapshot = get_blocklist_snapshot()
        categories = {e.category for e in snapshot}
        assert categories == {
            "diagnosis",
            "dosage",
            "prescription",
            "treatment_plan",
            "lab_results",
            "billing",
        }
        assert len(snapshot) == 6

    def test_each_category_has_patterns(self):
        snapshot = get_blocklist_snapshot()
        for entry in snapshot:
            assert len(entry.patterns) > 0, f"{entry.category}: empty patterns list"
            assert entry.description, f"{entry.category}: empty description"


# ---------------------------------------------------------------------------
# AC#2: backend 加载 + module-level cache + 重 load
# ---------------------------------------------------------------------------


class TestBlocklistCache:
    """模块级 cache + load 行为."""

    def test_snapshot_is_immutable_tuple(self):
        snapshot = get_blocklist_snapshot()
        assert isinstance(snapshot, tuple)
        for entry in snapshot:
            assert isinstance(entry.patterns, tuple)

    def test_load_with_missing_file_fails_open(self, tmp_path):
        """yml 不存在时 fail-open (snapshot 空, 不 raise)."""
        load_blocklist(tmp_path / "nonexistent.yml")
        assert get_blocklist_snapshot() == ()
        assert get_blocklist_version() == ""
        # 恢复 default
        load_blocklist()
        assert len(get_blocklist_snapshot()) == 6

    def test_load_with_custom_yml(self, tmp_path):
        """支持 inject 自定义 yml 路径 (test fixture 友好)."""
        yml = tmp_path / "custom-blocklist.yml"
        yml.write_text(
            """version: "test-1"
categories:
  test_category:
    description: "test"
    patterns:
      - "foo"
      - "bar"
""",
            encoding="utf-8",
        )
        load_blocklist(yml)
        assert get_blocklist_version() == "test-1"
        snap = get_blocklist_snapshot()
        assert len(snap) == 1
        assert snap[0].category == "test_category"
        assert snap[0].patterns == ("foo", "bar")
        # 恢复 default
        load_blocklist()


# ---------------------------------------------------------------------------
# AC#3: 双层 hit 检测 (L1 input + L2 output)
# ---------------------------------------------------------------------------


class TestL1InputFilter:
    """L1 input 层 - 用户主诉 / chief_complaint."""

    def setup_method(self):
        self.filt = AIPrepKeywordFilter()

    def test_normal_input_allows(self):
        r = self.filt.filter_input("我感冒了, 想问陪诊师")
        assert r.blocked is False
        assert r.layer is None
        assert r.category is None

    def test_empty_input_allows(self):
        r = self.filt.filter_input("")
        assert r.blocked is False

    def test_diagnosis_pattern_blocks(self):
        r = self.filt.filter_input("医生你给我诊断为什么病")
        assert r.blocked is True
        assert r.layer == FilterLayer.L1_INPUT
        assert r.category == "diagnosis"
        assert r.pattern == "诊断为"

    def test_dosage_pattern_blocks(self):
        r = self.filt.filter_input("这个药每天吃几次")
        assert r.blocked is True
        assert r.layer == FilterLayer.L1_INPUT
        assert r.category == "dosage"

    def test_prescription_pattern_blocks(self):
        r = self.filt.filter_input("请给我开药")
        assert r.blocked is True
        assert r.layer == FilterLayer.L1_INPUT
        assert r.category == "prescription"

    def test_billing_pattern_blocks(self):
        r = self.filt.filter_input("这个能不能医保报销")
        assert r.blocked is True
        assert r.layer == FilterLayer.L1_INPUT
        assert r.category == "billing"

    def test_case_insensitive(self):
        """大小写不敏感对比."""
        r = self.filt.filter_input("CT 显示什么")
        assert r.blocked is True
        assert r.category == "lab_results"


class TestL2OutputFilter:
    """L2 output 层 - AI 返回文本."""

    def setup_method(self):
        self.filt = AIPrepKeywordFilter()

    def test_normal_output_allows(self):
        r = self.filt.filter_output("请放松, 保持心情舒畅")
        assert r.blocked is False

    def test_diagnosis_output_blocks(self):
        r = self.filt.filter_output("你的症状确诊为感冒")
        assert r.blocked is True
        assert r.layer == FilterLayer.L2_OUTPUT
        assert r.category == "diagnosis"
        assert r.pattern == "确诊"

    def test_lab_results_output_blocks(self):
        r = self.filt.filter_output("化验单显示你的指标偏高")
        assert r.blocked is True
        assert r.layer == FilterLayer.L2_OUTPUT
        # 命中先到的 pattern - "化验单" 在 lab_results 第一个
        assert r.category == "lab_results"

    def test_treatment_plan_output_blocks(self):
        r = self.filt.filter_output("你上次需要手术")
        assert r.blocked is True
        assert r.layer == FilterLayer.L2_OUTPUT
        assert r.category == "treatment_plan"
        assert r.pattern == "需要手术"


class TestFilterResultDataclass:
    """FilterResult 工厂方法."""

    def test_allow_factory(self):
        r = FilterResult.allow()
        assert r.blocked is False
        assert r.layer is None
        assert r.category is None
        assert r.pattern is None

    def test_block_factory(self):
        r = FilterResult.block(
            layer=FilterLayer.L1_INPUT,
            category="diagnosis",
            pattern="诊断为",
        )
        assert r.blocked is True
        assert r.layer == FilterLayer.L1_INPUT
        assert r.category == "diagnosis"
        assert r.pattern == "诊断为"


# ---------------------------------------------------------------------------
# Metric incr verify (sanity)
# ---------------------------------------------------------------------------


def _metric_value(counter, **labels) -> float:
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


class TestMetricIncrement:
    """metric ai_prep_filter_l1/l2_blocked_total{category} 触发."""

    def setup_method(self):
        self.filt = AIPrepKeywordFilter()

    def test_l1_block_increments_metric(self):
        from app.utils.metrics import ai_prep_filter_l1_blocked_total

        baseline = _metric_value(
            ai_prep_filter_l1_blocked_total, category="diagnosis"
        )
        self.filt.filter_input("诊断为什么病")
        after = _metric_value(
            ai_prep_filter_l1_blocked_total, category="diagnosis"
        )
        assert after - baseline == pytest.approx(1.0)

    def test_l2_block_increments_metric(self):
        from app.utils.metrics import ai_prep_filter_l2_blocked_total

        baseline = _metric_value(
            ai_prep_filter_l2_blocked_total, category="prescription"
        )
        # "建议服用" 是 prescription patterns 中的 字面 pattern
        self.filt.filter_output("我建议服用这个药")
        after = _metric_value(
            ai_prep_filter_l2_blocked_total, category="prescription"
        )
        assert after - baseline == pytest.approx(1.0)
