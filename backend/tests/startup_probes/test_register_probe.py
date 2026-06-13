"""Unit tests for @register_startup_probe decorator + registry.

AC#6: at least 6 tests covering:
  1. register 正常 case (decorator 注入 registry)
  2. env 不在 enum → raise ImportError
  3. run_all 时 probe fail → raise (不吞)
  4. run_all 时 probe pass → 记 result + continue
  5. env mismatch → skip probe
  6. registry 隔离 (fixture cleanup 防 test 间污染)

Sentinel: SECRET_STARTUP_PROBE_REGISTRY_42 grep-defense (反案 #15).
"""

from __future__ import annotations

import pytest

from app.startup_probes import (
    _PROBES,
    StartupProbeEnv,
    _registered_probe,
    _registered_probe_names,
    _reset_for_tests,
    register_startup_probe,
    run_all_startup_probes,
)

# Sentinel for grep / rg 防误删 (反案 #15).
_SECRET_STARTUP_PROBE_TEST_42 = "SECRET_STARTUP_PROBE_TEST_42_DO_NOT_LEAK"


@pytest.fixture(autouse=True)
def _registry_isolation():
    """AC#6: cleanup _PROBES between tests to prevent cross-pollution."""
    _reset_for_tests()
    yield
    _reset_for_tests()


# ============================================================================
# AC#6.1: register 正常 case
# ============================================================================


class TestRegisterStartupProbe:
    def test_register_injects_to_registry(self) -> None:
        """正常 case: decorator runs → probe in _PROBES."""

        @register_startup_probe(name="probe_a", envs=("production",))
        def probe_a() -> None:
            pass

        assert "probe_a" in _PROBES
        names = _registered_probe_names()
        assert "probe_a" in names

    def test_register_preserves_decorated_fn(self) -> None:
        """decorator returns the same fn unchanged (so caller can still call it)."""

        @register_startup_probe(name="probe_b", envs=("production",))
        def probe_b() -> str:
            return "called"

        # Directly invokable, returns original value
        assert probe_b() == "called"

    def test_register_records_source_location(self) -> None:
        """source_location stored for observability/log."""

        @register_startup_probe(name="probe_c", envs=("production",))
        def probe_c() -> None:
            pass

        _, _, location = _registered_probe("probe_c")
        # location format: module:qualname:lineno (qualname may include
        # <locals>.probe_c when defined inside a test method)
        assert "probe_c" in location
        assert location.split(":")[-1].isdigit()  # lineno

    def test_register_envs_stored_as_frozenset(self) -> None:
        """envs stored as frozenset for immutable set semantics."""

        @register_startup_probe(name="probe_d", envs=("staging", "canary", "production"))
        def probe_d() -> None:
            pass

        _, envs, _ = _registered_probe("probe_d")
        assert isinstance(envs, frozenset)
        assert envs == frozenset({"staging", "canary", "production"})

    def test_register_preserves_insertion_order(self) -> None:
        """_PROBES is insertion-ordered dict (Python 3.7+ guarantee)."""

        @register_startup_probe(name="probe_first", envs=("production",))
        def first() -> None:
            pass

        @register_startup_probe(name="probe_second", envs=("production",))
        def second() -> None:
            pass

        @register_startup_probe(name="probe_third", envs=("production",))
        def third() -> None:
            pass

        names = _registered_probe_names()
        assert names == ("probe_first", "probe_second", "probe_third")


# ============================================================================
# AC#6.2: env 不在 enum / production missing → ImportError
# ============================================================================


class TestEnvValidation:
    def test_invalid_env_raises_import_error(self) -> None:
        """env name typo → ImportError at decorator time."""
        with pytest.raises(ImportError, match="invalid env"):

            @register_startup_probe(name="probe_bad_env", envs=("prodction",))  # typo
            def probe_bad_env() -> None:
                pass

    def test_invalid_env_lists_typo_in_error(self) -> None:
        """error message tells which env is invalid (for fast triage)."""
        with pytest.raises(ImportError, match="prodctn"):

            @register_startup_probe(name="probe_bad_env_2", envs=("prodctn", "production"))
            def probe_bad_env_2() -> None:
                pass

    def test_missing_production_raises_import_error(self) -> None:
        """AC#3: production is mandatory in envs."""
        with pytest.raises(ImportError, match="production.*MUST be in envs"):

            @register_startup_probe(name="probe_no_prod", envs=("staging", "canary"))
            def probe_no_prod() -> None:
                pass

    def test_empty_envs_raises_import_error(self) -> None:
        """envs=() is meaningless (no env runs)."""
        with pytest.raises(ImportError, match="non-empty tuple"):

            @register_startup_probe(name="probe_empty_envs", envs=())
            def probe_empty_envs() -> None:
                pass

    def test_envs_not_tuple_raises_import_error(self) -> None:
        """envs=list rejected (must be immutable tuple)."""
        with pytest.raises(ImportError, match="non-empty tuple"):

            @register_startup_probe(
                name="probe_envs_list",
                envs=["production"],  # type: ignore[arg-type]
            )
            def probe_envs_list() -> None:
                pass

    def test_all_valid_env_names_accepted(self) -> None:
        """Each enum member should be accepted (no typos in our own enum)."""

        @register_startup_probe(
            name="probe_all_envs",
            envs=("dev", "test", "staging", "canary", "production"),
        )
        def probe_all_envs() -> None:
            pass

        _, envs, _ = _registered_probe("probe_all_envs")
        assert envs == frozenset({"dev", "test", "staging", "canary", "production"})

    def test_duplicate_name_raises_import_error(self) -> None:
        """Same probe name registered twice → ImportError (fast-fail)."""

        @register_startup_probe(name="probe_dup", envs=("production",))
        def probe_dup_first() -> None:
            pass

        with pytest.raises(ImportError, match="duplicate probe name"):

            @register_startup_probe(name="probe_dup", envs=("production",))
            def probe_dup_second() -> None:
                pass


# ============================================================================
# AC#6.3-4: run_all fail re-raises, pass records result
# ============================================================================


class TestRunAllStartupProbes:
    @pytest.mark.asyncio
    async def test_probe_pass_records_result_and_continues(self) -> None:
        """AC#6.4: probe pass → result recorded; next probe still runs."""

        @register_startup_probe(name="probe_pass_1", envs=("production",))
        def probe_pass_1() -> None:
            return  # no-op pass

        @register_startup_probe(name="probe_pass_2", envs=("production",))
        def probe_pass_2() -> None:
            return

        results = await run_all_startup_probes("production")
        assert len(results) == 2
        names = [r[0] for r in results]
        assert names == ["probe_pass_1", "probe_pass_2"]
        # All ok=True
        assert all(r[1] is True for r in results)
        # Duration is non-negative float
        assert all(isinstance(r[2], float) and r[2] >= 0.0 for r in results)
        # No error
        assert all(r[3] is None for r in results)

    @pytest.mark.asyncio
    async def test_probe_fail_re_raises_does_not_swallow(self) -> None:
        """AC#6.3: probe fail → run_all re-raises original exception (not swallow)."""

        @register_startup_probe(name="probe_fail", envs=("production",))
        def probe_fail() -> None:
            raise RuntimeError("intentional probe failure")

        with pytest.raises(RuntimeError, match="intentional probe failure"):
            await run_all_startup_probes("production")

    @pytest.mark.asyncio
    async def test_probe_fail_stops_subsequent_probes(self) -> None:
        """Fail-fast: 1st probe fail → 2nd never runs."""
        invocations: list[str] = []

        @register_startup_probe(name="probe_first_fails", envs=("production",))
        def first_fails() -> None:
            invocations.append("first")
            raise ValueError("first probe boom")

        @register_startup_probe(name="probe_second_never_runs", envs=("production",))
        def second_never_runs() -> None:
            invocations.append("second")  # should NEVER append

        with pytest.raises(ValueError, match="first probe boom"):
            await run_all_startup_probes("production")

        assert invocations == ["first"], (
            f"second probe should NOT run after first fails; "
            f"got invocations={invocations!r}. {_SECRET_STARTUP_PROBE_TEST_42}"
        )

    @pytest.mark.asyncio
    async def test_async_probe_supported(self) -> None:
        """Async probe fn is awaited; sync fn called directly."""
        invoked_sync = []
        invoked_async = []

        @register_startup_probe(name="probe_sync", envs=("production",))
        def probe_sync() -> None:
            invoked_sync.append(True)

        @register_startup_probe(name="probe_async", envs=("production",))
        async def probe_async() -> None:
            invoked_async.append(True)

        results = await run_all_startup_probes("production")
        assert len(results) == 2
        assert invoked_sync == [True]
        assert invoked_async == [True]
        assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_async_probe_fail_re_raises(self) -> None:
        """Async probe fail → also re-raised (parity with sync)."""

        @register_startup_probe(name="probe_async_fail", envs=("production",))
        async def probe_async_fail() -> None:
            raise RuntimeError("async fail")

        with pytest.raises(RuntimeError, match="async fail"):
            await run_all_startup_probes("production")


# ============================================================================
# AC#6.5: env mismatch → skip probe
# ============================================================================


class TestEnvMismatch:
    @pytest.mark.asyncio
    async def test_env_mismatch_skips_probe(self) -> None:
        """env not in probe.envs → probe skipped (not in results)."""

        @register_startup_probe(name="probe_canary_only", envs=("canary", "production"))
        def probe_canary_only() -> None:
            raise AssertionError("should NOT run in staging")

        # current env = staging, probe needs canary or production → skip.
        results = await run_all_startup_probes("staging")
        assert results == []  # nothing ran

    @pytest.mark.asyncio
    async def test_env_match_runs_only_matched(self) -> None:
        """Mixed envs: only probes matching current env run."""

        @register_startup_probe(
            name="probe_all", envs=("dev", "test", "staging", "canary", "production")
        )
        def probe_all() -> None:
            pass

        @register_startup_probe(name="probe_prod_only", envs=("production",))
        def probe_prod_only() -> None:
            pass

        @register_startup_probe(name="probe_canary_only", envs=("canary", "production"))
        def probe_canary_only() -> None:
            pass

        # staging: only probe_all runs
        results = await run_all_startup_probes("staging")
        assert [r[0] for r in results] == ["probe_all"]

    @pytest.mark.asyncio
    async def test_unknown_env_skips_all_no_crash(self) -> None:
        """ENVIRONMENT typo → log warning + skip all (dev safety, NOT crash)."""

        @register_startup_probe(name="probe_x", envs=("production",))
        def probe_x() -> None:
            raise AssertionError("should NOT run with unknown env")

        results = await run_all_startup_probes("totally-bogus-env")
        assert results == []  # skipped, no crash

    @pytest.mark.asyncio
    async def test_empty_registry_no_crash(self) -> None:
        """No probes registered → no crash, empty result."""
        results = await run_all_startup_probes("production")
        assert results == []


# ============================================================================
# AC#6.6: registry isolation between tests (this is the autouse fixture)
# ============================================================================


class TestRegistryIsolation:
    def test_fixture_clears_registry_between_tests_part1(self) -> None:
        """Part 1: register a probe; part 2 should see empty registry."""

        @register_startup_probe(name="probe_isolation_part1", envs=("production",))
        def probe_isolation_part1() -> None:
            pass

        assert "probe_isolation_part1" in _registered_probe_names()

    def test_fixture_clears_registry_between_tests_part2(self) -> None:
        """Part 2: registry should be empty (autouse fixture cleared part 1's probe)."""
        # If isolation broken, part1's probe would still be here.
        assert "probe_isolation_part1" not in _registered_probe_names()
        # registry can be empty (other tests in same class can leave their own,
        # but this test is fresh after _reset_for_tests fixture).
        assert _registered_probe_names() == ()


# ============================================================================
# Bonus: enum literal sanity
# ============================================================================


class TestEnumLiteralSanity:
    def test_startup_probe_env_enum_matches_runtime(self) -> None:
        """StartupProbeEnv literal members match the runtime _VALID_ENVS."""
        from typing import get_args

        from app.startup_probes import _VALID_ENVS

        expected = frozenset({"dev", "test", "staging", "canary", "production"})
        assert _VALID_ENVS == expected
        assert frozenset(get_args(StartupProbeEnv)) == expected
