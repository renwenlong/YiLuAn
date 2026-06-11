#!/usr/bin/env python
"""pre-commit hook: 防 OpenAPI schema/admin doc drift。

触发条件 (`files` regex 在 .pre-commit-config.yaml 中):
  - backend/app/api/v1/admin/*.py (admin endpoint 改动)
  - backend/app/schemas/*.py (schema 改动)
  - backend/app/api/v1/*.py (任 v1 endpoint 改动)

行为:
  1. 重新生成 docs/api/openapi.json (跑 backend/scripts/dump_openapi.py)
  2. 重新生成 docs/api/admin*.md + docs/api/*.md (跑 backend/scripts/build_api_md.py)
  3. `git diff --exit-code` 检查 docs/api/ 有无未 commit 的改动
  4. 若有 diff → block + 提示

若 fastapi/python 环境不可达 (例 host 无 fastapi 模块) → 警告 + skip (与 alembic_check_hook
同模式)，CI 的 api-docs-check workflow 兜底强制检查。

反案 #15 (workspace-xiao MEMORY.md):
  PR #277 fail api-docs-check 触发本 task。改 endpoint description 时忘 regenerate
  openapi.json + admin docs md, 凝光 帮 fix (commit 5c9a450)。pre-commit hook 必须本地拦截。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
DOCS_API = REPO_ROOT / "docs" / "api"


def _python_with_fastapi() -> bool:
    """检测当前 python 是否能 import fastapi (host vs container 区别)。"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import fastapi"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    return result.returncode, result.stdout, result.stderr


def _git_diff_dirty(paths: list[str]) -> tuple[bool, str]:
    """check `git diff --exit-code` 在 paths 上, 返回 (有 diff?, 输出)。"""
    rel = [str(Path(p).relative_to(REPO_ROOT)) for p in paths]
    result = subprocess.run(
        ["git", "diff", "--exit-code", "--", *rel],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    # exit 0 = no diff, exit 1 = has diff
    return result.returncode != 0, result.stdout


def main() -> int:
    if not _python_with_fastapi():
        sys.stderr.write(
            "[openapi-drift hook] fastapi not importable in current python — skipping.\n"
            "  Install: cd backend && pip install -e .\n"
            "  Or rely on CI: .github/workflows/api-docs-check.yml will enforce drift check.\n"
        )
        return 0

    # 1. dump_openapi.py
    sys.stdout.write("[openapi-drift hook] regenerating openapi.json...\n")
    code, out, err = _run([sys.executable, "scripts/dump_openapi.py"], cwd=BACKEND)
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != 0:
        sys.stderr.write("[openapi-drift hook] dump_openapi.py failed.\n")
        return code

    # 2. build_api_md.py
    sys.stdout.write("[openapi-drift hook] regenerating admin*.md...\n")
    code, out, err = _run([sys.executable, "scripts/build_api_md.py"], cwd=BACKEND)
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != 0:
        sys.stderr.write("[openapi-drift hook] build_api_md.py failed.\n")
        return code

    # 3. git diff --exit-code on docs/api/
    dirty, diff_out = _git_diff_dirty([str(DOCS_API)])
    if dirty:
        sys.stderr.write(
            "\n[openapi-drift hook] ❌ OpenAPI/admin docs drift detected.\n"
            "  Endpoint/schema 改动未同步 OpenAPI 文档。\n"
            "  修复:\n"
            "    cd backend && python scripts/dump_openapi.py && python scripts/build_api_md.py\n"
            "    git add docs/api/\n"
            "    git commit --amend --no-edit  # 或新 commit\n"
            "\n  反案 #15: pre-commit hook 本地拦, CI api-docs-check 也会拦, 但本地修最快。\n"
        )
        return 1

    sys.stdout.write("[openapi-drift hook] ✅ docs/api/ 与 endpoint/schema 一致, 无 drift。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
