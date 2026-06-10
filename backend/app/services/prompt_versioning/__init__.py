"""Prompt versioning module (ADR-0048 §5).

Exposes:

- ``git_blame_commit``: subprocess-based git commit SHA lookup
- ``GitBlameError``: typed error for git failures
- ``validate_prompt_versions_on_startup``: AC#3 startup validator
- ``StartupValidationError``: raised by the validator on DB ↔ git drift
"""

from app.services.prompt_versioning.git_blame import (
    COMMIT_SHA_RE,
    GitBlameError,
    git_blame_commit,
)
from app.services.prompt_versioning.startup_validator import (
    StartupValidationError,
    validate_prompt_versions_on_startup,
)

__all__ = [
    "COMMIT_SHA_RE",
    "GitBlameError",
    "StartupValidationError",
    "git_blame_commit",
    "validate_prompt_versions_on_startup",
]
