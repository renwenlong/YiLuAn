# S2-INT-005 — admin-h5 联调冒烟报告

> 执行人：魈 · 日期：2026-06-03 · 分支：feature/s2-int-005-admin-h5
> staging 环境：./up.sh staging（6 容器 healthy，commit `1201c51`）
> 自动化脚本：`scripts/qa/s2_int_005_admin_smoke.sh`

---

## §1 结论

**🟢 INT-005 §3 验收（admin-h5 联调对接）实测全 PASS（15/15）。**

| 验收点 | 来源 | 实测 |
|--------|------|------|
| §3-1 非默认 ADMIN_API_TOKEN 登录成功 / 默认/空拒绝 | acceptance §3-1 | ✅ 帝君 6/3 拍 A 口径（字面解读：`dev-admin-token` 才算默认） |
| §3-2 订单列表状态正确 / 详情查询 | acceptance §3-2 | ✅ list 200 / 不存在 404 / 非 UUID 422 |
| §3-3 用户基本信息可查 / 越权拒绝 / phone 默认脱敏 | acceptance §3-3 | ✅ list 200 / phone `138******03` 默认脱敏 / 空 token 401 |
| §3-4 审计日志可查 + 读侧自动留痕 | acceptance §3-4 | ✅ audit-logs 200 / `view_orders_list` / `view_users_list` / `view_companions_list` 都已自动落库 |

---

## §2 实测细节

### 鉴权
```
空 token        → HTTP 401
错 token        → HTTP 401
dev-admin-token → HTTP 401（不在 staging 配置白名单内）
staging-admin-token → HTTP 200（staging 部署侧约定值，env.staging 注释明示「假值，可公开」）
```

### 订单查询（`GET /api/v1/admin/orders`）
- 列表 200，`{items, total, page, page_size}` schema 正确
- 字段实现见 `backend/app/api/v1/admin/orders.py::OrderItem`（W18 已落 9 字段契约，详见 `docs/qa/S2-INT-005-admin-contract.md` §1）
- 详情 404 fallback 正常
- 非 UUID 走 FastAPI/Pydantic 422 校验

### 用户查询（`GET /api/v1/admin/users`）
- phone 默认始终脱敏（`138******03`），与 ADR/PRD 一致
- `roles` 多角色字段已落（多角色用户：companion,patient）
- reveal-on-demand 走独立端点 + 独立审计（未在本次冒烟内）

### 审计日志（`GET /api/v1/admin/audit-logs`）
- 读侧自动留痕：每次 list/detail 调用都落 `view_*_list` / `view_*_detail` 一行
- `operator` 字段显示 `admin-token`（token 模式占位；admin JWT 模式会显示真实 operator UUID）
- `reason` 字段含查询参数摘要，方便事后追溯

### 边界
- PUT `/orders` 错 method → 405
- dashboard 合法 → 200 / 空 token → 401

---

## §3 关于 P0 误判的撤回

D+0 起手时，我把 `deploy/env.staging:30 ADMIN_API_TOKEN=stagin…ken` 判为「默认 token 泄露 P0，闭环 ADR-0038 漏修」。

**误判原因**：
- 没读 `env.staging` 注释——文件头明示「staging 假值，可公开」
- 没看清 `backend/app/config.py` startup guard 的环境分支——guard 设计上只在 `environment=production` 时强校验，staging 走「受控演练环境」路径
- ADR-0038 修的是前端 hint 文案 + CSP，部署侧 staging 假值是另一个范畴（受控演练 vs 安全约束的取舍）

**帝君 6/3 10:40 UTC 拍 A 口径**：「默认 token」指代码层 `dev-admin-token`，staging 部署侧约定值不算。

详情见 `docs/qa/S2-INT-005-admin-contract.md` §3（已更新为撤回版本）。

---

## §4 reviewer 待定

按 workflow，develop 的 `done` 只能架构师设。本人既是 develop 执行者又是唯一架构师，不可自 review。

帝君拍板候选：胡桃 / 刻晴 / 帝君本人。本 PR 等帝君指派 reviewer 后再发起 `set_status in-review`。

---

## §5 后续不变更点

- 不动 admin-h5 v1 框架（vanilla JS）—— ADMIN-V2 长期重构是 BACKLOG-ADMIN-V2 范畴（本周 B1 边界：React 骨架 + 1 样板）
- 不动 backend admin 路由结构 —— 联调验证已 PASS，无需改业务代码
- W18 fix-admin-h5-contract 已落 9 字段契约，本次冒烟实证有效，不重复

---

## §6 解锁下游

S2-TEST-007（admin-h5 冒烟 + §4 契约）的 `depends_on=S2-INT-005` 在本 PR merge 后即可解除。刻晴可立即起跑 TEST-007。
