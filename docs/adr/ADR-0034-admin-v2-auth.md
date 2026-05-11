# ADR-0034: Admin v2 — JWT 鉴权 + 操作员实体 + 真审计

- **Status**: Accepted
- **Date**: 2026-05-04
- **Deciders**: Backend Owner (假期通宵代码侧落地)
- **Related**: ADR-0032 (recon double-sign), `docs/admin-mvp-scope.md` (B5 follow-up), yiluan-phase2 轨道 B / G5-G6
- **Supersedes (partially)**: 现行 `app/core/admin_auth.py::require_admin_token` 共享口令模型

## Context

Admin MVP 阶段（B1–B4）所有后台接口走 `X-Admin-Token` 共享口令：
- 全公司复用同一 token，泄漏面大。
- `admin_audit_logs.operator` 一律写死 `"admin-token"`，无法回溯到具体管理员。
- 资金对账双签关单（D-048 / ADR-0032）只能靠前端自填的 `X-Admin-Operator` 头自证身份，缺少强约束。
- 任何"按管理员维度做权限或自我保护"的能力都做不到（例如 admin 不能停用自己的账号）。

提审 / 上线前，强制需要：
1. 真实操作员实体（数据库行，可禁用、可审计、可换密码）。
2. 真实身份令牌（不再是共享口令）。
3. 审计日志的 `operator` 字段能映射回真人。
4. 至少 3 种角色（super / ops / finance），未来可扩展。

## Decision

引入 Admin v2 鉴权栈：

1. **新表 `admin_users`**
   - `id BIGINT PK`
   - `username VARCHAR(64) UNIQUE NOT NULL`
   - `password_hash VARCHAR(255) NOT NULL`（bcrypt，cost=12）
   - `role ENUM('super','ops','finance') NOT NULL`
   - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
   - `last_login_at TIMESTAMPTZ NULL`
   - 索引：`UNIQUE (username)`
   - Seed：alembic upgrade 后插入一个 `super` 账号（`admin / Admin@2026!`，仅 dev/staging；prod 由运维手工改密）。

2. **登录接口**：`POST /api/v1/admin/login`
   - body `{username, password}`
   - 校验 bcrypt + `is_active`
   - 返回 JWT (HS256, 8h 过期) + `role`
   - claims：`{sub: admin_user.id (str), role, exp, type:"admin_access"}`
   - 复用全局 `settings.jwt_secret_key`，`type` 区分以防与用户 token 串用

3. **新依赖 `require_admin_jwt`**
   - 解析 `Authorization: Bearer <jwt>`，校验 `type=="admin_access"`、过期、`AdminUser.is_active`。
   - 返回 `AdminUser` 实体，供路由用 `Depends(require_admin_jwt)` 拿到 operator。

4. **双轨过渡（W19，本 PR 即落地）**
   - 引入新组合依赖 `require_admin`：JWT 优先（出现 `Authorization: Bearer` 头时按 JWT 走），否则回落到 `X-Admin-Token`。
   - 走 JWT 的请求 → `_audit(..., operator=str(admin_user.id))`
   - 走 X-Admin-Token 的请求 → `_audit(..., operator="admin-token")`（与现网行为一致，避免破坏审计连续性）
   - W20 摘掉 X-Admin-Token 路径，只留 JWT。

5. **自我保护规则**
   - 通过 JWT 调用 `/api/v1/admin/users/{id}/disable`：禁止 `target_id` 等于当前 admin 自己绑定的 `User`（如未来加 admin↔user 绑定，先用 disable 自身禁止；本 PR 范围：admin 不能 disable 自己的 admin 账号 — 通过新接口 `/admin/admin-users/{id}/disable` 留待后续）。
   - 通过 JWT 调用任何"用户禁用/订单强改"接口时，必须带 reason，由 `_audit` 真实落库。

6. **不上 RBAC 框架**
   - 3 个角色硬编码足够。super=全权，ops=订单/用户/陪诊师，finance=对账/钱包。本 PR 仅落 schema，暂不在路由层强制角色（W19/W20 再细化），避免一次改太多面。

## Trade-offs

| 选项 | 选择 | 理由 |
|---|---|---|
| Session vs JWT | JWT | admin-h5 是纯静态前端，没有服务端 session 中间件；无状态 JWT 更简单 |
| HS256 vs RS256 | HS256 | 单后端实例，无密钥分发 |
| 独立 secret vs 复用 jwt_secret_key | 复用 + `type` claim | 减少密钥管理面，`type=="admin_access"` 避免与用户 access token 串用 |
| 双轨期 vs 一刀切 | 双轨 1 sprint | 现网/staging 有定时任务 + 多客户端用 X-Admin-Token，骤切风险大 |
| 角色 RBAC 框架 vs 硬编码 | 硬编码 | 3 角色不值得引入 casbin |
| seed 默认密码 vs 必填环境变量 | seed 默认密码（仅 dev/staging） | 让本地 / staging 直接能跑；prod 必须手工改，写到 ops runbook |

## Migration 策略

- W19（本 PR）：alembic 加表 + seed + 双轨依赖 + 审计 operator 真化。
- W20：admin-h5 接 `/admin/login` + 切 `Authorization: Bearer`，运维改 prod super 账号密码。
- W20 末：移除 `require_admin_token` 路径，删 `ADMIN_API_TOKEN` 环境变量。

## Consequences

- **正向**
  - 审计日志真有人名（id），合规可过。
  - 共享口令风险消除。
  - 后续按角色细化权限的地基铺好。
- **负向 / 待办**
  - 双轨期需注意：同一请求两套头都带，依赖按 JWT 走；测试需覆盖两条路径。
  - admin-h5 W20 必须发版切换，否则 W20 末摘 X-Admin-Token 会导致前端登录失败。
  - prod seed 密码必须手工改，需写入运维 runbook。

## 验收

- [x] `admin_users` 表 alembic 跑通
- [x] `POST /api/v1/admin/login` 端到端通过
- [x] `require_admin_jwt` + 双轨 `require_admin` 接入
- [x] 至少 1 个 admin API 通过 JWT 调用成功并记录真实 `operator=admin_user.id`
- [x] X-Admin-Token 仍可用（双轨过渡期）
- [x] 单元测试覆盖：登录成功 / 密码错 / 账号禁用 / token 过期 / 审计 operator 正确 / 自我保护
