# admin-v2

> 医路安管理后台 v2 — React 18 + Vite + TS + AntD Pro 5.x
> ADR-0042 Phase 1（S2-DEV-013）

## v1 ↔ v2 共存策略

| 维度 | admin-h5 v1 | admin-v2 (本目录) |
|---|---|---|
| 技术栈 | vanilla JS + 单 HTML + 1073 行 app.js | React 18 + Vite + TS + AntD Pro 5.x |
| nginx 路径 | `/admin/` | `/admin-v2/` |
| sessionStorage token key | `yiluan.admin.token` | **同源共用**：`yiluan.admin.token` |
| Phase 1 已实现 | 9 项管理能力（全） | **1 样板**：陪诊师审核 |
| 其他 menu 项点击 | — | **跳回 v1**：`window.location.assign('/admin/#/...')` |

### 跨版本同步

v1 改 sessionStorage（如 logout） → v2 通过 `storage` event 监听 → 跳 `/admin-v2/login`。

详 `src/shared/api/authStore.ts` `subscribeToSessionStorageSync`。

---

## 开发

```bash
cd admin-v2
npm install
npm run dev              # http://localhost:5173/admin-v2/
                         # API 通过 vite proxy /api/v1 → backend:8000
```

## 构建

```bash
npm run build            # 输出到 dist/
npm run bundle-size      # 检查 gzip < 2MB budget gate
```

## 测试

```bash
npm run test             # vitest 单测（≥ 8 case 覆盖列表 / mutation / RBAC / authStore）
npm run test:watch       # 监听模式
```

## CI

`.github/workflows/admin-v2-ci.yml` — path-filter gate 模式：
- 改 `admin-v2/**` → 自动跑 tsc + vitest + build + bundle-size + path-consistency
- 不改 `admin-v2/**` → skip（required check 计 success，不锁死非 admin-v2 PR）

---

## Phase 1 (B1) 范围（ADR-0042 §3.1）

✅ 已实现
- Vite + TS + React 18 + AntD Pro 5.x 骨架
- 登录页 + sessionStorage admin token（与 v1 同源）
- **陪诊师审核样板**（list / 详情 drawer / 通过 / 拒绝，接 4 个 `/api/v1/admin/companions/*` 端点）
- 4 角色权限骨架（超管 / 财务 / 客服 / BD）+ AntD menu 按角色显隐
- menu `data-role-{role}` 属性给 Playwright E2E selector
- v1-only menu 项 tooltip + loading + `window.location.assign('/admin/#/...')`
- Vite dev proxy ↔ nginx prod 反代路径一致性 CI gate
- sessionStorage token 不缓存副本 + storage event cross-tab sync
- dist gzip < 2MB CI budget gate

❌ 不在 Phase 1（留后续 Phase 2-9 迭代）
- 订单管理 / 用户管理 / 审计 / 退款审批 / 仪表盘 / OrderDetailDrawer / dashboard 8 项业务能力
- 真实后端 RBAC（B1 用前端 mock）
- Playwright E2E（B1 用单测 + 手动 smoke）
- 国际化 i18n（B1 中文写死）
- nginx `/admin-v2/` 路径配置（PR-C 单独）

---

## 目录结构

```
admin-v2/
├── src/
│   ├── features/
│   │   ├── login/                # 登录页
│   │   └── companion-review/     # 陪诊师审核样板
│   ├── shared/
│   │   ├── api/                  # apiClient / authStore
│   │   ├── components/           # RequireAuth / ForbiddenPage
│   │   ├── layout/               # AppLayout（4 角色 menu）
│   │   ├── styles/               # global.css
│   │   └── types/                # role.ts (RBAC mock)
│   ├── App.tsx                   # 路由
│   └── main.tsx                  # entry
├── scripts/
│   ├── check-bundle-size.mjs     # CI gate: gzip < 2MB
│   └── check-api-path-consistency.mjs  # CI gate: vite / nginx 路径一致
├── vite.config.ts                # Vite + dev proxy + chunk split
├── tsconfig.json
├── package.json
└── README.md
```

后续 Phase 2-9 按 `features/<name>/` 复制陪诊师审核模板即可（list + detail drawer + mutation + audit）。

---

## 反向引用

- ADR-0042 admin-v2 框架选型 + B1 边界
- S2-DEV-013 本 task
- BACKLOG-ADMIN-V2 长期重构主线
- ADR-0038 admin-h5 默认 token 加固（v2 继承同样约束）
- ADR-0034 admin-v2 auth（Phase 6 接后端 RBAC 时反向引用）
