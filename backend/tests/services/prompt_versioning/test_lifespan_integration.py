"""S3-DEV-002-PROMPT-VERSIONING AC#3: lifespan integration.

This test exercises the FastAPI lifespan hook (``app.main.lifespan``)
end-to-end with the ``prompt_versions_validate_on_startup`` setting
re-enabled, so we cover the wire-up that the autouse fixture
``_disable_prompt_versions_validator`` would otherwise hide.

Why this exists
===============

PR #237 review (魈, comment 4661673187) called out: the unit suite for
``startup_validator`` calls the function directly with an in-memory
SQLite session, never going through ``lifespan``.  The autouse fixture
defaults ``prompt_versions_validate_on_startup=False`` in tests for
isolation reasons, which means the *integration* (the ``if
settings.prompt_versions_validate_on_startup:`` block in
``app.main.lifespan``) has 0 coverage.  We add the missing branch
coverage here.

Strategy
--------

We don't spin up the real module-level ``app`` (which would pull in
Redis, pubsub brokers, scheduler — all the side effects we explicitly
*don't* want here).  Instead we drive ``app.main.lifespan`` directly
against a minimal ``FastAPI()`` instance and monkeypatch the few
mandatory dependencies (``init_redis``, ``init_redis_sync``) so the
non-prompt-versioning startup code degrades to no-ops.  This keeps the
test surface small while still exercising **the exact production
control flow** through the validator branch.

What we assert
==============

  - validator-on + DB empty ⇒ lifespan starts cleanly (no rows, no raise)
  - validator-on + DB has active row + git mismatch ⇒ lifespan raises
    ``StartupValidationError`` and the boot fails-fast (no silent
    fallback)
  - validator-off ⇒ lifespan does not even import / call the validator
    (settings flag honoured, not just "always run but swallow")
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.prompt_version import PromptVersion
from app.services.prompt_versioning import StartupValidationError

# 40-char fake SHAs — must be distinct so "mismatch" cases produce
# a recognisable diff in the error message.
ACTIVE_SHA = "a" * 40
DRIFTED_GIT_SHA = "b" * 40


# ─── helpers ───────────────────────────────────────────────────────────────


def _make_minimal_app() -> FastAPI:
    """Bare FastAPI instance bound to the production lifespan.

    The module-level ``app`` in ``app.main`` already ran its lifespan
    once at import time and carries shared state (redis, scheduler).
    We need a *fresh* instance per test so the validator branch runs
    against a clean state.
    """
    from app.main import lifespan

    return FastAPI(lifespan=lifespan)


def _seed_active_row_sync(maker, *, axis: str, version: str, sha: str):
    """Return a coroutine that seeds one active row via the given maker.

    Caller awaits this inside their own async test (so we don't fight
    pytest-asyncio for the event loop).
    """

    async def _do() -> None:
        async with maker() as s:
            s.add(
                PromptVersion(
                    id=uuid.uuid4(),
                    axis=axis,
                    version=version,
                    git_commit_hash=sha,
                    prompt_text="system: test",
                    model="deepseek-chat",
                    is_active=True,
                )
            )
            await s.commit()

    return _do()


# ─── fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def in_memory_session_factory() -> AsyncIterator[tuple[Any, Any]]:
    """Per-test in-memory SQLite + matching async_sessionmaker.

    Returned as ``(engine, sessionmaker)`` so the test can both seed
    data and inject the sessionmaker into ``app.database.async_session``.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, maker
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _bypass_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lifespan calls ``init_redis()`` and ``init_redis_sync()`` for
    real before reaching our validator branch.  Swap both for the
    project's bundled ``FakeRedis`` stub (same one the regular ``client``
    fixture uses) so we don't need a running Redis to test the
    prompt-versioning startup wire-up.
    """
    from app.core import redis as redis_module
    from tests.conftest import FakeRedis as ProjectFakeRedis

    monkeypatch.setattr(redis_module, "init_redis", lambda: ProjectFakeRedis())
    monkeypatch.setattr(redis_module, "init_redis_sync", lambda: ProjectFakeRedis())


@pytest.fixture(autouse=True)
def _re_enable_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite-wide autouse fixture forces the validator OFF for
    isolation.  These tests are the one place where we want it ON.
    """
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "prompt_versions_validate_on_startup", True)


# ─── tests ─────────────────────────────────────────────────────────────────


class TestLifespanIntegration:
    @pytest.mark.asyncio
    async def test_empty_db_lets_lifespan_complete(
        self,
        in_memory_session_factory: tuple[Any, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validator on + no prompt rows ⇒ lifespan startup completes.

        Empty DB has zero axes, validator no-ops, lifespan finishes
        and we can take an ASGI request through the ctx manager.
        """
        _, maker = in_memory_session_factory
        # Inject our SQLite sessionmaker where the lifespan block opens it.
        monkeypatch.setattr("app.database.async_session", maker)

        test_app = _make_minimal_app()
        # Drive the lifespan: __aenter__ runs startup, __aexit__ runs shutdown.
        async with test_app.router.lifespan_context(test_app):
            # If we got here, validator didn't raise.  Pass.
            pass

    @pytest.mark.asyncio
    async def test_drifted_git_sha_fails_lifespan_boot(
        self,
        in_memory_session_factory: tuple[Any, Any],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Active row says SHA=AAA but git tree says SHA=BBB ⇒ raise.

        Exactly the production scenario we built fail-fast to catch:
        someone force-pushed / rebased the prompt commit out from
        under us and the DB is now pointing at a stale row.
        """
        _, maker = in_memory_session_factory
        monkeypatch.setattr("app.database.async_session", maker)

        # Seed: axis s3_prep, version v1.0.0, expects SHA=AAA in git.
        await _seed_active_row_sync(
            maker, axis="s3_prep", version="v1.0.0", sha=ACTIVE_SHA
        )

        # Stage a real file on disk so the "file exists" check passes
        # but make git_blame_commit return a different SHA — that's the
        # specific drift scenario we want to assert lifespan catches.
        prompt_dir = tmp_path / "docs" / "ai-prompts" / "s3_prep" / "v1.0.0"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "system_prompt.md").write_text("system: drifted\n")

        from app.config import settings as _settings

        monkeypatch.setattr(_settings, "prompt_versions_repo_root", str(tmp_path))

        with patch(
            "app.services.prompt_versioning.startup_validator.git_blame_commit",
            return_value=DRIFTED_GIT_SHA,
        ):
            test_app = _make_minimal_app()
            with pytest.raises(StartupValidationError) as exc_info:
                async with test_app.router.lifespan_context(test_app):
                    pytest.fail(
                        "lifespan should have raised before reaching the body"
                    )

        # Validator error must name the axis + both SHAs so an operator
        # gets a one-glance diagnosis from the boot log.
        msg = str(exc_info.value)
        assert "s3_prep" in msg
        assert ACTIVE_SHA[:8] in msg or ACTIVE_SHA in msg
        assert DRIFTED_GIT_SHA[:8] in msg or DRIFTED_GIT_SHA in msg

    @pytest.mark.asyncio
    async def test_validator_off_skips_validator_entirely(
        self,
        in_memory_session_factory: tuple[Any, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Settings flag off ⇒ validator never called, even with a
        drifted row that *would* fail.

        Asserts the production switch actually short-circuits the
        block, not "always run but swallow exceptions".
        """
        _, maker = in_memory_session_factory
        monkeypatch.setattr("app.database.async_session", maker)
        # Override the re-enable autouse: turn it back off.
        from app.config import settings as _settings

        monkeypatch.setattr(_settings, "prompt_versions_validate_on_startup", False)

        # Plant a drifted row that *would* fail validation if it ran.
        await _seed_active_row_sync(
            maker, axis="s3_prep", version="v1.0.0", sha=ACTIVE_SHA
        )

        called = {"n": 0}

        def _spy(*_args: object, **_kw: object) -> None:
            called["n"] += 1

        # If the off-switch is broken and validator runs, this spy
        # would fire (and probably also raise on the missing axis).
        with patch(
            "app.services.prompt_versioning.validate_prompt_versions_on_startup",
            _spy,
        ):
            test_app = _make_minimal_app()
            async with test_app.router.lifespan_context(test_app):
                pass

        assert called["n"] == 0, (
            "validator was called despite prompt_versions_validate_on_startup=False"
        )
