"""Canary whitelist service — S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2.

Loads the canary whitelist yaml lazily on first access (or via explicit
reload) and exposes :func:`is_whitelisted(phone)` returning a boolean.
Gated by ``settings.canary_whitelist_enabled``: when False the
service short-circuits to ``True`` (all phones pass) so the gate is a
no-op by default and existing behaviour is preserved.

Yaml path injection (S3-OPS-CANARY-REAL-YAML-PATH-ENV, 魈 2026-06-23 方案 b):
the effective path is resolved per-load from ``settings.canary_whitelist_path``
(env ``CANARY_WHITELIST_PATH``, default ``whitelist_phones.yaml``). Production
canary containers set it to ``whitelist_phones.real.yaml`` so the real list
lives in its own file — honouring whitelist_phones.yaml §20 (mock/real 物理
隔离, 避免串). Before this, load() always read the hard-coded mock yaml and
the real list (約定另起 .real.yaml) could not be switched in at deploy time.

Design:
- thread-safe module cache (lock + immutable frozenset snapshot)
- normalisation: strip whitespace, no special transform (phone yaml stores
  raw 11-digit strings)
- placeholder rejection: phones starting with ``__PENDING_`` / ``__PLACEHOLDER_``
  are ignored at load (treated as not in whitelist)
- real-number env indirection (S2-OPS-A-REAL-LAUNCH, 凝光 Q2=a 2026-06-29):
  an entry may carry ``phone_env`` naming an env var holding the real number;
  ``phone`` is then a masked audit string (``157****2719``) never loaded.
  env unset / placeholder => that single entry fail-safe skips. legacy mock
  yaml without phone_env loads ``phone`` unchanged (backward compat)
- malformed yaml fail-closed when ``canary_whitelist_enabled=True``
  (returns empty whitelist → all phones fail F2 entry) to prevent
  silent leakage of feature to non-canary users
- sentinel test number ``13800000000`` from yaml ``sentinels`` block
  retained for e2e
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

# Canary yaml directory: repo_root/deploy/canary/
# Resolved from this file: backend/app/services/canary_whitelist.py
#   -> .parent = services/
#   -> .parent = app/
#   -> .parent = backend/
#   -> .parent = repo_root/
_CANARY_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "deploy" / "canary"

# Default yml path (mock list). Kept as the import-time fallback / back-compat
# constant; the effective path is resolved per-load via _resolve_yml_path()
# so CANARY_WHITELIST_PATH can switch the canary container to a real list.
_DEFAULT_YML_PATH: Path = _CANARY_DIR / "whitelist_phones.yaml"


def _resolve_yml_path() -> Path:
    """Resolve the active whitelist yaml path from settings.

    S3-OPS-CANARY-REAL-YAML-PATH-ENV (魈 2026-06-23 方案 b): reads
    ``settings.canary_whitelist_path`` (env ``CANARY_WHITELIST_PATH``) so the
    production canary container can switch to an independent real list
    (``whitelist_phones.real.yaml``) without overwriting the mock yaml --
    honouring whitelist_phones.yaml §20 (mock/real 物理隔离, 避免串).

    A bare filename is joined under deploy/canary/; an absolute path (or any
    value containing a path separator) is honoured as-is. Falls back to the
    mock default when the env value is empty.
    """
    raw = (settings.canary_whitelist_path or "").strip()
    if not raw:
        return _DEFAULT_YML_PATH
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return candidate
    return _CANARY_DIR / raw


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
        path = yml_path or _resolve_yml_path()
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
    """Extract all phone strings from the parsed yaml, skipping placeholders.

    S2-OPS-A-REAL-LAUNCH (凝光 Q2=a, 2026-06-29): per-entry ``phone_env``
    indirection. When an entry has ``phone_env``, the real 11-digit number is
    read from that env var at load time and the yaml ``phone`` is treated as a
    masked audit string (e.g. ``157****2719``) that is *never* loaded into the
    whitelist. ENV not injected / injected with a placeholder → that single
    entry fail-safe skips (does not affect other entries). When ``phone_env``
    is absent the legacy ``phone`` path runs unchanged (mock yaml backward
    compat). 1 env = 1 number, no list/JSON, fully decoupled per entry.
    """
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
            # New path: real number lives in env, yaml phone is a masked
            # audit-only string. Takes precedence over phone.
            phone_env = entry.get("phone_env")
            if isinstance(phone_env, str) and phone_env.strip():
                real = os.environ.get(phone_env.strip(), "").strip()
                if not real or any(
                    real.startswith(p) for p in _PLACEHOLDER_PREFIXES
                ):
                    # env unset / env holds placeholder → fail-safe skip
                    continue
                out.append(real)
                continue
            # Legacy path (mock yaml): raw phone in yaml.
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
