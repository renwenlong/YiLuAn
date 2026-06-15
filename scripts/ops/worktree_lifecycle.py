#!/usr/bin/env python3
"""worktree_lifecycle.py — S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP

帝君 2026-06-08 16:03 UTC 指令: PR MERGED 后 worktree 应用完自动删.

扫 `git worktree list --porcelain` + `gh pr list`, 交叉验:
- stale: branch 有 merged PR && commit SHA 在 origin/main → 自动 remove
- active: branch 有 OPEN PR → 保留
- orphan: branch 无 PR → 报警, 默认不删

支持 dry-run / --apply 模式, 6 个安全闸门 (uncommitted/stash/main-branch/
detached/excluded-path/HEAD-not-in-origin-main) 防误删.

usage:
    python scripts/ops/worktree_lifecycle.py --dry-run
    python scripts/ops/worktree_lifecycle.py --apply
    python scripts/ops/worktree_lifecycle.py --apply --include-orphan
    python scripts/ops/worktree_lifecycle.py --apply \
        --exclude-paths "/home/wenlongren/repo/YiLuAn"

cron (AC#3):
    */30 * * * * cd /home/wenlongren/repo/YiLuAn && \
        python scripts/ops/worktree_lifecycle.py --apply \
        --exclude-paths "/home/wenlongren/repo/YiLuAn" \
        >> ~/.openclaw/logs/worktree-cleanup-$(date +%%Y-%%m-%%d).log 2>&1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

logger = logging.getLogger(__name__)

# Hardcoded deny list — never delete a worktree on these branches even if
# CLI flags conflict. Defense-in-depth.
_FORBIDDEN_BRANCHES: tuple[str, ...] = ("main", "master", "develop", "release")

# Default excluded paths (extend via --exclude-paths)
_DEFAULT_EXCLUDED_PATHS: tuple[str, ...] = ("/home/wenlongren/repo/YiLuAn",)


@dataclass
class WorktreeInfo:
    """Parsed `git worktree list --porcelain` entry."""

    path: str
    branch: str  # plain branch name, "HEAD" for detached, "" if bare
    head: str  # commit SHA
    detached: bool = False
    bare: bool = False


@dataclass
class ClassifiedWorktree:
    """Worktree + categorisation + decision metadata."""

    worktree: WorktreeInfo
    category: str  # 'stale' | 'active' | 'orphan' | 'protected'
    reason: str
    pr_number: int | None = None
    pr_url: str | None = None
    skip_reasons: list[str] = field(default_factory=list)


@dataclass
class CleanupReport:
    """Final report returned + serialised to JSON for cron log."""

    timestamp: str
    cwd: str
    dry_run: bool
    apply: bool
    include_orphan: bool
    excluded_paths: list[str]
    stale: list[ClassifiedWorktree] = field(default_factory=list)
    active: list[ClassifiedWorktree] = field(default_factory=list)
    orphan: list[ClassifiedWorktree] = field(default_factory=list)
    protected: list[ClassifiedWorktree] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[ClassifiedWorktree] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _serialize_cw(cw):
            return {
                "path": cw.worktree.path,
                "branch": cw.worktree.branch,
                "head": cw.worktree.head,
                "detached": cw.worktree.detached,
                "category": cw.category,
                "reason": cw.reason,
                "pr_number": cw.pr_number,
                "pr_url": cw.pr_url,
                "skip_reasons": cw.skip_reasons,
            }

        return {
            "timestamp": self.timestamp,
            "cwd": self.cwd,
            "dry_run": self.dry_run,
            "apply": self.apply,
            "include_orphan": self.include_orphan,
            "excluded_paths": self.excluded_paths,
            "stale": [_serialize_cw(cw) for cw in self.stale],
            "active": [_serialize_cw(cw) for cw in self.active],
            "orphan": [_serialize_cw(cw) for cw in self.orphan],
            "protected": [_serialize_cw(cw) for cw in self.protected],
            "removed": list(self.removed),
            "skipped": [_serialize_cw(cw) for cw in self.skipped],
        }


# ---------------------------------------------------------------------------
# Subprocess wrappers (mockable in tests)
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: str | None = None, check: bool = True) -> str:
    """Run subprocess capturing stdout. Returns stdout text."""
    res = subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )
    return res.stdout


def git_worktree_list_porcelain(cwd: str | None = None) -> str:
    """Wrap `git worktree list --porcelain`."""
    return _run(["git", "worktree", "list", "--porcelain"], cwd=cwd)


def gh_pr_list_for_branch(
    branch: str, state: str = "merged", cwd: str | None = None
) -> list[dict]:
    """Wrap `gh pr list --state <state> --head <branch> --json ...`. Returns
    list of PR dicts or [] on failure."""
    try:
        out = _run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                state,
                "--head",
                branch,
                "--json",
                "number,url,mergeCommit,headRefName,state",
                "--limit",
                "20",
            ],
            cwd=cwd,
            check=False,
        )
        return json.loads(out) if out.strip() else []
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        logger.warning("gh_pr_list_for_branch(%s, %s) failed: %s", branch, state, exc)
        return []


def git_check_uncommitted(worktree_path: str) -> bool:
    """Return True if uncommitted changes (staged or unstaged) present."""
    try:
        out = _run(["git", "status", "--porcelain"], cwd=worktree_path, check=False)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return True  # fail-closed


def git_stash_list(worktree_path: str) -> list[str]:
    """Return list of stash refs in this worktree."""
    try:
        out = _run(["git", "stash", "list"], cwd=worktree_path, check=False)
        return [line for line in out.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        return []


def git_commit_in_origin_main(sha: str, cwd: str | None = None) -> bool:
    """Check if commit SHA is reachable from origin/main."""
    try:
        # Exit 0 = is ancestor; non-zero = not ancestor
        rc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
            cwd=cwd,
            capture_output=True,
        ).returncode
        return rc == 0
    except subprocess.CalledProcessError:
        return False


def git_worktree_remove(worktree_path: str, cwd: str | None = None) -> None:
    """Wrap `git worktree remove <path>`. Raises on error."""
    _run(["git", "worktree", "remove", worktree_path], cwd=cwd, check=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_worktree_list_porcelain(porcelain: str) -> list[WorktreeInfo]:
    """Parse `git worktree list --porcelain` output into WorktreeInfo list.

    Format example:
        worktree /home/u/repo
        HEAD abc123
        branch refs/heads/main

        worktree /home/u/repo-feat
        HEAD def456
        branch refs/heads/feature/x

        worktree /home/u/repo-detached
        HEAD ghi789
        detached
    """
    out: list[WorktreeInfo] = []
    blocks = [b for b in porcelain.split("\n\n") if b.strip()]
    for block in blocks:
        info = WorktreeInfo(path="", branch="", head="")
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("worktree "):
                info.path = line[len("worktree ") :].strip()
            elif line.startswith("HEAD "):
                info.head = line[len("HEAD ") :].strip()
            elif line.startswith("branch "):
                ref = line[len("branch ") :].strip()
                info.branch = (
                    ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref
                )
            elif line == "detached":
                info.detached = True
                info.branch = "HEAD"
            elif line == "bare":
                info.bare = True
        if info.path:
            out.append(info)
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_worktree(
    wt: WorktreeInfo,
    excluded_paths: Iterable[str],
    cwd: str | None = None,
) -> ClassifiedWorktree:
    """Categorise one worktree as stale/active/orphan/protected."""
    norm_excluded = {os.path.realpath(p) for p in excluded_paths}
    if os.path.realpath(wt.path) in norm_excluded or wt.bare:
        return ClassifiedWorktree(
            worktree=wt,
            category="protected",
            reason="excluded-path or bare worktree",
        )

    if wt.detached:
        return ClassifiedWorktree(
            worktree=wt,
            category="protected",
            reason="detached HEAD; require manual review",
        )

    if wt.branch in _FORBIDDEN_BRANCHES:
        return ClassifiedWorktree(
            worktree=wt,
            category="protected",
            reason=f"branch {wt.branch} in forbidden list",
        )

    # Check for OPEN PR first
    open_prs = gh_pr_list_for_branch(wt.branch, state="open", cwd=cwd)
    if open_prs:
        pr = open_prs[0]
        return ClassifiedWorktree(
            worktree=wt,
            category="active",
            reason=f"open PR #{pr.get('number')}",
            pr_number=pr.get("number"),
            pr_url=pr.get("url"),
        )

    # Check for MERGED PR
    merged_prs = gh_pr_list_for_branch(wt.branch, state="merged", cwd=cwd)
    if merged_prs:
        pr = merged_prs[0]
        # Verify the worktree HEAD is in origin/main (commit already landed)
        in_main = git_commit_in_origin_main(wt.head, cwd=cwd)
        if in_main:
            return ClassifiedWorktree(
                worktree=wt,
                category="stale",
                reason=f"PR #{pr.get('number')} merged and HEAD in origin/main",
                pr_number=pr.get("number"),
                pr_url=pr.get("url"),
            )
        return ClassifiedWorktree(
            worktree=wt,
            category="orphan",
            reason=(
                f"PR #{pr.get('number')} merged but HEAD {wt.head[:7]} not yet "
                "in origin/main (possible local unpushed commits)"
            ),
            pr_number=pr.get("number"),
            pr_url=pr.get("url"),
        )

    return ClassifiedWorktree(
        worktree=wt,
        category="orphan",
        reason="no PR found for branch (may be unpushed feature or stale)",
    )


# ---------------------------------------------------------------------------
# 6 safety gates
# ---------------------------------------------------------------------------


def check_safety_gates(
    cw: ClassifiedWorktree, excluded_paths: Iterable[str]
) -> list[str]:
    """Run 6 safety gates; return list of reasons to skip (empty list = OK to delete)."""
    reasons: list[str] = []

    # gate 1: uncommitted changes
    if git_check_uncommitted(cw.worktree.path):
        reasons.append("uncommitted changes present")

    # gate 2: stash entries
    stashes = git_stash_list(cw.worktree.path)
    if stashes:
        reasons.append(f"{len(stashes)} stash entries present")

    # gate 3: main/master/develop/release branch (forbidden list)
    if cw.worktree.branch in _FORBIDDEN_BRANCHES:
        reasons.append(f"branch {cw.worktree.branch} in forbidden list")

    # gate 4: detached HEAD
    if cw.worktree.detached:
        reasons.append("detached HEAD")

    # gate 5: in excluded-paths
    norm_excluded = {os.path.realpath(p) for p in excluded_paths}
    if os.path.realpath(cw.worktree.path) in norm_excluded:
        reasons.append("path in excluded-paths list")

    # gate 6: HEAD not in origin/main
    if not cw.worktree.detached and not git_commit_in_origin_main(
        cw.worktree.head, cwd=cw.worktree.path
    ):
        reasons.append(f"HEAD commit {cw.worktree.head[:7]} not in origin/main")

    return reasons


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run(
    *,
    dry_run: bool = True,
    apply: bool = False,
    include_orphan: bool = False,
    excluded_paths: Iterable[str] | None = None,
    cwd: str | None = None,
) -> CleanupReport:
    """Run lifecycle scan + optional cleanup. Returns CleanupReport."""
    excluded = list(excluded_paths or _DEFAULT_EXCLUDED_PATHS)
    report = CleanupReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        cwd=cwd or os.getcwd(),
        dry_run=dry_run,
        apply=apply,
        include_orphan=include_orphan,
        excluded_paths=excluded,
    )

    porcelain = git_worktree_list_porcelain(cwd=cwd)
    worktrees = parse_worktree_list_porcelain(porcelain)

    for wt in worktrees:
        cw = classify_worktree(wt, excluded_paths=excluded, cwd=cwd)
        if cw.category == "stale":
            report.stale.append(cw)
        elif cw.category == "active":
            report.active.append(cw)
        elif cw.category == "orphan":
            report.orphan.append(cw)
        else:
            report.protected.append(cw)

    if not apply:
        return report

    # apply removal
    targets = list(report.stale)
    if include_orphan:
        targets.extend(report.orphan)

    for cw in targets:
        skip_reasons = check_safety_gates(cw, excluded_paths=excluded)
        if skip_reasons:
            cw.skip_reasons = skip_reasons
            report.skipped.append(cw)
            logger.warning(
                "skip remove %s (branch=%s): %s",
                cw.worktree.path,
                cw.worktree.branch,
                "; ".join(skip_reasons),
            )
            continue
        try:
            git_worktree_remove(cw.worktree.path, cwd=cwd)
            report.removed.append(cw.worktree.path)
            logger.info(
                "removed worktree %s (branch=%s, PR #%s)",
                cw.worktree.path,
                cw.worktree.branch,
                cw.pr_number,
            )
        except subprocess.CalledProcessError as exc:
            cw.skip_reasons = [f"git worktree remove failed: {exc}"]
            report.skipped.append(cw)
            logger.error("remove failed for %s: %s", cw.worktree.path, exc)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan & clean up stale git worktrees (S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Scan and report only; do not remove worktrees (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually remove stale worktrees (overrides --dry-run)",
    )
    parser.add_argument(
        "--include-orphan",
        action="store_true",
        default=False,
        help="Also remove orphan worktrees (no PR found); default skips them",
    )
    parser.add_argument(
        "--exclude-paths",
        nargs="*",
        default=list(_DEFAULT_EXCLUDED_PATHS),
        help="Worktree paths to never delete",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Git repo cwd (default = current dir)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit JSON report to stdout (in addition to log lines)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress non-error logging",
    )
    args = parser.parse_args(argv)

    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    apply_mode = args.apply
    dry_run = not apply_mode

    report = run(
        dry_run=dry_run,
        apply=apply_mode,
        include_orphan=args.include_orphan,
        excluded_paths=args.exclude_paths,
        cwd=args.cwd,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        logger.info(
            "summary: stale=%d active=%d orphan=%d protected=%d "
            "removed=%d skipped=%d",
            len(report.stale),
            len(report.active),
            len(report.orphan),
            len(report.protected),
            len(report.removed),
            len(report.skipped),
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
