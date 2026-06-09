# PRD-003 v0.5 PM 业务验收 checklist v1

> 产出：凝光（PM）@ 2026-06-08 16:42 UTC
> 触发：帝君 16:39 UTC「上面问题处理完，继续推进新开发」
> 用途：PM 业务验收 owner 视角的 acceptance 验收 checklist，待 hutao implement 完进 in-review 时 PM 用本 checklist 逐条 verify 业务边界
> 关联：PRD-003 v0.5（pending 帝君 Owner Accept）+ ADR-0046/0047/0048/0049 + 8 已合 PR（#212/#213/#214/#215/#216/#217/#218 + 后续 KEYWORD-FILTER/HOT-RELOAD）

## 0. 用途与生效时点

- **用途**：PM 业务边界守门工具。develop task 进 in-review 时，PM 拉本 checklist 对应章节逐条 verify，对得上 = approve，对不上 = comment 打回。
- **生效时点**：v0.5 PRD Owner Accept 后逐步生效；当前 v1-draft 由 PM 维护。
- **不替代**：架构师技术 review（魈本职）+ 测试员 acceptance test（刻晴本职）。本 checklist 是 PM 业务侧 third gate。

## 1. S3-REQ-001 合同 + 保险（PRD §3）

### 1.1 PM 业务验收 — 合同生成链路

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-001-1 | 用户支付完订单后 5s 内订单详情显示「合同生成中（待陪诊师接单后生成）」占位 | UI 截图 + endpoint poll | AC-2 |
| PM-001-2 | admin 端 paid 但未 accept 订单显示「未生成 - 等待陪诊师接单」占位文案 | admin endpoint 调用 | AC-2a |
| PM-001-3 | 陪诊师 accept_order 后 5s 内 contract row INSERT 完成 + hash 计算完成 | DB query `SELECT * FROM service_contracts WHERE order_id=...` | AC-2 |
| PM-001-4 | 合同包含 9 项必含字段：订单号 / 服务档位 / 患者脱敏信息 / 陪诊师信息 / 价格 / 服务时间 / 退款规则 / 免责边界 / 模板版本 | 渲染 PDF 内容 grep | AC-2 |
| PM-001-5 | 合同 hash = SHA-256(模板版本 + 订单字段 snapshot 含 companion_id) | DB hash 字段对照 ADR-0046 §3.2 公式 | AC-2 |
| PM-001-6 | 合同生成后内容不可被用户侧修改（WORM）| 尝试 update contract row 应被 trigger reject | AC-3 |
| PM-001-7 | admin 更新模板后只影响新订单，历史合同保留原版本（含 template_version 字段） | template_version 字段历史合同对照 | AC-3 |

### 1.2 PM 业务验收 — 保险/合同字段

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-001-8 | admin 可按订单号查到：保障状态 / 保额文案 / policy_no（允许 PENDING）/ contract_hash / template_version / generated_at | admin endpoint 查询 | AC-4 |
| PM-001-9 | 合同/保障生成失败不阻塞订单支付成功 | mock fail + verify order status 仍 paid | AC-5 |
| PM-001-10 | 订单详情失败状态显示「合同生成中/生成失败，请联系客服」（不是空白）| UI 截图 | AC-5 |
| PM-001-11 | 补偿 cron 指数退避重试 3 次（5min/30min/2h），3 次仍失败触发 admin alert | DB retry_count + alert log | AC-5 |
| PM-001-12 | 用户端、陪诊师端、admin 看到的保障/合同状态一致 | 三端 endpoint 调用对照 | AC-6 |

### 1.3 PM 业务边界守门 — 契约 + admin-v2

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-001-13 | 新增字段不污染 S2 share_* 9 字段契约 | schemathesis CI gate `GUARDED_FIELDS` | AC-7 |
| PM-001-14 | 新字段强制前缀 `contract_*` / `insurance_*` | schemathesis CI gate + grep API spec | AC-7 |
| PM-001-15 | admin 配置入口走 admin-v2（不允许走 admin-h5） | admin URL 路由 | AC-8 |
| PM-001-16 | 理赔/纠纷入口三种：客服微信 + 平台在线表单 + 客服电话（ADR-0047 §6.2 简化为微信+电话，PM 同意 v1.0 评估是否补表单） | 合同 §5.2 文案 + UI 入口 | AC-1 |

## 2. S3-REQ-002 AI 准备包（PRD §4）

### 2.1 PM 业务验收 — 准备包生成链路

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-002-1 | 支付成功后 1h 内订单详情出现「就诊准备包」 | endpoint poll | AC-1 |
| PM-002-2 | AI 失败时降级通用模板（不是空白）| mock AI fail + verify 通用模板 | AC-1 |
| PM-002-3 | 准备包 4 块完整：携带材料 / 到院前注意事项 / 可能问诊问题 / 陪诊师关注点 | endpoint response grep | AC-2 |
| PM-002-4 | 每块至少 1 项（不为空）| schema validate | AC-2 |
| PM-002-5 | 准备包显式标注「仅供就诊准备，不构成诊断或用药建议」 | endpoint response grep | AC-3 |
| PM-002-6 | 命中诊断/用药/剂量等禁区关键词时降级通用模板 + 记录原因 | mock 命中 case + DB log | AC-4 |
| PM-002-7 | 禁区关键词清单经医疗顾问 review + git 版本控制 | `docs/qa/s3-ai-prep-blocklist-v1.md` git history + medical-advisor-approved label | AC-4 |
| PM-002-8 | 关键词命中触发告警（Prometheus + Alertmanager）| metric + alert rule | AC-4 |
| PM-002-9 | 灰度期 fallback 率纳入指标统计 | Grafana dashboard | AC-4 |

### 2.2 PM 业务边界守门 — ABAC + 成本

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-002-10 | 用户勾选准备项 1s 内持久化 + 重开订单不丢进度 | UI 操作 + endpoint poll | AC-5 |
| PM-002-11 | 陪诊师端看到用户准备进度 + 陪诊师关注点（不见用户病史原文）| ABAC test sentinel | AC-6 |
| PM-002-12 | RowSecurity/ABAC 强制：数据访问层强制（schema 层不返回 `pre_visit_notes`/`possible_questions`），不仅 UI 不展示 | 4 层防御 unit test | AC-6 |
| PM-002-13 | admin 按订单号查到准备包内容 + 生成状态 + 模型版本 + trace_id + 失败原因 | admin endpoint | AC-7 |
| PM-002-14 | 单订单 AI 成本上限 + 日预算耗尽自动通用模板 | mock 超限 case | AC-8 |
| PM-002-15 | S2 沿用现有 `ai_*_yuan` 配置真源不改名（零迁移）| settings.py grep | AC-8 |
| PM-002-16 | S3 新增 `s3_prep_cost_per_order_yuan` / `s3_prep_daily_budget_yuan` 独立配置轴 | settings.py grep | AC-8 |
| PM-002-17 | 灰度起步：单订单 ¥0.10 / 日 ¥100（S2 × 1.5-2 倍）| env file grep | AC-8 |

## 3. S3-REQ-003 信任前置 UI（PRD §5）

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-003-1 | 微信/iOS 创建订单页每个服务档位展示：服务内容 / 适合场景 / 预计时长 / 价格 / 是否含保障 | UI 截图 | AC-1 |
| PM-003-2 | 陪诊师卡片展示：认证状态 / 服务次数 / 评分摘要 | UI 截图 | AC-2 |
| PM-003-3 | 未认证/数据不足陪诊师有明确兜底文案 | UI 截图 | AC-2 |
| PM-003-4 | 支付前确认页展示：退款规则摘要 / 合同摘要 / 保障摘要 | UI 截图 | AC-3 |
| PM-003-5 | 勾选默认未勾选 + 未勾选时支付按钮 disabled（PIPL 明示同意）| UI 操作 | AC-3 |
| PM-003-6 | admin 维护文案：服务边界 / 保障摘要 / 合同摘要 | admin endpoint | AC-4 |
| PM-003-7 | admin 修改后只影响后续展示，不篡改历史合同 | template_version 历史对照 | AC-4 |
| PM-003-8 | admin 入口走 admin-v2 | admin URL 路由 | AC-4 |
| PM-003-9 | 微信/iOS 两端文案与字段一致 | schemathesis CI gate | AC-5 |
| PM-003-10 | 不新增超过 1 个支付前强制弹窗 | UI 操作计数 | AC-6 |
| PM-003-11 | 支付前页面跳转次数 ≤ S2 现状 + 1，增加项仅为 1 个强制同意勾选 | UI 操作计数 | AC-6 |

## 4. PM 业务验收节奏建议

### 4.1 develop in-review 阶段

- 胡桃 PR push → CI 三绿 → 魈技术 review approve → **PM 业务 review**（拉本 checklist 对应章节）→ 自合 / 打回
- 时间预算：PM 业务 review 5-15min（小 PR）/ 30-60min（大 PR）

### 4.2 test in-progress 阶段

- 刻晴跑 acceptance test → bug task 立 → 胡桃修 → 刻晴复测
- PM **不**重复跑 test，只在 acceptance ambiguity 时业务边界澄清

### 4.3 task done handoff 阶段

- 魈 set develop done + handoff → 触发 PM check（业务边界确认）+ 触发刻晴 acceptance test
- PM check 用本 checklist 对应章节，对得上 → 不打回 → 继续 handoff 链路

## 5. 锁版条件

v1-draft → v1.0 锁版条件：
- PRD-003 v0.5 帝君 Owner Accept
- S3-REQ-001 合同保险 implement 完 + 测完 + PM 业务验收 PASS
- S3-REQ-002 AI 准备包 implement 完 + 测完 + PM 业务验收 PASS  
- S3-REQ-003 信任前置 implement 完 + 测完 + PM 业务验收 PASS

锁版后 v1.1+ 改动需 PM + 测试 + 帝君三签。

## 6. 后续 follow-up

- v1 完成后立 PRD-004 反馈采集 + PRD-001 v1.4 §F8 资质透明度对应 checklist v1（同款结构）
- v1 跑实战后调整断言粒度 + verify 方法（如有过粗过细）
- 跟刻晴 S3-TEST 系列 acceptance test 对齐字段，避免 PM/test double check 重复

---

PM 业务边界守门工具就位。下一个 develop PR in-review 时 PM 拉本 checklist 对应章节验收。
