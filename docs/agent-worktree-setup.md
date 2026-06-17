# Agent Worktree 启动 SOP — git identity 隔离 (S3-OPS-WORKTREE-GIT-IDENTITY-ISOLATION)

每个 agent 在自己的 worktree (`~/repo/YiLuAn-<agent>`) 启动 / 首次 commit 前，
必须跑一次 identity setup，确保 commit author 落到本 agent 真实身份。

---

## TL;DR

```bash
cd ~/repo/YiLuAn-<agent>            # 例: ~/repo/YiLuAn-hutao
bash scripts/setup-agent-worktree.sh   # 自动从目录名推断 agent 并配置
# 校验:
make verify-worktree-identity          # 或 bash scripts/setup-agent-worktree.sh --verify
```

配置后 `git config user.name` 应打印本 agent 中文名（如 `胡桃`），
`git config user.email` 应为 `<agent>@yiluan.local`。

| agent slug | user.name | user.email |
|---|---|---|
| hutao | 胡桃 | hutao@yiluan.local |
| keqing | 刻晴 | keqing@yiluan.local |
| xiao | 魈 | xiao@yiluan.local |
| ningguang | 凝光 | ningguang@yiluan.local |
| ganyu | 甘雨 | ganyu@yiluan.local |

> 唯一真实来源：workspace `TOOLS.md`「团队角色（璃月）」表。

---

## 为何 per-worktree identity 必须隔离

### 反案 #16 同源教训：base `.git/config` 是共享的

`git worktree` 创建的子 worktree **默认共享** base repo 的 `.git/config`，
**包括 `user.name` / `user.email`**。只有 `HEAD` / `index` / `refs` 是每个
worktree 独立的；config 不独立（除非显式启用 `extensions.worktreeConfig`）。

后果：同一个 base repo (`~/repo/YiLuAn/.git`) 被多个 agent 各开一个 worktree
(`YiLuAn-hutao` / `YiLuAn-keqing` / …) 时，**任何一个 agent 在 base config 里
`git config user.name '<X>'` 都会同时改掉所有其他 worktree 的提交身份**。

### 实测事故 (2026-06-15 PR #310 commit `aeb5e09`)

- 现象：hutao 在 `YiLuAn-hutao` worktree 提交的 commit `aeb5e09`，
  `git show` 显示 **author=刻晴 `<keqing@yiluan.local>`**，不是 hutao 本人。
- root cause：`~/repo/YiLuAn/.git/config` 残留了刻晴 worktree 之前设的
  `user.name=刻晴 / user.email=keqing@yiluan.local`，污染了共享 base，
  hutao worktree 没有自己的 worktree-scoped 覆盖 → 落到被污染的 base 值。
- 临时修法（PR #310 commit `896a969` 内）：单 worktree 手动
  `git config extensions.worktreeConfig true` + `git config --worktree user.*`。
  但那只修了 hutao 一个 worktree，没系统化 → 本 task 把它脚本化 + 可校验。

### 为何 `extensions.worktreeConfig` 必须开

不开 `extensions.worktreeConfig`，`git config --worktree` 会报错或落不到
worktree-级 config；只有开启后，`--worktree` 写入
`.git/worktrees/<name>/config.worktree`，该文件**优先级高于** base
`.git/config`，才能赢过被污染的 base `user.*`。

config 优先级（高 → 低）：

```
.git/worktrees/<name>/config.worktree   ← git config --worktree（本 worktree 独占，赢）
.git/config                              ← 共享 base（会被其他 agent 污染）
~/.gitconfig                             ← 全局 fallback（AI智能助手，匿名兜底）
```

全局 `~/.gitconfig` 的 `AI智能助手 <ai-assistant@yiluan.local>` 只是匿名兜底，
**会被 base `.git/config` 覆盖**，所以不能依赖它——必须用 `--worktree` 覆盖。

---

## setup 脚本行为

`scripts/setup-agent-worktree.sh`：

1. 解析 agent slug：显式传参优先，否则从 worktree 目录名 `YiLuAn-<agent>`
   自动推断。base repo 目录（无 `-` 后缀）会被拒绝——base 不应配 agent identity。
2. 校验 slug 在已知 5 agent 内，否则报错退出。
3. 配置模式：`git config extensions.worktreeConfig true` +
   `git config --worktree user.name '<中文名>' user.email '<slug>@yiluan.local'`。
4. `--verify` 模式：只读校验当前 worktree 的 effective `user.name/email` +
   `extensions.worktreeConfig` 是否正确，不做任何写入，不匹配则非零退出。

---

## 与远程身份隔离 task 的关系

| task | 层 | 解决什么 |
|---|---|---|
| **本 task** (WORKTREE-GIT-IDENTITY-ISOLATION) | 本地 commit 层 | `git user.name/email` per-worktree 隔离，commit author 落到真实 agent |
| S3-OPS-SEPARATE-GH-IDENTITY-PER-AGENT | 远程仓库层 | 5 个独立 GitHub account + PAT，让 native PR review approve 走通、audit trail 清晰 |

两者互补、可独立 ship；合起来才是 per-agent identity 的端到端方案。

---

## 启动 SOP 集成

每个 agent worktree 启动 / 首次 commit 前跑 setup（见上 TL;DR）。
commit 前可加 `make verify-worktree-identity` 做一次自检，防 base config 被
其他 agent 重新污染后无声落到错误身份。

相关：worktree 用完自动清理见 `docs/ops/worktree-lifecycle.md`。
