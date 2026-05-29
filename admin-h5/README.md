# YiLuAn Admin H5 — MVP

内部运营后台 H5（独立部署，**不进微信小程序**）。当前 MVP 已覆盖：

1. **陪诊师审核**（`#/companions`） — [A21-04] 待审核陪诊师 → 通过 / 拒绝
2. **订单管理**（`#/orders`） — 订单列表、筛选、详情、人工改状态、退款
3. **用户管理**（`#/users`） — 用户列表、筛选、详情、禁用 / 启用
4. **资金对账**（`#/reconciliation`） — TD-MONEY-01 M3 PR-2 (D-048)：差异工单列表、筛选、详情查看、**双签关单**（需不同 Operator 标识 完成第二签）
5. **钱包账本**（`#/wallet`） — TD-MONEY-01 M1 收尾 (D-050)：按 user_id 查 `wallet_ledger` 流水（按 reason 过滤），支持**人工调账**（强制 Operator + 原因，落 `admin_audit_logs`，不可撤销）

## 设计目标

- 内部运营快速完成审核 / 干预闭环
- **零构建**：单页 HTML + Vanilla JS + fetch；不引入 npm 依赖、不打包
- 套 Ant Design Pro 视觉风格的极简自写样式（`styles.css`）

## 目录结构

```
admin-h5/
├── index.html      # 单页结构：登录 / 侧栏 + 三大视图 / 各类弹窗
├── styles.css      # AntD Pro 风格的极简样式（含 sidebar / filter-bar / status-pill）
├── app.js          # Companions / Orders / Users 三个模块 + hash 路由
└── README.md
```

## 本地启动

### 方式 A：Python http.server（推荐）

```bash
cd admin-h5
python -m http.server 8080
```

浏览器打开 <http://127.0.0.1:8080/>

### 方式 B：npx vite

```bash
cd admin-h5
npx vite --port 8080
```

> 后端没起也能打开页面，调用接口时会显示 toast 报错，UI 仍可切换。

## 路由

通过 hash 路由切换主区视图，左侧导航高亮当前项：

| Hash             | 页面          |
|------------------|---------------|
| `#/companions`   | 陪诊师审核（默认） |
| `#/orders`       | 订单管理       |
| `#/users`        | 用户管理       |

## 后端要求

需要后端 dev server 运行（默认 `http://127.0.0.1:8000`），后端 CORS 已设为 `*`。所有请求都需 `X-Admin-Token` header（Token 缓存在 sessionStorage `yiluan.admin.token`）。涉及资金对账双签关单的接口额外要求 `X-Admin-Operator` header（1-64 字符，缓存在 sessionStorage `yiluan.admin.operator`，用于审计 + 双签身份比对）。

### 接口清单

#### 陪诊师审核

- `GET  /api/v1/admin/companions/?page=&page_size=`
- `POST /api/v1/admin/companions/{id}/approve`
- `POST /api/v1/admin/companions/{id}/reject` — body `{ "reason": "1-500 字" }`

#### 订单管理

- `GET  /api/v1/admin/orders?page=&page_size=&status=&patient_id=&companion_id=&date_from=&date_to=`
- `GET  /api/v1/admin/orders/{id}`
- `POST /api/v1/admin/orders/{id}/force-status` — body `{ "status": "...", "reason": "..." }`
- `POST /api/v1/admin/orders/{id}/refund` — body `{ "amount": 199.0, "reason": "..." }`

订单字段（前端读取）：`id` / `order_number` / `status` / `patient_id` / `patient_name` / `companion_id` / `companion_name` / `amount` / `created_at`。

订单状态枚举（与 `backend/app/models/order.py::OrderStatus` 一致）：

- `created`：已下单，等待陪诊师接单
- `accepted`：陪诊师已接单
- `in_progress`：服务进行中
- `completed`：服务完成
- `reviewed`：用户已评价
- `cancelled_by_patient`：用户取消
- `cancelled_by_companion`：陪诊师取消
- `rejected_by_companion`：陪诊师拒单
- `expired`：超时未接单

> 旧文档曾写 `pending / paid / serving / completed / cancelled / refunded`，已废弃，**仅以代码为准**。

#### 用户管理

- `GET  /api/v1/admin/users?page=&page_size=&role=&status=&phone=`
- `GET  /api/v1/admin/users/{id}`
- `POST /api/v1/admin/users/{id}/disable` — body `{ "reason": "..." }`
- `POST /api/v1/admin/users/{id}/enable`

用户字段（前端读取）：`id` / `phone` / `nickname` / `role` / `status` / `created_at`。
角色枚举：`patient / companion / admin`。状态枚举：`active / disabled`。

> 后端字段名以 snake_case 为准，前端原样使用。

## 通用 UX 约定

- 所有破坏性操作走 `confirm()`（MVP，先简单）
- 失败 toast 在右上角，3 秒自动消失
- `401 / 403` → 提示 token 无效 / 无权限，清 localStorage，跳回登录
- 表格 loading 态显示「加载中…」占位
- 审计日志由后端写入，前端无需感知

## 使用流程

1. 打开页面 → 登录界面输入「后端地址」和「Admin Token」
2. Token 缓存在 localStorage（`yiluan.admin.token`），下次自动登录
3. 左侧栏切换三大模块；URL hash 同步更新
4. 顶栏「退出」清 token 回到登录

#### 资金对账（D-048）

- `GET  /api/v1/admin/reconciliation/diffs?page=&page_size=&status=&kind=&provider=&order_id=&run_id=&date_from=&date_to=`
- `GET  /api/v1/admin/reconciliation/diffs/{id}` — 含 `actions[]`
- `POST /api/v1/admin/reconciliation/diffs/{id}/close-requests` — body `{ reason }`，header 额外 `X-Admin-Operator`
- `POST /api/v1/admin/reconciliation/diffs/{id}/close-confirms` — body `{ reason }`，header 额外 `X-Admin-Operator`，**必须与第一签为不同 Operator**
- `GET  /api/v1/admin/reconciliation/runs?page=&page_size=`

差异 status 枚举：`pending / matched / mismatched / compensated / closed`；kind 枚举：`missing_payment / orphan_payment / amount_mismatch / status_mismatch`。仅 `pending / mismatched / compensated` 状态的差异可走双签关单。

## 部署校验（W19-P0-11）

生产部署 admin-h5 前，**必须**确保后端 `ADMIN_API_TOKEN` 环境变量已显式设置为高熵随机串。后端在 `environment=production` 时会校验该值不能为 `dev-admin-token` / 空 / `None`，否则启动 fail（见 `backend/app/config.py::validate_production_config`）。

admin-h5 登录页不再展示任何默认 token 提示；运维通过密钥分发渠道（KMS / 1Password / 内部 secret 仓库）将 token 交付给运营人员，登录时手工粘贴。

## 不在 MVP 范围

- 资质材料图片预览（待后端补图片 URL 列表）
- 角色 / 权限分级（当前 token = super admin）
- 审计日志查看页（后端已写入，前端 v2 再做）
- 美化、动效、移动端适配
- 强校验（金额上限、状态机合法性等，后端兜底）
