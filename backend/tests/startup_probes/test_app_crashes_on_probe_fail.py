"""S3-OPS-STARTUP-PROBE-FRAMEWORK AC#7: e2e fail-loud verification.

mock 'ai_prep_filter' 不可用 + env='production' → import app → crash;
mock 可用 → import OK; 验证 'fail-loud' 不会 silent skip.

测试 lifespan startup hook 实际触发 probe (不只 unit test registry).

This file exercises the WHOLE chain:
  decorator → registry → run_all_startup_probes → FastAPI lifespan → app crash

Sentinel: SECRET_STARTUP_PROBE_E2E_42 grep-defense (反案 #15).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SECRET_STARTUP_PROBE_E2E_42 = "SECRET_STARTUP_PROBE_E2E_42_DO_NOT_LEAK"


@pytest.fixture(autouse=True)
def _reset_probe_registry():
    """Ensure clean probe registry between tests; the real registry is
    populated by ``import app.probes`` so we save+restore."""
    from app.startup_probes import _PROBES

    saved = dict(_PROBES)
    _PROBES.clear()
    yield
    _PROBES.clear()
    _PROBES.update(saved)


def _build_test_app_with_probes() -> FastAPI:
    """Build a minimal FastAPI app with the lifespan probe runner.

    Mirrors ``app.main`` lifespan but lightweight — only triggers
    ``run_all_startup_probes`` (no DB / redis / pubsub init).
    """
    from contextlib import asynccontextmanager

    from app.startup_probes import run_all_startup_probes

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Mirror app.main: import probes module to trigger registration,
        # then run all probes.
        # (caller may pre-register probes via _PROBES directly for tests)
        await run_all_startup_probes(app.state.test_env)
        yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


class TestE2EProbeCrashesApp:
    """E2E: probe fail → app fail-loud at startup, /health never returns 200."""

    def test_probe_fail_crashes_lifespan_startup(self) -> None:
        """probe raise → TestClient(app) fails to enter context."""
        from app.startup_probes import register_startup_probe

        @register_startup_probe(name="probe_unavailable_asset", envs=("production",))
        def probe_unavailable_asset() -> None:
            raise RuntimeError(
                f"simulated prod-required asset missing. {_SECRET_STARTUP_PROBE_E2E_42}"
            )

        app = _build_test_app_with_probes()
        app.state.test_env = "production"

        # TestClient context-manager 触发 lifespan startup; probe fail → raise
        with pytest.raises(RuntimeError, match="simulated prod-required asset missing"):
            with TestClient(app) as client:
                # If startup didn't fail, /health would 200. AC#4: probe fail
                # MUST NOT be masked by /health endpoint.
                response = client.get("/health")
                # If we reach here, fail-loud broke.
                pytest.fail(
                    f"App startup should have crashed but /health returned "
                    f"{response.status_code}. fail-loud broken. "
                    f"{_SECRET_STARTUP_PROBE_E2E_42}"
                )

    def test_probe_pass_app_starts_normally(self) -> None:
        """Opposite case: all probes pass → app starts → /health 200."""
        from app.startup_probes import register_startup_probe

        @register_startup_probe(name="probe_all_good", envs=("production",))
        def probe_all_good() -> None:
            pass  # no-op success

        app = _build_test_app_with_probes()
        app.state.test_env = "production"

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"ok": True}

    def test_probe_env_mismatch_does_not_crash(self) -> None:
        """env=dev, probe envs=(production,) → probe skipped → app starts OK.

        Verifies the env gating works at lifespan-level (not crashing dev box).
        """
        from app.startup_probes import register_startup_probe

        @register_startup_probe(name="probe_prod_only_skip", envs=("production",))
        def probe_prod_only_skip() -> None:
            raise RuntimeError("should NOT run in dev")

        app = _build_test_app_with_probes()
        app.state.test_env = "dev"  # not in probe.envs → skip

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

    def test_health_endpoint_cannot_mask_probe_failure(self) -> None:
        """AC#4 explicit: /health MUST 503 (or crash) when probe fails.

        Verify: even though /health is registered, it never gets a chance
        to return 200 if startup probes fail. The TestClient context
        propagates the lifespan exception out.
        """
        from app.startup_probes import register_startup_probe

        @register_startup_probe(name="probe_critical_asset", envs=("production",))
        def probe_critical_asset() -> None:
            raise RuntimeError("CRITICAL: asset missing")

        app = _build_test_app_with_probes()
        app.state.test_env = "production"

        # Try multiple times — even if we retry, /health should NEVER 200
        # because lifespan never completed.
        for _attempt in range(3):
            with pytest.raises(RuntimeError, match="CRITICAL: asset missing"):
                with TestClient(app) as client:
                    client.get("/health")

    def test_multiple_probes_first_failure_stops_rest(self) -> None:
        """Fail-fast at lifespan level: if probe #1 fails, #2/3 never run."""
        from app.startup_probes import register_startup_probe

        invocations: list[str] = []

        @register_startup_probe(name="probe_e2e_first", envs=("production",))
        def probe_e2e_first() -> None:
            invocations.append("first")
            raise RuntimeError("first probe failed")

        @register_startup_probe(name="probe_e2e_second", envs=("production",))
        def probe_e2e_second() -> None:
            invocations.append("second")  # MUST NOT run

        @register_startup_probe(name="probe_e2e_third", envs=("production",))
        def probe_e2e_third() -> None:
            invocations.append("third")

        app = _build_test_app_with_probes()
        app.state.test_env = "production"

        with pytest.raises(RuntimeError, match="first probe failed"):
            with TestClient(app):
                pass

        assert invocations == ["first"], (
            f"Expected only ['first']; got {invocations!r}. "
            f"Fail-fast at lifespan-level broken. {_SECRET_STARTUP_PROBE_E2E_42}"
        )


class TestE2ERealRegistryIntegration:
    """E2E: the actual app.probes registry imports + registers without error.

    This catches: typos in @register_startup_probe arguments at import time
    (ImportError), missing probe modules, circular imports.
    """

    def test_app_probes_module_imports_without_error(self) -> None:
        """Importing app.probes triggers all probe registrations.

        If any decorator raises ImportError (bad envs / missing production /
        duplicate name), this test fails immediately.
        """
        # Clear probe registry to avoid duplicate registration error
        # (autouse fixture saved+cleared before this test)
        import sys

        from app.startup_probes import _PROBES, _reset_for_tests

        _reset_for_tests()
        # Force re-import via sys.modules eviction (importlib.reload runs
        # module body again which retains decorator state across reloads).
        sys.modules.pop("app.probes", None)
        import app.probes  # noqa: F401

        # Check expected probes are registered (AC#5 — 4 migrations)
        assert "ai_prep_filter_blocklist" in _PROBES
        assert "canary_whitelist_yml" in _PROBES
        assert "sms_provider_configured" in _PROBES
        assert "jwt_secret_key_changed" in _PROBES

    def test_all_registered_probes_include_production_in_envs(self) -> None:
        """AC#3: every registered probe MUST include 'production' in envs.

        decorator enforces this at register time; this test is double-check
        for the actual production registry.
        """
        import sys

        from app.startup_probes import _PROBES, _reset_for_tests

        _reset_for_tests()
        sys.modules.pop("app.probes", None)
        import app.probes  # noqa: F401

        for name, (_fn, envs, _loc) in _PROBES.items():
            assert "production" in envs, (
                f"probe {name!r} envs={envs!r} missing 'production' "
                f"(AC#3 — prod-required cannot opt-out). "
                f"{_SECRET_STARTUP_PROBE_E2E_42}"
            )
