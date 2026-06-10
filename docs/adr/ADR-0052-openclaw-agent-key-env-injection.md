# ADR-0052 — OpenClaw runtime: agent identity env injection (`OPENCLAW_AGENT_KEY`)

> 状态：**Proposed** · 作者：魈 · 日期：2026-06-09 · Accept 日期：TBD
> 关联：`S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION` task (P1, uuid `61af6b2b`, coordinator own) · ADR-0050 r2 §1.5 前置依赖标注 · `S3-OPS-A-WORKTREE-OWNER-METADATA` implement 阻塞此 task
> 触发：2026-06-09 01:33 UTC hutao 群里 ping 帝君「要不要立 OpenClaw issue」+ 我 fact check OpenClaw runtime gap 实测确认
> Owner Approval：**等帝君拍**（OpenClaw 主）

---

## 1. 背景

### 1.1 问题陈述

OpenClaw multi-agent runtime 中, exec 工具触发的子进程**没有 agent identity env**, 导致 worktree pre-push hook (ADR-0050 r2) 无法可靠识别当前 agent.

### 1.2 fact check (2026-06-09 01:43 UTC, host 在 OpenClaw 进程实测)

**现存 `OPENCLAW_*` env**:
```
OPENCLAW_SERVICE_KIND=gateway
OPENCLAW_SHELL=exec
OPENCLAW_GATEWAY_SERVICE_PID=135863
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service
OPENCLAW_SERVICE_MARKER=openclaw
OPENCLAW_PATH_BOOTSTRAPPED=1
OPENCLAW_WINDOWS_TASK_NAME=...
OPENCLAW_CLI=1
OPENCLAW_SERVICE_VERSION=2026.4.29
```

**关键缺失**: 无 `OPENCLAW_AGENT_KEY` (或同等 agent identity env).

### 1.3 现状: OpenClaw gateway 已有 agent identity, 只是没注入 exec 子进程

源码 inspect (`/usr/lib/node_modules/openclaw/`):

- `dist/acp-spawn-DsswNKre.js:481`: gateway 解析 agent id `parseAgentSessionKey(params.sessionKey)?.agentId` → `requesterAgentId`
- `dist/acp-spawn-DsswNKre.js:506, 732`: `requesterAgentId` 已被 spawn 子 session 使用
- `dist/exec-DuIacDCM.js`: exec 工具调 `mergeChildEnv(baseEnv, params.env)` → spawn child process env
- **gap**: exec 工具调 `mergeChildEnv` 时**没传** requesterAgentId, child env 无 agent identity

### 1.4 业务影响

- `S3-OPS-A-WORKTREE-OWNER-METADATA` (ADR-0050 r2) pre-push hook **依赖** `$OPENCLAW_AGENT_KEY` 推导当前 agent
- 短期 fallback (workspace glob `realpath $HOME/.openclaw/workspace-*`) **不可靠**, 多 workspace host 不准
- 无此 env → ADR-0050 r2 implement 阻塞 (S3-OPS-A 标 `depends_on: ['S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION']`)

---

## 2. 方案对比

### 2.1 方案 A: gateway exec 工具注入 `OPENCLAW_AGENT_KEY` env (**推荐**)

**设计**:

修改 `dist/exec-DuIacDCM.js` `mergeChildEnv` (或上游 exec 工具调用方), 在 baseEnv 合并阶段注入:

```js
// dist/exec-DuIacDCM.js (or upstream exec tool caller)
function mergeChildEnv({ baseEnv, env, platform, requesterAgentId }) {
  const resolvedEnv = {};
  for (const [key, value] of Object.entries(baseEnv)) {
    assignChildEnvValue({ env: resolvedEnv, key, platform, value });
  }
  // NEW: inject agent identity (if available from gateway sessionKey)
  if (requesterAgentId) {
    resolvedEnv.OPENCLAW_AGENT_KEY = requesterAgentId;
  }
  for (const [key, value] of Object.entries(env ?? {})) {
    assignChildEnvValue({ env: resolvedEnv, key, platform, value });
  }
  return resolvedEnv;
}
```

调用方 (exec 工具触发位置) 必须传 `requesterAgentId`:

```js
// exec tool caller (e.g., dist/agent-tools-DkIWbsdu.js:1882-2001)
const requesterAgentId = parseAgentSessionKey(sessionKey)?.agentId;
const childEnv = mergeChildEnv({ baseEnv, env, platform, requesterAgentId });
```

**优势**:
- 利用 gateway 已有的 `requesterAgentId` 解析 (acp-spawn-DsswNKre.js)
- 零新外部依赖 (复用 sessionKey 解析机制)
- backward compat: 旧子进程不读 env, 无副作用
- ADR-0050 r2 pre-push hook 可直接读 `$OPENCLAW_AGENT_KEY`
- 跟 OpenClaw 现有 `OPENCLAW_*` env 命名约定一致

**劣势**:
- 需修改 `/usr/lib/node_modules/openclaw/` (OpenClaw 源码)
- 需发新版本 npm publish + WSL host 升级 (`npm install -g openclaw@<new>`)
- WSL host 升级需重启 gateway service

### 2.2 方案 B: 应用层从 workspace path 推导 agent_key

**设计**: 应用层 (pre-push hook) 用 `realpath $HOME/.openclaw/workspace-* | sed 's/workspace-//'` 推导.

**已实测**: ADR-0050 r2 §1.5 标 fallback 用此方法.

**优势**: 不依赖 OpenClaw 改造, 应用层自助

**劣势**:
- 单 workspace host 准, 多 workspace host **不准** (多个 workspace-* 目录无法区分)
- multi-agent 同 host 设计 (设计文档 = 多 agent 共享 OpenClaw 进程, 每 agent 一个 workspace) 此 fallback 必然不准
- 是 **fallback** 不是正解, ADR-0050 r2 §1.5 已标

### 2.3 方案 C: gateway 注入 sessionKey 全文 + 应用层解析

**设计**: 注入 `OPENCLAW_SESSION_KEY` 全文 (例 `agent:xiao:agent_squad:group:776a55e9-d12e-4702-85ea-640714e8863a`), 应用层调 `parseAgentSessionKey` 解析.

**优势**: 一次注入支持多用途 (agent_key + session_id + channel)

**劣势**:
- session_key 含敏感信息 (group_id), 不应所有子进程读
- 应用层依赖 OpenClaw 解析逻辑 (耦合度高)
- 解析逻辑可能升级 → 应用层 break

### 2.4 决定: 方案 A

理由:
- 利用 gateway 已有 `requesterAgentId` 解析, 实施成本最低 (~30 lines OpenClaw 源码改 + npm publish)
- 命名约定一致 `OPENCLAW_AGENT_KEY` 跟 `OPENCLAW_SERVICE_KIND` etc. 同 prefix
- 应用层 hook 简单 `cat .OWNER` 对比 `$OPENCLAW_AGENT_KEY` 即可
- backward compat 完全 (旧子进程不读)
- ADR-0050 r2 pre-push hook 设计可直接 work

---

## 3. 详细设计

### 3.1 修改位置

**OpenClaw 源码** (`/usr/lib/node_modules/openclaw/` 或 GitHub repo):

| 文件 | 修改 |
|---|---|
| `dist/exec-DuIacDCM.js` `mergeChildEnv()` | 加 `requesterAgentId` 参数 + inject env |
| `dist/agent-tools-DkIWbsdu.js` `name: "exec"` handler | 调 `mergeChildEnv` 时传 `requesterAgentId` |
| (相关) exec 工具的 sessionKey 解析 | 复用 `parseAgentSessionKey()` (已存在 acp-spawn) |
| `docs/openclaw/env-vars.md` | 加 `OPENCLAW_AGENT_KEY` 说明 |

### 3.2 env 字段定义

```
OPENCLAW_AGENT_KEY=<agent_id>
```

- `agent_id`: lowercase letter agent identifier (`xiao` / `hutao` / `ganyu` / `keqing` / `ningguang`)
- 来源: `parseAgentSessionKey(sessionKey)?.agentId` (gateway 已实现)
- 缺失场景: sessionKey 无 agent prefix (例如 main session 启动早期), env 不设 (应用层 fallback)

### 3.3 backward compat

- 旧子进程不读 `OPENCLAW_AGENT_KEY` → 无副作用 (env 多一个无害)
- 新子进程 (ADR-0050 pre-push hook 等) 读不到 → fallback workspace glob (跟现在一样)
- 跨 OpenClaw 版本: 老 gateway 不 inject env → 子进程读不到 → fallback (兼容)

### 3.4 应用层使用 (ADR-0050 r2 pre-push hook 示例)

```bash
# .git/hooks/pre-push (ADR-0050 r2 §3.2)
CURRENT_AGENT="${OPENCLAW_AGENT_KEY:-$(realpath $HOME/.openclaw/workspace-* 2>/dev/null | head -1 | sed 's/workspace-//')}"
```

优先 env, fallback workspace glob (graceful degradation).

---

## 4. 落地 plan

### 4.1 phase 1: OpenClaw 源码改 (帝君 / OpenClaw 团队 own)

1. 修改 `dist/exec-DuIacDCM.js` `mergeChildEnv` 加 `requesterAgentId` 参数 + inject env
2. 修改 exec 工具 handler (agent-tools-DkIWbsdu.js) 调 mergeChildEnv 时传 requesterAgentId
3. 单测: exec 子进程 env 含 `OPENCLAW_AGENT_KEY=<expected>` (跨 5 agent: xiao/hutao/ganyu/keqing/ningguang)
4. backward compat 测试: 旧子进程 (不读 env) 不破

### 4.2 phase 2: npm publish + host 升级

1. OpenClaw 发新版本 (例 `2026.4.30` 或 `2026.5.0`)
2. WSL host `npm install -g openclaw@<new>` 升级
3. 重启 gateway service (`systemctl restart openclaw-gateway`)
4. 实测 (在 host 跑 `env | grep OPENCLAW_AGENT_KEY` 在 exec 子进程, 应有值)

### 4.3 phase 3: 应用层启用 (ADR-0050 r2 implement)

1. `S3-OPS-A-WORKTREE-OWNER-METADATA` task unblock (前置 done)
2. hutao implement ADR-0050 r2 (`.OWNER` YAML + pre-push hook + tools/* 脚本)
3. 实测 cross-owner push reject (AC#4) work

### 4.4 phase 4: 文档

1. `docs/openclaw/env-vars.md` 加 `OPENCLAW_AGENT_KEY` 说明
2. ADR-0050 r2 §1.5 更新前置依赖状态 (前置 → done)

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| OpenClaw 发版周期长 (~weeks) | ADR-0050 r2 implement 长期阻塞 | ADR-0050 r2 §3.2 hook fallback workspace glob, 单 workspace host 可工作 |
| `requesterAgentId` 解析失败 (sessionKey 格式异常) | env 缺失 → 应用层 fallback | hook fallback workspace glob (graceful) |
| 多 workspace host 短期 fallback 不准 | cross-owner push 误判 | 1. 升级 OpenClaw 后准 2. 多 workspace host 是少数 case |
| 旧 OpenClaw 版本不 inject env | 应用层 fallback | backward compat (兼容) |
| env 名跟其他 OPENCLAW_* 冲突 | 已 grep 无 | `OPENCLAW_AGENT_KEY` 是新名, 不冲突 |

---

## 6. Acceptance Criteria (对应 task `S3-OPS-OPENCLAW-AGENT-KEY-ENV-INJECTION`)

- [ ] **AC#1**: exec 工具触发的子进程实测 env 含 `OPENCLAW_AGENT_KEY=<agent key>`
- [ ] **AC#2**: agent key 与 session agent 字面一致 (xiao/hutao/ganyu/keqing/ningguang)
- [ ] **AC#3**: 不破坏现有 `OPENCLAW_*` env (`SERVICE_KIND / SHELL / GATEWAY_PORT / ...`)
- [ ] **AC#4**: backward compat: 旧子进程不读 env 时无副作用
- [ ] **AC#5**: 文档 `docs/openclaw/env-vars.md` 加 `OPENCLAW_AGENT_KEY` 说明
- [ ] **AC#6 (新增)**: gateway sessionKey 异常时 env 不 inject (应用层 fallback graceful)
- [ ] **AC#7 (新增)**: npm publish 后 WSL host 升级 + 重启 gateway 测试 env 实际存在

---

## 7. 后续

- ADR-0050 r2 implement 启动 (S3-OPS-A unblock)
- `docs/openclaw/env-vars.md` 整理所有 `OPENCLAW_*` env 用途 (本 ADR 新增 + 现有 SERVICE_KIND/SHELL/etc. 都补)
- 同模式扩展: 未来 OpenClaw 可能注入更多 agent context env (例如 `OPENCLAW_SESSION_KIND=group|direct`), 本 ADR 设立的 `OPENCLAW_AGENT_KEY` 是第一个 agent identity env

---

## 8. Owner 决策点

帝君需要回答:
1. ✅ / ❌ 接受方案 A (gateway 注入 `OPENCLAW_AGENT_KEY` env)?
2. 实施 Owner 是? (帝君自己 inject patch / OpenClaw 团队 / 其他)
3. 优先级是? (P1 当前, 是否升 P0?)
4. 发版节奏? (next minor 还是 next patch?)

我不进 wait 模式: 等帝君 PR review (本 ADR 通过 PR #229 push), 不需要群聊单字拍.

---

End of ADR-0052.
