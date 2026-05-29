"""[S2-DEV-005] AI summary post-check blocklist matcher.

职责
----
拿生成完的摘要文本，命中 ``config/ai_blocklist.yaml`` 中任意 phrase →
返回 ``(blocked=True, hit_phrase)``。命中后调用方应：

1. 不入库原始 summary
2. 入库模板文案 + ``status=degraded`` + ``degraded_reason="post_check_blocked"``
3. ``ai_summary_degraded_total{reason="post_check_blocked"}`` +1

热更新
------
``BlocklistChecker`` 缓存 yaml 解析结果 + 文件 mtime。每次 ``check`` 前
对比 mtime，变化则原地重载——无需重启服务、无需外部 watcher 进程、O(1)
开销（一次 ``os.stat``）。

匹配语义
--------
子串 ``in`` 匹配（大小写不敏感 for 英文 phrase；中文天然区分不到）。
不做正则——blocklist 词典由产品/法务维护，正则维护成本高且容易误伤。

测试边界（参考 acceptance #6）
-----------------------------
- 命中："小明确诊为高血压" 含 "确诊"
- 不命中（边界）："医生建议休息几天" — 与 "建议用药" 不同，必须放行
- 热更新：写入新 phrase 后 mtime+1，下一次 check 立刻生效
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

logger = logging.getLogger("app.services.ai_summary.post_check")

# 默认 yaml 路径：仓库内 ``backend/config/ai_blocklist.yaml``。
DEFAULT_BLOCKLIST_PATH = Path(__file__).resolve().parents[3] / "config" / "ai_blocklist.yaml"


@dataclass(frozen=True)
class CheckResult:
    blocked: bool
    hit_phrase: str | None = None


class BlocklistChecker:
    """Mtime-cached blocklist matcher (thread-safe, hot-reloadable)."""

    def __init__(self, path: Path | str = DEFAULT_BLOCKLIST_PATH):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._phrases: tuple[str, ...] = ()
        self._mtime_ns: int = -1
        # Eager load so first check doesn't surprise the caller with a
        # missing-file error mid-request.
        self._reload_if_changed()

    # ------------------------------------------------------------------
    # public

    def check(self, text: str | None) -> CheckResult:
        if not text:
            return CheckResult(blocked=False)
        self._reload_if_changed()
        haystack = text.lower()
        for phrase in self._phrases:
            needle = phrase.lower()
            if needle and needle in haystack:
                return CheckResult(blocked=True, hit_phrase=phrase)
        return CheckResult(blocked=False)

    def phrases(self) -> tuple[str, ...]:
        """Snapshot of currently-loaded phrases (mainly for tests/audits)."""
        self._reload_if_changed()
        return self._phrases

    # ------------------------------------------------------------------
    # internals

    def _reload_if_changed(self) -> None:
        try:
            stat = os.stat(self._path)
        except FileNotFoundError:
            with self._lock:
                if self._mtime_ns != 0:
                    logger.warning(
                        "ai_blocklist.yaml missing at %s — treating as empty",
                        self._path,
                    )
                self._phrases = ()
                self._mtime_ns = 0
            return

        if stat.st_mtime_ns == self._mtime_ns:
            return

        with self._lock:
            # Re-check under the lock to avoid duplicate reloads racing.
            try:
                stat2 = os.stat(self._path)
            except FileNotFoundError:
                self._phrases = ()
                self._mtime_ns = 0
                return
            if stat2.st_mtime_ns == self._mtime_ns:
                return
            try:
                raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
                phrases = raw.get("phrases") or []
                if not isinstance(phrases, list):
                    raise ValueError("phrases must be a YAML list")
                cleaned = tuple(
                    str(p).strip()
                    for p in phrases
                    if isinstance(p, (str, int))
                    and str(p).strip()
                )
                self._phrases = cleaned
                self._mtime_ns = stat2.st_mtime_ns
                logger.info(
                    "ai_blocklist loaded: %d phrases from %s",
                    len(cleaned),
                    self._path,
                )
            except Exception as exc:  # never fail the caller — fail open is unsafe; fail closed
                logger.error(
                    "ai_blocklist parse error (%s); keeping previous %d phrases",
                    exc,
                    len(self._phrases),
                )
                # 保留旧词典 + 不更新 mtime → 下一轮 reload 会再试。


# Process-wide singleton — cheap to share, lock-protected.
_default_checker: BlocklistChecker | None = None
_default_lock = threading.Lock()


def get_default_checker() -> BlocklistChecker:
    global _default_checker
    if _default_checker is None:
        with _default_lock:
            if _default_checker is None:
                _default_checker = BlocklistChecker()
    return _default_checker


def reset_default_checker_for_test() -> None:
    """Pytest helper — drop the singleton so a new path can be injected."""
    global _default_checker
    with _default_lock:
        _default_checker = None


__all__ = [
    "BlocklistChecker",
    "CheckResult",
    "DEFAULT_BLOCKLIST_PATH",
    "get_default_checker",
    "reset_default_checker_for_test",
]
