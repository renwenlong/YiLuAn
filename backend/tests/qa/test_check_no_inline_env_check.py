"""S3-OPS-STARTUP-PROBE-FRAMEWORK AC#8 lint sentinel test.

Verify ``backend/scripts/qa/check_no_inline_env_check.py``:
  - 当前 ``backend/app/`` 状态 (post-PR1 收编后) 通过 lint (exit 0)
  - 故意构造命中 pattern 的临时文件 → lint 必报错 + 列位置 (exit 1)
  - 故意把命中文件加进 ALLOWLIST_PATHS → lint 必放过 (exit 0)
  - allowlist 配置正确不漏 (probes/, startup_probes.py, etc.)
  - dev-only pattern (``env == "development"``) 不被误报

sentinel: ``SECRET_LINT_NO_INLINE_ENV_CHECK_TEST_42_DO_NOT_LEAK`` 防误删本测试.

Refs:
  - 反案 #25 (ADR-0051 r3 §2.3): 协议层禁止散点 env check
  - PR #306 (S3-OPS-STARTUP-PROBE-FRAMEWORK PR1): @register_startup_probe 落
  - AC#8 lint 哨兵 (本 PR2)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# sentinel — 反案 #15
_SECRET_LINT_TEST = "SECRET_LINT_NO_INLINE_ENV_CHECK_TEST_42_DO_NOT_LEAK"

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_SCRIPT = REPO_ROOT / "backend" / "scripts" / "qa" / "check_no_inline_env_check.py"
BACKEND_APP = REPO_ROOT / "backend" / "app"


def _run_lint() -> subprocess.CompletedProcess[str]:
    """Run the lint script and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(LINT_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )


class TestLintScriptExists:
    """AC#8 #1: lint 脚本存在 + 可执行."""

    def test_lint_script_file_exists(self):
        """Lint script must exist at backend/scripts/qa/check_no_inline_env_check.py."""
        assert (
            LINT_SCRIPT.is_file()
        ), f"lint script 缺失: {LINT_SCRIPT}. sentinel: {_SECRET_LINT_TEST}"

    def test_lint_script_has_sentinel_string(self):
        """Lint script 必含 sentinel string 防误删 (反案 #15)."""
        text = LINT_SCRIPT.read_text(encoding="utf-8")
        assert (
            "SECRET_LINT_NO_INLINE_ENV_CHECK_42_DO_NOT_LEAK" in text
        ), f"lint script 缺 sentinel string. sentinel: {_SECRET_LINT_TEST}"


class TestLintScriptCurrentState:
    """AC#8 #2: 当前 backend/app/ 状态通过 lint (post-PR1 收编后)."""

    def test_current_backend_app_passes_lint(self):
        """Post-PR1 (PR #306) 收编后 backend/app/ 应 lint clean.

        若本测试 fail = 有新加 inline env check 散点, 必走
        @register_startup_probe 收编 (PR #306 框架).
        """
        result = _run_lint()
        assert result.returncode == 0, (
            f"current backend/app/ lint FAIL (exit={result.returncode}). "
            f"必走 @register_startup_probe 收编新加散点. "
            f"stdout: {result.stdout!r}, stderr: {result.stderr!r}. "
            f"sentinel: {_SECRET_LINT_TEST}"
        )
        assert "[lint:ok]" in result.stdout, f"lint ok 信号缺失. stdout: {result.stdout!r}"


class TestLintCatchesViolations:
    """AC#8 #3: lint 必能 catch 故意构造的违例 pattern."""

    @pytest.fixture
    def temp_violation_file(self, tmp_path, monkeypatch):
        """Create a fake violation file under backend/app/ temporarily."""
        # 不污染真 backend/app/, 用临时文件 + monkey patch BACKEND_APP
        # 但 lint 是 subprocess 跑, 不能 monkeypatch — 改用真 backend/app/
        # 临时加 .py 文件 + cleanup.
        fake_file = BACKEND_APP / "_test_violation_sentinel.py"
        violations_content = (
            '"""Temp violation file for lint test."""\n'
            "from app.config import settings\n"
            "\n"
            "def check_prod_only():\n"
            '    if settings.environment == "production":\n'
            "        return True\n"
            "    return False\n"
            "\n"
            "# sentinel: SECRET_LINT_NO_INLINE_ENV_CHECK_TEST_42_DO_NOT_LEAK\n"
        )
        fake_file.write_text(violations_content, encoding="utf-8")
        yield fake_file
        # cleanup
        if fake_file.exists():
            fake_file.unlink()

    def test_lint_catches_settings_env_eq_production(self, temp_violation_file):
        """``if settings.environment == "production"`` 必被 catch."""
        result = _run_lint()
        assert result.returncode == 1, (
            f"lint 未 catch settings.environment == 'production' 违例. "
            f"exit={result.returncode}, stdout: {result.stdout!r}, "
            f"stderr: {result.stderr!r}. sentinel: {_SECRET_LINT_TEST}"
        )
        # 必须在 stderr 报出违例文件
        assert (
            "_test_violation_sentinel.py" in result.stderr
        ), f"lint 未报违例文件. stderr: {result.stderr!r}"
        # 必须报具体行号
        assert (
            "L5:" in result.stderr or "L4:" in result.stderr
        ), f"lint 未报行号. stderr: {result.stderr!r}"

    @pytest.fixture
    def temp_in_set_violation(self, tmp_path):
        """Create file with ``env in {production,canary}`` pattern."""
        fake_file = BACKEND_APP / "_test_in_set_violation.py"
        violations_content = (
            '"""Temp violation file: env in {...} pattern."""\n'
            "from app.config import settings\n"
            "\n"
            "def is_prod_like():\n"
            '    if settings.environment in {"production", "canary", "staging"}:\n'
            "        return True\n"
            "    return False\n"
            "\n"
            "# sentinel: SECRET_LINT_NO_INLINE_ENV_CHECK_TEST_42_DO_NOT_LEAK\n"
        )
        fake_file.write_text(violations_content, encoding="utf-8")
        yield fake_file
        if fake_file.exists():
            fake_file.unlink()

    def test_lint_catches_env_in_set_pattern(self, temp_in_set_violation):
        """``settings.environment in {"production","canary","staging"}`` 必被 catch."""
        result = _run_lint()
        assert result.returncode == 1, (
            f"lint 未 catch 'env in {{...}}' 违例. exit={result.returncode}. "
            f"sentinel: {_SECRET_LINT_TEST}"
        )
        assert (
            "_test_in_set_violation.py" in result.stderr
        ), f"lint 未报违例文件 (set pattern). stderr: {result.stderr!r}"


class TestLintAllowlistRespected:
    """AC#8 #4: allowlist 路径不被报 (合法 env check 不误伤)."""

    def test_allowlist_includes_probes_module(self):
        """probes/__init__.py 含 envs=... tuple 必须在 allowlist."""
        text = LINT_SCRIPT.read_text(encoding="utf-8")
        assert (
            '"probes/__init__.py"' in text
        ), f"allowlist 漏 probes/__init__.py. sentinel: {_SECRET_LINT_TEST}"

    def test_allowlist_includes_startup_probes(self):
        """startup_probes.py 框架自身必须在 allowlist."""
        text = LINT_SCRIPT.read_text(encoding="utf-8")
        assert (
            '"startup_probes.py"' in text
        ), f"allowlist 漏 startup_probes.py. sentinel: {_SECRET_LINT_TEST}"

    def test_allowlist_includes_mock_sms(self):
        """Mock SMS provider 是 dev-only, 必须在 allowlist."""
        text = LINT_SCRIPT.read_text(encoding="utf-8")
        assert (
            '"services/providers/sms/mock.py"' in text
        ), f"allowlist 漏 mock SMS provider. sentinel: {_SECRET_LINT_TEST}"


class TestLintDevelopmentPatternFlagged:
    """development env checks are no longer allowed in runtime code."""

    @pytest.fixture
    def temp_dev_only_file(self):
        """File with ``if env == "development"`` (legacy shortcut)."""
        fake_file = BACKEND_APP / "_test_dev_only_legacy.py"
        content = (
            '"""Temp legacy env file — should be flagged."""\n'
            "from app.config import settings\n"
            "\n"
            "def print_legacy_warning():\n"
            '    if settings.environment == "development":\n'
            '        print("legacy mode")\n'
            "\n"
            "# sentinel: SECRET_LINT_NO_INLINE_ENV_CHECK_TEST_42_DO_NOT_LEAK\n"
        )
        fake_file.write_text(content, encoding="utf-8")
        yield fake_file
        if fake_file.exists():
            fake_file.unlink()

    def test_development_check_flagged(self, temp_dev_only_file):
        """``if env == "development"`` must be caught after staging-only pivot."""
        result = _run_lint()
        assert result.returncode != 0, (
            f"lint 未 catch legacy 'env == development' 检查. "
            f"sentinel: {_SECRET_LINT_TEST}"
        )
        assert "development" in result.stderr


class TestLintCommentsLinesIgnored:
    """AC#8 #6: 注释 / docstring 内 cite pattern 不被误报."""

    @pytest.fixture
    def temp_comment_only_file(self):
        """File with prohibited pattern only in comments — should NOT be flagged."""
        fake_file = BACKEND_APP / "_test_comment_only.py"
        content = (
            '"""Temp file — pattern only in comments / docstring."""\n'
            '# 反案 #25 example: if settings.environment == "production":\n'
            "# 上面这行 是 comment, 不是真 code, lint 必须放过.\n"
            "\n"
            "def real_code():\n"
            "    return True\n"
            "\n"
            "# sentinel: SECRET_LINT_NO_INLINE_ENV_CHECK_TEST_42_DO_NOT_LEAK\n"
        )
        fake_file.write_text(content, encoding="utf-8")
        yield fake_file
        if fake_file.exists():
            fake_file.unlink()

    def test_pattern_in_comments_not_flagged(self, temp_comment_only_file):
        """Comments / docstring 中 cite pattern 不被 lint catch."""
        result = _run_lint()
        assert result.returncode == 0, (
            f"lint 误报 comment 内 cite pattern — comments 不是真 code, "
            f"不应 catch. exit={result.returncode}, stderr: {result.stderr!r}. "
            f"sentinel: {_SECRET_LINT_TEST}"
        )
