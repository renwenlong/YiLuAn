# AGENTS.md worktree 生命周期 SOP 段 (S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP AC#4)

各 agent workspace `~/.openclaw/workspace-<agent>/AGENTS.md` 必加下面这段 (lint 哨兵 `scripts/qa/check_agents_md_has_worktree_sop.py` 强制扫这段标题字符串):

---

### worktree 生命周期

- 一 agent 一 worktree, 不开多 worktree
- PR MERGED 后立即:
  1. `cd ~/repo/YiLuAn-<your-agent-name>`
  2. `git checkout main && git pull` (回 main + 同步)
  3. 不再开新 feature → 留 worktree 复用
  4. 下次开新 feature → 直接 `git checkout -b feature/...` 在本 worktree (不开新 worktree)
- 紧急 race: stash + sessions_send 通知 + 协调者拍方向, 不自己抢救

cron `*/30 *` (见 `docs/ops/worktree-lifecycle.md`) 自动 sweep stale worktree, 你忘 cleanup 也兜底.
