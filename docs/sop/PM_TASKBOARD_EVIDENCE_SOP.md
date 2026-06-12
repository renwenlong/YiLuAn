# PM Taskboard Evidence SOP

**版本**: v1.1 (2026-06-12, r1 amend 吃 keqing review M1-M3)
**作者**: 凝光 (PM)
**审核**: 魈 (architect, AC#6 review pending) / 刻晴 (tester, 02:46Z approve)
**关联 task**: S3-OPS-PM-LISTTASKS-EVIDENCE-AUDIT (uuid `a771cc8c-957a-451a-95d7-ac5c7cc093c0`)
**关联 ADR**: ADR-0051 §6.8 enforce (待 r3 amend)
**关联反案**: #15 (PM evidence audit), #28 (本日新 hutao 不等主 PRD merge), #29 (本日新 PM 引用 ADR 必 verify 主题字面)

> **适用范围 (r1 amend, 吃 keqing M1 选项 A)**: 虽题为 "PM SOP", 但 §2.1 evidence 顺序 + §2.3 命令模板字面**对所有角色 (PM/dev/tester/architect/coordinator) 同样硬适用**. tester / dev / architect 用 mjs 时同套规则, 无角色特殊化. 后续 r2 amend 可重命名为 `TASKBOARD_EVIDENCE_SOP.md` 去 PM 前缀.

## 1. 起源 (AC#1 误判链路复盘)

### 1.1 原始误判事件 (2026-06-10)

PM 用 `list_tasks | grep` 查找 task 时漏读两个真实存在的 task, 误判为"task 不存在", 错误上升为"协议违反":
- 漏读 task: `S3-DEV-005-CACHE-INVALIDATE`, `S3-DEV-003-PRECHECK-BACKEND`
- 错误判断: PM 当时声称这两个 task 不存在, 推论"流程缺失"
- 纠正: 魈用 `get_task` 单点复核证明两个 task 真实存在, PM 撤回

### 1.2 失败原因分析

| 失败模式 | 触发条件 | 隐蔽度 |
|---|---|---|
| **超长 JSON truncate** | `list_tasks` 返回 100+ task 时 stdout buffer 截断 | 高 (无报错, silent loss) |
| **shell pipe 缓冲限制** | `grep` 在 pipe 中截断长行 | 高 (无报错) |
| **regex 路径漏匹配** | grep pattern 大小写 / 部首字 / 分隔符不匹配 | 中 |
| **status filter 默认排除** | `list_tasks --status in-progress` 漏掉其他状态 task | 中 (PM 易忘) |
| **pagination 默认 limit** | mjs 默认 page=1 size=20, PM 不感知 | 低 (mjs 提示) |
| **json.load 解析失败** | 超长 JSON python `json.load(sys.stdin)` truncate 报 `Unterminated string` | 中 (有报错但 PM 易忽略) |

### 1.3 本日 (2026-06-12 02:26 UTC) 再次重现

PM 在帝君 @all action turn 内, 试图用以下命令查 in-progress task:

```bash
RUN list_tasks yiluan-study-iter 2>&1 | python3 -c "
import json,sys
data = json.load(sys.stdin)
..."
```

实际报错: `json.decoder.JSONDecodeError: Unterminated string starting at: line 536 column 22 (char 56296)` — PM 又一次踩到 JSON truncate 坑.

**当时正确做法**: 直接 `get_task <id>` 单点查询 (后续 PM 改用 `get_task S3-TEST-007-RECOMMENDATION-API-E2E` 正常拿到状态).

**root cause (r1 amend, 吃 keqing M3)**: PM 起手默认 `list_tasks | python3 json.load` muscle memory, 即使前已有反案 #15 教训, 此 muscle memory 需通过 §3 ADR-0051 §6.8 trigger 自检字面强化. PM turn 内开场必跑 self-audit "我在用 evidence 顺序首选 (get_task) 吗?" 而非凭 muscle memory 起手 list_tasks pipe.

## 2. AC#2: PM SOP 字面规则

### 2.1 evidence 顺序 (hard rule)

PM 查询 task 时**必须按以下优先级**:

1. **First choice**: `get_task <project> <task_id>` — 单点精确查询, 无 truncate 风险, 返回完整字段
2. **Second choice**: raw API `curl` 按 task_name 精确查询 — 当 task_id 形态不确定时兜底
3. **Third choice (only for batch overview)**: `list_tasks <project> [--status X]` — 仅用于**批量概览**, **不作 task 不存在的最终证据**

### 2.2 禁止行为

| 禁止 | 原因 | 替代 |
|---|---|---|
| ❌ `list_tasks \| grep <id>` 没命中 → 判 task 不存在 | grep 在长 JSON / pipe 中 silent truncate | ✅ `get_task <id>` 单点复核 |
| ❌ `list_tasks --status in-progress` 没结果 → 判无 in-progress | status filter 默认排除 done/awaiting 等 | ✅ `list_tasks` 全量后 client-side filter |
| ❌ python `json.load(stdin)` 无 try/except, 报错就退出 | JSON truncate 不抛 Python 友好错 | ✅ 用 `jq` 替代, jq 对 truncate 更鲁棒 |
| ❌ PM 把"基础事实不成立"的判断写入团队反案 | 反案是教材, 错的反案误导团队 | ✅ 反案前先三方 fact check, 错的反案立即撤回 |
| ❌ tester/PM `set_status("done")` 后不调 `get_handoff_targets`, 直接 stop (r1 amend, 吃 keqing M2) | 流程死链, 下游 agent 不知道接手 | ✅ done 后**本 turn 必须**调 `get_handoff_targets` 并按 `must_act` 通知下游 (multi-agent-dev-workflow skill 已有规则, 合并放此处同源) |

### 2.3 命令模板 (AC#5 可复制)

```bash
# 1. inline env (避免 shell export 跨 child process 问题)
RUN() {
  AGENTSQUAD_TOKEN="$(cat /tmp/tk)" \
  AGENTSQUAD_BASE_URL=http://localhost:8000 \
  AGENTSQUAD_AGENT_KEY=<your-agent-key> \
  node ~/.openclaw/skills/multi-agent-dev-workflow/scripts/taskboard-agentsquad.mjs "$@"
}

# 2. 单点查询 (PM evidence 首选)
RUN get_task yiluan-study-iter <TASK_ID>

# 3. 批量概览 (不作 task 不存在最终证据)
RUN list_tasks yiluan-study-iter 2>&1 | jq -r '.data.tasks[] | "\(.id) | \(.status) | \(.assignee)"' | head -50

# 4. raw API 按 task_name 精确查询 (兜底)
curl -s -H "Authorization: Bearer $(cat /tmp/tk)" \
  "http://localhost:8000/api/v1/boards/<BOARD_UUID>/tasks?q=<task_name_substring>" | jq

# 5. project 概览 (ready_tasks / in-progress 汇总)
RUN get_project_status yiluan-study-iter
```

## 3. AC#3: ADR-0051 §6.8 enforce 升级提案

ADR-0051 r3 amend 加入以下规则 (PM 自动 trigger):

```markdown
### §6.8 PM evidence 顺序 (enforce, r3 amend 2026-06-12)

PM 对 task 状态/存在性的所有判断, evidence 优先级如下:

1. `get_task <id>` 精确查 (默认)
2. raw API task_name 精确查 (兜底)
3. `list_tasks` grep 仅用于批量概览, **不作 task 不存在的最终证据**

违反此顺序 PM 任何"task 不存在"或"协议违反"判断**自动 retract**, 不进团队反案.

trigger 自检 (PM turn 内开场):
- 当 PM 准备说 "task X 不存在" / "流程缺失" / "协议违反" → 必须 first 跑 `get_task X` 验证
- 反案族 #15 case 即为此规则触发条件 (PM 在 2026-06-10 漏读 S3-DEV-005/003 案例)

本规则 enforce ≠ 自动化, 由 PM 自律 + 团队 cross-check (魈 / hutao 看到 PM 判断不一致时 challenge).
```

## 4. AC#4: 反案族补充 (memory/2026-06-10.md 已有, 本 doc 补)

### 反案 #15 (2026-06-10 PM evidence audit)

**事件**: PM list_tasks 漏读两个真实存在的 dev task, 误判协议违反.
**纠正**: 魈 get_task 单点复核纠正.
**教训**: PM evidence 不准也必须撤回, 不把基础事实不成立的 case 写入团队反案.
**enforce**: ADR-0051 §6.8 PM evidence 顺序硬规则.

### 反案 #28 (2026-06-12 本日新, hutao 不等主 PRD merge 起手 = 最佳实践)

**事件**: hutao 在 V15 主 PRD spec doc patch PR (#284) 还没 merge 时, 就并行起 S3-DEV-006 实施 (PR #285 createdAt 2026-06-11 23:42:20Z) **领先于 V15 PR (#284 mergedAt 2026-06-12 00:03:59Z) 22 分钟**, V15 PR 后 16 分钟 impl PR merged (#285 mergedAt 00:21:54Z).
**判定**: 这是务实最佳实践, 不是协议违反.
**规则**: 当 spec draft v1 final 已 lock 且通过 review, 实施方可直接吃 draft 起手, 不必等主 PRD 字面 merge. 适用前提:
- spec draft 已 v1 final lock (字面 reviewer 已点 ratify)
- 主 PRD patch 只是字面 merge 不会引入新逻辑
- impl PR 引用 spec draft sha (反案 #23 跨文档 reference 一致性)

**PM 教训**: PM 通知前必 verify task 实际状态 (raw API task.status), 不假设 dependency merge 顺序 = 实施 trigger 顺序.

### 反案 #29 (2026-06-12 本日新, PM 引用 ADR 必 verify 主题字面)

**事件**: PM 在建 S3-DEV-006-FOLLOWUP-ADMIN-OVERRIDE task 时, AC#1 字面写 "ADR-0046 amend 或新 ADR 决定 schema 位置". 魈 evidence-first verify (06-12 00:58Z) 发现 ADR-0046 主题是 "contract storage extension", 与 admin override 无关. AC#1 引用错.

**根因**: PM 建 task 时复制粘贴前一个 task 的 ADR-0046 reference, 没核 ADR 主题.

**规则升级** (反案 #14 延伸):
- 反案 #14 (旧): PM 引用 ADR 前必 `ls docs/adr/` 核实文件存在
- 反案 #29 (新): PM 引用 ADR 前必 `ls docs/adr/` + grep ADR 主题字面 verify 主题相关, 不只查文件存在

**enforce**: PM 建 task 时, 任何 ADR-XXXX 引用必同 commit 提供 grep 主题字面 evidence (1 行 `grep -l "<keyword>" docs/adr/ADR-XXXX*.md` 或 `head -5 docs/adr/ADR-XXXX*.md`).

## 5. AC#6: review by architect (魈)

本 doc 由魈 review:
- 字面与 ADR-0051 §6.8 enforce 提案是否兼容?
- 反案 #28 / #29 规则是否需要协议哲学族编号 (OPS-021)?
- 命令模板是否需要补充其他 mjs action?

review pass 后本 task → done, PM 完成 design own.

## 附录: 本 SOP 不替代的事项

- **不替代** PM 业务判断 (业务边界守门仍 PM 主观判断)
- **不替代** 协议哲学族 ADR-0051 主体 (本 SOP 仅 §6.8 局部 enforce)
- **不替代** 三方 fact check loop (PM 不顽固, 接受 cross-check 反向纠正)

---

End of SOP v1.0.
