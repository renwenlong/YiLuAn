"""Unit tests for scripts/openapi_drift_check_hook.py.

Case A: backend code 改完并 regen docs/api/ → hook PASS (exit 0)
Case B: backend code 改完未 regen docs/api/ → hook BLOCK (exit non-zero)

反案 #15 (workspace-xiao MEMORY.md): pre-commit hook 防 dev 本地未跑 dump_openapi.py
直接 commit, 与 CI api-docs-check workflow 双层防御.

Run: cd backend && pytest ../tests/scripts/test_openapi_drift_check_hook.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "scripts" / "openapi_drift_check_hook.py"
BACKEND = REPO_ROOT / "backend"


def _run_hook(env_python: str | None = None) -> tuple[int, str, str]:
    python = env_python or sys.executable
    result = subprocess.run(
        [python, str(HOOK)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def _backend_venv_python() -> str | None:
    """Return backend .venv python if installed (try multiple locations).

    Try in order:
    1. {REPO_ROOT}/backend/.venv (preferred, local worktree)
    2. /home/wenlongren/repo/YiLuAn/backend/.venv (fallback for shared workspaces)
    3. /repo/YiLuAn/backend/.venv (CI/container fallback)
    """
    candidates = [
        BACKEND / ".venv" / "bin" / "python",
        Path("/home/wenlongren/repo/YiLuAn/backend/.venv/bin/python"),
        Path("/repo/YiLuAn/backend/.venv/bin/python"),
    ]
    for venv_python in candidates:
        if venv_python.exists():
            return str(venv_python)
    return None


@pytest.fixture
def fastapi_python() -> str:
    """Skip test if no python with fastapi."""
    backend_python = _backend_venv_python()
    if not backend_python:
        pytest.skip("backend/.venv not installed, hook integration test skipped")
    # verify fastapi import works
    check = subprocess.run(
        [backend_python, "-c", "import fastapi"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if check.returncode != 0:
        pytest.skip(f"backend/.venv python cannot import fastapi: {check.stderr}")
    return backend_python


def test_hook_skips_when_no_fastapi(tmp_path: Path):
    """Hook 应 graceful skip 当 fastapi 不可 import (与 alembic_check_hook 同模式)."""
    # 用 system python (大概率无 fastapi) 跑
    code, out, err = _run_hook(env_python="/usr/bin/python3")
    # 期望 exit 0 (skip) 而非 fail
    assert code == 0, f"Hook should skip when fastapi missing, got exit {code}: {err}"
    # 期望 skip message 在 stderr
    assert "fastapi not importable" in err or "skipping" in err, f"Expected skip message, got: {err}"


def test_hook_case_a_clean_state_passes(fastapi_python: str):
    """Case A: docs/api/ 与 backend code 同步 → hook PASS exit 0.

    前置: main HEAD 状态 (PR merge 时 docs/api/ regenerate 完毕).
    """
    code, out, err = _run_hook(env_python=fastapi_python)
    # 期望 exit 0 (pass)
    assert code == 0, f"Hook should PASS on clean main HEAD, got exit {code}:\nstdout: {out}\nstderr: {err}"
    # 期望成功 message
    assert "无 drift" in out or "in sync" in out, f"Expected success message, got: {out}"


def test_hook_case_b_blocks_drift(fastapi_python: str, tmp_path: Path):
    """Case B: 故意 modify backend docstring 而不 regen docs/api/ → hook BLOCK exit 1.

    模拟流程:
    1. 备份 prep_packages.py
    2. modify docstring (e.g. add '(test drift)' suffix)
    3. 跑 hook (它会 regen docs/api/ + 比较 vs HEAD)
    4. 期望 hook return 1 因 docs/api/ 现在与 HEAD diff
    5. 还原 prep_packages.py + 重新 regen docs/api/ 复原干净

    NOTE: hook 实装会 modify docs/api/ in-place (跑 dump_openapi.py 写盘), 然后 git diff
    检测. 所以 case B 后 docs/api/ 会 dirty, 测试 teardown 还原.
    """
    backend_file = BACKEND / "app" / "api" / "v1" / "admin" / "prep_packages.py"
    docs_openapi = REPO_ROOT / "docs" / "api" / "openapi.json"
    docs_admin = REPO_ROOT / "docs" / "api" / "admin.md"
    docs_admin_prep = REPO_ROOT / "docs" / "api" / "admin-prep-package.md"

    # 备份原 file 内容
    original_backend = backend_file.read_text(encoding="utf-8")
    original_openapi = docs_openapi.read_text(encoding="utf-8")
    original_admin = docs_admin.read_text(encoding="utf-8")
    original_admin_prep = docs_admin_prep.read_text(encoding="utf-8")

    try:
        # modify backend file docstring
        modified = original_backend.replace(
            "admin 侦察行为",
            "admin 侦察行为 (test_drift_marker)",
            1,  # 只替换第一处
        )
        assert modified != original_backend, "Modification not applied"
        backend_file.write_text(modified, encoding="utf-8")

        # 跑 hook (它会 regen docs/api/ 并比 HEAD)
        code, out, err = _run_hook(env_python=fastapi_python)
        # 期望 exit 1 (block, drift detected)
        # NOTE: hook 实装跑 dump_openapi.py 后 working tree docs/api/ = 新版,
        # HEAD = 旧版, git diff exit 1 → hook return 1
        assert code == 1, (
            f"Hook should BLOCK when backend modified but docs/api/ stale.\n"
            f"Got exit {code}\n"
            f"stdout: {out}\nstderr: {err}"
        )
        assert "drift detected" in err or "drift" in err.lower(), (
            f"Expected drift error message, got: {err}"
        )
    finally:
        # 还原 backend file
        backend_file.write_text(original_backend, encoding="utf-8")
        # 还原 docs/api/ (hook 跑过会 modify in-place)
        docs_openapi.write_text(original_openapi, encoding="utf-8")
        docs_admin.write_text(original_admin, encoding="utf-8")
        docs_admin_prep.write_text(original_admin_prep, encoding="utf-8")
