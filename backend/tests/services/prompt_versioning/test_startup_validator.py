"""Unit tests for ``validate_prompt_versions_on_startup``.

S3-DEV-002-PROMPT-VERSIONING AC#3.

Approach
--------

We test the orchestrator end-to-end against an in-memory SQLite session
(real ORM, real partial unique index) but mock ``git_blame_commit`` so
the test does not depend on a checked-in fixture file.  This isolates
the validator's own logic (axis selection, active-row lookup,
exception translation) from subprocess behaviour, which already has
deep coverage in ``test_git_blame.py``.

Test matrix
-----------

  - empty DB ⇒ no-op pass
  - axis has rows but none is_active ⇒ StartupValidationError
  - axis active + git file missing ⇒ StartupValidationError
  - axis active + git commit mismatch ⇒ StartupValidationError
  - axis active + git ok ⇒ pass
  - two axes, one missing active ⇒ raises on the missing one (order
    independent — we just assert *some* axis raises)
  - explicit ``axes=[...]`` overrides DB scan
  - underlying ``GitBlameError`` is wrapped, not leaked
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.prompt_version import PromptVersion
from app.services.prompt_versioning import (
    StartupValidationError,
    validate_prompt_versions_on_startup,
)
from app.services.prompt_versioning.git_blame import GitBlameError

GOOD_SHA = "a" * 40
OTHER_SHA = "b" * 40


# ─── fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory SQLite + ORM tables for each test (isolation)."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _make_row(
    *,
    axis: str = "s3_prep",
    version: str = "v1.0.0",
    sha: str = GOOD_SHA,
    active: bool = True,
) -> PromptVersion:
    return PromptVersion(
        id=uuid.uuid4(),
        axis=axis,
        version=version,
        git_commit_hash=sha,
        prompt_text="system: you are a helpful assistant",
        model="deepseek-chat",
        is_active=active,
    )


# ─── happy + empty paths ───────────────────────────────────────────────────


class TestEmptyAndHappyPath:
    @pytest.mark.asyncio
    async def test_empty_db_passes(self, session: AsyncSession) -> None:
        """No rows ⇒ nothing to verify ⇒ no exception."""
        await validate_prompt_versions_on_startup(session)

    @pytest.mark.asyncio
    async def test_single_axis_active_and_git_match_passes(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        """1 axis, 1 active row, git file exists, sha matches ⇒ pass."""
        # arrange: real file on disk under tmp_path
        prompt_dir = tmp_path / "docs" / "ai-prompts" / "s3_prep" / "v1.0.0"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "system_prompt.md").write_text("hi\n")

        session.add(_make_row())
        await session.commit()

        with patch(
            "app.services.prompt_versioning.startup_validator.git_blame_commit",
            return_value=GOOD_SHA,
        ) as mock_blame:
            await validate_prompt_versions_on_startup(
                session, repo_root=tmp_path
            )
        mock_blame.assert_called_once()

    @pytest.mark.asyncio
    async def test_inactive_only_rows_ignored_means_raises(
        self, session: AsyncSession
    ) -> None:
        """Axis with rows but no active flag is a misconfiguration."""
        session.add(_make_row(active=False))
        await session.commit()

        with pytest.raises(StartupValidationError, match="no row with is_active"):
            await validate_prompt_versions_on_startup(session)


# ─── git side failures ─────────────────────────────────────────────────────


class TestGitSideFailures:
    @pytest.mark.asyncio
    async def test_git_file_missing_raises(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        """Active row points at version whose file does not exist."""
        # do NOT create the prompt file
        session.add(_make_row())
        await session.commit()

        with pytest.raises(StartupValidationError, match="git file missing"):
            await validate_prompt_versions_on_startup(
                session, repo_root=tmp_path
            )

    @pytest.mark.asyncio
    async def test_git_commit_mismatch_raises(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        """File exists but git_blame_commit returns a different SHA."""
        prompt_dir = tmp_path / "docs" / "ai-prompts" / "s3_prep" / "v1.0.0"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "system_prompt.md").write_text("hi\n")

        session.add(_make_row(sha=GOOD_SHA))
        await session.commit()

        with patch(
            "app.services.prompt_versioning.startup_validator.git_blame_commit",
            return_value=OTHER_SHA,
        ):
            with pytest.raises(StartupValidationError, match="git HEAD"):
                await validate_prompt_versions_on_startup(
                    session, repo_root=tmp_path
                )

    @pytest.mark.asyncio
    async def test_git_blame_error_is_wrapped(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        """GitBlameError surfaces as StartupValidationError with `from`."""
        prompt_dir = tmp_path / "docs" / "ai-prompts" / "s3_prep" / "v1.0.0"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "system_prompt.md").write_text("hi\n")

        session.add(_make_row())
        await session.commit()

        with patch(
            "app.services.prompt_versioning.startup_validator.git_blame_commit",
            side_effect=GitBlameError("git binary missing"),
        ):
            with pytest.raises(StartupValidationError) as exc_info:
                await validate_prompt_versions_on_startup(
                    session, repo_root=tmp_path
                )
        assert isinstance(exc_info.value.__cause__, GitBlameError)


# ─── multi-axis & axes filter ──────────────────────────────────────────────


class TestMultipleAxes:
    @pytest.mark.asyncio
    async def test_two_axes_both_active_and_match_passes(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        for axis in ("s3_prep", "s2_summary"):
            prompt_dir = tmp_path / "docs" / "ai-prompts" / axis / "v1.0.0"
            prompt_dir.mkdir(parents=True)
            (prompt_dir / "system_prompt.md").write_text("hi\n")
            session.add(_make_row(axis=axis))
        await session.commit()

        with patch(
            "app.services.prompt_versioning.startup_validator.git_blame_commit",
            return_value=GOOD_SHA,
        ) as mock_blame:
            await validate_prompt_versions_on_startup(
                session, repo_root=tmp_path
            )
        assert mock_blame.call_count == 2

    @pytest.mark.asyncio
    async def test_one_axis_missing_active_raises_for_that_axis(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        """One axis ok, another axis has only inactive rows ⇒ raise."""
        prompt_dir = tmp_path / "docs" / "ai-prompts" / "s3_prep" / "v1.0.0"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "system_prompt.md").write_text("hi\n")

        session.add(_make_row(axis="s3_prep", active=True))
        session.add(_make_row(axis="s2_summary", active=False))
        await session.commit()

        with patch(
            "app.services.prompt_versioning.startup_validator.git_blame_commit",
            return_value=GOOD_SHA,
        ):
            with pytest.raises(StartupValidationError, match="s2_summary"):
                await validate_prompt_versions_on_startup(
                    session, repo_root=tmp_path
                )

    @pytest.mark.asyncio
    async def test_explicit_axes_filter_overrides_db_scan(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        """``axes=['s3_prep']`` ignores rows from other axes in DB."""
        # DB has only inactive s2_summary row — would normally raise
        session.add(_make_row(axis="s2_summary", active=False))
        await session.commit()

        # but we ask explicitly for an axis with no rows ⇒ should raise
        # because the explicit axis must have an active row too
        with pytest.raises(StartupValidationError, match="s3_prep"):
            await validate_prompt_versions_on_startup(
                session, repo_root=tmp_path, axes=["s3_prep"]
            )


# ─── partial unique index sanity (DB enforces 1-active-per-axis) ───────────


class TestDbInvariant:
    @pytest.mark.asyncio
    async def test_db_rejects_two_active_in_same_axis(
        self, session: AsyncSession
    ) -> None:
        """The partial unique index from migration 7a8e1c2d4f60 must hold.

        Note: ``Base.metadata.create_all`` includes the partial index
        because the SQLAlchemy model declares it via ``__table_args__``
        (we mirror the migration in the model so test-suite SQLite
        databases share the invariant).
        """
        session.add(_make_row(version="v1.0.0", active=True))
        session.add(_make_row(version="v1.1.0", active=True))
        with pytest.raises(Exception):  # IntegrityError or similar
            await session.commit()
