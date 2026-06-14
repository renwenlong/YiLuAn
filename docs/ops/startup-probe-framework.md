# Startup Probe Framework

任务: **S3-OPS-STARTUP-PROBE-FRAMEWORK** (PR1)
ADR: ADR-0051 r3 §1.2.2 #7 + §1.2.3 #8 + §2.3 #25
Background: 胡桃 PR #258 review comment 4676805533 ask 3

## TL;DR

Use `@register_startup_probe(name=..., envs=...)` to declare any
prod-required asset/config check. The framework runs all matching probes
at FastAPI lifespan startup. Any probe failure crashes the app (uvicorn
exit code != 0). No silent fail-open.

```python
from app.startup_probes import register_startup_probe


@register_startup_probe(
    name="my_critical_asset",
    envs=("staging", "canary", "production"),
)
def probe_my_critical_asset() -> None:
    from app.services.my_asset import _CACHE
    if not _CACHE.is_loaded():
        raise RuntimeError("my asset failed to load")
```

That's it. The probe will run automatically in `lifespan` startup for the
listed envs.

## Why

Before this framework, prod-required asset checks were scattered:

```python
# OLD: services/sms.py:68
if settings.environment == "production":
    raise RuntimeError("creds missing")

# OLD: services/ai_prep_filter.py + app/main.py
assert_blocklist_loaded_or_raise(strict=settings.ai_blocklist_strict_load)

# OLD: hypothetical new check — would copy-paste the inline env check pattern
if env in {"staging", "canary", "production"}:
    ...
```

Problems:

1. **No central registry**: PR review can't ask "what are all the
   prod-required things?".
2. **Inconsistent env logic**: each call-site re-implements `env in {...}`,
   easy to typo `prodction`.
3. **Easy to silently break**: removing an `if env == "production"` block
   doesn't trigger CI fail.
4. **反案 #11 复发风险**: unit test 用 `monkeypatch` 跑, root cause
   (asset missing in container) 不暴露.

After this framework:

1. All probes live in `app/probes/__init__.py` (or sub-modules) — `git
   log app/probes/` shows what every prod-required check is.
2. `@register_startup_probe(envs=...)` validates env strings against a
   strict `Literal["dev","test","staging","canary","production"]` enum
   at decorator time — typo fails ImportError, not at prod startup.
3. Lint sentinel (PR2, S3-OPS-STARTUP-PROBE-FRAMEWORK AC#8) bans the
   inline `if env in {...}` pattern in `backend/app/` — new probes MUST
   use the decorator.
4. e2e test (`test_app_crashes_on_probe_fail.py`) verifies the WHOLE
   chain (decorator → registry → run_all → FastAPI lifespan → crash).

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  app/startup_probes.py        ← framework (decorator + runner)│
│                                                               │
│   @register_startup_probe → _PROBES = {name: (fn, envs, loc)}│
│                                                               │
│   await run_all_startup_probes(env)                          │
│     for name, (fn, envs, loc) in _PROBES.items():            │
│       if env in envs:                                         │
│         fn()  # raise → re-raise → uvicorn exit              │
└──────────────────────────────────────────────────────────────┘
                          ▲
                          │  imports trigger registration
                          │
┌──────────────────────────────────────────────────────────────┐
│  app/probes/__init__.py       ← concrete probes (AC#5 migration)│
│                                                               │
│   @register_startup_probe(name="ai_prep_filter_blocklist", ...)│
│   def probe_ai_prep_filter_blocklist(): ...                  │
│                                                               │
│   @register_startup_probe(name="canary_whitelist_yml", ...)   │
│   def probe_canary_whitelist_yml(): ...                       │
│                                                               │
│   @register_startup_probe(name="sms_provider_configured", ...) │
│   def probe_sms_provider_configured(): ...                    │
│                                                               │
│   @register_startup_probe(name="jwt_secret_key_changed", ...) │
│   def probe_jwt_secret_key_changed(): ...                     │
└──────────────────────────────────────────────────────────────┘
                          ▲
                          │  import in lifespan
                          │
┌──────────────────────────────────────────────────────────────┐
│  app/main.py::lifespan(app)                                   │
│                                                               │
│   import app.probes  # side-effect: register all probes      │
│   from app.startup_probes import run_all_startup_probes      │
│   await run_all_startup_probes(settings.environment)         │
│   # ↑ raises → lifespan startup fail → uvicorn exit          │
└──────────────────────────────────────────────────────────────┘
```

## API

### `register_startup_probe`

```python
@register_startup_probe(
    *,
    name: str,              # unique registry key, used in log/metric
    envs: tuple[str, ...],  # MUST include "production"
)
def my_probe() -> None | Awaitable[None]:
    ...
```

- `envs` must be a non-empty `tuple` of env names. All must be in
  `StartupProbeEnv = Literal["dev","test","staging","canary","production"]`.
- `"production"` MUST be in `envs` (AC#3: prod-required probes cannot opt-out).
- Duplicate `name` raises `ImportError` at decorator time.
- The decorator returns the original function unchanged (so caller can
  still invoke directly if needed for tests).
- The probe fn may be sync or async; both are supported by `run_all_*`.

### `run_all_startup_probes`

```python
async def run_all_startup_probes(env: str) -> list[ProbeResult]: ...
```

Where `ProbeResult = tuple[name, ok, duration_ms, error|None, source_location]`.

- Iterates `_PROBES` in registration order.
- Skips probes whose `envs` doesn't contain `env`.
- Sync fn invoked directly; async fn awaited.
- First probe fail → log STARTUP_PROBE_FAIL + push metric + **re-raise**
  (fail-fast, subsequent probes do NOT run).
- All pass → returns the result list (currently unused by main.py but
  stashed on `app.state.startup_probe_results` for ops introspection).
- Unknown env (typo in `ENVIRONMENT=xyz`) → log warning + skip all
  (dev safety, NOT crash). Production runners always pass valid env.

### Metric

```
startup_probe_fail_total{probe=<name>,env=<env>} counter
```

Pushed via `prometheus_client.Counter`. Singleton on module to avoid
dup-register errors. Failure to push the metric is logged but doesn't
swallow the original probe exception.

### Log format

On pass:
```
STARTUP_PROBE_OK probe=<name> env=<env> duration_ms=<ms> location=<file:fn:lineno>
```

On fail:
```
STARTUP_PROBE_FAIL probe=<name> env=<env> duration_ms=<ms>
                   location=<file:fn:lineno> error=<msg>
                   <full traceback>
```

## Adding a new probe

1. Create a `def my_probe() -> None` in `app/probes/__init__.py` (or a
   new file in `app/probes/` and import it from `__init__.py`).
2. Decorate with `@register_startup_probe(name=..., envs=...)`.
3. probe body raises on any failure that should crash the app.
4. Add a unit test in `backend/tests/startup_probes/` that registers
   then asserts run_all behavior with mock probe.
5. (Optional) Add an asset-presence integration test like
   `test_blocklist_yml_present.py` / `test_canary_whitelist_yml_present.py`
   if your probe checks a file's existence.

## What does NOT belong as a probe

- Per-request runtime checks (e.g. "is THIS user authorized") — those
  belong in route deps.
- Things that can change at runtime (DB connection, Redis up/down) —
  those belong in health endpoints (`/readiness`).
- Probes whose failure should NOT crash the app — those are warnings,
  not probes. Use `logger.warning` directly.

A probe is for **startup-time invariants** that, if violated, mean the
app is fundamentally misconfigured and serving traffic would be unsafe.

## AC#5 migrations (PR1)

| Probe name | Replaces | Why |
|---|---|---|
| `ai_prep_filter_blocklist` | `assert_blocklist_loaded_or_raise + settings.ai_blocklist_strict_load` | Central registry, env-driven instead of separate config flag |
| `canary_whitelist_yml` | (new — defense for PR #304 同 bug pattern 反案 #11 复发) | Asset-presence check at startup, double-defense with Dockerfile COPY |
| `sms_provider_configured` | Legacy `services/sms.py:68/172` runtime env check | Move to startup-time check (creds + factory selection) so per-call code can trust config |
| `jwt_secret_key_changed` | (new — security hardening) | Default dev secret in prod = JWT forgery vuln; catch at startup |

## CI gate (PR2 lint sentinel — out of scope for PR1)

PR2 (`scripts/qa/check_no_inline_env_check.py` + workflow) will:
- Scan `backend/app/` for `if.*env.*in.*(staging|canary|production)` or
  `if.*environment.*==.*production`.
- Fail CI if found (force migration to `@register_startup_probe`).
- Scope strictly `backend/app/` (not tests/migrations/scripts).

PR2 splits because lint哨兵 added BEFORE 散点收编完 risks self-blocking PR1.

## Refs

- ADR-0051 r3 §1.2.2 #7 (decoupled fail-loud)
- ADR-0051 r3 §1.2.3 #8 (env enum standardization)
- ADR-0051 r3 §2.3 #25 (no inline env checks)
- PR #258 review comment 4676805533 (ask 3 — 胡桃 raised pattern)
- S3-BUG-003 (sister bug — Dockerfile missing COPY)
- PR #304 (canary whitelist 反案 #11 复发 fix)
- 反案 #11 (单元覆盖 ≠ 生产能跑)
- 反案 #15 (sentinel 命名规则)
- 反案 #25 (散点 env check 协议禁止)
