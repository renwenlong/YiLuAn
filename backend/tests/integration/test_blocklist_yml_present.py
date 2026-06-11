"""S3-BUG-003 regression: blocklist yml asset-presence integration test.

任务: S3-BUG-003-DOCKER-MISSING-MEDICAL-CONTENT-YML

背景:
backend Docker image 长期漏 COPY ``docs/medical-content/`` →
``prohibited-keywords.yml`` 在容器内永远 not found,
``ai_prep_filter._BlocklistCache.load()`` fail-open empty,
ADR-0048 §4.1 / §4.3 L1+L2 关键词过滤完全失效 in prod.

unit test 用 ``monkeypatch.setenv`` / mock yml path 跑,
覆盖率 100% 但**根本没暴露 build artifact 缺失**.

本 test:
- assert ``_DEFAULT_YML_PATH.exists() is True`` (不 mock)
- assert ``_FALLBACK_TEMPLATE_PATH.exists() is True``
  (同 bug 模式, 同目录 prep-fallback-template.yml)
- assert load 后 ``snapshot`` 非空、``version`` 非空 (fail-open 检测)
- assert categories/patterns 数量 > 0 (空 yml 同样触发 fail-open)

测试不依赖 Redis / DB / FastAPI — 纯文件 + yml parse, 跑得快,
CI 必跑无 marker exclude.
"""
from __future__ import annotations

import pytest

from app.services.ai_prep_filter import (
    _DEFAULT_YML_PATH,
    _BlocklistCache,
    get_blocklist_snapshot,
    get_blocklist_version,
)
from app.services.prep_generate_service import (
    _FALLBACK_TEMPLATE_PATH,
    _load_fallback_template,
    reset_fallback_cache,
)


class TestBlocklistYmlPresent:
    """ai_prep_filter prohibited-keywords.yml 必须随 backend image 一起 ship."""

    def test_default_yml_path_exists(self) -> None:
        """assert SoT yml 存在: 不存在即 Dockerfile / build context 漏 COPY."""
        assert _DEFAULT_YML_PATH.exists(), (
            f"prohibited-keywords.yml 必须随 backend image 一起 ship. "
            f"Expected at: {_DEFAULT_YML_PATH}. "
            f"如该测试 fail, 检查 backend/Dockerfile 是否 COPY docs/medical-content/ "
            f"+ deploy/docker-compose.yml build.context 是否在 repo 根."
        )

    def test_default_yml_path_is_file(self) -> None:
        """assert SoT yml 是文件 (不是目录或 symlink dangling)."""
        assert _DEFAULT_YML_PATH.is_file(), (
            f"{_DEFAULT_YML_PATH} exists but is not a regular file "
            f"(possibly broken symlink or directory)."
        )

    def test_real_load_populates_snapshot(self) -> None:
        """assert 真 yml load 后 snapshot 非空 + version 非空 (fail-open 检测)."""
        # 用一个 fresh cache 避免污染 module singleton
        cache = _BlocklistCache()
        cache.load()  # 走 _DEFAULT_YML_PATH 真路径
        assert cache._loaded, "cache should be marked loaded after load()"
        assert cache._snapshot, (
            "blocklist snapshot 为空 → fail-open. "
            "可能原因: yml 不存在 / yml parse 失败 / categories 字段非 dict. "
            f"yml path: {_DEFAULT_YML_PATH}"
        )
        assert cache._version, (
            f"blocklist version 为空字符串 → yml 缺 version 字段或 fail-open. "
            f"yml path: {_DEFAULT_YML_PATH}"
        )

    def test_real_load_categories_and_patterns_sane(self) -> None:
        """assert categories >= 6 且 total patterns >= 50 (ADR-0048 §4.1 baseline).

        当前 yml: 6 categories × ~12 patterns = 72 total. baseline 下调到
        50 给后续微调留余地, 但 << 50 一定是 fixture 漂移 / yml 漂移.
        """
        cache = _BlocklistCache()
        cache.load()
        n_categories = len(cache._snapshot)
        n_patterns = sum(len(e.patterns) for e in cache._snapshot)
        assert n_categories >= 6, (
            f"categories 数 {n_categories} < 6, ADR-0048 §4.1 要求"
            f" diagnosis/dosage/prescription/treatment_plan/lab_results/billing 6 类全在."
        )
        assert n_patterns >= 50, (
            f"total patterns {n_patterns} < 50, 可能 yml 大量条目被裁."
        )

    def test_module_singleton_loaded_at_import(self) -> None:
        """assert module-level _cache 在 import 时已 load (非空 snapshot/version).

        因为 ai_prep_filter.py 行 188 `_cache.load()` 模块导入即跑,
        本 test 直接看 module singleton 当前状态 — 若已 fail-open,
        snapshot=() / version=''.
        """
        snapshot = get_blocklist_snapshot()
        version = get_blocklist_version()
        assert snapshot, (
            "module singleton snapshot 为空 (fail-open). "
            "可能 import-time _cache.load() 跑时 yml 不存在."
        )
        assert version, (
            "module singleton version 为空字符串 (fail-open). 同上诊断."
        )


class TestFallbackTemplateYmlPresent:
    """prep_generate_service prep-fallback-template.yml 同 bug 模式 (S3-BUG-003).

    `_FALLBACK_TEMPLATE_PATH` 用 `Path(__file__).resolve().parents[3] / 'docs' / 'medical-content'`,
    与 ai_prep_filter._DEFAULT_YML_PATH 同样依赖 `docs/medical-content/` 在
    container 内可访问. 修 S3-BUG-003 同时验证 prep-fallback-template.yml 一并修复.
    """

    def test_fallback_template_path_exists(self) -> None:
        assert _FALLBACK_TEMPLATE_PATH.exists(), (
            f"prep-fallback-template.yml 必须随 backend image 一起 ship. "
            f"Expected at: {_FALLBACK_TEMPLATE_PATH}."
        )

    def test_fallback_template_loads_real_content(self) -> None:
        """assert _load_fallback_template() 不 raise + 返非空 dict."""
        reset_fallback_cache()  # clear module cache to force re-read
        try:
            template = _load_fallback_template()
        except Exception as exc:
            pytest.fail(
                f"_load_fallback_template() raised {type(exc).__name__}: {exc}. "
                f"yml path: {_FALLBACK_TEMPLATE_PATH}. "
                f"可能 yml 缺失 / parse 失败."
            )
        assert isinstance(template, dict) and template, (
            "fallback template empty/non-dict — yml 漂移或 fail-open."
        )
        # SoT yml 至少含 service_type-level keys (errand/half_accompany/full_accompany)
        # 不强制写死, 只要非空即 OK.
