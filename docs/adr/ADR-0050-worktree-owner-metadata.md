# ADR-0050 — Worktree `.OWNER` 元数据 + pre-push hook 协议 (r2)

> 状态：**Proposed** · 作者：魈 · 日期：2026-06-08 · Accept 日期：TBD
> 关联：task `S3-OPS-A-WORKTREE-OWNER-METADATA` r2 设计 (06-08 13:45 UTC 拆) · 前置依赖 `S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION` (P1, coordinator own) · OPS-021 反模式 #14 (worktree 安全 announce-before-touch) + #6 (派单去重, r) 互补关系
> 触发：2026-06-08 12:57 UTC hutao 2 active session (main + group) 同 worktree race + 16:00 UTC architect (魈) 误判 int004 worktree owner 险触发 6 worktree clobber
> Owner Approval：**等帝君拍**
> 修订：r1 (01:30 UTC PR #227 v1) 被 hutao 01:33 UTC fact check 出**功能退化 + env 名错 + 漏前置依赖**, **r2 (本版本)** 跟 task description r2 既有设计 align

---

## 0. 修订记录

| 版本 | 时间 | 变更 | 触发 |
|---|---|---|---|
| r1 | 2026-06-08 13:45 UTC | task description r2 拆 (魈) | hutao race 事故 |
| ADR v1 (1.0) | 2026-06-09 01:30 UTC | PR #227 单行 ascii .OWNER + AGENTSQUAD_AGENT_KEY env, 6 AC | 自启动 (没读 task description) |
| ADR v2 (2.0) | 2026-06-09 01:35 UTC | **本版本**, 跟 task description r2 align: YAML .OWNER + OPENCLAW_AGENT_KEY env + 前置依赖标注 + 11 AC | hutao 01:33 UTC fact check |

**ADR v1 → v2 主要变更**:
- `.OWNER` 格式: 单行 ascii → **YAML** (含 primary / shared_read[] / shared_write[] / notes)
- env 名: `AGENTSQUAD_AGENT_KEY` → **`OPENCLAW_AGENT_KEY`** (依赖 OpenClaw gateway 注入, 见 §1.5)
- 前置依赖: 无 → **`S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION`** P1 (coordinator own)
- AC 数: 6 → **11** (覆盖 shared_read/shared_write 授权 + main pull-only + agent key 推导优先级 + 完整文档 + OPS-021 link)
- pre-push hook 校验维度: only primary → primary + shared + shared_write + main exempt
- 文档路径: `docs/dev/multi-agent-worktree-protocol.md` → `docs/ops/worktree-ownership.md`

---

## 1. 背景

### 1.1 实测痛点 (2026-06-08)

| 时间 | 事件 | 后果 |
|---|---|---|
| 12:57 UTC | hutao 2 active session (main + group) 同 worktree race | 双 PR (#217 + #218) merge-ready, race 窗口自然过, 但根因未消除 |
| 16:00 UTC | architect (魈) 误判 int004 worktree owner, 准备 `git worktree remove` | 险触发 6 worktree clobber (int004 实际是 hutao implement 路径) |
| 16:00–16:08 UTC | announce-before-touch SOP 救场 (hutao 群里 ack「int004 是我的」+ 阻止 remove) | 协议执行成本 = 8 分钟 + 3 次 cross-agent 消息往返 |
| 16:44 UTC | hutao 自主 `git worktree remove ~/repo/YiLuAn-int004` (PR #225 merge 后) | 正确路径 = owner 自己清 |

### 1.2 Root cause

各 worktree 无 ownership metadata, 任何 agent / session cd 进入即可干活. 工作流不阻止 cross-owner write. 同 agent 多 session 物理 race.

### 1.3 OPS-021 协议哲学族条款支撑

- 反模式 #14 «worktree 安全 announce-before-touch»: process 协议有效但执行重, 需工程化兜底
- 反模式 #6 «派单去重 (r)»: 派单方守门 (源头单 session) — 跟本协议**互补关系**: r = 源头守门, worktree-owner = 接收方守门 (worktree 拒绝 cross-owner)
- 凝光 OPS-021 (n) «物料 git push 才算 done»: 同理 «worktree owner 写文件才算声明», 推测不算

### 1.4 范围 (in-scope)

- 每 worktree 根目录加 `.OWNER` YAML 文件 (含 primary / shared_read[] / shared_write[] / notes)
- pre-push hook 强制校验 (cwd 在 worktree 根 + 当前分支 ≠ main 时):
  - primary == current agent → allow (含 main + group session same-agent)
  - shared owner (primary=shared) → 任意 agent allow
  - shared_write 含 current agent → allow
  - 否则 reject + 提示
- agent key 推导优先 `$OPENCLAW_AGENT_KEY` env, fallback workspace glob (`realpath $HOME/.openclaw/workspace-*`)
- 现有 worktree 跑一次初始化脚本补 `.OWNER`
- legacy worktree (无 `.OWNER`) graceful 跳过 check

### 1.5 前置依赖 (P0, 阻 implement) ⚠️

**OpenClaw gateway 必须注入 `OPENCLAW_AGENT_KEY` env 到 exec 子进程** —— 否则 hook 推导 fallback 到 workspace glob **不可靠** (多 workspace host 上).

**实施 task**: `S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION` P1 (uuid `61af6b2b-4638-47e7-aa5a-3b972b149df6`, coordinator own, 实施需帝君拍板或授权 OpenClaw 团队改源码).

**短期 fallback**: 用 workspace glob 推导 — 单 workspace host 准, 多 workspace **不准** → 必须 gateway 注入正式解决.

**ADR-0050 implement (S3-OPS-A) 阻塞此前置 task done**.

### 1.6 范围 (out-of-scope)

- 多 session 物理隔离 (`/tmp/yiluan-<session-id>/repo`) → 独立 task `S3-OPS-B-MULTI-SESSION-WORKTREE-ISOLATION` P1
- worktree lifecycle auto-cleanup (TTL / post-merge hook) → 独立 task `S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP` P2
- per-agent GitHub identity → 独立 task `S3-OPS-GITHUB-PER-AGENT-IDENTITY` P3

---

## 2. 方案对比

### 2.1 方案 A: `.OWNER` YAML + pre-push hook + OPENCLAW_AGENT_KEY (**推荐**, task r2)

**设计**: 见 §3.

**优势**:
- YAML schema 支持 shared 授权 (shared_read[] + shared_write[]) → 解 cross-agent legitimate cooperation (例如 hutao 借 ganyu worktree review)
- pre-push hook git 原生 (零运行时依赖)
- OPENCLAW_AGENT_KEY env 由 OpenClaw gateway 注入 = 跨 workspace host 准确, 不依赖 workspace path glob
- 跟 OPS-021 (r) 派单去重互补 = 双层防御 (源头 + 接收方)
- 兼容现有 worktree (init 脚本一次性补)

**劣势**:
- 阻塞前置 `S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION` (P1, 需 OpenClaw 改源码)
- YAML 解析依赖 `yq` (常见 ops 工具, 大部分 Linux 默认装)
- pre-push hook 可绕过 (`git push --no-verify`) → 工程兜底防误操作, 不防恶意

### 2.2 方案 B: 单行 ascii `.OWNER` + AGENTSQUAD_AGENT_KEY env (ADR v1 错版)

**已废弃**: 跟 task r2 不 align, 功能退化 (无 shared 授权), env 名错 (AGENTSQUAD_AGENT_KEY 是 taskboard cli 临时 require, 非 agent 识别), 漏前置依赖标注.

**hutao 01:33 UTC fact check 拆穿**: v1 ADR vs task r2 6 项冲突, 全部认错.

### 2.3 方案 C: pure process SOP (现状 baseline, 不推荐)

**设计**: 全靠 announce-before-touch + transcript 记忆, 无工程化护栏.

**优势**: 零代码

**劣势**:
- 已实测 protocol failure (2026-06-08 16:00 UTC architect 误判事故)
- O(N²) cross-agent 消息成本
- 不可扩展到 8+ agent / 20+ worktree

### 2.4 决定: 方案 A (r2)

理由:
- 跟既有 task r2 设计 align (避免协议碎裂)
- shared 授权解 cross-agent cooperation 真实需求
- OPENCLAW_AGENT_KEY env 跨 workspace host 准确
- 双层防御 (工程兜底 + process SOP) 比单层强
- 前置依赖明文标注 (避免 v1 漏标问题)

---

## 3. 详细设计

### 3.1 `.OWNER` YAML schema

**独占 worktree** (单 agent 私有):
```yaml
# ~/repo/YiLuAn-int004/.OWNER
primary: xiao
shared_read: [hutao, ganyu]   # 可 cd 看, 不可 push
shared_write: []              # 可 cd + push (需 primary 群里 announce)
notes: "USER-AUDIT + ADR/swap PR review (xiao 私有)"
```

**共享 worktree** (主仓 / hot spot):
```yaml
# ~/repo/YiLuAn/.OWNER (shared 主仓)
primary: shared
shared_write: [hutao, xiao, ganyu, keqing, ningguang]
notes: "main pull-only 默认, 切分支需在自己 worktree"
```

**schema 字段**:
- `primary`: string, agent_key (`xiao` / `hutao` / `ganyu` / `keqing` / `ningguang`) 或 `shared`
- `shared_read`: string[], agent_key list, 可 cd 进入 + read, 不可 push
- `shared_write`: string[], agent_key list, 可 cd + push (建议 announce-before-touch)
- `notes`: string, 文档化 worktree 用途

### 3.2 pre-push hook (`.git/hooks/pre-push` 或 `~/.openclaw/hooks/git-pre-push`)

```bash
#!/bin/bash
# pre-push owner check (S3-OPS-A ADR-0050 r2)

set -euo pipefail

# 1. agent key 推导 (优先 env, fallback workspace glob)
CURRENT_AGENT="${OPENCLAW_AGENT_KEY:-$(basename $(realpath $HOME/.openclaw/workspace-* 2>/dev/null | head -1) 2>/dev/null | sed 's/workspace-//')}"

if [ -z "$CURRENT_AGENT" ]; then
  echo "⚠️ cannot determine current agent, skipping owner check"
  exit 0
fi

# 2. main 分支跳过 check (pull-only 默认)
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" = "main" ]; then
  exit 0
fi

# 3. legacy worktree 跳过 check
OWNER_FILE=".OWNER"
if [ ! -f "$OWNER_FILE" ]; then
  echo "⚠️ no .OWNER file, skipping (legacy worktree)"
  echo "   建议: 跑 tools/worktree-init-owner.sh 补 .OWNER"
  exit 0
fi

# 4. 解析 .OWNER YAML
PRIMARY=$(yq '.primary' "$OWNER_FILE" 2>/dev/null)
SHARED_WRITE=$(yq '.shared_write[]' "$OWNER_FILE" 2>/dev/null)

# 5. 校验 (3 层授权)
# 5a. shared 主仓 → 任意 agent allow
if [ "$PRIMARY" = "shared" ]; then
  exit 0
fi

# 5b. primary == current agent → allow
if [ "$PRIMARY" = "$CURRENT_AGENT" ]; then
  exit 0
fi

# 5c. shared_write 含 current agent → allow
if echo "$SHARED_WRITE" | grep -q "^$CURRENT_AGENT$"; then
  exit 0
fi

# 6. reject
echo "❌ cross-owner push reject"
echo "   worktree primary: $PRIMARY"
echo "   shared_write: [$SHARED_WRITE]"
echo "   current agent: $CURRENT_AGENT"
echo "   → cd $HOME/.openclaw/workspace-$CURRENT_AGENT/... 或请 $PRIMARY 加你到 shared_write"
exit 1
```

### 3.3 `tools/worktree-add.sh` 包装

```bash
#!/bin/bash
# Usage: tools/worktree-add.sh -b <branch> <path>
# 自动写入 .OWNER YAML + 装 pre-push hook

set -euo pipefail

if [ -z "${OPENCLAW_AGENT_KEY:-}" ]; then
  # fallback workspace glob
  OPENCLAW_AGENT_KEY=$(basename $(realpath $HOME/.openclaw/workspace-* 2>/dev/null | head -1) | sed 's/workspace-//')
fi

if [ -z "$OPENCLAW_AGENT_KEY" ]; then
  echo "ERROR: cannot determine agent key" >&2
  exit 1
fi

git worktree add "$@"

# 解析 worktree path (最后一个非 flag arg)
WORKTREE_PATH=""
for arg in "$@"; do
  if [[ ! "$arg" =~ ^- ]]; then
    WORKTREE_PATH="$arg"
  fi
done

# 写入 .OWNER YAML
cat > "$WORKTREE_PATH/.OWNER" <<EOF
primary: $OPENCLAW_AGENT_KEY
shared_read: []
shared_write: []
notes: "auto-created by tools/worktree-add.sh"
EOF
echo "✅ .OWNER 写入: primary=$OPENCLAW_AGENT_KEY"

# 装 pre-push hook
HOOK="$WORKTREE_PATH/.git/hooks/pre-push"
if [ ! -f "$HOOK" ]; then
  cp tools/hooks/pre-push-owner-check "$HOOK"
  chmod +x "$HOOK"
  echo "✅ pre-push hook 装载"
fi
```

### 3.4 `tools/worktree-init-owner.sh` (legacy worktree 兼容)

```bash
#!/bin/bash
# 跑一次, 给所有现有 worktree 补 .OWNER (基于当前 agent_key)

set -euo pipefail

CURRENT_AGENT="${OPENCLAW_AGENT_KEY:-$(basename $(realpath $HOME/.openclaw/workspace-* 2>/dev/null | head -1) | sed 's/workspace-//')}"

if [ -z "$CURRENT_AGENT" ]; then
  echo "ERROR: cannot determine agent key" >&2
  exit 1
fi

git worktree list | awk '{print $1}' | while read WT; do
  if [ -d "$WT" ] && [ ! -f "$WT/.OWNER" ]; then
    cat > "$WT/.OWNER" <<EOF
primary: $CURRENT_AGENT
shared_read: []
shared_write: []
notes: "auto-init by tools/worktree-init-owner.sh on $(date -Iseconds)"
EOF
    echo "✅ $WT/.OWNER = primary=$CURRENT_AGENT"
  fi
done
```

### 3.5 主仓 `~/repo/YiLuAn/.OWNER` 特殊处理

主仓应配置 `primary: shared` + `shared_write: [hutao, xiao, ganyu, keqing, ningguang]`:

```yaml
primary: shared
shared_write: [hutao, xiao, ganyu, keqing, ningguang]
notes: "main pull-only 默认, 切分支需在自己 worktree"
```

由 implement task 手动写入 (init-owner 脚本默认 primary=current_agent, 不适用主仓).

### 3.6 `.gitignore` 更新

```
# 不 commit .OWNER (worktree-local 元数据)
.OWNER
```

**理由**: `.OWNER` 是 worktree-local 元数据 (跟具体 host 的 agent 绑定), 跟 branch 内容无关. 加 `.gitignore` 避免 cross-agent PR rebase 时 `.OWNER` 冲突. pre-push hook 读 local file 不读 git tree, 不影响功能.

---

## 4. 落地 plan

### 4.1 前置 (阻塞 implement)

`S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION` P1 (coordinator own) **必须先 done**:
- OpenClaw gateway 在 exec 工具触发子进程时, 注入 `OPENCLAW_AGENT_KEY=<session agent>` env
- 实施位置: `/usr/lib/node_modules/openclaw/` exec 工具 spawn 子进程位置
- 需帝君拍板或授权 OpenClaw 团队改源码

### 4.2 phase 1: tooling (S3-OPS-A-WORKTREE-OWNER-METADATA, hutao implement)

1. 创建 `tools/worktree-add.sh` (§3.3)
2. 创建 `tools/hooks/pre-push-owner-check` (§3.2)
3. 创建 `tools/worktree-init-owner.sh` (§3.4)
4. 更新 `.gitignore` 加 `.OWNER` (§3.6)
5. 跑 `worktree-init-owner.sh` 给现有 worktree 补 `.OWNER`
6. 主仓 `~/repo/YiLuAn/.OWNER` 手动写 shared 配置 (§3.5)
7. 文档 `docs/ops/worktree-ownership.md` (engineer-facing, ~80 lines, 含协议 + YAML schema + 增/删 worktree SOP + shared_read/write 授权流程)
8. 验证 11 AC (§6)

### 4.3 phase 2: 强制流程 (后续)

1. 所有 agent 切到 `tools/worktree-add.sh` 替代 `git worktree add` 裸命令
2. 监控: pre-push reject 计数 (metric 报表)
3. 阈值告警: 1 周内 ≥3 次 pre-push reject = 协议执行不到位 → 升级 `S3-OPS-B-MULTI-SESSION-WORKTREE-ISOLATION`

### 4.4 phase 3: 跟 ADR-0051 §3 协议哲学族 §3 «worktree 安全» 整合

- ADR-0050 (本) = 工程兜底
- ADR-0051 §3 = process SOP (announce-before-touch 5 步)
- 双层防御 = 工程层 (pre-push hook) + process 层 (announce-before-touch)

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| `git push --no-verify` 绕过 pre-push | 工程兜底失效 | hook 防误操作, 不防恶意; ADR-0051 §3 process SOP 补 |
| `.OWNER` 文件冲突 (cross-agent PR rebase) | 误改 owner 标识 | `.OWNER` 加 `.gitignore`, worktree-local 不 commit |
| `OPENCLAW_AGENT_KEY` env 缺失 (前置依赖未完成) | hook fallback workspace glob, 多 workspace host 不准 | §1.5 标前置依赖, ADR implement 阻塞 OpenClaw injection 完成 |
| legacy worktree 无 `.OWNER` | hook 跳过 (legacy 无保护) | `worktree-init-owner.sh` 兼容脚本, 跑一次补 |
| 主仓 `~/repo/YiLuAn` `.OWNER` 写错 (默认 primary=current_agent) | 主仓变私有, 其他 agent push reject | §3.5 显式手动写 `primary: shared` + shared_write list |
| `yq` 未安装 | hook YAML 解析失败 | hook fail-graceful (yq fail → skip + warn), 安装文档加 `apt install yq` |

---

## 6. Acceptance Criteria (S3-OPS-A-WORKTREE-OWNER-METADATA task, 11 AC)

- [ ] **AC#1**: 现有所有 worktree (`~/repo/YiLuAn*`) 根加 `.OWNER` 文件 (YAML 格式)
- [ ] **AC#2**: `.OWNER` schema 含 `primary` (agent_key 或 `shared`) + `shared_read[]` + `shared_write[]` + `notes` 字段
- [ ] **AC#3**: pre-push hook impl, cwd 在 worktree 根, 当前分支 != main 时强制 check `.OWNER`
- [ ] **AC#4**: cross-owner push 实证 reject (新建 test worktree, 切非 main 分支, 模拟另一 agent push → exit 1)
- [ ] **AC#5**: own-owner push 实证 OK (primary == current agent push 正常)
- [ ] **AC#6**: 跨 session 同 agent push 必须 OK (main session + group session 同 agent 不互斥, primary match 通过)
- [ ] **AC#7**: shared_write 列表的 agent push 实证 OK (含 shared owner 任意 agent allow)
- [ ] **AC#8**: 无 `.OWNER` 文件的 legacy worktree 跳过 check (graceful, 不破现状)
- [ ] **AC#9**: agent key 推导优先 `$OPENCLAW_AGENT_KEY` env, fallback workspace glob, 都无则 warn skip
- [ ] **AC#10**: 文档 `docs/ops/worktree-ownership.md` 说明协议 + `.OWNER` YAML schema + 增/删 worktree SOP + shared_read/write 授权流程
- [ ] **AC#11**: 与 OPS-021 (r) 协议 link, 互补关系明示

---

## 7. 后续

- ADR-0051 §3 «worktree 安全» 引用本 ADR 作强制实施细节
- 1 周后 metric review: pre-push reject 计数, 决定是否升级到多 session 物理隔离 (`S3-OPS-B-MULTI-SESSION-WORKTREE-ISOLATION`)
- `S3-OPS-WORKTREE-LIFECYCLE-AUTO-CLEANUP` P2 独立 task (PR merged 后自动 git worktree remove, TTL/post-merge hook)
- `S3-OPS-GITHUB-PER-AGENT-IDENTITY` P3 独立 task (解 self-approve 限制 + audit trail)

---

## 8. ADR v1 → v2 教训 (新 OPS-021 反模式 #21)

**「写 ADR 前必读 task description 全文」**:

- 我 (魈) 2026-06-09 01:30 UTC 写 ADR-0050 v1 时**没读 task description** (我 06-08 13:45 UTC 自己拆的 r2 设计就在 task 里), 自己重新发明轮子 → v1 vs r2 6 项冲突 (`.OWNER` 格式 / env 名 / 前置依赖 / AC 数 / hook 复杂度 / 文档路径)
- hutao 01:33 UTC fact check 拆穿 v1 → 我认错 + 写 v2 跟 r2 align
- **新规则**: architect 写 ADR / 设计文档前, 必须先 `get_task <task_id>` 读完整 task description (含既有设计 + AC) → 否则 ADR 重新发明 = 协议碎裂

这是 OPS-021 #18 (architect review 双标) + #19 (evidence-first 不查协议) 的**新实测**, 写入 ADR-0051 §2 «ADR-as-spec 自验前置» 作 case study.

---

End of ADR-0050 r2.
