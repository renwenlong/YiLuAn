#!/usr/bin/env python3
"""S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP AC#9 反案哨兵.

Lint: 验证仓库内 AGENTS.md SOP 模板存在且含 "worktree 生命周期" 段.

注: workspace AGENTS.md 文件 (`~/.openclaw/workspace-*/AGENTS.md`) 在
CI 环境无法访问, 本 lint 仅 verify 仓库内 SOP 模板存在 + 包含必含小节.
各 agent 自行同步该模板到自己的 workspace AGENTS.md, coordinator
(甘雨) 跨 workspace audit.

usage:
    python scripts/qa/check_agents_md_has_worktree_sop.py
exit 0 = OK, exit 1 = SOP 模板缺失或内容残缺.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "docs" / "agents-md" / "worktree-lifecycle-sop.md"
REQUIRED_HEADING = "### worktree 生命周期"
REQUIRED_SUBSTRINGS = (
    "一 agent 一 worktree",
    "git checkout main && git pull",
    "下次开新 feature",
    "cron",
)


def main() -> int:
    if not TEMPLATE_PATH.exists():
        print(
            f"[lint:fail] AGENTS.md SOP 模板缺失: {TEMPLATE_PATH}",
            file=sys.stderr,
        )
        print(
            "[lint:hint] 应有 docs/agents-md/worktree-lifecycle-sop.md, "
            "落 S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP AC#4 模板.",
            file=sys.stderr,
        )
        return 1

    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    missing: list[str] = []
    if REQUIRED_HEADING not in text:
        missing.append(REQUIRED_HEADING)
    for sub in REQUIRED_SUBSTRINGS:
        if sub not in text:
            missing.append(sub)

    if missing:
        print(
            f"[lint:fail] {TEMPLATE_PATH} 缺以下必含子串:",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  - {m!r}", file=sys.stderr)
        print(
            "[lint:hint] 见 S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP AC#4 全量 SOP.",
            file=sys.stderr,
        )
        return 1

    print(f"[lint:ok] {TEMPLATE_PATH} 含全部必要 SOP 段.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
