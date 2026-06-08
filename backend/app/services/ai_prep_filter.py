"""AI 准备包双层禁区关键词过滤 service.

[S3-DEV-002-KEYWORD-FILTER / ADR-0048 §4]

双层过滤:
- L1 (input): 用户主诉 / chief_complaint 入 prompt 前过滤, hit -> 不发 LLM, 直接 fallback
- L2 (output): AI 返回文本过滤, hit -> fallback 通用模板 (防 LLM 越界)

加载策略:
- backend 启动时 load yml -> 模块级 cache
- v1.0 不支持 hot reload (后续 task 加 redis pub/sub)
- yml 路径: ``docs/medical-content/prohibited-keywords.yml`` (repo 根相对)

Metric:
- ``ai_prep_filter_l1_blocked_total{category=...}`` - L1 拦截率
- ``ai_prep_filter_l2_blocked_total{category=...}`` - L2 拦截率
"""
from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("app.services.ai_prep_filter")


class FilterLayer(str, enum.Enum):
    """过滤层标识."""

    L1_INPUT = "L1_INPUT"
    L2_OUTPUT = "L2_OUTPUT"


@dataclass(frozen=True)
class FilterResult:
    """过滤结果. ``blocked=False`` 表示通过, ``blocked=True`` 时 ``category`` / ``pattern`` 必填."""

    blocked: bool
    layer: Optional[FilterLayer] = None
    category: Optional[str] = None
    pattern: Optional[str] = None

    @classmethod
    def allow(cls) -> "FilterResult":
        return cls(blocked=False)

    @classmethod
    def block(cls, layer: FilterLayer, category: str, pattern: str) -> "FilterResult":
        return cls(blocked=True, layer=layer, category=category, pattern=pattern)


# Default yml path - repo 根 docs/medical-content/.
# 测试环境可通过 ``set_blocklist_path`` 或 ``load_blocklist`` 重 init.
_DEFAULT_YML_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "medical-content"
    / "prohibited-keywords.yml"
)


@dataclass(frozen=True)
class BlocklistEntry:
    """单个分类的 pattern list snapshot."""

    category: str
    description: str
    patterns: tuple[str, ...]


class _BlocklistCache:
    """模块级 thread-safe blocklist cache.

    启动加载一次后 read path lock-free (通过 immutable snapshot 替换).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: tuple[BlocklistEntry, ...] = ()
        self._version: str = ""
        self._loaded: bool = False

    def load(self, yml_path: Path | None = None) -> None:
        path = yml_path or _DEFAULT_YML_PATH
        with self._lock:
            if not path.exists():
                logger.warning(
                    "ai_prep_filter: yml not found at %s, blocklist empty (fail-open)",
                    path,
                )
                self._snapshot = ()
                self._version = ""
                self._loaded = True
                return

            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                logger.error(
                    "ai_prep_filter: yml parse failed at %s: %s",
                    path,
                    exc,
                )
                # parse 失败保持旧 snapshot (避免 atomic swap 到空) - 启动期则 empty.
                if not self._loaded:
                    self._snapshot = ()
                    self._version = ""
                    self._loaded = True
                return

            version = str(raw.get("version") or "")
            categories_raw = raw.get("categories") or {}
            if not isinstance(categories_raw, dict):
                logger.error(
                    "ai_prep_filter: categories must be dict, got %r",
                    type(categories_raw),
                )
                self._snapshot = ()
                self._version = version
                self._loaded = True
                return

            entries: list[BlocklistEntry] = []
            for category, body in categories_raw.items():
                if not isinstance(body, dict):
                    logger.warning(
                        "ai_prep_filter: category %r body not dict, skip", category
                    )
                    continue
                patterns_raw = body.get("patterns") or []
                if not isinstance(patterns_raw, list):
                    logger.warning(
                        "ai_prep_filter: category %r patterns not list, skip", category
                    )
                    continue
                cleaned = tuple(
                    str(p).strip().lower()
                    for p in patterns_raw
                    if isinstance(p, (str, int)) and str(p).strip()
                )
                description = str(body.get("description") or "")
                entries.append(
                    BlocklistEntry(
                        category=str(category),
                        description=description,
                        patterns=cleaned,
                    )
                )

            self._snapshot = tuple(entries)
            self._version = version
            self._loaded = True
            total_patterns = sum(len(e.patterns) for e in entries)
            logger.info(
                "ai_prep_filter: blocklist loaded version=%s categories=%d patterns=%d path=%s",
                version,
                len(entries),
                total_patterns,
                path,
            )

    @property
    def snapshot(self) -> tuple[BlocklistEntry, ...]:
        if not self._loaded:
            # lazy load 兜底 (test 直接调时 main app startup 未跑)
            self.load()
        return self._snapshot

    @property
    def version(self) -> str:
        if not self._loaded:
            self.load()
        return self._version


# Module-level singleton cache. App startup 调 load_blocklist(); read path 走 snapshot.
_cache = _BlocklistCache()

# Import-time auto-load:
# - 主路径 (FastAPI app) import 本模块时立即加载, 使在 main.py lifespan 外也 OK
# - test 如需重 load 可显式调 load_blocklist(custom_path)
# - load 失败 fail-open (snapshot 留空, 不 raise) — 按 admin-v2 可看规则
_cache.load()


def load_blocklist(yml_path: Path | None = None) -> None:
    """启动期 + 重加载入口. 测试 fixture 可 inject 自定义 yml_path."""
    _cache.load(yml_path)


def get_blocklist_snapshot() -> tuple[BlocklistEntry, ...]:
    """供 admin-v2 read-only 页 + 测试断言获取当前 snapshot."""
    return _cache.snapshot


def get_blocklist_version() -> str:
    """yml 版本号 (用于 admin-v2 显示 + reload 通知)."""
    return _cache.version


def _try_increment_metric(layer: FilterLayer, category: str) -> None:
    """触发 prometheus metric, 失败不阻业务."""
    try:
        from app.utils.metrics import (
            ai_prep_filter_l1_blocked_total,
            ai_prep_filter_l2_blocked_total,
        )

        if layer == FilterLayer.L1_INPUT:
            ai_prep_filter_l1_blocked_total.labels(category=category).inc()
        else:
            ai_prep_filter_l2_blocked_total.labels(category=category).inc()
    except Exception:  # pragma: no cover - metric infra glitch
        logger.exception("ai_prep_filter: metric increment failed")


def _check_against_blocklist(text: str, layer: FilterLayer) -> FilterResult:
    """对一段文本对照 snapshot 找首个 hit. 大小写不敏感."""
    if not text:
        return FilterResult.allow()
    lowered = text.lower()
    for entry in _cache.snapshot:
        for pattern in entry.patterns:
            if pattern in lowered:
                _try_increment_metric(layer, entry.category)
                logger.info(
                    "ai_prep_filter: %s blocked category=%s pattern=%r",
                    layer.value,
                    entry.category,
                    pattern,
                )
                return FilterResult.block(
                    layer=layer,
                    category=entry.category,
                    pattern=pattern,
                )
    return FilterResult.allow()


class AIPrepKeywordFilter:
    """双层过滤入口 (S3-DEV-002 ADR-0048 §4.2).

    Usage:
        filt = AIPrepKeywordFilter()
        l1 = filt.filter_input(user_chief_complaint)
        if l1.blocked:
            return fallback_template(reason=f"L1_{l1.category}")
        ai_resp = call_llm(prompt)
        l2 = filt.filter_output(ai_resp)
        if l2.blocked:
            return fallback_template(reason=f"L2_{l2.category}")
        return ai_resp
    """

    def filter_input(self, user_input: str) -> FilterResult:
        """L1: 用户主诉 / chief_complaint 入 prompt 前过滤."""
        return _check_against_blocklist(user_input, FilterLayer.L1_INPUT)

    def filter_output(self, ai_response: str) -> FilterResult:
        """L2: AI 返回文本过滤 (防 LLM 越界生成)."""
        return _check_against_blocklist(ai_response, FilterLayer.L2_OUTPUT)


__all__ = [
    "AIPrepKeywordFilter",
    "BlocklistEntry",
    "FilterLayer",
    "FilterResult",
    "get_blocklist_snapshot",
    "get_blocklist_version",
    "load_blocklist",
]
