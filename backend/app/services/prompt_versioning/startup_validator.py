"""Startup validator: DB-active prompt ↔ git source-of-truth.

S3-DEV-002-PROMPT-VERSIONING AC#3 (ADR-0048 §5.2).

Why a startup check?
====================

The system runs LLM inference against prompt text that lives in
``docs/ai-prompts/<axis>/<version>/system_prompt.md``.  At runtime, we
must know which version was used so AB-test / cost audit / safety
postmortem can replay the exact prompt.

The "double lock" design (git tag + DB ``prompt_versions`` row) only
works if **both sides agree**.  If the DB says "v1.2.0 is active" but
the git tree no longer carries that commit (rebase / revert / squash
merge wiped it), every subsequent generation silently writes
``prompt_version_id`` pointing at a stale row whose ``git_commit_hash``
points at a commit nobody can git-show.  We catch this at boot, not on
the first 500 in production.

What we check
=============

For each axis that has any rows in ``prompt_versions``:

  1. Exactly one row has ``is_active=True`` (DB partial unique index
     enforces "at most one"; we additionally enforce "at least one").
  2. The conventional git path
     ``docs/ai-prompts/<axis>/<version>/system_prompt.md`` exists.
  3. ``git log -n 1 --format=%H -- <path>`` returns a SHA equal to the
     row's ``git_commit_hash``.

If any check fails we raise :class:`StartupValidationError` and the
caller (FastAPI lifespan) must propagate the boot failure.  No silent
fall-back — degrading silently would hide the very drift we want to
catch.

When NOT to run
===============

  - Unit tests using an in-memory SQLite often skip the migration
    entirely (``Base.metadata.create_all``) — the
    ``prompt_versions_validate_on_startup`` setting lets test fixtures
    short-circuit.
  - First boot after the AC#1 migration but before any prompt row was
    seeded: no rows ⇒ no axes to check ⇒ pass.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_version import PromptVersion

from .git_blame import GitBlameError, git_blame_commit

logger = logging.getLogger(__name__)


class StartupValidationError(RuntimeError):
    """Raised when DB-active prompt diverges from git source of truth.

    Sub-classed from :class:`RuntimeError` so the FastAPI lifespan
    treatment is "boot dies" (we *want* the orchestrator to refuse to
    serve), not "log warning and continue".
    """


# ─── conventional git path helpers ──────────────────────────────────────────


def _prompt_git_path(axis: str, version: str) -> Path:
    """Return ADR-0048 §5.1 conventional path for a prompt version file.

    ADR-0048 §5.1 sketches ``docs/ai-prompts/s3-prep/v1.0.0/system_prompt.md``
    but the *axis enum value* is ``s3_prep`` (underscored — see
    ``BudgetAxis.S3_PREP``).  We follow the enum value verbatim — the
    ADR will be patched to match (one source of truth = the enum, not
    a free-form ADR string).
    """

    return Path("docs/ai-prompts") / axis / version / "system_prompt.md"


# ─── orchestrator ──────────────────────────────────────────────────────────


async def _list_axes_with_rows(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(PromptVersion.axis).distinct()
    )
    return [row[0] for row in result.all()]


async def _fetch_active_row(
    session: AsyncSession, axis: str
) -> PromptVersion | None:
    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.axis == axis,
            PromptVersion.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


def _verify_active_row(
    *,
    axis: str,
    row: PromptVersion,
    repo_root: Path | None,
) -> None:
    """Verify single active row's git side.  Raises on mismatch."""

    git_path = _prompt_git_path(axis, row.version)
    absolute = (repo_root / git_path) if repo_root else git_path
    if not absolute.exists():
        raise StartupValidationError(
            f"prompt_versions axis={axis!r} version={row.version!r} "
            f"is_active=True but git file missing: {git_path}"
        )

    try:
        observed_sha = git_blame_commit(git_path, repo_root=repo_root)
    except GitBlameError as exc:
        raise StartupValidationError(
            f"prompt_versions axis={axis!r} version={row.version!r}: "
            f"git_blame_commit failed for {git_path}: {exc}"
        ) from exc

    if observed_sha != row.git_commit_hash:
        raise StartupValidationError(
            f"prompt_versions axis={axis!r} version={row.version!r}: "
            f"DB git_commit_hash={row.git_commit_hash} but git HEAD "
            f"for {git_path}={observed_sha}"
        )


async def validate_prompt_versions_on_startup(
    session: AsyncSession,
    *,
    repo_root: Path | str | None = None,
    axes: Iterable[str] | None = None,
) -> None:
    """Entry point.  Iterate axes with rows, verify each active row.

    Parameters
    ----------
    session :
        Open ``AsyncSession`` on the application DB.  Caller owns
        lifetime.
    repo_root :
        Absolute path to the git repo root.  If ``None``, the helper
        searches upward from the cwd for ``.git`` (matches
        ``git_blame_commit`` default).
    axes :
        If supplied, restrict verification to these axes (useful for
        tests).  ``None`` ⇒ verify every axis that has any rows in DB
        (so a freshly-migrated DB with no rows trivially passes).

    Raises
    ------
    StartupValidationError
        On any mismatch — caller (FastAPI lifespan) propagates ⇒ boot
        aborts.
    """

    resolved_root: Path | None
    if repo_root is None:
        resolved_root = None
    else:
        resolved_root = Path(repo_root).resolve()

    target_axes: list[str]
    if axes is None:
        target_axes = await _list_axes_with_rows(session)
    else:
        target_axes = list(axes)

    if not target_axes:
        logger.info("prompt_versions: no rows yet, startup validation skipped")
        return

    for axis in target_axes:
        active = await _fetch_active_row(session, axis)
        if active is None:
            raise StartupValidationError(
                f"prompt_versions axis={axis!r}: no row with is_active=True "
                "(every axis with any rows must mark exactly one active)"
            )
        _verify_active_row(axis=axis, row=active, repo_root=resolved_root)
        logger.info(
            "prompt_versions: axis=%s version=%s verified against git",
            axis,
            active.version,
        )
