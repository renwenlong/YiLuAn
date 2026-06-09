"""Tests for app.services.prompt_versioning.git_blame.

ADR-0048 §5.2 + S3-DEV-002-PROMPT-VERSIONING AC#4:
- subprocess fallback paths
- commit_sha 格式提取
- git 不存在 / path 未追踪 / 非零退出 / timeout / 输出污染 各失败分支
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.prompt_versioning.git_blame import (
    COMMIT_SHA_RE,
    GitBlameError,
    git_blame_commit,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_completed(returncode: int, stdout: str = "", stderr: str = ""):
    """Build subprocess.CompletedProcess for mocking subprocess.run."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# COMMIT_SHA_RE 形态测试
# ---------------------------------------------------------------------------


class TestCommitShaRegex:
    """SHA-1 校验正则 — 防止 git 输出被劫持/编码污染。"""

    def test_valid_40_lowercase_hex(self):
        assert COMMIT_SHA_RE.match("9f9c84b3d2e10000000000000000000000000abc")

    def test_reject_39_chars_too_short(self):
        assert not COMMIT_SHA_RE.match("9f9c84b3d2e1000000000000000000000000abc")

    def test_reject_41_chars_too_long(self):
        assert not COMMIT_SHA_RE.match(
            "9f9c84b3d2e10000000000000000000000000abc1"
        )

    def test_reject_uppercase(self):
        # git log %H 只输出小写, 大写视为污染
        assert not COMMIT_SHA_RE.match(
            "9F9C84B3D2E10000000000000000000000000ABC"
        )

    def test_reject_non_hex_char(self):
        assert not COMMIT_SHA_RE.match(
            "9f9c84b3d2e100000000000000000000000000Xg"
        )

    def test_reject_empty(self):
        assert not COMMIT_SHA_RE.match("")


# ---------------------------------------------------------------------------
# git_blame_commit happy path
# ---------------------------------------------------------------------------


class TestGitBlameCommitSuccess:
    """正常 commit SHA 提取路径。"""

    def test_returns_clean_40_hex_sha(self, tmp_path: Path):
        sha = "abc1234567890abcdef1234567890abcdef12345"
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            return_value=_make_completed(0, stdout=sha + "\n"),
        ):
            result = git_blame_commit(tmp_path / "fake.md")
        assert result == sha

    def test_strips_trailing_whitespace(self, tmp_path: Path):
        sha = "0123456789abcdef0123456789abcdef01234567"
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            return_value=_make_completed(0, stdout=f"  {sha}  \n\n"),
        ):
            result = git_blame_commit(tmp_path / "x.md")
        assert result == sha

    def test_respects_explicit_repo_root(self, tmp_path: Path):
        """Verify subprocess cwd uses repo_root override, not path.parent."""
        sha = "fedcba9876543210fedcba9876543210fedcba98"
        captured: dict = {}

        def fake_run(cmd, cwd, **kw):  # noqa: D401
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            return _make_completed(0, stdout=sha)

        repo_root = tmp_path / "repo-root"
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            side_effect=fake_run,
        ):
            git_blame_commit(
                "docs/foo.md", repo_root=repo_root, git_bin="/opt/bin/git"
            )
        assert captured["cwd"] == str(repo_root)
        assert captured["cmd"][0] == "/opt/bin/git"
        assert "docs/foo.md" in captured["cmd"]


# ---------------------------------------------------------------------------
# subprocess fallback / error paths (AC#4 主要覆盖点)
# ---------------------------------------------------------------------------


class TestGitBlameCommitErrors:
    """各 fallback 分支 — git 缺失 / timeout / 非零退出 / 输出污染。"""

    def test_raises_when_git_binary_missing(self, tmp_path: Path):
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value=None,
        ):
            with pytest.raises(GitBlameError, match="git 二进制找不到"):
                git_blame_commit(tmp_path / "x.md")

    def test_raises_when_git_binary_unexecutable(self, tmp_path: Path):
        # subprocess.run 直接抛 FileNotFoundError = 路径解析时 git_bin 失效
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            side_effect=FileNotFoundError("[Errno 2] No such file"),
        ):
            with pytest.raises(GitBlameError, match="git 二进制不可执行"):
                git_blame_commit(tmp_path / "x.md")

    def test_raises_on_timeout(self, tmp_path: Path):
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=5),
        ):
            with pytest.raises(GitBlameError, match="timeout"):
                git_blame_commit(tmp_path / "x.md")

    def test_raises_on_nonzero_exit(self, tmp_path: Path):
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            return_value=_make_completed(
                128, stderr="fatal: not a git repository"
            ),
        ):
            with pytest.raises(GitBlameError) as exc_info:
                git_blame_commit(tmp_path / "x.md")
        assert "rc=128" in str(exc_info.value)
        assert "not a git repository" in str(exc_info.value)

    def test_raises_when_path_untracked_empty_stdout(self, tmp_path: Path):
        # git log 0 returncode but empty stdout = path 未被 git 追踪
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            return_value=_make_completed(0, stdout=""),
        ):
            with pytest.raises(GitBlameError, match="未被 git 追踪"):
                git_blame_commit(tmp_path / "never_committed.md")

    def test_raises_on_polluted_output_not_40_hex(self, tmp_path: Path):
        # 防御: 输出不是合法 40-hex (注入 / 编码污染场景)
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            return_value=_make_completed(
                0, stdout="not-a-sha-just-garbage-here\n"
            ),
        ):
            with pytest.raises(GitBlameError, match="非 40-hex SHA"):
                git_blame_commit(tmp_path / "x.md")

    def test_raises_on_uppercase_sha_pollution(self, tmp_path: Path):
        # git 永远 lowercase, 大写视为格式污染
        with patch(
            "app.services.prompt_versioning.git_blame.shutil.which",
            return_value="/usr/bin/git",
        ), patch(
            "app.services.prompt_versioning.git_blame.subprocess.run",
            return_value=_make_completed(
                0,
                stdout="ABC1234567890ABCDEF1234567890ABCDEF12345\n",
            ),
        ):
            with pytest.raises(GitBlameError, match="非 40-hex SHA"):
                git_blame_commit(tmp_path / "x.md")


# ---------------------------------------------------------------------------
# real git integration smoke (本仓库自己跑 git log)
# ---------------------------------------------------------------------------


class TestRealGitIntegration:
    """Real subprocess + real git — 不 mock, 跑本仓库自己。

    确保在 CI runner (装了 git) 中 happy path 真能 work, 避免 mock
    层假阳过强而漏 subprocess API 飘移。
    """

    def test_blame_self_file_returns_real_sha(self):
        # 本测试文件自己肯定被 git 追踪 (它存在于 git 里我们才能跑它)
        repo_root = Path(__file__).resolve()
        # walk up 找 backend/ 上一级 = repo root
        for parent in repo_root.parents:
            if (parent / ".git").exists():
                repo_root = parent
                break
        else:  # pragma: no cover — 在 git checkout 内必然找到
            pytest.skip("not in a git checkout")

        # Use a file definitely tracked: this test file itself.
        rel_path = Path(__file__).resolve().relative_to(repo_root)
        try:
            sha = git_blame_commit(rel_path, repo_root=repo_root)
        except GitBlameError as exc:
            # 文件可能是当前 uncommitted (本 PR 内新增) — 这种情况预期
            assert "未被 git 追踪" in str(exc)
            pytest.skip(f"file not yet committed: {exc}")

        assert COMMIT_SHA_RE.match(sha), f"Got non-SHA: {sha!r}"
