"""Unit tests for .githooks/pre-push diff marker-gate decision.

S3-OPS-PREPUSH-HOOK-DOCONLY-SHORTCIRCUIT / 反案 #46:
纯 docs diff 不应因 backend/.venv 缺失被 marker gate 卡住；但必须用 allowlist，
避免 Makefile / CI / frontend / backend 等风险 diff 被 silent skip。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".githooks" / "pre-push"


def _decision(*files: str) -> tuple[int, str, str]:
    diff = "\n".join(files)
    script = f"""
set -euo pipefail
export PRE_PUSH_UNIT_TESTING=1
source {HOOK}
if pre_push_diff_requires_marker_gate $'{diff}'; then
  exit 0
else
  exit 10
fi
"""
    result = subprocess.run(
        ["bash", "-lc", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def test_doc_only_diff_skips_marker_gate():
    code, out, err = _decision("docs/adr/ADR-0055.md", "README.md")

    assert code == 10
    assert "skip: doc-only diff" in out
    assert err == ""


def test_docs_plus_backend_runs_marker_gate():
    code, out, _ = _decision("docs/ops/runbook.md", "backend/app/config.py")

    assert code == 0
    assert "run: backend diff" in out


def test_docs_plus_ci_workflow_runs_marker_gate():
    code, out, _ = _decision("docs/ops/runbook.md", ".github/workflows/test.yml")

    assert code == 0
    assert "run: CI workflow / QA script diff" in out


def test_makefile_diff_falls_through_to_marker_gate():
    code, out, _ = _decision("Makefile")

    assert code == 0
    assert "run: non-allowlisted diff" in out
    assert "Makefile" in out


def test_frontend_diff_runs_marker_gate():
    code, out, _ = _decision("wechat/pages/order/index.js", "admin-v2/src/App.tsx")

    assert code == 0
    assert "run: frontend / client diff" in out
