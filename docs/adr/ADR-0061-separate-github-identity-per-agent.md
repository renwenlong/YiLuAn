# ADR-0061: 各 Agent 独立 GitHub Identity（根治 self-approve 物理禁 + audit trail 单一化）

- **状态**: 设计中（Proposed）；**实施分层 gated**——技术设计/自动化脚本部分可即刻推进，账号物料（AC#1/AC#2 真 PAT）+ branch protection apply（AC#5）卡帝君出物料 + 治理背书。
- **日期**: 2026-07-01
- **决策者**: 魈（架构师）
- **关联**: `S3-OPS-SEPARATE-GH-IDENTITY-PER-AGENT`（P2 develop, 凝光 2026-06-15 surface）/ 反案#37（self-approve workaround 留痕断链）/ 反案#45 v3（GitHub self-approve 物理禁）/ 反案#48（改 branch protection 治理硬规必帝君本人背书）
- **触发**: PR #309 review 闭环时 PM 凝光 surface：5 agent 共用 `renwenlong` 单账号 → GitHub 协议禁 self-approve → architect 被迫走 `--comment`(state=COMMENTED) 代替 `--approve`(state=APPROVED) → branch protection 无法加 `required_approving_review_count=1`。

> ⚠️ **实施边界（分层 gate）**: 本 ADR 锁**技术设计契约 + 可自动化部分**。**卡帝君物料**的三点明标：AC#1（建 5 个 GH 账号，人工注册）、AC#2 真 PAT（帝君生成后交付）、AC#5 apply（branch protection 变更 = 反案#48 治理硬规，需帝君背书 + 全 in-flight PR batch 协调）。**架构师先落设计 + 写好自动化脚本（读 token 逻辑/gh 配置隔离/规约还原），物料到位胡桃即接实施，不空等。**

---

## 1. 背景与问题

### 1.1 现状（evidence-first 实测 2026-07-01）

```
- 5 个 yiluan-* 账号: 全 HTTP 404（不存在）
- 5 个 workspace 的 .openclaw/secrets 目录: 全不存在
- 当前 gh auth: renwenlong via 全局 ~/.config/gh/hosts.yml（单例，5 agent 共享）
- GH_TOKEN env: 未设
```

### 1.2 问题链（凝光 surface 的反案#37 root cause）

```
5 agent 共用 renwenlong 单账号
  → GitHub 协议层禁 self-approve（PR author 不能 approve 自己 PR）
  → architect review 被迫 gh pr review --comment（state=COMMENTED）代替 --approve
  → 后果:
    ① GitHub UI 显示 0 APPROVED reviews，看似 unreviewed code merged
    ② branch protection 无法加 required_approving_review_count=1（设了全 PR 卡死）
    ③ audit trail 模糊（author/reviewer/merger 都是 renwenlong）
    ④ 反案#37 是 workaround 非根治
```

---

## 2. 核心技术难点

**gh CLI 配置是全局单例**：`~/.config/gh/hosts.yml` 一份，5 个 workspace 共享同一 gh 身份。要实现 per-agent identity，必须**隔离每个 workspace 的 gh 配置上下文**。

两种隔离机制（gh CLI 原生支持）：
1. **`GH_CONFIG_DIR` 环境变量**：每 workspace 指向独立配置目录 → 各自 hosts.yml → 各自身份
2. **`GH_TOKEN` 环境变量**：每 workspace 注入各自 PAT → gh 直接用 token 身份（不读 hosts.yml）

---

## 3. 方案对比

### 方案 A：`GH_TOKEN` per-workspace 注入（推荐）

每 workspace secret 文件存 PAT，agent 进程启动时 `export GH_TOKEN=$(cat ~/.openclaw/workspace-<agent>/.openclaw/secrets/github_pat)`。gh CLI 见 `GH_TOKEN` 优先用它，跳过 hosts.yml。

| 维度 | 评估 |
|---|---|
| 隔离强度 | ✅ 强（token 直接决定身份，无共享状态） |
| 实现复杂度 | ✅ 低（1 个 env 注入，无需管理多份 config 目录） |
| PAT 轮换 | ✅ 简单（换 secret 文件内容即可） |
| git push 身份 | ✅ gh 配置的 credential helper 用 GH_TOKEN；git commit author 另需 per-workspace `user.name/email` |
| 风险 | token 泄露即身份泄露 → secret 文件必 gitignore + chmod 600 |

### 方案 B：`GH_CONFIG_DIR` 隔离配置目录

每 workspace 指向 `~/.openclaw/workspace-<agent>/.openclaw/gh-config/`，各自 `gh auth login` 一次，hosts.yml 独立。

| 维度 | 评估 |
|---|---|
| 隔离强度 | ✅ 强（配置目录物理隔离） |
| 实现复杂度 | 🟡 中（需管理 5 份 config 目录 + 各自 login 一次） |
| PAT 轮换 | 🟡 中（需重跑 gh auth login --with-token） |
| 状态残留 | 🟡 config 目录含 cache/state，多份维护成本高 |
| 风险 | 配置目录漂移风险（升级 gh 可能改 config 结构） |

### 决定：**方案 A（GH_TOKEN 注入）**

理由：
1. **最小状态**——身份完全由 token 决定，无 config 目录漂移风险
2. **轮换最简**——换 secret 文件内容即生效，无需重 login
3. **符合 12-factor**——配置经环境变量注入，不落地多份 stateful 目录
4. git commit author 身份用 per-workspace git config 补齐（`git config user.name "yiluan-<agent>"` + email），与 gh identity 正交解决

---

## 4. 实施设计（分层）

### 4.1 可即刻推进（不依赖真账号/PAT）— 架构师本 ADR + 胡桃脚本

**S1. gh 身份注入脚本** `scripts/agent-gh-identity.sh`（幂等）:
```bash
#!/usr/bin/env bash
# 各 agent worktree 启动时 source, 注入本 workspace 的 GH 身份
set -euo pipefail
AGENT_KEY="${1:?usage: agent-gh-identity.sh <agent_key>}"
SECRET="$HOME/.openclaw/workspace-${AGENT_KEY}/.openclaw/secrets/github_pat"
if [[ -f "$SECRET" ]]; then
  export GH_TOKEN="$(tr -d '[:space:]' < "$SECRET")"
  # git commit author 身份（与 gh 正交）
  git config --global user.name  "yiluan-${AGENT_KEY}"
  git config --global user.email "yiluan-${AGENT_KEY}@users.noreply.github.com"
  echo "[gh-identity] ${AGENT_KEY} → GH_TOKEN 注入 + git author 设定"
else
  echo "[gh-identity] WARN: ${SECRET} 不存在, 回退共享 renwenlong (反案#37 workaround)"
fi
```

**S2. secret 文件规范**：
- 路径：`~/.openclaw/workspace-<agent>/.openclaw/secrets/github_pat`
- 权限：`chmod 600`
- gitignore：`.openclaw/secrets/` 全目录（每 workspace 的 .gitignore 加，若 workspace 本身纳入 git 管理）
- scope：`repo` + `workflow` + `read:org`

**S3. branch protection amend 脚本** `scripts/qa/enable-required-approvals.sh`（**写好但不 apply**，物料到位帝君背书后跑）:
```bash
#!/usr/bin/env bash
# ⚠️ 治理变更(反案#48): 需帝君背书 + 全 in-flight PR batch 协调后 apply
# apply 前提: 5 个 yiluan-* 账号 + PAT 就位, architect(yiluan-xiao)≠author 可真 --approve
set -euo pipefail
gh api -X PUT repos/renwenlong/YiLuAn/branches/main/protection/required_pull_request_reviews \
  -f required_approving_review_count=1 \
  -F dismiss_stale_reviews=true
echo "[branch-protection] required_approving_review_count=1 已启用"
```

**S4. 反案#37 规约还原设计**（AC#6/#7）：
- 还原点：r1/r2 review 走 `gh pr review --approve`（state=APPROVED 真留痕）
- `--comment` + body 首行表态 → 标记 **deprecated fallback**（仅 PAT 失效等极端 case 用）
- 旧 PR（renwenlong era, 2026-06-15 04:23Z 前）：历史保留 COMMENTED，**不回溯改写**
- 新 PR（本 task 完成后）：必走 APPROVED 真留痕
- 规约落点：更新 MEMORY 反案#37 段 + 相关 skill（若有）

### 4.2 卡帝君出物料（人工前置）

| AC | 前置动作 | Owner |
|---|---|---|
| AC#1 | 注册 5 个 GH 账号 `yiluan-{hutao,keqing,xiao,ningguang,ganyu}`（邮箱/手机验证，反 bot） | **帝君** |
| AC#2 | 各账号生成 PAT（scope=repo+workflow+read:org），交付到各 workspace secret | **帝君**（生成）→ 架构师/胡桃（写文件） |
| AC#4 | 真账号到位后验证各 identity push/PR/comment | 胡桃（实施）→ 架构师（review） |
| AC#5 apply | branch protection 变更（反案#48 背书 + batch 协调） | **帝君背书** → 架构师 apply |

---

## 5. 后果

### 正面
- ✅ 根治 self-approve 物理禁：architect(yiluan-xiao) ≠ author(yiluan-hutao) → 真 `--approve`(state=APPROVED)
- ✅ branch protection 可加 `required_approving_review_count=1`（真强制 review 闸）
- ✅ audit trail 清晰：author/reviewer/merger 各自身份可辨
- ✅ 反案#37 workaround 退役为 fallback

### 负面 / 风险
- 🟡 multi-account 管理成本（5 个账号 + PAT 轮换）
- 🟡 branch protection 变更 = breaking change，全 in-flight PR 需 batch 协调（apply 时机选低峰 + 提前通知）
- 🟡 历史 audit 断裂：renwenlong era PR 全留 renwenlong 名（AC#7 明确不回溯，可接受）
- 🟡 GH free tier 账号可能触发平台风控（5 个新账号同 IP/同仓协作，需帝君注册时留意）

### 迁移期兼容
- secret 文件不存在时脚本回退共享 renwenlong（反案#37 workaround），**平滑过渡**——不是硬切换，账号逐个到位逐个切。

---

## 6. 实施任务映射

| AC | 实施内容 | 可推时机 |
|---|---|---|
| AC#1 | 建 5 账号 | 🛑 卡帝君 |
| AC#2 | PAT 生成（帝君）+ 写 secret 文件（脚本 S2 规范） | 🛑 真 PAT 卡帝君；机制/gitignore 可先 |
| AC#3 | gh 身份注入脚本 S1 | ✅ 可即刻（胡桃实施） |
| AC#4 | 各 identity 验证 | 🛑 需真账号 |
| AC#5 | branch protection amend 脚本 S3（写）+ apply | ✅ 脚本可写；🛑 apply 卡帝君背书 |
| AC#6 | 反案#37 规约还原 S4 | ✅ 可即刻（设计+文档） |
| AC#7 | 旧/新 PR 留痕策略 | ✅ 可即刻（策略文档） |

**结论**：AC#3/#6/#7 + AC#2 机制 + AC#5 脚本 = 现在可推（胡桃实施 S1/S2 规范/S3 脚本/S4 文档）；AC#1 + AC#2 真 PAT + AC#4 + AC#5 apply = 帝君物料到位后接续。
