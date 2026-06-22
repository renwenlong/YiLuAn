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
        ["bash", "-c", script],
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


# ── S3-OPS-PREPUSH-HOOK-WHITELIST-REFINE / 反案 #46 双向精确化 ──────────────
# gap 1: tests/*.md 漏豁免(纯测试报告被迫走 marker gate)→ 加 tests/.*\.md$ 白名单
# gap 2: docs/ai-prompts/ 误豁免(^docs/ 太宽,prompt 改动静默放行)→ 前置拦截


def test_tests_markdown_report_skips_marker_gate():
    """AC#1: 纯 tests/*.md(测试报告)走 doc-only 短路,不跑 marker gate。"""
    code, out, err = _decision(
        "tests/canary-mock-drill-test-report.md",
        "tests/test-report-s3-test-003-precheck-cross-replica.md",
    )

    assert code == 10
    assert "skip: doc-only diff" in out
    assert err == ""


def test_tests_python_code_falls_through_to_marker_gate():
    """AC#2: tests/*.py(测试代码)仍 fallthrough 跑 marker gate,不被 .md 豁免误放。"""
    code, out, _ = _decision("tests/scripts/test_pre_push_hook.py")

    assert code == 0
    assert "run: non-allowlisted diff" in out
    assert "tests/scripts/test_pre_push_hook.py" in out


def test_ai_prompt_diff_runs_marker_gate():
    """AC#3: docs/ai-prompts/**/system_prompt.md(AI prompt 内容)fallthrough 跑 marker
    gate — prompt = AI 行为,不可静默短路(startup_validator.py:87 运行时加载)。"""
    code, out, _ = _decision("docs/ai-prompts/s3-prep/v1.0.0/system_prompt.md")

    assert code == 0
    assert "run: AI prompt diff (docs/ai-prompts)" in out


def test_ordinary_docs_still_skip_marker_gate():
    """AC#4: docs/ 下非 ai-prompts 文档(qa/ops/adr)仍走 doc-only 短路,不受影响。"""
    code, out, err = _decision("docs/qa/report.md", "docs/ops/runbook.md", "docs/adr/ADR-0056.md")

    assert code == 10
    assert "skip: doc-only diff" in out
    assert err == ""


def test_docs_plus_backend_mixed_runs_marker_gate():
    """AC#5 case(e): 非白名单 diff(docs/qa + backend/*.py)混合 fallthrough 跑 marker gate。"""
    code, out, _ = _decision("docs/qa/report.md", "backend/app/services/x.py")

    assert code == 0
    assert "run: backend diff" in out
