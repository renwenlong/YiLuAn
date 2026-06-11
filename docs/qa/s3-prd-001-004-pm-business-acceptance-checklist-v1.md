# PRD-001 v1.4 §F8 资质透明度 + PRD-004 v0.3 反馈采集 PM 业务验收 checklist v1

> 产出：凝光（PM）@ 2026-06-09 15:50 UTC
> 触发：帝君 15:43 UTC「全力冲刺 完成剩余任务」+ PM D5 补全（v1 只覆盖 PRD-003，PRD-001/004 还没出 checklist）
> 用途：PM 业务验收 owner 视角，S3-REQ-004/005 implement 完进 in-review 时 PM 拉本 checklist 对应章节逐条 verify
> 关联：PRD-001 v1.4 §F8 + PRD-004 v0.3 + ADR-0049 user_feedbacks + S3-REQ-004/005 task

## 0. 用途与生效时点

- **用途**：PM 业务边界守门工具。胡桃 PR push → CI 三绿 → 魈技术 approve → PM 业务 review（拉本 checklist 对应章节）→ 自合 / 打回。
- **生效时点**：PRD-001 v1.4 + PRD-004 v0.3 Owner Accept 后逐步生效（PRD-001 v1.4 已 06-06 Owner Accept ✅ / PRD-004 v0.3 已 06-06 Owner Accept ✅）。
- **不替代**：架构师技术 review + 测试员 acceptance test。本 checklist 是 PM 业务侧 third gate。

## 1. PRD-001 v1.4 §F8 陪诊师资质透明度（S3-REQ-005）

### 1.1 PM 业务验收 — 资质徽章三态展示

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-005-1 | 下单人选陪诊师阶段能看到资质状态徽章；未认证不隐藏但明示 | UI 截图 | AC-F8-1 |
| PM-005-2 | 三态徽章颜色 + icon：已认证=绿 + check / 临时证明补交中=黄 + clock / 未认证=灰 + dash；不得只靠颜色区分（a11y） | UI 截图 + 色盲模拟 | AC-F8-1 |
| PM-005-3 | 陪诊师卡片有「资质详情」弱入口；点开只看到三态文案 + 证件类型文案（不见证件原图）| UI 操作 + endpoint response grep | AC-F8-2 |
| PM-005-4 | 家属共享落地页同样看到资质状态徽章；不能查详情 | UI 操作 | AC-F8-3 |

### 1.2 PM 业务边界守门 — 字段契约 + admin lint

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-005-5 | ShareOrderResponse 不新增任何 `share_*` 字段；用 `response.companion.cert_status` sub-object 承载 masked enum；不新增 `companion_cert_url` / `companion_cert_image_url` 等 URL 字段 | schemathesis CI gate + API spec grep | AC-F8-3 |
| PM-005-6 | admin-v2 修证件状态后调用 `POST /admin/cache/invalidate {key: "companion_cert:{id}"}` + 发布 `precheck.status.updated` 事件 (envelope 含 cert 状态语义, 与 c4 aggregator 实装一致) | endpoint trace + Redis pub/sub log | AC-F8-4 |
| PM-005-7 | 活跃端 ≤5s invalidate + refetch；不走 CDN 缓存 | WS test + UI poll | AC-F8-4 |
| PM-005-8 | 离线/非活跃页面下次打开取最新值 | UI 操作 + endpoint poll | AC-F8-4 |
| PM-005-9 | 未认证陪诊师不进首屏推荐位（`recommended=true` 或 top3）；排序规则：已认证 > 临时证明补交中 > 未认证；admin 不得 override 未认证进 top3 | 排序算法 unit test + admin endpoint 测试 | AC-F8-5 |
| PM-005-10 | admin-v2 文案 lint 禁词「已护士 / 已医生 / 资格 / 执业」命中 reject | lint 哨兵 unit test | AC-F8-6 |
| PM-005-11 | `companion_cert_*` 字段作为 ADR-0046 §3.5 `S3_NEW_FIELD_PREFIXES` 第 4 域前缀纳入 positive list | schemathesis CI gate config grep | AC-F8-7 |

## 2. PRD-004 v0.3 用户/家属反馈采集（S3-REQ-004）

### 2.1 PM 业务验收 — 反馈提交链路

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-004-1 | 订单完成页 + 家属共享落地页有「反馈」入口；不点不强制 | UI 截图 | AC-1 |
| PM-004-2 | 反馈分类 6 类（服务态度/专业能力/平台流程/费用问题/隐私担忧/建议）+ 严重度 3 档（一般/重要/紧急）必填 | UI 表单 validate | AC-2 |
| PM-004-3 | 严重度=紧急 5min 内触发 Prometheus + Alertmanager 告警；admin-v2 看板必须可见 | metric + alert rule + Grafana dashboard | AC-2 |
| PM-004-4 | 单订单单用户每类只能 1 次；补充反馈新增 row + `feedback_parent_id` 串版本链 | DB query + endpoint | AC-3 |
| PM-004-5 | `feedback_function_module` 必填 + DB enum 化：`{insurance, contract, ai_prep, family_share, service_package, service_quality, payment, other}`；运行时不可新增；`other` 占比 ≤20% | schema + grafana stats | AC-4 |
| PM-004-6 | 客服代录入需标记「客服代录」+ 来源（`user`/`customer_service`/`phone`/`offline`）；与用户自填分开统计 | endpoint + DB query | AC-5 |
| PM-004-7 | `feedback_submitted_total{source=...}` metric 落地；客服代录入占比 ≤50% 可量化 | metric grep | AC-5 |

### 2.2 PM 业务边界守门 — ABAC + 摘要 + 契约

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-004-8 | 陪诊师端看到摘要 + 严重度 + 处理状态（不见用户原文/截图/联系方式）| ABAC test sentinel + endpoint response grep | AC-6 |
| PM-004-9 | 反馈摘要由 admin 人工脱敏生成；S3 不走 AI 自动摘要（避免 AI 误透传用户原话） | service layer 实现核 | AC-6 |
| PM-004-10 | 陪诊师可申诉；申诉文字进同一处理流 | endpoint + DB query | AC-6 |
| PM-004-11 | admin 处理流四状态闭环（待处理 → 处理中 → 已处理 → 已关闭）；状态变更留痕（处理人 + 时间 + 摘要） | state machine + audit log | AC-7 |
| PM-004-12 | feedback endpoint negative list 拒 `share_*` / `contract_*` / `insurance_*` / `preparation_*` 跨域字段 | schemathesis CI gate | AC-8 |
| PM-004-13 | 新字段强制 `feedback_*` 前缀 | schemathesis CI gate + API spec grep | AC-8 |
| PM-004-14 | 反馈聚合看板能按 S3 灰度功能切片（保险 / 合同 / AI 准备包 3 维度）| Grafana dashboard | AC-9 |
| PM-004-15 | 反馈截图走 ADR-0045 StorageBackend ABC + `FeedbackAttachmentStorageBackend` 子类（不直接塞 DB / 不另起存储栈） | service 层实现 + ABC 子类 check | AC-10 |
| PM-004-16 | feedback ABAC policy 与 S3-REQ-002 preparation 表共用同一 attribute set | ABAC config grep | AC-11 |

### 2.3 PM 业务边界守门 — admin-v2 + 领域模型

| Check ID | 业务断言 | verify 方法 | 来源 AC |
|---|---|---|---|
| PM-004-17 | 反馈采用独立领域模型 + `user_feedbacks` 表 + 独立处理状态机（第 7 个，ADR-0049）| DB schema + state machine | AC-12 |
| PM-004-18 | admin-v2 新增 `/admin-v2/feedbacks/*` 顶级模块 | admin URL 路由 | AC-12 |

## 3. PM 业务验收节奏建议

### 3.1 develop in-review 阶段

- 胡桃 PR push → CI 三绿 → 魈技术 review approve → **PM 业务 review**（拉本 checklist 对应章节）→ 自合 / 打回
- 时间预算：PM 5-15min（小 PR）/ 30-60min（大 PR）

### 3.2 test in-progress 阶段

- 刻晴跑 acceptance test → bug task 立 → 胡桃修 → 刻晴复测
- PM 不重复跑 test，只在 acceptance ambiguity 时业务边界澄清

## 4. 锁版条件

v1-draft → v1.0 锁版条件：
- PRD-001 v1.4 + PRD-004 v0.3 已 Owner Accept ✅（06-06 已完成）
- S3-REQ-004 反馈采集 implement 完 + 测完 + PM 业务验收 PASS
- S3-REQ-005 资质透明度 implement 完 + 测完 + PM 业务验收 PASS

v1.0 锁版后改动需 PM + 测试 + 帝君三签。

## 5. 后续 follow-up

- 跟刻晴 S3-TEST-005 (反馈采集) / S3-TEST-006 (F8 资质) acceptance test 对齐字段，避免 PM/test double check 重复
- v1 跑实战后调整断言粒度 + verify 方法
- 帝君拍 S4 路线后立 ADR-0051 OPS-021 协议哲学族（PM own §1/§6/§7）

---

PM 业务边界守门工具补全（v1 覆盖 PRD-003 + 本 v1 覆盖 PRD-001 v1.4 + PRD-004 v0.3 = 三大 PRD 全覆盖）。
