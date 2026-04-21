# YiLuAn Admin H5 — Companion Audit MVP

[A21-04] 内部运营专用的最简陪诊师审核页面。**不进微信小程序**，独立 H5。

## 设计目标

- 内部运营 5 分钟内完成一次「待审核陪诊师 → 通过 / 拒绝」闭环
- 零构建：单页 HTML + Vanilla JS + fetch，套 Ant Design Pro 视觉风格但不引入任何框架
- 不做美化、不做动画、不做移动端适配（MVP 唯一目标是跑通业务闭环）

## 目录结构

```
admin-h5/
├── index.html      # 单页结构 + 登录/列表/拒绝弹窗
├── styles.css      # AntD Pro 风格的极简样式
├── app.js          # 业务逻辑（fetch + 渲染 + 事件）
└── README.md
```

## 本地启动

### 方式 A：Python http.server（推荐，依赖最少）

```bash
cd admin-h5
python -m http.server 8080
```

然后浏览器打开 <http://127.0.0.1:8080/>

### 方式 B：npx vite

```bash
cd admin-h5
npx vite --port 8080
```

> **不需要** 装任何 npm 依赖；Vite 临时运行，纯静态服务即可。

## 后端要求

需要后端 dev server 运行（默认 `http://127.0.0.1:8000`），后端 CORS 已设为 `*`，无需额外配置。

涉及的 endpoint（已实现，参考 `backend/app/api/v1/admin/companions.py`）：

- `GET  /api/v1/admin/companions/?page=1&page_size=20`
- `POST /api/v1/admin/companions/{id}/approve`
- `POST /api/v1/admin/companions/{id}/reject`  body: `{ "reason": "xxx" }`

所有请求都需要 `X-Admin-Token` header。Token 取自后端环境变量 `ADMIN_TOKEN`。

审计日志由后端 `AdminAuditService` 自动写入，前端无需关心。

## 使用流程

1. 打开页面 → 登录界面输入「后端地址」和「Admin Token」
2. Token 缓存在浏览器 localStorage（`yiluan.admin.token`），下次自动登录
3. 列表展示待审核陪诊师（分页 20 条/页）
4. 单条记录右侧「通过 / 拒绝」按钮
   - 通过：弹 confirm，确认后调 `/approve`
   - 拒绝：弹模态框填原因（1-500 字），调 `/reject`
5. 操作成功后自动刷新当前页

## 不在 MVP 范围

- 资质材料图片预览（当前后端 `certifications` 仅返回文本字段，待后端补图片 URL 列表后再迭代）
- 角色/权限分级（当前 token = super admin）
- 审计日志查看页（后端已写入，前端 v2 再做）
- 美化、动效、移动端适配
