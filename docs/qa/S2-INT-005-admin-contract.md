# S2-INT-005 — admin-h5 联调契约表（9 字段互锁 + 安全口径）

> 作者：魈 · 起手 2026-06-03 D+0 · D+1 已实测全 PASS（见 smoke-report.md）
> 关联：ADR-0036 / ADR-0038 / ADR-0039 / S2-INT-001 验收口径 §3+§4
> 反向互锁：微信端 `wechat/utils/orderSummary.js` / iOS `APIEndpointTests.swift`

---

## §0 本文件目的

钉死 admin-h5 联调期间「订单」相关后端响应字段——避免三端漂移再次出现。

凡 admin-h5 / 微信端 / iOS 端读到的字段名 / 类型 / 必填性偏离本表，**直接打回 develop，不进 review**（与 ADR-0036 §4 同口径）。

本表是 `GET /api/v1/admin/orders` + `GET /api/v1/admin/orders/{id}` 响应的契约真源；微信端 / iOS 端订单摘要渲染字段来源最终都落到同一个 backend `OrderItem` schema 上。

---

## §1 OrderItem 字段钉死表

来源：`backend/app/api/v1/admin/orders.py::OrderItem`（W18 fix-admin-h5-contract 落地）

| # | 字段名 | 类型 | 必填 | 微信端对应渲染函数 | iOS APIEndpointTests 断言点 | 备注 |
|---|--------|------|------|------------------|--------------------------|------|
| 1 | `id` | string (UUID) | ✅ | — | `Order.id` 反序列化非空 | 订单主键 |
| 2 | `patient_id` | string (UUID) | ✅ | — | `Order.patient_id` | 患者关联 |
| 3 | `patient_display_name` | string \| null | 可空 | `summaryPatient(name,...)` 取首字 | `Order.patient.displayName?` | admin 端原文；微信/iOS 端取首字+「**」脱敏后渲染 |
| 4 | `patient_phone_masked` | string \| null | 可空 | — | — | admin 列表/详情始终脱敏；reveal-on-demand 走 `/admin/users/{id}/phone`（独立审计） |
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

## §2 admin-h5 端验收（§3 验收口径展开）

D+1 已实测 15/15 PASS，详见 `docs/qa/S2-INT-005-smoke-report.md`。

| AC | 要求 | 实测结果 |
|----|------|---------|
| §3-1 | 非默认 ADMIN_API_TOKEN 登录成功 | ✅ staging-admin-token → 200 |
| §3-1 | 默认/空 token 拒绝 | ✅ 空 → 401 / wrong → 401 / dev-admin-token → 401 |
| §3-2 | 订单列表/详情可查 | ✅ list 200 / 不存在 404 / 非 UUID 422 |
| §3-3 | 用户信息可查 + phone 脱敏 | ✅ list 200 / phone 默认 `138******03` |
| §3-3 | 越权拒绝 | ✅ 空 token / 错 token / 错 method 全 401/405 |
| §3-4 | 审计日志可查 + 读侧自动留痕 | ✅ view_orders_list / view_users_list / view_companions_list 全落库 |

---

## §3 关于 D+0 P0 误判的撤回

D+0 我把 `env.staging:30 ADMIN_API_TOKEN=*** 判为「默认 token 泄露 P0」。**这是误判，已撤回。**

### 现状勘察（重读后）
- `deploy/env.staging:30` → `ADMIN_API_TOKEN=*** 假值，可公开」**
- `deploy/env.staging:14` → `ENVIRONMENT=development`（注释：为让演练脚本能用 dev-OTP 000000）
- `backend/app/config.py` startup guard 设计上**只在 environment=production 时强校验**
- `up.sh` / `seed_staging.py` / `run-weekly-rehearsal.py` 硬编码 `staging-admin-token` 是与 env.staging **一致的设计**

### 误判原因
- 没读 env.staging 文件头注释
- 没看清 config.py guard 的环境分支

### 帝君 6/3 10:40 UTC 拍板
**A 字面口径**：「默认 token」指代码层 `dev-admin-token`，staging 部署侧约定值（受控演练环境，仅 nginx:18080 + mock provider）不算。

### 与 ADR-0038 的关系
ADR-0038 修了前端 hint 文案 + CSP，部署侧 staging 假值是另一个范畴（受控演练 vs 安全约束的取舍），**不属于 ADR-0038 漏修**。

### 如果未来口径转 B（严格解读）
保留修复路径供参考：
1. `deploy/env.staging` 删 ADMIN_API_TOKEN 行 + JWT_SECRET_KEY 行，统一移到 env.staging.local（破坏现有演练脚本，需 seed_staging / replay 一起改）
2. `backend/app/config.py` 黑名单扩 staging-admin-token，environment ∈ (staging, production) 都校验
3. `up.sh` / `up.ps1` 检测 env.staging.local 存在 + 必含 ADMIN_API_TOKEN，否则 exit 2
4. seed_staging.py / run-weekly-rehearsal.py 从 env 读 token，不给默认值
5. 演练 SOP 文档：演练员首次拉起需手动生成高熵 token 写入 env.staging.local
6. 单测：`tests/test_config.py` 新增 `test_staging_rejects_known_default_tokens`

工作量估计 = 0.5 ~ 1 个工作日（含演练 SOP）。

---

## §4 联调实际节奏（D+1 已完成）

```
D+0 起手：分支 + 9 字段契约表 + P0 误判 → 撤回
D+1 上午：staging 实跑 + 三查 baseline（已 ✅ 15/15 PASS）
        → 联调冒烟脚本 scripts/qa/s2_int_005_admin_smoke.sh
        → 冒烟报告 docs/qa/S2-INT-005-smoke-report.md
        → 准备提 PR（等帝君拍 reviewer）
D+2/D+3 原计划：富裕时间提前到 D+1 完成
```

---

## §5 不变更边界

- 不改 admin-h5 v1 框架（vanilla JS）—— admin-v2 长期重构归 BACKLOG-ADMIN-V2
- 不动 admin-h5 现有 9 项能力的业务逻辑 —— 联调验证 PASS
- 不动 backend admin 路由结构 —— 验证 PASS
- 微信端 / iOS 端订单契约不动 —— 本表只是把现状钉成显式互锁表
