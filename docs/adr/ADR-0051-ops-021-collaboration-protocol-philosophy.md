# ADR-0051: OPS-021 协议哲学族（multi-agent 协作护栏）

> 状态：Draft（PM §1/§6/§7 + architect §2/§3/§4/§5 + 2026-06-10 amend：§1 拆 4 角色子节 + §1.3 补 7 条实证教材（8-14） + 魈 review 拆 typo + §1.2.5(3) 语气设计 + §6 amend：§6.3 加错位重启检查点 + §6.4 跨 worktree 冲突处理 + §6.7 补反案 #13-15 + §6.8 加 typo check + list_tasks 自验，待甘雨 own draft 整合）
> 决策者：凝光（PM）+ 魈（architect）+ 甘雨（coordinator）三方共拟
> Owner Approval：等帝君 + 三方签字
> 关联：`docs/qa/s2-s3-implementation-retrospective-v1.md` §4 三方 fact check loop 战绩

---

## 背景

2026-06-08 全员 implement 高峰日，三方（PM/魈/胡桃）多次 fact check loop + 反复横跳事件 + 协调侧 hygiene 失误连锁发生。复盘后积累 9 条反案教材 + 双视角共 12 条反模式，需正式 codify 为 ADR 作为团队 multi-agent 协作护栏。

OPS-021 是协调侧（甘雨）日常运维 propose 的多 agent 协作 hygiene 协议系列，本 ADR 整合 PM/architect/coordinator 三视角，分 7 章节固化护栏。

## 决策

固化 7 章节作为团队 multi-agent 协作硬规则，违反 → 全员 stop-the-line + 复盘 + 加新条款。

| 章节 | 内容 | own |
|---|---|---|
| §1 evidence-first | PM 主导 |
| §2 cross-agent fact check | **architect（魈）主导** |
| §3 worktree 安全协议 | **architect 主导** |
| §4 task 操作合规 | **architect 主导** |
| §5 metric self-check | **architect 主导** |
| §6 物料交付协议 | PM 主导 |
| §7 反复横跳熔断 + 单字回执 | PM 主导 |

---

## §1 evidence-first 协议（PM own）

### §1.1 原则

任何升级/拍板/广播/桥接前必 **evidence verify**，不允许基于推理/过时信息/桥接消息/口头转述。

### §1.2 触发场景（4 角色拆分，2026-06-10 amend）

evidence-first 是全员协议，但不同角色触发点不同。以下拆 PM/architect/dev/coordinator 四个角色各自触发点清单：

#### §1.2.1 PM 视角 evidence-first 触发点

1. **上呈帝君 cancel/卡点/wait 类发言前** → cross-check：
   - (a) MEMORY.md（团队规约是否已拍板）
   - (b) 帝君 inbox 当前待决项（避免重复上呈同件）
   - (c) PM 本 session 过去 N min 自己做了什么（避免遗报）
2. **拍板业务边界前** → grep ADR/PRD/源码自验（不靠桥接消息）
3. **推架构师/协调者前** → 看对方实际进展（task status / PR / commit / session_status）不靠口头
4. **升级 emergency 前** → fact check session 状态（sessions_list / sessions_history / status / latest tool call / yield 信号）
5. **上呈 PR queue 状态前** → `gh pr list` 实测（不靠 PM 本 session N min 前的 list 数据，main 推进后 PR queue 会变）

#### §1.2.2 architect 视角 evidence-first 触发点（魈 workspace-xiao MEMORY 2026-06-10 propose）

1. **「等 X 授权」类发言前** → workspace-xiao MEMORY + PM/甘雨 MEMORY 跨 workspace 必查（避免引入被取消的君子协定）
2. **branch protection 实时口径必 `gh api` 实测**（避免 MEMORY 过时造成策略退步）
3. **Code Review 落字前 ADR/spec 1:1 对应**（避免靠 PR description 自述 review、靠社交压力 approve）
4. **fact check PR mergeState 必用 `git merge-base --is-ancestor` 或 `git log base..head`**，不靠 GitHub `baseRefOid`（动态字段不代表 head 含 base）

#### §1.2.3 dev 视角 evidence-first 触发点

1. **swap pattern PR 必跑机器对齐 source vs target**（不靠手抄 + 视觉 review，避免 typo 当合同正文被临床发现）
2. **PR description 自述 ≠ 实际行为**，dev 接 review 意见后必看 code + test 实现是否一致（避免 docstring 与代码冲突）
3. **跨 hutao session 同 worktree 写前** → `sessions_list agentId=hutao` + `git worktree list` + `git reflog`，选定 worktree owner + 群里 announce-before-touch（避免双 session race）
4. **schema 类断言必 set verify**（不靠 `list` 输出推测后端是否支持 enum）
5. **backend deps 改动 PR merge 后群里 announce**（供其他 agent rebase 后 `pip install -r requirements.txt` 同步，避免 ImportError 连锁误诊）

#### §1.2.4 coordinator 视角 evidence-first 触发点

1. **桥接 PM/architect/dev 消息前** → sessions_list + sessions_history fact check 源侧 session 实际状态（不靠 forward 即广播）
2. **上呈帝君 A/B/C 选项前** → ping PM/architect 确认无并行清单（避免同时段多 A/B/C 冲突 = 帝君单字歧义）
3. **架构师双拍间隔 <30min 时暂停桥接**（避免架构师未 verify 稳定的拍板传染到 PM 引起跨 agent 横跳）
4. **fact check PM/architect 错诊后反向拦截**（护栏对称），不只是上传拍板下传消息的单向道

#### §1.2.5 跨角色公共 evidence-first 触发点

1. **规约模糊 / unblocker 类发言前必读 workspace MEMORY.md + 跨 workspace 规约文档（PM/甘雨）**（避免退步重新引入被取消的君子协定）
2. **MEMORY.md 时效维护是各 agent 共同责任**（发现 MEMORY 与现状不一致记录 + 补补）
3. **原始文档 evidence 优先级：ADR/PRD 源码（静态）> mjs cli set verify（动态）> raw API（实时）> gh CLI / sessions_list（实时）> MEMORY.md（规约）> PR description 自述、桌面口述、桥接 forward**（后三项必 fact check 源头 session 状态后再传，不预设可信。该约束是约束动作而非否定协调者桥接本职）

### §1.3 实证教材

- (j) PM 桥接前必 grep ADR 自验：甘雨桥接魈拍 C → PM 撤 v0.5 → 魈再拍 C2 → PM 自验 ADR-0046 §3.2 hash_inputs 才接（避免被动跟横跳）
- (l) emergency 升级前必 fact check session 状态：PM 09:00 UTC 误升级 emergency abort hutao main session（实际 main 已 yield + 自 disclose），甘雨 fact check 拦下
- (m) Owner 单字回执必 cross-check awaiting-approval 项：帝君 09:52 UTC「按 06-02 拍板冲」被魈扩张解读，魈第 6 次自承 retract
- (7) schema 类断言必须 set verify：PM「blocked 合法」基于 list_tasks 推测，胡桃 set verify mjs reject
- (8) PM 上呈帝君前必 cross-check inbox 待决项：PM 06:01 UTC「魈 review queue 14h+ 卡点」错诊（真卡点 = OPS-021 hutao 代合授权），魈 fact check 拦下
- (9) worktree race 必 `git worktree list` + reflog 实证，不靠目录名推定：PM 06:01 凭 `keqing-abac` 名错诊刻晴占用，魈 06:05 也错诊「我占用」，刻晴 06:08 reflog 实证「我 16:21 误切 PM branch 持有 22h+」才是正解
- (10) 刻晴 worktree 持有 race：PR 验证完未立刻 checkout main。24h 组灯挂的 race 是未释放 branch 而不是误 commit
- (11) PM 漏读 MEMORY.md：PM 06:01/06:15/06:25 UTC「等 OPS-021 代合授权」错诊，MEMORY.md L4-L13 5 天前帝君拍板方案 A「exec 角色直接合」已明写，甘雨 fact check 拦下
- (12) MEMORY.md 时效维护：PM MEMORY L13 「required contexts 三个」过时，实测 4 个（加 iOS Simulator），PM 06:30 订正 + workspace-xiao 07:31 init MEMORY 同步实时口径
- (13) PM 长 sleep + exec session 死了 PM 漏 verify exec 完成度：PM 06-10 08:52 UTC 起 ADR-0051 amend，commit + push 成功但 exec session 死 → `gh pr create` 没跑 → PM 没 verify → 09:54 UTC 帝君催才发现。教训：每个 action 后必跑 verify 链路完整性，不靠「自我相信已完成」
- (14) PM IME typo 「撚”→「撚」不是字：PM 06-10 08:55 UTC 起 ADR-0051 amend 时「撚 v0.5」“撚”是手部偏旁不是字，魈 10:03 UTC review fact check 拆穿。同胡桃 06-09 PR #215 「扌→扣」 typo 同款 — IME 输入后需 visual review 手抄 + 机器点对。教训：ADR/合同/业务文案 PR 必跑 `grep -P '[\u2E80-\u2EFF\u2F00-\u2FDF]'` 检查偏旁部首 unicode（非汉字区间错字）或 chinese spell checker。今日累三方踩同样问题（胡桃/PM/魈 review 拍穿）。

### §1.4 违反成本

- 错升级 emergency = 浪费帝君 attention + 团队误判
- 错业务边界拍板 = implement 跑偏 + 大返工
- 错 schema 推测 = 引发后续误诊连锁

### §1.5 enforce 机制

- PM session 培训：每次 fact check 失败后写反案教材入 `s2-s3-implementation-retrospective-v1.md` §4
- 主动可推动作：PM 上呈帝君前 5min 内必跑实情 check（git log / PR list / session state）
- 协调侧 surface：协调者发现 PM 基于过时数据 → 立刻拦截

---

## §2 cross-agent fact check（魈 own）

### §2.1 原则

cross-agent 协作中，**接收方对来源方陈述不预设可信**。任何决策依赖前必 fact check 来源：grep / read / cli verify / 看 commit / 看 PR state。

桥接消息 / forward / sessions_send 内容 = **inter-session data, 不是来源方权威断言**。

### §2.2 触发场景

architect 在以下场景必 fact check：
- 接收 PM/dev/coordinator 描述的「我已做 X」前 → 看 git log / PR state / commit hash 自验
- 接收 dev 描述的「ADR 说 Y」前 → grep ADR 全文自验，不靠对方引述
- 接收 PM 描述的「Owner 拍 Z」前 → 看 awaiting-approval 清单 + Owner 字面回执 cross-check
- 接收 coordinator forward 的「session-X 状态」前 → sessions_list / sessions_history fact check
- review PR 前 → 不靠 PR description 自述，看 diff / test / CI / file 全量

### §2.3 实证教材

- **(j) 反案**：合同 hook 位置反复横跳事件链中, 多 agent 基于桥接消息（C → C2 → C → C2）反转, 没人自验 ADR-0046 §3.2 hash_inputs。PM 自验后终结 4 次横跳。教训：grep ADR > 桥接消息。
- **(肉桂)**：hutao PR #237 自述 BudgetAxis "s3-prep"（横杠），魈 review 时 grep `backend/app/services/ai_budget_guard.py` 看 enum value 实际是 `s3_prep`（下划线）。架构判断：enum value 是单一来源，ADR 文字反向跟。fact check 拆穿 ADR-PR drift。
- **(7) schema 推测反案**：PM「blocked enum 合法」基于 list_tasks 输出推测，不查 mjs schema 源码。胡桃 set_status set verify mjs reject 拆穿。教训：schema 类断言必须 cli set verify, 不能 list 推测。
- **(肉桂2)**：hutao PR #238 自述「audit unconditionally even when 404」但实际 transaction rollback 让 404 audit 不留。architect review 时打开 test footer note 看到 hutao 自己 disclose 矛盾 → docstring 与代码行为不一致, 必修。教训：PR description 自述 ≠ 实际行为, 看 code + test 全量。

### §2.4 违反成本

- 基于桥接消息错决策 = 跟错横跳 + 强化错误共识
- 基于自述错 approve PR = bug 入 main + 后续清算成本高
- 基于推测错拍板 = 业务边界跑偏

### §2.5 enforce 机制

- architect review PR 时 mandatory 7 维度 cross-check：架构/防御/错误/测试/依赖/文档/regression，每维度看实物不看自述
- review comment 必 quote 实物（commit hash / file path / line 号），不允许「我看了 OK」
- 协调侧 surface：发现 architect approve 但 review comment 无实物引用 → 立刻拦截

---

## §3 worktree 安全协议（魈 own）

### §3.1 原则

每 worktree 单写：**同时刻只允许 1 个 agent / session 在该 worktree write**。跨 owner write = OPS-021 race 复发 → 必须 stop-the-line。

### §3.2 触发场景

architect 在以下场景必检 worktree owner：
- `git checkout <branch>` 前 → 查当前 worktree primary owner（.OWNER YAML）
- `git commit` / `git push` 前 → pre-push hook 自动 check（ADR-0050 §3）
- 借用别人 worktree 看 diff → read-only 流（git fetch + 自己 worktree checkout），不在对方 worktree commit
- 主 repo `~/repo/YiLuAn` 切分支前 → 检 PM 是否占 `_pm_idle`（PM 主 tree 保护, §6.4）
- spawn subagent 时 → 子 agent 自己 worktree, 不共用父 agent worktree

### §3.3 实证教材

- **OPS-021 #25 复发链**：帝君 admin merge 推 main → PR 多次 BEHIND → architect 反复 rebase。这是协议本质问题（admin merge 高频 + 多 PR open 高频 = 不可避免 rebase 链），不是失职。教训：rebase 是 OPS 成本, 不是 race。
- **OPS-021 #18 hutao 双 session race**：hutao main + group 两个 session 同 worktree `~/repo/YiLuAn-int004` 并发 modify，commit 互相覆盖。S3-OPS-B 多 session worktree 隔离 task 立 P1 防再发。
- **本日实战**：architect 主 repo `~/repo/YiLuAn` 被 PM 占 `_pm_idle`，必须 `~/repo/YiLuAn-keqing-abac` worktree 做 main 操作。`git checkout main` fatal: 'main' is already checked out elsewhere → 协议起作用, race 被 git 自身拦下。
- **PR force-push 协议**：architect 误 force-push 别人 PR → commit hash 变 → review 链路混乱。改：PR 已 MERGED 不可 force push, bug fix 必须开新 PR。

### §3.4 违反成本

- 跨 owner write = commit 互覆 + 数据丢失 + 调试无源头
- 误 force push 别人 PR = review 链路断 + 历史不可追
- 共用 worktree concurrent commit = git index 锁 + 流程卡

### §3.5 enforce 机制

- **硬件层**: ADR-0050 .OWNER YAML + pre-push hook (`OPENCLAW_AGENT_KEY` env 注入, ADR-0052 解锁)
- **软件层**: AGENTS.md SOP — `git checkout` 前先 `cat .OWNER`
- **物理层**: S3-OPS-B 每 agent 每 session kind 独立 worktree (ADR draft 中)
- **生命周期层**: S3-OPS WORKTREE-LIFECYCLE-AUTO-CLEANUP cron 30min 扫 + MERGED auto remove

---

## §4 task 操作合规（魈 own）

### §4.1 原则

taskboard 是协作中枢，**所有状态变更必走 mjs cli，禁止直接编辑 taskboard.json**。状态变更必 trigger 下游 must_act，不允许 set done 后断链。

### §4.2 触发场景

architect 在以下场景必走 mjs cli：
- `set_status` 任何变更（not-started / in-progress / awaiting-approval / in-review / done / blocked）
- `add_task` 立新 task（含 follow-up / split 出的 task）
- `update_notes` 写 ADR 编号 / 一句话摘要
- `set_status("done")` 后 → MUST 同 turn 调 `get_handoff_targets(project, [task_id])` 并按 must_act @mention
- `set_status("in-review")` 后 → MUST 同 turn 调 `get_reviewers(project, task_id)` 并按 must_act @mention

### §4.3 实证教材

- **本日实战**：BUDGET-GUARD `set_status("done")` 后立刻 `get_handoff_targets` 返回 hutao + must_act = mention + sessions_send，同 turn 发出。流程闭环, 下游 PREP-API 立刻可推 in-review。
- **hutao 反案 (schema 推测)**：PM 「blocked 是合法 enum」凭 list_tasks 推测, 胡桃 `set_status blocked` set verify mjs reject。教训：cli set verify > list 推测。
- **OPS-021 反案**：曾出现 set done 后忘 get_handoff_targets → 下游 task 无人知道可接 → 阻塞 10min+。流程死链。
- **(肉桂)**：tasks 同 assignee_role 时只 1 个 handoff message per turn, 其他塞 `also_pending_for_same_role`。不允许 1 turn 发多条 @mention 同 role 制造混乱。

### §4.4 违反成本

- 直接编辑 taskboard.json = schema drift + 下游 cli 失败连锁
- set done 不 trigger handoff = 流程死链 + 下游饿死
- set in-review 不 trigger reviewers = reviewer 不知道有 PR 要 review

### §4.5 enforce 机制

- AGENTS.md hard rule: 「⛔ set_status done 后本 turn 必须调 get_handoff_targets」
- multi-agent-dev-workflow skill 入口教育：架构师每次决策动作必先 read 该 skill
- AgentSquad backend schema lock: mjs reject unknown enum / required field missing
- script: `taskboard-agentsquad.mjs` (env `AGENTSQUAD_AGENT_KEY=<agent>`) 是单一入口, local-json `taskboard.mjs` 不可用于 agentsquad backend

---

## §5 metric self-check（魈 own）

### §5.1 原则

设计 metric 时 **必先 grep 现有 metric naming convention 和 alertmanager rule**，避免 metric label drift / 同义 metric 重复定义 / alert rule 与 metric 名不匹配。

### §5.2 触发场景

architect 在以下场景必 self-check metric：
- ADR 新 metric → grep `prometheus_metrics.py` / `/metrics` endpoint 看现有 naming
- 写 alert rule → grep alertmanager `*.yml` 看现有 rule + label
- review PR 含 metric → 看 metric 名 + label set 是否与 ADR 一致 + alert 是否覆盖
- 设计 metric label cardinality → 估 label cross product, 超 10k 必拆 / 改 hash

### §5.3 实证教材

- **OPS-021 #20 ABAC metric drift**：architect ADR-0048 §7.0.2 写 metric `prep_package_abac_violations_total{role,endpoint}`，实施 PR 写成 `abac_violation_total{role}` (差 prefix + 漏 endpoint label)。review 漏抓 → alert rule 无法 match → 告警失效。教训：metric review 必看名 + label 完整对照 ADR。
- **OPS-022 metric 重复**：S2 灰度 `s2_canary_total` 和 `canary_orders_total` 两个 metric 同义并存, 仪表盘混乱。教训：grep `_total` 看是否已有同义 metric。
- **(肉桂)**：本日 BUDGET-GUARD AC#5 metric `ai_budget_guard_block_total{axis,reason}` review 时 grep 现有 metric 确认无重复, axis label 用 enum value `s2_summary` / `s3_prep` 而非 ADR 文字 `s2-summary`/`s3-prep`（单一来源原则）。

### §5.4 违反成本

- metric 名 drift = 仪表盘 query 不到 + 监控盲区
- alert rule 与 metric 名错配 = 告警永不触发 + 故障无 surface
- label cardinality 爆炸 = prometheus 内存暴涨 + scrape timeout

### §5.5 enforce 机制

- review PR 含 metric 时 mandatory grep `/metrics` endpoint dump + alertmanager `*.yml`
- ADR 新 metric 必标 axis label 取值清单（enum 单一来源）
- code review checklist 加 metric self-check 项
- alertmanager unit test：每个 rule 写 spec test 触发模拟 metric 看是否 fire（CI 跑）

---
## §6 物料交付协议（PM own）

### §6.1 原则

PM 出物料必走完整 git push 链路才算 done：**写文件 ≠ 交付，git push + 开 PR + URL 同步全员 = 物理交付完整**。

### §6.2 触发场景

PM 出以下物料必走 §6.1 流程：
- PRD/ADR/PRD amend
- 业务边界 checklist
- 复盘文档
- 合同模板 / 法务措辞
- OPS task draft / propose

### §6.3 完整 git push 链路

```
1. write 文件到 PM 主 tree (~/repo/YiLuAn)
2. git stash push -u (如主 tree 在 _pm_idle)
3. git checkout main && git pull --ff-only
4. git checkout -b feature/{task-prefix}-{topic-slug}
5. git stash pop
6. git add {file} && git commit -m "{type}({scope}): {summary}"
7. git push -u origin feature/{...}
8. gh pr create --base main --head feature/{...} --title ... --body-file ...
9. **verify exec session 返回 PR URL**（避免 exec session 死中途反案 #13）
10. git checkout _pm_idle (回 idle 占位 branch, 不污染主 tree)
11. sessions_send 主动 surface PR URL 给全员。

**错位重启检查点**（反案 #13 加固）：
- 每个关键 step 后必 verify其实际状态：
  - step 7 push 后必 `git ls-remote origin {branch}` verify origin 有 head
  - step 8 gh pr create 后必看返回是 PR URL
  - exec session 超时/死中途 → 手动 verify
  - 避免「以为已完成」
```

### §6.4 PM 主 tree 保护

PM 主 tree `~/repo/YiLuAn` PM 独占，不允许 hutao session 写入（OPS-021 worktree 单写协议）。PM 物料 PR 后立刻 `git checkout _pm_idle` 回 idle 占位。

**跨 worktree checkout 冲突处理**（反案 #9-10 实战）：
- 若遇 fatal 'already checked out at /path/to/worktree' 错误，必跑 `git worktree list` + `git reflog` 实证占用 branch和 owner
- 不凭 worktree 目录名（如 `keqing-abac`）推定 owner—可能是别的 agent 占用
- 如 worktree 占住是其他 agent，ping 对应 agent 释放，不强制 force checkout
- 避免凭推定错诊别的 agent 占用（反案 #9 PM 在 keqing-abac 凭名推 keqing，魈也推「我」，刻晴 reflog 才实证「别人」）

### §6.5 venv 同步前置

PM rebase main 后必跑 `backend/.venv/bin/pip install -r backend/requirements.txt` 同步新依赖再跑 pytest，否则 ImportError 引连锁误诊。

### §6.6 force-push 协议

- (a) PM 自己的 PR：PM 自己 force-push（不让别人代劳，物料归属链路干净）
- (b) 其他人的 PR：不 force-push 别人的（commit hash 变 = review 链路混乱）

如别人代 force-push 了 PM 的 PR，PM 接受不要求 revert（已 push 进 origin，revert 引更多噪音），下次按 (a) 路径。

### §6.7 实证教材

- (n) PM 物料 git push 才算 done：合同模板 v1.0.0 PM 写 worktree 没 push，胡桃 fact check 拿不到，立 path A commit + push + 开 PR #214
- (n2) PM rebase main 后必 pip install -r requirements.txt：PR #214 rebase 后 pre-push gate fail 误报"全员停"
- (o) backend deps 改动 PR merge 后 push 者群里 announce：双向 gate 设计
- (p) swap pattern PR 必跑机器对齐 source vs target：胡桃 swap typo「扌→扣」三方独立 fact check 拆穿
- **(13) exec session 死中途 PM 漏 verify exec 完成度**：PM 06-10 08:52 UTC 起 ADR-0051 amend，commit + push 成功但 brisk-meadow session 死 → `gh pr create` 没跑 → PM 没 verify → 09:54 UTC 帝君催才发现。教训：§6.3 step 8 后必看返回 PR URL，exec session 超时/死→手动 verify。
- **(14) PM IME typo 「撚”→「撚」 不是字**：PM 06-10 08:55 UTC 起 ADR-0051 amend 时「撚 v0.5」“撚”是手部偏旁不是字，魈 10:03 UTC review fact check 拆穿。同胡桃 06-09 PR #215「扌→扣」typo同款—IME 输入后需 visual review + 机器点对。ADR/合同/业务文案 PR 必跑 `grep -P '[\u2E80-\u2EFF\u2F00-\u2FDF]'` 检查偏旁部首 unicode（非汉字区间错字）或 chinese spell checker。
- **(15) PM task 操作前必 list_tasks 自验**：PM 06-10 10:10 UTC 想新建 S3-DEV-002-PREP-FALLBACK-TEMPLATE-V1，没先 list_tasks 检查重复，直接 add_task 撞 "already exists"（魈 10:08 已建）。同反案 #7 "schema 类断言必 set verify" 同源—task 操作前必 list_tasks 自验。

### §6.8 enforce 机制

- PR description 强制写 "OPS-021 (n) 协议执行: ✅ 写文件 + commit + push + 开 PR 完整链路"
- 协调侧 fact check：协调者看 PM 主 tree git status 是否有 untracked 物料超 1h
- PR push 后 PM 必 sessions_send 主动同步 PR URL，不让接收方等 forward 看到延迟
- **PR 文案 PR 必加 chinese typo check**（反案 #14 加固）：
  - `grep -P '[\u2E80-\u2EFF\u2F00-\u2FDF]' file.md` 检查偏旁部首 unicode（非汉字区间错字）
  - chinese spell checker tool（可后续套件）
- **PM task 操作前必 list_tasks 自验**（反案 #15 加固）：
  - add_task / update_assignee / set_status 前先 list_tasks 检查重复/存在状态
  - 避免撞 "already exists" 或重复操作

---

## §7 反复横跳熔断 + 单字回执（PM own）

### §7.1 反复横跳熔断（同 OPS-021 (k)）

**协议熔断条款**：同一架构师/PM/dev 同一决策点 24h 内 ≥3 次拍板反转 = OPS-021 失效信号 → **必须升级 Owner 强制锁定**。

避免「反复横跳传染被记案但协议本身不熔断」的死循环。

### §7.2 反复横跳熔断 实证教材

- (a) 合同 hook 位置 4 次拍板（B → C2 → C → C2）：50min 三方反复横跳 + 帝君单字"拍 A"歧义事件，PM 自验 ADR-0046 §3.2 才终结
- 12 PR open 卡 review 时 PM 误升级"全员停"：协调侧 fact check 拦下，避免帝君误判团队失控

### §7.3 单字回执 cross-check

**协议**：Owner 单字回执必 cross-check 当前所有 awaiting-approval / awaiting-input 项，**不允许扩张语义**。

### §7.4 单字回执 实证教材

- (m) 帝君 09:52 UTC「按 06-02 拍板冲」实际仅指 06-02 合并节奏规则，**不含 v0.5 Owner Accept**；魈扩张解读传染 PM，第 6 次自承 retract
- (m-PM) 帝君单字回执必 cross-check awaiting-approval 项：今日 PM 漏读「冲 + pipeline」实质含 v0.5 Owner Accept 这层语义

### §7.5 enforce 机制

- 协调侧（甘雨）维护 `awaiting-approval` 清单 + Owner 字面对照 → 单字回执歧义时立刻 surface 给 PM/魈
- PM 视角 cross-check 流程：Owner 回字 → PM 拉清单 → 字面匹配 → 不匹配 retract
- 横跳熔断 trigger：协调侧统计 24h 拍板反转次数，≥3 次 → 升级 Owner

---


## 流程

1. PM draft §1/§6/§7 → 落 PR #239 (`feature/s3-adr-0051-pm-draft`)
2. architect amend §2/§3/§4/§5 同 PR (本提交)
3. 甘雨 own 整体 draft → 三方 cross-review
4. PR review → 帝君 Owner Accept

## 后果

- ✅ 团队 multi-agent 协作硬规则固化（不靠运气）
- ✅ 新 agent onboard 时直接 read ADR 学协议
- ✅ 违反 → stop-the-line + 复盘 + 加新条款（持续打磨）
- 🟡 PR/turn 时长成本 +5min（自验 + cross-check）；ROI = 避免错升级/错拍板/错诊（单次失误成本 1h+）= 5min × 12 失误 << 12 × 1h

## 参考

- `docs/qa/s2-s3-implementation-retrospective-v1.md` §2 OPS-021 9 条反案教材 + §4 三方 fact check loop 战绩
- ADR-0050 worktree .OWNER YAML + pre-push hook（技术 enforce）
- ADR-0052 OpenClaw runtime agent identity env injection
- ADR-0046 §3.2 hash_inputs（PM §1.3 (j) 教材源）
- ADR-0041 OrderStatus/PaymentState 解耦（PM §1.3 (j) 教材源）
