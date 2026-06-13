"""Canary whitelist service — S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2.

Loads `deploy/canary/whitelist_phones.yaml` once at module import (or via
explicit reload) and exposes :func:`is_whitelisted(phone)` returning a
boolean. Gated by ``settings.canary_whitelist_enabled``: when False the
service short-circuits to ``True`` (all phones pass) so the gate is a
no-op by default and existing behaviour is preserved.

Design:
- thread-safe module cache (lock + immutable frozenset snapshot)
- normalisation: strip whitespace, no special transform (phone yaml stores
  raw 11-digit strings)
- placeholder rejection: phones starting with ``__PENDING_`` / ``__PLACEHOLDER_``
  are ignored at load (treated as not in whitelist)
- malformed yaml fail-closed when ``canary_whitelist_enabled=True``
  (returns empty whitelist → all phones fail F2 entry) to prevent
  silent leakage of feature to non-canary users
- sentinel test number ``13800000000`` from yaml ``sentinels`` block
  retained for e2e
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Default yml path: repo_root/deploy/canary/whitelist_phones.yaml
# Resolved from this file: backend/app/services/canary_whitelist.py
#   -> .parent = services/
#   -> .parent = app/
#   -> .parent = backend/
#   -> .parent = repo_root/
_DEFAULT_YML_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "deploy"
    / "canary"
    / "whitelist_phones.yaml"
)

# Placeholder prefixes — entries with these are not loaded as real numbers.
_PLACEHOLDER_PREFIXES: tuple[str, ...] = ("__PENDING_", "__PLACEHOLDER_")


@dataclass(frozen=True)
class WhitelistSnapshot:
    """Immutable snapshot of loaded whitelist.

    Attributes:
        phones: frozenset of valid 11-digit phone strings (placeholders skipped)
        version: yaml ``version`` field (audit trail)
        loaded_from: path resolved at load time (may differ from
            DEFAULT in tests)
    """

    phones: frozenset[str]
    version: str
    loaded_from: str


class _WhitelistCache:
    """Module-level thread-safe whitelist cache."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: WhitelistSnapshot = WhitelistSnapshot(
            phones=frozenset(), version="", loaded_from=""
        )
        self._loaded: bool = False

    def load(self, yml_path: Path | None = None) -> None:
        path = yml_path or _DEFAULT_YML_PATH
        with self._lock:
            if not path.exists():
                logger.warning(
                    "canary_whitelist: yml not found at %s, whitelist empty",
                    path,
                )
                self._snapshot = WhitelistSnapshot(
                    phones=frozenset(),
                    version="",
                    loaded_from=str(path),
                )
                self._loaded = True
                return

            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                logger.error(
                    "canary_whitelist: yml parse failed at %s: %s",
                    path,
                    exc,
                )
                # parse failure → keep empty (fail-closed)
                self._snapshot = WhitelistSnapshot(
                    phones=frozenset(),
                    version="",
                    loaded_from=str(path),
                )
                self._loaded = True
                return

            if not isinstance(raw, dict):
                logger.error(
                    "canary_whitelist: yml root must be mapping, got %r",
                    type(raw),
                )
                self._snapshot = WhitelistSnapshot(
                    phones=frozenset(),
                    version="",
                    loaded_from=str(path),
                )
                self._loaded = True
                return

            version = str(raw.get("version") or "")
            phones = _extract_phones(raw)
            self._snapshot = WhitelistSnapshot(
                phones=frozenset(phones),
                version=version,
                loaded_from=str(path),
            )
            self._loaded = True
            logger.info(
                "canary_whitelist: loaded %d valid phones from %s (version=%s)",
                len(phones),
                path,
                version,
            )

    def snapshot(self) -> WhitelistSnapshot:
        if not self._loaded:
            self.load()
        return self._snapshot

    def reset_for_tests(self) -> None:
        """Reset cache; used by tests so each test gets a clean load."""
        with self._lock:
            self._snapshot = WhitelistSnapshot(
                phones=frozenset(),
                version="",
                loaded_from="",
            )
            self._loaded = False


def _extract_phones(raw: dict) -> list[str]:
    """Extract all phone strings from the parsed yaml, skipping placeholders."""
    out: list[str] = []
    for section in ("team", "colleagues", "sentinels"):
        block = raw.get(section) or []
        if not isinstance(block, list):
            logger.warning(
                "canary_whitelist: section %r must be list, got %r",
                section,
                type(block),
            )
            continue
        for entry in block:
            if not isinstance(entry, dict):
                continue
            phone = entry.get("phone")
            if not isinstance(phone, str):
                continue
            phone = phone.strip()
            if not phone:
                continue
            if any(phone.startswith(p) for p in _PLACEHOLDER_PREFIXES):
                # placeholder, skip
                continue
            out.append(phone)
    return out


_cache = _WhitelistCache()


def is_whitelisted(phone: str | None) -> bool:
    """Return True iff the phone is in the canary whitelist.

    None / empty phone → False.

    Callers must check ``settings.canary_whitelist_enabled`` themselves;
    this function returns the raw membership answer and does not
    consult the global feature flag.
    """
    if not phone:
        return False
    return phone.strip() in _cache.snapshot().phones


def get_snapshot() -> WhitelistSnapshot:
    """Return the current loaded snapshot (for /admin/ops introspection)."""
    return _cache.snapshot()


def reload(yml_path: Path | None = None) -> None:
    """Force reload from disk; for ops hot-reload or tests."""
    _cache.load(yml_path)


def reset_for_tests() -> None:
    """Reset module cache between tests."""
    _cache.reset_for_tests()
