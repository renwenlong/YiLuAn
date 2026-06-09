# ADR-0051: OPS-021 协议哲学族（multi-agent 协作护栏） — PM draft §1/§6/§7

> 状态：Draft（PM 视角 §1/§6/§7，待魈补 §2/§3/§4/§5 + 甘雨 own draft 整合）
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
| §2 cross-agent fact check | architect（魈）主导 |
| §3 worktree 安全协议 | architect 主导 |
| §4 task 操作合规 | architect 主导 |
| §5 metric self-check | architect 主导 |
| §6 物料交付协议 | **PM 主导** |
| §7 反复横跳熔断 + 单字回执 | **PM 主导** |

---

## §1 evidence-first 协议（PM own）

### §1.1 原则

任何升级/拍板/广播/桥接前必 **evidence verify**，不允许基于推理/过时信息/桥接消息/口头转述。

### §1.2 触发场景

PM 在以下场景必 evidence verify：
- 上呈帝君实情前 → fact check 当前 git/PR/session/cron 真实状态
- 拍板业务边界前 → grep ADR/PRD/源码自验（不靠桥接消息）
- 推架构师/协调者前 → 看对方实际进展（task status / PR / commit）不靠口头
- 升级 emergency 前 → fact check session 状态（status / latest tool call / yield 信号）

### §1.3 实证教材

- (j) PM 桥接前必 grep ADR 自验：甘雨桥接魈拍 C → PM 撤 v0.5 → 魈再拍 C2 → PM 自验 ADR-0046 §3.2 hash_inputs 才接（避免被动跟横跳）
- (l) emergency 升级前必 fact check session 状态：PM 09:00 UTC 误升级 emergency abort hutao main session（实际 main 已 yield + 自 disclose），甘雨 fact check 拦下
- (m) Owner 单字回执必 cross-check awaiting-approval 项：帝君 09:52 UTC「按 06-02 拍板冲」被魈扩张解读，魈第 6 次自承 retract
- (7) schema 类断言必须 set verify：PM「blocked 合法」基于 list_tasks 推测，胡桃 set verify mjs reject

### §1.4 违反成本

- 错升级 emergency = 浪费帝君 attention + 团队误判
- 错业务边界拍板 = implement 跑偏 + 大返工
- 错 schema 推测 = 引发后续误诊连锁

### §1.5 enforce 机制

- PM session 培训：每次 fact check 失败后写反案教材入 `s2-s3-implementation-retrospective-v1.md` §4
- 主动可推动作：PM 上呈帝君前 5min 内必跑实情 check（git log / PR list / session state）
- 协调侧 surface：协调者发现 PM 基于过时数据 → 立刻拦截

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
9. git checkout _pm_idle (回 idle 占位 branch, 不污染主 tree)
10. sessions_send 主动 surface PR URL 给全员
```

### §6.4 PM 主 tree 保护

PM 主 tree `~/repo/YiLuAn` PM 独占，不允许 hutao session 写入（OPS-021 worktree 单写协议）。PM 物料 PR 后立刻 `git checkout _pm_idle` 回 idle 占位。

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

### §6.8 enforce 机制

- PR description 强制写 "OPS-021 (n) 协议执行: ✅ 写文件 + commit + push + 开 PR 完整链路"
- 协调侧 fact check：协调者看 PM 主 tree git status 是否有 untracked 物料超 1h
- PR push 后 PM 必 sessions_send 主动同步 PR URL，不让接收方等 forward 看到延迟

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

## 待补章节（PM 不写）

- §2 cross-agent fact check（魈 own）
- §3 worktree 安全协议（魈 own）
- §4 task 操作合规（魈 own）
- §5 metric self-check（魈 own）

## 流程

1. PM draft §1/§6/§7（本文）→ 落 PR
2. 魈 draft §2/§3/§4/§5 → 同 PR amend
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
