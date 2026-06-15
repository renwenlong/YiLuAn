"""S3-OPS-STARTUP-PROBE-FRAMEWORK: @register_startup_probe decorator framework.

任务: S3-OPS-STARTUP-PROBE-FRAMEWORK (PR1)
ADR: ADR-0051 r3 §1.2.2 #7 + §1.2.3 #8 + §2.3 #25 落 fail-loud probe 协议层强约束
胡桃 PR #258 review comment 4676805533 ask 3 提出.

设计目标:
统一 prod-required asset / config fail-loud probe 注册中心, 避免散点 ``if env in
{staging, canary, production}`` 写法在多 codepath 重复 (ai_prep_filter / sms /
canary_whitelist / 后续 probe).

核心 API:

    from app.startup_probes import register_startup_probe

    @register_startup_probe(name="ai_prep_filter", envs=("staging", "canary", "production"))
    def probe_ai_prep_filter() -> None:
        assert get_ai_filter_client() is not None

    # 在 FastAPI lifespan startup 调:
    await run_all_startup_probes(settings.env)

设计决策:
1. **decorator 只 register 不 run**: 让 import 顺序与 startup 顺序解耦,
   probe 顺序 = register 顺序 (insertion-ordered dict).
2. **fail-loud 不允许 try/except 吞**: probe fn raise 任何 Exception →
   ``run_all_startup_probes`` 立即 re-raise → FastAPI lifespan fail →
   uvicorn exit code != 0. 不允许 \"prod degrade\" 路径.
3. **production 必跑 (无法 opt-out)**: AC#3 协议规定 ``\"production\" in envs``
   一定为 True (decorator 启动时强制 — 缺 production 即 ImportError).
4. **env enum**: ``Literal[\"dev\",\"test\",\"staging\",\"canary\",\"production\"]``
   字面闭合, 防 typo (env 名字 typo 即 ImportError, 不到 prod 才发现).
5. **app.state.startup_probe_results**: 留 observability hook —
   /admin/ops 后续可暴露 ``[(name, ok, duration_ms, error?), ...]``.
6. **/health 不允许 mask**: AC#4 规定即使 probe 全 fail, /health 必反 503
   (probe fail → app 已 exit → /health 不会 200 — 物理上不可 mask).

反案约束:
- 反案 #25: 散点 ``if env in {staging,canary,production}`` 协议层不允许
- 反案 #11: unit test 覆盖 ≠ 生产能跑 — 配 e2e test 走 lifespan 真路径
- 反案 #15: probe registry 命名包含 sentinel 防误删
"""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from typing import Literal, get_args

logger = logging.getLogger(__name__)


# AC#3: env 名 enum, 字面闭合.
StartupProbeEnv = Literal["dev", "test", "staging", "canary", "production"]

_VALID_ENVS: frozenset[str] = frozenset(get_args(StartupProbeEnv))

# Production 必跑 — decorator 启动时 enforce.
_PRODUCTION_ENV: str = "production"


# Sentinel for grep / rg 防误删 (反案 #15).
_SECRET_STARTUP_PROBE_REGISTRY_42 = "SECRET_STARTUP_PROBE_REGISTRY_42_DO_NOT_LEAK"


# Type alias: probe fn signature.
# probe MAY be sync OR async; both supported.
ProbeFn = Callable[[], object]


# Registry tuple: (probe_fn, envs_set, source_location)
# source_location = "module:funcname:lineno" for log/observability.
_PROBES: dict[str, tuple[ProbeFn, frozenset[str], str]] = {}


def register_startup_probe(
    *,
    name: str,
    envs: tuple[str, ...],
) -> Callable[[ProbeFn], ProbeFn]:
    """Decorator: register a startup probe.

    Args:
        name: unique probe name (e.g. "ai_prep_filter"). Used in log,
              metric label, registry key. Duplicate → ImportError.
        envs: tuple of env names the probe MUST run in. Each must be in
              ``StartupProbeEnv``. Missing "production" → ImportError
              (AC#3 production cannot opt-out).

    Returns:
        the decorated function, untouched (only side-effect = register).

    Raises:
        ImportError: if name dup, envs invalid, or "production" missing.

    Example:
        @register_startup_probe(name="ai_prep_filter",
                                envs=("staging", "canary", "production"))
        def probe_ai_prep_filter() -> None:
            assert _DEFAULT_YML_PATH.exists()

    Note:
        Decorator runs at module import time. The probe fn is NOT
        invoked here — only registered. Actual invocation happens in
        ``await run_all_startup_probes(env)`` from FastAPI lifespan.
    """
    # AC#3 envs validation (fail loud at import time, not at startup).
    if not isinstance(envs, tuple) or not envs:
        raise ImportError(
            f"register_startup_probe(name={name!r}): envs must be non-empty tuple, "
            f"got {type(envs).__name__}={envs!r}"
        )
    bad = [e for e in envs if e not in _VALID_ENVS]
    if bad:
        raise ImportError(
            f"register_startup_probe(name={name!r}): invalid env(s) {bad!r}. "
            f"Valid: {sorted(_VALID_ENVS)}. "
            f"(Typo? prod-required probes MUST include 'production'.)"
        )
    if _PRODUCTION_ENV not in envs:
        raise ImportError(
            f"register_startup_probe(name={name!r}): 'production' MUST be in "
            f"envs (AC#3 — prod-required cannot opt-out). Got envs={envs!r}. "
            f"If this probe is truly NOT prod-required, do NOT use "
            f"@register_startup_probe; use a different pattern."
        )

    def decorator(fn: ProbeFn) -> ProbeFn:
        # Duplicate name → ImportError (registry must be globally unique).
        if name in _PROBES:
            existing_loc = _PROBES[name][2]
            raise ImportError(
                f"register_startup_probe: duplicate probe name {name!r}; "
                f"first registered at {existing_loc}, "
                f"second attempt from {_describe_callable_location(fn)}"
            )
        source_location = _describe_callable_location(fn)
        _PROBES[name] = (fn, frozenset(envs), source_location)
        logger.debug(
            "register_startup_probe: %s registered (envs=%s, loc=%s)",
            name,
            sorted(envs),
            source_location,
        )
        return fn

    return decorator


def _describe_callable_location(fn: ProbeFn) -> str:
    """Return 'module:funcname:lineno' for log/observability."""
    module = getattr(fn, "__module__", "?")
    qualname = getattr(fn, "__qualname__", getattr(fn, "__name__", "?"))
    code = getattr(fn, "__code__", None)
    lineno = getattr(code, "co_firstlineno", "?") if code is not None else "?"
    return f"{module}:{qualname}:{lineno}"


# Observability: per-run result tuple.
# (name, ok, duration_ms, error_str_or_none, source_location)
ProbeResult = tuple[str, bool, float, str | None, str]


async def run_all_startup_probes(env: str) -> list[ProbeResult]:
    """Run all probes whose ``envs`` contains ``env``. Fail-loud on first error.

    Args:
        env: current env name (from ``settings.environment`` or equivalent).
             If not in ``StartupProbeEnv`` → log warning, treat as "skip all"
             (dev-only safety: a typo in ENVIRONMENT shouldn't crash dev box,
             but production runners always pass "production").

    Returns:
        list of ProbeResult in registration order (only probes that ran).

    Raises:
        Any Exception raised by a probe fn. AC#2 explicitly: must NOT swallow.
        The exception is re-raised AS-IS so caller (FastAPI lifespan) can
        propagate to uvicorn (exit code != 0).

    Behavior:
        - env not in enum → log warning + return empty list (no crash in dev typo case)
        - probe envs mismatch → skip (no record in results)
        - probe sync → invoke directly
        - probe async → await the coroutine
        - probe fail → log STARTUP_PROBE_FAIL + push metric + re-raise
        - probe pass → log INFO + record duration + continue to next
    """
    results: list[ProbeResult] = []

    if env not in _VALID_ENVS:
        logger.warning(
            "run_all_startup_probes: env=%r not in %s; "
            "treating as skip-all (dev typo safety). %s",
            env,
            sorted(_VALID_ENVS),
            _SECRET_STARTUP_PROBE_REGISTRY_42,
        )
        return results

    if not _PROBES:
        logger.info("run_all_startup_probes: no probes registered (env=%s)", env)
        return results

    logger.info(
        "run_all_startup_probes: starting %d probe(s) for env=%s",
        len(_PROBES),
        env,
    )

    for name, (fn, envs, source_location) in _PROBES.items():
        if env not in envs:
            logger.debug(
                "run_all_startup_probes: skip %s (envs=%s, current=%s)",
                name,
                sorted(envs),
                env,
            )
            continue

        t0 = time.perf_counter()
        try:
            ret = fn()
            # support async probe fn:
            if hasattr(ret, "__await__"):
                await ret  # type: ignore[func-returns-value]
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            tb = traceback.format_exc()
            logger.error(
                "STARTUP_PROBE_FAIL probe=%s env=%s duration_ms=%.2f " "location=%s error=%s\n%s",
                name,
                env,
                duration_ms,
                source_location,
                exc,
                tb,
            )
            _increment_fail_metric(name, env)
            results.append((name, False, duration_ms, str(exc), source_location))
            # AC#2/#4: re-raise — DO NOT swallow.
            raise

        duration_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "STARTUP_PROBE_OK probe=%s env=%s duration_ms=%.2f location=%s",
            name,
            env,
            duration_ms,
            source_location,
        )
        results.append((name, True, duration_ms, None, source_location))

    logger.info(
        "run_all_startup_probes: all %d probe(s) passed for env=%s",
        len(results),
        env,
    )
    return results


def _increment_fail_metric(name: str, env: str) -> None:
    """Push ``startup_probe_fail_total{probe=<name>,env=<env>}``.

    Failure here MUST NOT swallow the original probe error — we log + skip.
    """
    try:
        # Import lazily to avoid pulling prometheus_client at module import
        # (some test fixtures don't have it installed).
        from prometheus_client import Counter

        # Use a module-level singleton — re-creating Counter would dup-register
        # and raise. Stash on the module.
        global _STARTUP_PROBE_FAIL_COUNTER
        try:
            counter = _STARTUP_PROBE_FAIL_COUNTER  # type: ignore[name-defined]
        except NameError:
            counter = Counter(
                "startup_probe_fail_total",
                "Total fail-loud startup probe failures by probe name and env",
                labelnames=("probe", "env"),
            )
            _STARTUP_PROBE_FAIL_COUNTER = counter  # type: ignore[assignment]
        counter.labels(probe=name, env=env).inc()
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "STARTUP_PROBE_FAIL metric push failed (probe=%s env=%s): %s",
            name,
            env,
            exc,
        )


# ============================================================================
# Test-only helpers
# ============================================================================


def _registered_probe_names() -> tuple[str, ...]:
    """Return registered probe names in registration order (for tests)."""
    return tuple(_PROBES.keys())


def _registered_probe(name: str) -> tuple[ProbeFn, frozenset[str], str]:
    """Return registered probe tuple by name (for tests/observability)."""
    return _PROBES[name]


def _reset_for_tests() -> None:
    """Clear registry between tests. NEVER call from production code."""
    _PROBES.clear()
