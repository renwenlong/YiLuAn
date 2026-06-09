"""Prompt versioning module (ADR-0048 §5).

Exposes:
- ``git_blame_commit``: subprocess-based git commit SHA lookup
- ``GitBlameError``: typed error for git failures
"""

from app.services.prompt_versioning.git_blame import (
    COMMIT_SHA_RE,
    GitBlameError,
    git_blame_commit,
)

__all__ = ["COMMIT_SHA_RE", "GitBlameError", "git_blame_commit"]
