"""S2-TEST-016-READ-ONLY-FLAG-E2E E#9 — CI lint hard gate meta test.

Validates that ``backend/scripts/lint_writeable_user.py`` (landed in
PR #297) actually fails when a mutating endpoint regresses to
``CurrentUser``. We construct a temporary fake endpoint file with a
known-bad signature, run the lint script with that file in scope, and
assert non-zero exit + the offending path appears in stderr/stdout.

This is the **inverse / red-test** of the lint: dev's AC#5 unit tests
prove "real codebase passes"; here we prove "lint would catch a
regression". Without this, a buggy lint script that always returns 0
would never be detected.

References:
- S2-DEV-016-READ-ONLY-FLAG-DB AC#5 — lint script ship
- S2-TEST-016-READ-ONLY-FLAG-E2E AC E#9 — verify lint catches violations
- PR #297 ``backend/scripts/lint_writeable_user.py``
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


REPO_ROOT = Path(__file__).resolve().parents[3]  # YiLuAn-keqing-test016/
LINT_SCRIPT = REPO_ROOT / "backend" / "scripts" / "lint_writeable_user.py"
TARGET_DIR = REPO_ROOT / "backend" / "app" / "api" / "v1" / "_lint_test_fixtures"


@pytest.fixture
def lint_script_exists():
    assert LINT_SCRIPT.is_file(), (
        f"PR #297 lint script not found at {LINT_SCRIPT}; cannot run E#9 "
        f"meta test. Was the lint deliverable lost in a merge?"
    )
    return LINT_SCRIPT


@pytest.fixture
def fixture_dir_clean():
    """Create + cleanup a fixture dir under the lint glob scope.

    The lint script greps ``backend/app/api/v1/**/*.py`` so the fixture
    must live there for the lint to pick it up.
    """
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True)
    yield TARGET_DIR
    shutil.rmtree(TARGET_DIR, ignore_errors=True)


def _run_lint() -> subprocess.CompletedProcess:
    """Run the lint script from the repo root with full output capture."""
    return subprocess.run(
        ["python3", str(LINT_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_lint_script_passes_on_clean_codebase(lint_script_exists):
    """Sanity: the unmodified main branch should pass the lint cleanly.

    If this fails, either (a) the lint has a real violation that snuck
    through PR #297 review, or (b) the lint logic is too strict and is
    flagging legitimate code. Either way, E#9 has a real blocker.
    """
    result = _run_lint()
    assert result.returncode == 0, (
        f"unmodified main branch fails lint — investigate before adding "
        f"new endpoints. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_lint_script_catches_post_endpoint_with_current_user(
    lint_script_exists, fixture_dir_clean
):
    """E#9 red-test: a POST endpoint with ``CurrentUser`` must trigger
    a non-zero exit and the offending function name in the output.
    """
    bad_endpoint = TARGET_DIR / "bad_post.py"
    bad_endpoint.write_text(
        "from fastapi import APIRouter\n"
        "from app.dependencies import CurrentUser\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/test-bad-endpoint')\n"
        "async def bad_endpoint_should_fail_lint(user: CurrentUser):\n"
        "    return {'ok': True}\n"
    )

    result = _run_lint()
    assert result.returncode != 0, (
        f"lint should have FAILED for fake POST using CurrentUser but "
        f"returned 0. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "bad_endpoint_should_fail_lint" in result.stdout, (
        f"lint failed but did not report the offending function name. "
        f"stdout:\n{result.stdout}"
    )


def test_lint_script_catches_put_endpoint_with_current_user(
    lint_script_exists, fixture_dir_clean
):
    """E#9 red-test: same as above for PUT (regex must cover all 4 verbs)."""
    bad_endpoint = TARGET_DIR / "bad_put.py"
    bad_endpoint.write_text(
        "from fastapi import APIRouter\n"
        "from app.dependencies import CurrentUser\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.put('/test-bad-put')\n"
        "async def bad_put_should_fail_lint(user: CurrentUser):\n"
        "    return {'ok': True}\n"
    )

    result = _run_lint()
    assert result.returncode != 0, result.stdout
    assert "bad_put_should_fail_lint" in result.stdout


def test_lint_script_catches_delete_endpoint_with_current_user(
    lint_script_exists, fixture_dir_clean
):
    """E#9 red-test: DELETE coverage."""
    bad_endpoint = TARGET_DIR / "bad_delete.py"
    bad_endpoint.write_text(
        "from fastapi import APIRouter\n"
        "from app.dependencies import CurrentUser\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.delete('/test-bad-delete')\n"
        "async def bad_delete_should_fail_lint(user: CurrentUser):\n"
        "    return {'ok': True}\n"
    )

    result = _run_lint()
    assert result.returncode != 0, result.stdout
    assert "bad_delete_should_fail_lint" in result.stdout


def test_lint_script_catches_patch_endpoint_with_current_user(
    lint_script_exists, fixture_dir_clean
):
    """E#9 red-test: PATCH coverage. Even if no current PATCH endpoints
    use this pattern, the lint must still catch a future one."""
    bad_endpoint = TARGET_DIR / "bad_patch.py"
    bad_endpoint.write_text(
        "from fastapi import APIRouter\n"
        "from app.dependencies import CurrentUser\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.patch('/test-bad-patch')\n"
        "async def bad_patch_should_fail_lint(user: CurrentUser):\n"
        "    return {'ok': True}\n"
    )

    result = _run_lint()
    assert result.returncode != 0, result.stdout
    assert "bad_patch_should_fail_lint" in result.stdout


def test_lint_script_rejects_noqa_bypass(
    lint_script_exists, fixture_dir_clean
):
    """E#9 red-test: ``# noqa`` annotation must NOT silence the lint
    (PR #297 docstring explicitly bans this; if the regex change drops
    the noqa branch in future, this catches it).
    """
    bad_endpoint = TARGET_DIR / "bad_noqa.py"
    bad_endpoint.write_text(
        "from fastapi import APIRouter\n"
        "from app.dependencies import CurrentUser\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/test-noqa-bypass')\n"
        "async def bad_noqa_bypass(user: CurrentUser):  # noqa: lint-writeable\n"
        "    return {'ok': True}\n"
    )

    result = _run_lint()
    assert result.returncode != 0, (
        f"# noqa must NOT bypass the lint, but lint returned 0. "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # PR #297 marks noqa-bypass cases explicitly with [noqa-bypass] suffix.
    assert (
        "bad_noqa_bypass" in result.stdout
        or "noqa-bypass" in result.stdout
    ), (
        f"lint flagged the file but did not surface noqa context. "
        f"stdout:\n{result.stdout}"
    )


def test_lint_script_does_not_flag_allowlist_logout_or_delete_account(
    lint_script_exists, fixture_dir_clean
):
    """E#9 red-test: the two legitimate KEEP-CurrentUser endpoints
    (``logout_all``, ``delete_account``) per ratify 魈 08:14Z r3 must
    NOT trigger lint. Verifies the ALLOW set in the lint script is
    still wired correctly.

    NB: we add a fake file with these names; lint should ignore both.
    """
    keep_file = TARGET_DIR / "keep_allowed.py"
    keep_file.write_text(
        "from fastapi import APIRouter\n"
        "from app.dependencies import CurrentUser\n"
        "\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/logout-all-fixture')\n"
        "async def logout_all(user: CurrentUser):\n"
        "    return {'ok': True}\n"
        "\n"
        "@router.delete('/delete-account-fixture')\n"
        "async def delete_account(user: CurrentUser):\n"
        "    return {'ok': True}\n"
    )

    result = _run_lint()
    assert result.returncode == 0, (
        f"lint must NOT flag the allowlisted endpoints (logout_all + "
        f"delete_account per ADR ratify). stdout:\n{result.stdout}"
    )
