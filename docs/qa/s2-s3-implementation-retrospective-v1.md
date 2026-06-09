# S2 灰度上线 + S3 implement 复盘 v1（2026-06-08 沉淀）

> 产出：凝光（PM）@ 2026-06-08 16:50 UTC
> 触发：帝君「上面问题处理完，继续推进新开发」+ PM 主动 D4 路径
> 范围：S2 灰度门 06-06 收口 → S3 implement 第一阶段 06-08（合同主线收口）
> 目的：业务复盘 + 流程沉淀 + 给 S4 立项参考

## 1. 摘要（30s）

S2 灰度门 06-06 16:15 UTC 四方签字闭环，mock 灰度上线（PR #210 whitelist 占位 + canary 栈跑稳）；S3 implement 06-07/08 两天合 22+ PR，合同主线（保险/契约/PDF/审计/补偿）完工，AI 准备包链路（关键词/budget/hot-reload）推进中，信任前置 UI 等 backend 拆分。

**PM 视角：今天是团队成熟度阶跃日**。OPS-021 协议哲学族从 (a) 反复横跳 → (l) emergency 升级前 fact check → (n) PM 物料 git push 才算 done 一路沉淀；三方 fact check loop（PM/魈/胡桃）打破单方推理 + 桥接消息 ≠ Owner Accept 等抽象原则在现场被实证。

## 2. S2 灰度上线复盘

### 2.1 关键路径

| 里程碑 | 时间 | 关键产物 |
|---|---|---|
| S2-TEST-004 v1（真 wxpay 路径） | 06-04 之前 | 卡帝君 3 物料 65h+ |
| 帝君拍 "先 canary mock 跑通" | 06-06 10:04 UTC | acceptance v2 |
| S2-TEST-004 v2 §1 资金线主体 PASS | 06-06 10:12 UTC | mock-pay/mock-sms 链路通 |
| canary OPS 2 gap 修（rebuild + seed companion） | 06-06 ~14:00 UTC | gap 1 rebuild f0b8e1b + gap 2 seed_canary.py PR #201 |
| §6 四方签字闭环 | 06-06 14:38-16:15 UTC | 刻晴 → PM → 魈 → 帝君 |
| A2 实际灰度上线（10% 内部白名单 mock）| 06-08 03:21 UTC 帝君拍 | task 立 / PR #210 whitelist 占位 |

### 2.2 业务侧学到的

1. **真物料路径周期不可控**：wxpay 沙箱号 + 阿里云 SMS + 企微 webhook 三件全卡企业实体认证（营业执照/法人/对公账户/医疗资质）= PM 自助不可能。胡桃 PR #188 canary mock 栈是务实兜底，把 mock 灰度门和 real 灰度门解耦为 S2-TEST-004 / S2-TEST-004-REAL 两个 task。
2. **mock 灰度门 ≠ 真灰度上线**：四方签字只是 acceptance 路径完成，实际流量切（A2 内部白名单）是后续动作。06-06 16:15 UTC 帝君 "mock 灰度批准" 和 06-08 03:21 UTC "拍 A 启动 10% 白名单" 是两件事，PM 一度混淆引发协调侧 retract。
3. **白名单 task 仍卡帝君外部输入**：S2-OPS-A AC#1 等帝君指派 5-10 同事手机号 + 5 团队成员真手机号，8h+ 卡板，PM 加 cron 白名单 + task notes ⏸ AWAITING marker 兜底。

### 2.3 协调侧学到的（OPS-021 雏形）

| 反案 ID | 教训 | 现场触发 |
|---|---|---|
| (a) 反复横跳 | 架构师/PM 同一决策点 24h 内 ≥3 次反转 = 协议失效信号 | 合同 hook 位置 4 次拍板（B → C2 → C → C2）|
| (j) PM 桥接前必 grep ADR 自验 | 桥接消息 ≠ Owner Accept | 甘雨桥接魈拍 C → PM 撤 v0.5 → 魈再拍 C2 → PM 自验 ADR-0046 §3.2 hash_inputs 才接 |
| (l) emergency 升级前必 fact check session 状态 | forward 即广播 = 误升级风险 | PM 09:00 UTC 误升级 emergency abort hutao main session（实际 main 已 yield + 自 disclose） |
| (m) Owner 单字回执必 cross-check awaiting-approval 项 | 单字回执可能不只对应一件事 | 帝君 09:52 UTC「按 06-02 拍板冲」被魈扩张解读为含 v0.5 Owner Accept，魈第 6 次自承 retract |
| (n) PM 物料 git push 才算 done | 写文件 ≠ 交付 | PM 合同模板写到 worktree 没 push，胡桃 fact check 拿不到，立 path A commit + push + 开 PR #214 |
| (n2) PM rebase main 后必 pip install -r requirements.txt | venv 同步债 → ImportError → 误诊 marker gate 红 | PM PR #214 rebase 后 pre-push gate fail 误报"全员停"，胡桃实测 main 健康 + PM venv 缺 reportlab |
| (o) backend deps 改动 PR merge 后 push 者群里 announce | 收 PR 端 venv 同步前置 | 双向 gate 设计 |
| (p) swap pattern PR 必跑机器对齐 source vs target | 手抄 Chinese plain text 字符不可信 | 胡桃 swap typo「扌→扣」三方独立 fact check 拆穿 |
| 7 | schema 类断言必须 set verify | PM「blocked 合法」基于 list_tasks 返 0 results 推测，胡桃实测 mjs reject |

## 3. S3 implement 第一阶段复盘

### 3.1 合同主线（S3-REQ-001）

完工：
- ✅ ADR-0046/0047 落 + PR #189 三 ADR 合
- ✅ CONTRACT-HASH（PR #197）
- ✅ CONTRACT-STORAGE（PR #195）
- ✅ CONTRACT-DOMAIN（PR #200）
- ✅ INSURANCE-DOMAIN（PR #199）
- ✅ ContractService core + accept_order wiring + pickup cron（PR #212）
- ✅ PDF-RENDER reportlab + 中文 + idempotent（PR #213）
- ✅ TEMPLATE-SWAP 4 段法务文案（PR #215）
- ✅ USER-AUDIT user_audit_logs + UA/IP（PR #204）
- ✅ WORM-COMPENSATION worm_status + repair cron（PR #218）
- ✅ SALT deploy fix（PR #217）
- ✅ ADR-0047 §3.1 enum 注释 amend（PR ADR-0047-CONTRACT-TRIGGER-CONSISTENCY）

PM 业务侧产物：
- ✅ PRD-003 v0.5（accept_order hook + AC-2a admin pending_companion）
- ✅ 合同模板 v1.0.0-draft + 4 段法务措辞（PR #214）
- ✅ PM 业务验收 checklist v1（PR #226 当前）

剩待办：
- ⏳ CONTRACT-API（PR #206 已合，task 状态等 set done）
- ⏳ CONTRACT-UI（微信/iOS 勾选 UI）
- ⏳ 刻晴 S3-TEST-001 12 AC（SALT unblock 后起跑 9 AC + 后批 3 WORM AC）

### 3.2 AI 准备包链路（S3-REQ-002）

推进中：
- 🟡 KEYWORD-FILTER + HOT-RELOAD 链（胡桃今日完成）
- ⏳ ABAC-4LAYER P0
- ⏳ BUDGET-GUARD P0
- ⏳ PROMPT-VERSIONING P1
- ⏳ PREP-API P0

PM 业务侧产物：
- ✅ AI 准备包禁区关键词清单 v1-draft（`docs/qa/s3-ai-prep-blocklist-v1.md`）
- 🟡 等帝君拍 ①/②（直接进 git OR 等医疗顾问 review）

### 3.3 信任前置 UI（S3-REQ-003）

待 PRECHECK-BACKEND（P0）拆分 + TRUST-UI-WX/IOS（P1）+ ADMIN-COPY（P2）。当前全 not-started。

### 3.4 反馈采集（S3-REQ-004）+ 资质透明度（S3-REQ-005）

P1 ready 等手起。

## 4. 三方 fact check loop 战绩

### 4.1 健康案例（multi-agent 协作信号）

| 时间 | 触发方 | 内容 | 结果 |
|---|---|---|---|
| 06-08 08:30 UTC | 胡桃 | OrderStatus/PaymentState ADR-0041 解耦 + hash 公式 companion_id 必填 | PM/魈 接受拍 C2 |
| 06-08 08:42 UTC | 魈 | ADR-0046 §3.2 hash_inputs 7 字段 = 合同与 companion 强绑设计 | PM 自验 ADR 后拍 C2 |
| 06-08 10:36 UTC | 胡桃 | PM venv 缺 reportlab → ImportError 假装 marker fail | PM 接受 + 立刻 pip install fix |
| 06-08 10:48 UTC | PM | 胡桃 swap PR 「扌→扣」typo（手抄错字）| 胡桃 30s amend force-push fix |
| 06-08 16:08 UTC | 胡桃 | mjs schema reject `blocked` enum（PM 凭推测） | PM 接受 + propose schema 升级 task |

### 4.2 反复横跳案例（待协议熔断）

| 决策点 | 反转次数 | 解决方式 |
|---|---|---|
| 合同 hook 位置（B → C2 → C → C2） | 4 次 | PM 自验 ADR-0046 §3.2 后终结 |
| 「按 06-02 拍板冲」语义扩张 | 魈第 6 次自承 retract | 严格字面引用 only |

## 5. 给 S4 立项的建议

1. **OPS-021 协议哲学族正式 ADR 化**：今天积累 7 条反案教材 + 协议哲学（evidence-first / 桥接 ≠ Owner / emergency 必 fact check / 物料必 git push / schema 必 set verify / 物料 PR 必 spelling check / 单字 cross-check）值得固化为 ADR 或 docs/process/ COORDINATOR_DECISION_PROTOCOL.md（甘雨 own draft）
2. **PM 物料 PR 工具链**：spelling check + diff source vs target + auto 跑 markdown lint 兜底（避免今天 typo 事件）
3. **per-agent GitHub identity**（S3-OPS-GITHUB-PER-AGENT-IDENTITY task）：解决 self-approve 限制 + audit trail
4. **多 hutao session worktree 隔离**：S3-OPS-A WORKTREE-OWNER-METADATA + S3-OPS-B MULTI-SESSION-WORKTREE-ISOLATION 已立 P1，等 implement
5. **真物料申请并行**：S2-TEST-004-REAL + S2-DEV-016-PHASE-B-REAL 仍卡帝君外部输入（wxpay 沙箱 + 阿里云 SMS + 企微 webhook + 21Vianet）；S4 阶段建议帝君 batch 申请

## 6. 帝君视角的 ROI 摘要

- 今天 14 PR merged（PM 数到 22 PR 含 06-07/08 全部）= 团队效率高峰
- mock 灰度门通了但真灰度仍卡帝君 5 件外部输入回执
- PM 6+ 条反案教材积累 + 三方 fact check loop 实证 = 协作成熟度阶跃
- S3 合同主线接近完工，AI 准备包链路推进中

## 7. PM 自我反思

今天 PM 主要失误：
1. 4 次合同 hook 拍板横跳（最后 PM 自验 ADR 才稳）
2. 一次 emergency 误升级（基于 hutao forward 没 fact check session）
3. 一次 Owner 单字误读（魈扩张解读传染 PM）
4. 一次写文件没 push（合同模板 buffer 物理交付不到胡桃）
5. 一次 venv 同步债（rebase 后没 pip install）
6. 一次 schema 推测断言（"blocked 合法"凭印象）
7. 一次 swap typo 未自查（虽 PM 发现但 PM 自己出文档也可能有同款问题）

主要做对：
- PM 业务边界守门坚持（拒 GitHub OPS task 辅 assignee、拒替架构师拆 develop task）
- 三方 fact check loop 接受反向纠正不顽固
- 主动可推动作（PM 业务验收 checklist v1 + 复盘文档 v1 + 合同模板 v1.0.0）
- 协议哲学族沉淀（OPS-021 (j)/(l)/(m)/(n)/(p) PM 视角条款 cont）

---

PM 视角复盘 v1。下次帝君问「卡点+继续」时 PM 可拉本文档相关章节回答，不用每次临场盘点。
