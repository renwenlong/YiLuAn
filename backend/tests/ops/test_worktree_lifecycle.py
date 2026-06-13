"""Tests for scripts/ops/worktree_lifecycle.py (S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP).

12 sentinel tests covering AC#1, #2, #6, #7 (script behaviour + 6 safety
gates). Uses pytest tmp_path + monkeypatch to mock git/gh subprocess
calls. No real git operations; tests do not require gh CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ops/ importable
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_OPS = _REPO_ROOT / "scripts" / "ops"
sys.path.insert(0, str(_SCRIPTS_OPS))

import worktree_lifecycle as wl  # noqa: E402

# ---------------------------------------------------------------------------
# AC#1 — parse_worktree_list_porcelain
# ---------------------------------------------------------------------------


def test_ac1_parse_porcelain_returns_branch_path_head():
    porcelain = (
        "worktree /home/u/repo\n"
        "HEAD abc1234567890123456789012345678901234567\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /home/u/repo-feat\n"
        "HEAD def1234567890123456789012345678901234567\n"
        "branch refs/heads/feature/x\n"
    )
    result = wl.parse_worktree_list_porcelain(porcelain)
    assert len(result) == 2
    assert result[0].path == "/home/u/repo"
    assert result[0].branch == "main"
    assert result[0].head == "abc1234567890123456789012345678901234567"
    assert result[1].branch == "feature/x"


def test_ac1_parse_porcelain_handles_detached_head():
    porcelain = (
        "worktree /home/u/repo-d\n" "HEAD ghi1234567890123456789012345678901234567\n" "detached\n"
    )
    result = wl.parse_worktree_list_porcelain(porcelain)
    assert len(result) == 1
    assert result[0].detached is True
    assert result[0].branch == "HEAD"


def test_ac1_parse_porcelain_handles_bare_repo():
    porcelain = "worktree /home/u/bare\nHEAD 0000000\nbare\n"
    result = wl.parse_worktree_list_porcelain(porcelain)
    assert len(result) == 1
    assert result[0].bare is True


# ---------------------------------------------------------------------------
# AC#1 + #6 — classify_worktree (mock gh + git)
# ---------------------------------------------------------------------------


def test_ac1_classify_stale_when_merged_pr_and_head_in_origin_main(monkeypatch):
    wt = wl.WorktreeInfo(path="/home/u/repo-feat", branch="feature/x", head="abc123")

    def fake_pr_list(branch, state="merged", cwd=None):
        if state == "open":
            return []
        return [{"number": 42, "url": "https://gh.com/o/r/pull/42", "state": "MERGED"}]

    monkeypatch.setattr(wl, "gh_pr_list_for_branch", fake_pr_list)
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)

    cw = wl.classify_worktree(wt, excluded_paths=[])
    assert cw.category == "stale"
    assert cw.pr_number == 42


def test_ac1_classify_active_when_open_pr_exists(monkeypatch):
    wt = wl.WorktreeInfo(path="/home/u/repo-feat", branch="feature/x", head="abc123")

    def fake_pr_list(branch, state="merged", cwd=None):
        if state == "open":
            return [{"number": 99, "url": "https://gh.com/o/r/pull/99"}]
        return []

    monkeypatch.setattr(wl, "gh_pr_list_for_branch", fake_pr_list)
    cw = wl.classify_worktree(wt, excluded_paths=[])
    assert cw.category == "active"
    assert cw.pr_number == 99


def test_ac1_classify_orphan_when_no_pr_found(monkeypatch):
    wt = wl.WorktreeInfo(path="/home/u/repo-feat", branch="feature/x", head="abc123")
    monkeypatch.setattr(wl, "gh_pr_list_for_branch", lambda *a, **k: [])
    cw = wl.classify_worktree(wt, excluded_paths=[])
    assert cw.category == "orphan"


def test_ac1_classify_protected_when_excluded_path(monkeypatch, tmp_path):
    excluded = tmp_path / "main-worktree"
    excluded.mkdir()
    wt = wl.WorktreeInfo(path=str(excluded), branch="main", head="abc123")
    # Even main branch in excluded paths is correctly protected
    cw = wl.classify_worktree(wt, excluded_paths=[str(excluded)])
    assert cw.category == "protected"
    assert "excluded-path" in cw.reason


def test_ac1_classify_protected_when_detached_head(monkeypatch):
    wt = wl.WorktreeInfo(path="/home/u/repo-d", branch="HEAD", head="abc123", detached=True)
    cw = wl.classify_worktree(wt, excluded_paths=[])
    assert cw.category == "protected"
    assert "detached" in cw.reason


# ---------------------------------------------------------------------------
# AC#6 — 6 safety gates (skip removal even if classified stale)
# ---------------------------------------------------------------------------


def test_ac6_safety_gate_uncommitted_changes(monkeypatch):
    cw = wl.ClassifiedWorktree(
        worktree=wl.WorktreeInfo(
            path="/home/u/repo-feat",
            branch="feature/x",
            head="abc",
        ),
        category="stale",
        reason="merged",
    )
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: True)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: [])
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    reasons = wl.check_safety_gates(cw, excluded_paths=[])
    assert any("uncommitted" in r for r in reasons)


def test_ac6_safety_gate_stash_entries(monkeypatch):
    cw = wl.ClassifiedWorktree(
        worktree=wl.WorktreeInfo(path="/home/u/repo-feat", branch="feature/x", head="abc"),
        category="stale",
        reason="merged",
    )
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: False)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: ["stash@{0}: WIP"])
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    reasons = wl.check_safety_gates(cw, excluded_paths=[])
    assert any("stash" in r for r in reasons)


def test_ac6_safety_gate_forbidden_branch_main(monkeypatch):
    cw = wl.ClassifiedWorktree(
        worktree=wl.WorktreeInfo(path="/home/u/repo", branch="main", head="abc"),
        category="stale",
        reason="merged",
    )
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: False)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: [])
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    reasons = wl.check_safety_gates(cw, excluded_paths=[])
    assert any("forbidden list" in r for r in reasons)


def test_ac6_safety_gate_head_not_in_origin_main(monkeypatch):
    cw = wl.ClassifiedWorktree(
        worktree=wl.WorktreeInfo(path="/home/u/repo-feat", branch="feature/x", head="abc123"),
        category="stale",
        reason="merged",
    )
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: False)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: [])
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: False)
    reasons = wl.check_safety_gates(cw, excluded_paths=[])
    assert any("not in origin/main" in r for r in reasons)


# ---------------------------------------------------------------------------
# AC#2 — dry-run vs --apply
# ---------------------------------------------------------------------------


def test_ac2_dry_run_does_not_call_worktree_remove(monkeypatch):
    """dry-run scans but does NOT call git worktree remove."""
    porcelain = (
        "worktree /home/u/main\n"
        "HEAD abc\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /home/u/feat\n"
        "HEAD def\n"
        "branch refs/heads/feature/x\n"
    )
    monkeypatch.setattr(wl, "git_worktree_list_porcelain", lambda cwd=None: porcelain)

    def fake_pr_list(branch, state="merged", cwd=None):
        if state == "open":
            return []
        return [{"number": 1, "url": "u", "state": "MERGED"}]

    monkeypatch.setattr(wl, "gh_pr_list_for_branch", fake_pr_list)
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    remove_called = []
    monkeypatch.setattr(
        wl,
        "git_worktree_remove",
        lambda path, cwd=None: remove_called.append(path),
    )

    report = wl.run(dry_run=True, apply=False, excluded_paths=["/home/u/main"])
    assert report.removed == []
    assert remove_called == []
    assert len(report.stale) == 1  # feat classified as stale (dry)


def test_ac2_apply_invokes_worktree_remove(monkeypatch):
    """--apply triggers actual git worktree remove for stale items."""
    porcelain = (
        "worktree /home/u/main\n"
        "HEAD abc\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /home/u/feat\n"
        "HEAD def\n"
        "branch refs/heads/feature/x\n"
    )
    monkeypatch.setattr(wl, "git_worktree_list_porcelain", lambda cwd=None: porcelain)

    def fake_pr_list(branch, state="merged", cwd=None):
        if state == "open":
            return []
        return [{"number": 1, "url": "u", "state": "MERGED"}]

    monkeypatch.setattr(wl, "gh_pr_list_for_branch", fake_pr_list)
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: False)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: [])
    remove_called = []
    monkeypatch.setattr(
        wl,
        "git_worktree_remove",
        lambda path, cwd=None: remove_called.append(path),
    )

    report = wl.run(dry_run=False, apply=True, excluded_paths=["/home/u/main"])
    assert remove_called == ["/home/u/feat"]
    assert report.removed == ["/home/u/feat"]


def test_ac2_apply_skips_orphan_unless_include_orphan(monkeypatch):
    """--apply alone does NOT delete orphan; --include-orphan does."""
    porcelain = (
        "worktree /home/u/main\n"
        "HEAD abc\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /home/u/orphan-feat\n"
        "HEAD def\n"
        "branch refs/heads/feature/orphan\n"
    )
    monkeypatch.setattr(wl, "git_worktree_list_porcelain", lambda cwd=None: porcelain)
    monkeypatch.setattr(wl, "gh_pr_list_for_branch", lambda *a, **k: [])
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: False)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: [])
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    remove_called = []
    monkeypatch.setattr(
        wl,
        "git_worktree_remove",
        lambda path, cwd=None: remove_called.append(path),
    )

    # Without --include-orphan
    report = wl.run(
        dry_run=False,
        apply=True,
        include_orphan=False,
        excluded_paths=["/home/u/main"],
    )
    assert remove_called == []
    assert len(report.orphan) == 1

    # Now with --include-orphan
    remove_called.clear()
    report = wl.run(
        dry_run=False,
        apply=True,
        include_orphan=True,
        excluded_paths=["/home/u/main"],
    )
    assert remove_called == ["/home/u/orphan-feat"]


# ---------------------------------------------------------------------------
# AC#7 — full e2e: skip stale when safety gate triggers
# ---------------------------------------------------------------------------


def test_ac7_apply_skips_stale_when_uncommitted_changes(monkeypatch):
    """Even classified stale, --apply skips if uncommitted changes present."""
    porcelain = (
        "worktree /home/u/main\n"
        "HEAD abc\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /home/u/feat\n"
        "HEAD def\n"
        "branch refs/heads/feature/x\n"
    )
    monkeypatch.setattr(wl, "git_worktree_list_porcelain", lambda cwd=None: porcelain)

    def fake_pr_list(branch, state="merged", cwd=None):
        if state == "open":
            return []
        return [{"number": 1, "url": "u", "state": "MERGED"}]

    monkeypatch.setattr(wl, "gh_pr_list_for_branch", fake_pr_list)
    monkeypatch.setattr(wl, "git_commit_in_origin_main", lambda *a, **k: True)
    monkeypatch.setattr(wl, "git_check_uncommitted", lambda *a, **k: True)
    monkeypatch.setattr(wl, "git_stash_list", lambda *a, **k: [])
    remove_called = []
    monkeypatch.setattr(
        wl,
        "git_worktree_remove",
        lambda path, cwd=None: remove_called.append(path),
    )

    report = wl.run(dry_run=False, apply=True, excluded_paths=["/home/u/main"])
    assert remove_called == []  # skipped due to uncommitted
    assert len(report.skipped) == 1
    assert any("uncommitted" in r for r in report.skipped[0].skip_reasons)
