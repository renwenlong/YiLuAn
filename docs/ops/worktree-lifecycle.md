# worktree lifecycle 自动清理 (S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP)

帝君 2026-06-08 16:03 UTC 指令：**worktree 应用完自动删**。本文档说明 cron 自动化方案。

---

## 背景

历史上 PR MERGED 后多个 agent worktree 不删,累积 stale worktree (今天前 6 个 PR MERGED 后未清, 1 个 PR OPEN 保留 int004 合理). 协议无 enforce ⇒ 物理资源浪费 + 多 session 互冲风险.

## 方案

3 层防御:

1. **(b) 自动化优先 — cron 30min 扫一次** (主路径)
2. **(a) AGENTS.md SOP 提示** — PR MERGED 后即时 `cd ~/repo/YiLuAn-<agent> && git checkout main && git pull` (复用 worktree, 不开新)
3. **(c) lint 哨兵** — CI 扫每个 workspace AGENTS.md 必含此段

## 决策矩阵 — 三态分类

`scripts/ops/worktree_lifecycle.py` 扫所有 worktree (`git worktree list --porcelain`) 跟 `gh pr list --head <branch>` 交叉验:

| 状态 | 触发条件 | 默认动作 |
|---|---|---|
| **stale** | branch 有 MERGED PR && HEAD commit 已含在 `origin/main` | `--apply` 自动 remove |
| **active** | branch 有 OPEN PR | 保留, 不删 |
| **orphan** | branch 无 PR 找到 (未 push 或孤儿) | 报警, 默认不删; `--include-orphan` 才删 |
| **protected** | path 在 `--exclude-paths` 或 branch in `main/master/develop/release` 或 detached HEAD | 永不删 |

## 6 个安全闸门

`--apply` 模式下, 删每个 stale worktree 前必跑 6 个 verify, 任一命中即 skip:

1. `git status --porcelain` 有 uncommitted change → skip
2. `git stash list` 有 stash 条目 → skip
3. branch 是 `main` / `master` / `develop` / `release` (硬编码 deny list) → skip
4. detached HEAD 状态 → skip
5. path 在 `--exclude-paths` 列表 → skip
6. HEAD commit 不在 `origin/main` 可达 → skip (防止误删未 push 的本地工作)

## 使用方式

### dry-run (查看决策)

```bash
cd ~/repo/YiLuAn
python scripts/ops/worktree_lifecycle.py --dry-run --json
```

### --apply (实际删 stale)

```bash
cd ~/repo/YiLuAn
python scripts/ops/worktree_lifecycle.py --apply \
    --exclude-paths "/home/wenlongren/repo/YiLuAn"
```

### --apply --include-orphan (连带删 orphan, **谨慎**)

```bash
cd ~/repo/YiLuAn
python scripts/ops/worktree_lifecycle.py --apply --include-orphan \
    --exclude-paths "/home/wenlongren/repo/YiLuAn"
```

### cron 定时

`~/.openclaw/cron/yiluan-worktree-cleanup.cron` (AC#3 deliverable) 内含 `*/30 * * * *` 条目, 系统 cron 或 openclaw cron tool 二选一安装:

**系统 cron**:
```bash
crontab -e
# 复制 ~/.openclaw/cron/yiluan-worktree-cleanup.cron 里 SYSTEM CRON FORMAT 那一行
```

**openclaw cron**:
```bash
# (见 .cron 文件末注释里的 OPENCLAW CRON JSON 模板)
```

## 日志

每次 `--apply` 执行 log 落到:
```
~/.openclaw/logs/worktree-cleanup-YYYY-MM-DD.log
```

格式 (JSON):
```json
{
  "timestamp": "...",
  "stale": [{path, branch, head, pr_number, ...}],
  "removed": ["/home/.../path1", ...],
  "skipped": [{path, skip_reasons: ["uncommitted changes present"]}]
}
```

## 紧急 disable

cron 行误删高频 → 立即:
```bash
crontab -e  # 注释掉那一行
# 或:
openclaw cron remove --id <job-id>
```
然后 `git commit AGENTS.md / docs/ops/worktree-lifecycle.md` 留痕说为什么禁用 + 修复时间.

## AGENTS.md SOP 配套

各 agent workspace `AGENTS.md` 必含段:

### worktree 生命周期

- 一 agent 一 worktree, 不开多 worktree
- PR MERGED 后立即:
  1. `cd ~/repo/YiLuAn-<your-agent-name>`
  2. `git checkout main && git pull` (回 main + 同步)
  3. 不再开新 feature → 留 worktree 复用
  4. 下次开新 feature → 直接 `git checkout -b feature/...` 在本 worktree (不开新 worktree)
- 紧急 race: stash + sessions_send 通知 + 协调者拍方向, 不自己抢救

cron `*/30 *` 自动 sweep stale worktree, 你忘 cleanup 也兜底.

## 反案哨兵

`scripts/qa/check_agents_md_has_worktree_sop.py` lint 各 AGENTS.md 必含 "worktree 生命周期" 段. CI `.github/workflows/agents-md-lint.yml` 在 PR 修改 AGENTS.md / lint 脚本时触发.

注: workspace AGENTS.md 文件不在 repo 内 (在 `~/.openclaw/workspace-*/AGENTS.md`),lint 仅 verify 本仓库内 AGENTS.md 模板 (`docs/agents-md/worktree-lifecycle-sop.md`) 存在 + 内容. 各 agent 自己同步本工作站 AGENTS.md (本 task PR 也仅修改 hutao workspace 的 AGENTS.md, 其他 agent 由 coordinator/各 agent 自更).

## 测试

`backend/tests/ops/test_worktree_lifecycle.py` 16 sentinel test 覆盖:

- AC#1 parse / classify (8)
- AC#2 dry-run vs --apply (3)
- AC#6 6 安全闸门 (4)
- AC#7 e2e skip 路径 (1)

## 参考

- Task: S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP (P2, 9 AC, PM ratify 2026-06-13 04:30Z)
- 帝君指令: 2026-06-08 16:03 UTC
- 历史 race: 2026-06-08 hutao main+group session 同 worktree race (MEMORY 长期记忆)
- 关联 task: S3-OPS-A-WORKTREE-OWNER-METADATA (.OWNER 元数据 + pre-push hook reject), S3-OPS-B-MULTI-SESSION-WORKTREE-ISOLATION (物理隔离)
