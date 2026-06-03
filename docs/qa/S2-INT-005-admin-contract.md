# S2-INT-005 — admin-h5 联调契约表（9 字段互锁 + 安全口径）

> 作者：魈（架构师，本期临时接 develop） · 起手：2026-06-03 · 状态：起手版（D+0）
> 关联：ADR-0036 / ADR-0038 / ADR-0039 / S2-INT-001 验收口径 §3+§4
> 反向互锁：微信端 `wechat/utils/orderSummary.js` / iOS `APIEndpointTests.swift`

---

## §0 本文件目的

**钉死 admin-h5 联调期间「订单」相关后端响应字段**——避免三端漂移再次出现。

凡 admin-h5 / 微信端 / iOS 端读到的字段名 / 类型 / 必填性偏离本表，**直接打回 develop，不进 review**（与 ADR-0036 §4 同口径）。

本表是 `GET /api/v1/admin/orders` + `GET /api/v1/admin/orders/{id}` 响应的契约真源；微信端 / iOS 端的订单摘要渲染字段来源最终都落到这同一个 backend `OrderItem` schema 上（admin 多了 `patient_phone_masked` / 审计字段，但订单本身字段必须对齐）。

---

## §1 OrderItem 9 字段钉死表（admin 订单列表/详情共用）

来源：`backend/app/api/v1/admin/orders.py::OrderItem`（W18 fix-admin-h5-contract 落地）

| # | 字段名 | 类型 | 必填 | 微信端对应渲染函数 | iOS APIEndpointTests 断言点 | 备注 |
|---|--------|------|------|------------------|--------------------------|------|
| 1 | `id` | string (UUID) | ✅ | — | `Order.id` 反序列化非空 | 订单主键 |
| 2 | `patient_id` | string (UUID) | ✅ | — | `Order.patient_id` | 患者关联 |
| 3 | `patient_display_name` | string \| null | 可空 | `summaryPatient(name,...)` 取首字 | `Order.patient.displayName?` | **admin 端始终原文，微信/iOS 端取首字 +「**」脱敏后渲染** |
| 4 | `patient_phone_masked` | string \| null | 可空 | — | — | **admin 列表/详情始终脱敏**；reveal-on-demand 走 `/admin/users/{id}/phone`（独立审计） |
| 5 | `companion_id` | string (UUID) \| null | 可空 | — | `Order.companion?.id` | 未派单时 null |
| 6 | `companion_display_name` | string \| null | 可空 | `summaryPatient(...,relation,...)` 关系字段 | `Order.companion?.displayName` | 与 patient 同口径，但 admin 端原文 |
| 7 | `hospital_id` | string (UUID) | ✅ | `summaryHospital(name,dept)` 名字来源 | `Order.hospitalId` | 名字需联表查 hospitals |
| 8 | `status` | string (OrderStatus enum) | ✅ | — | `Order.status` 枚举非法值 fail | admin-h5 `STATUS_LABELS` 映射中文 |
| 9 | `appointment_date` + `appointment_time` | string (YYYY-MM-DD) + string (HH:MM) | ✅ | `summaryDate(date,period)` 拼接 | `Order.appointmentDate/Time` | 两字段必须组合，缺一打回 |
| + | `price` | string (decimal, 两位小数) | ✅ | `summaryService(name,price)` price 来源 | `Order.price` Decimal 解码 | **必须 string 不能 float**（精度），admin-h5 `formatCurrency` 渲染 |
| + | `created_at` | string (ISO8601) \| null | 可空 | — | — | 时间戳 |

**漂移触发条件（任一即 CI fail）：**
1. 字段名拼写变更
2. 类型从 string ↔ number 切换（尤其 `price`）
3. 必填字段（✅ 标记）变成 null/可空，或反之
4. 枚举值新增/删除未同步 `OrderStatus` + admin-h5 `STATUS_LABELS` + 微信端 mapping

---

## §2 admin-h5 端验收硬要求（§3 验收口径展开）

| AC | 要求 | 实现状态（D+0 勘察） | INT-005 期间动作 |
|----|------|---------------------|-----------------|
| §3-1 | 非默认 ADMIN_API_TOKEN 登录成功 | ⚠️ **未达**：`env.staging` 写死 `staging-admin-token` 作为默认入库值，backend startup guard 只拦 `dev-admin-token`/空 | **P0 修复**：见 §3 |
| §3-1 | 默认/空 token 登录拒绝 | ⚠️ 部分达成：空被 backend startup guard 拦，但 `staging-admin-token` 当前算"合法默认" | 同 P0 |
| §3-2 | 订单列表可查（状态正确） | ✅ 已实装（admin-h5/app.js + orders.py W18） | 联调验证 + audit 留痕检查 |
| §3-3 | 用户基本信息可查 | ✅ 已实装（users.py + admin-h5 multi-role） | 联调验证 + 越权用例 |
| §3-3 | 越权拒绝 | ✅ 已实装（require_admin 依赖） | 编写负向用例 |
| §3-4 | 审计日志可查（admin_audit_logs） | ✅ 已实装（audit_logs.py + admin-h5 AuditLog 模块） | 联调验证 + 检查 view_orders_list / view_order_detail 留痕 |

---

## §3 P0 修复方案：env.staging 默认 token 泄露

### 现状（违规清单）
- `deploy/env.staging:30` → `ADMIN_API_TOKEN=staging-admin-token`（应入 `env.staging.local`，不入库）
- `backend/app/config.py:209` → startup guard 只拦 `dev-admin-token` + 空，**不拦 `staging-admin-token`**
- `deploy/up.sh:95` / `deploy/up.ps1:36` / `deploy/staging/seed_staging.py:207` / `deploy/staging/replay/run-weekly-rehearsal.py:413` → 硬编码 `--admin-token staging-admin-token`

### 修复（INT-005 D+1 完成）
1. `deploy/env.staging` 删 `ADMIN_API_TOKEN=staging-admin-token`，改 `# ADMIN_API_TOKEN 必须通过 env.staging.local 设置高熵随机串，本文件不入库默认值`
2. `deploy/env.staging.local.example` 补 `ADMIN_API_TOKEN` 模板
3. `backend/app/config.py` startup guard 黑名单加入 `staging-admin-token`（任何 env 命中 black-list 即 fail）
4. `deploy/up.sh` / `up.ps1` 不再写死 token，从 `env.staging.local` 读 + fail-fast：未设置直接 exit 2
5. `seed_staging.py` / `run-weekly-rehearsal.py` 同上，`--admin-token` 取 env，不给默认值
6. 单测：`tests/test_config.py` 新增 `test_startup_rejects_staging_default_token`

### 与 ADR-0038 闭环
ADR-0038 修了 admin-h5 前端 hint 文案 + CSP，但漏修了部署侧 env 默认值。本 task 闭环。

---

## §4 联调步骤（D+1 ~ D+2）

```
D+1 上午：修 P0（§3 1-5 项）+ 单测（§3 6）
D+1 下午：./up.sh staging 拉起，curl 三查接通（订单/用户/审计），录 baseline log
D+2 上午：越权负向用例（空 token / 错误 token / 越权访问其他患者）
D+2 下午：审计 view_orders_list / view_order_detail 留痕核验 + admin-h5 浏览器实测
D+3 上午：提 PR（feature/s2-int-005-admin-h5 → main），run pytest -m money_safety + share_security
D+3 下午：reviewer（待帝君拍：胡桃/刻晴/帝君本人）
```

---

## §5 不变更点（划清边界）

- **不改 admin-h5 v1 框架**（vanilla JS）——admin-v2 长期重构是 BACKLOG-ADMIN-V2 范畴
- **不动 admin-h5 现有 9 项能力的业务逻辑**——只联调验证 + 修 P0 token 缺陷
- **不动 backend admin 路由结构**——仅在 startup guard / env 默认值层面动刀
- 微信端 / iOS 端订单契约不动，本表只是承认现状 + 写成钉死表给后续 PR diff 用
