# ADR-0042 — admin-v2 框架选型（React vs Vue）+ B1 边界

> 状态：**Draft（D+1）** · 作者：魈 · 日期：2026-06-03
> 关联：BACKLOG-ADMIN-V2 / ADR-0034 (admin-v2 auth) / 帝君 2026-06-03 拍板 B1 边界
> Supersedes: 无（首份 admin-v2 框架决策）

---

## 1. 背景

admin-h5 v1 是 vanilla JS + 单 HTML + 1073 行 app.js 形态。9 项管理能力（陪诊师审核 / 订单管理 / 用户管理 / 审计 / 退款审批 / 仪表盘 / 多角色 / OrderDetailDrawer / dashboard），实质已是中型 SPA 但缺框架。

帝君 2026-06-03 拍板 BACKLOG-ADMIN-V2 本周交付 **B1 边界**：React 骨架 + 1 个迁移样板（陪诊师审核），其余 8 项下迭代。

理由：硬塞全迁移 = 6-8 周工作量必假交付；骨架 + 1 样板出来后下迭代复制粘贴 8 次速度极快。

本 ADR 钉死框架选型 + 骨架边界 + 迁移策略。

---

## 2. 选型对比：React vs Vue 3

| 维度 | React 18 | Vue 3 | 选 React 理由 |
|------|----------|-------|---------------|
| 团队熟悉度 | 业内主流，AI agent (胡桃) 训练数据更厚 | 国内中型项目偏多 | ✅ AI 协作产物质量 React > Vue |
| 生态 admin 模板 | Refine / react-admin / Ant Design Pro / Material UI Pro 多个成熟方案 | Vben Admin / Naive Admin | 持平，但 Ant Design Pro 与 admin-h5 现有 9 项能力对齐度最高 |
| 类型系统 | TypeScript first-class | TypeScript 良好但 Vue SFC 类型推导稍弱 | ✅ React TS 体验更稳 |
| state management | Zustand / TanStack Query / Redux Toolkit | Pinia | 持平 |
| 学习曲线 | 中等（hooks 心智） | 低（template 友好） | 持平（本项目纯 AI agent 开发不影响） |
| build / dev | Vite + React | Vite + Vue | 持平 |
| 与 backend admin token auth 兼容 | 框架无关 | 框架无关 | 持平 |
| Playwright E2E | 框架无关 | 框架无关 | 持平 |
| AI agent 实施成本 | 训练数据丰富，模板代码生成质量高 | 同样可，但样例少于 React | ✅ 略胜 |
| 长期招聘市场 | React 工程师供给 > Vue 工程师 | 同样可，但 Vue 在国内大厂占比上升 | 持平 |

### 决策：**React 18 + Vite + TypeScript + Ant Design Pro 5.x**

附加依赖：
- **状态**：Zustand（轻量，不引 Redux 复杂度）
- **数据**：TanStack Query（query/mutation/cache 一站式，与 admin REST API 契合）
- **路由**：React Router 6
- **权限**：Casbin / 自实现 RBAC（4 角色：超管/财务/客服/BD）
- **表单**：Ant Design Form + Zod 校验

---

## 3. B1 边界（本周交付）

### 3.1 必交付

| 项 | 范围 | 验收 |
|---|---|---|
| **React 骨架** | Vite + TS + React Router + AntD Pro 布局 + 登录页 + sessionStorage admin token 接入 | `npm run dev` 起 + 登录页可见 + token 写入 sessionStorage |
| **1 样板：陪诊师审核** | 列表 / 详情 / 通过/拒绝 / 审计联动 | 走通 4 个 REST 端点 / 列表分页 / 详情 drawer / 审计行写入 |
| **权限分层骨架** | 4 角色定义（超管/财务/客服/BD）+ 路由守卫 + AntD menu 按角色显隐（不真实接入后端权限）；menu 项加 `data-role-{role}` 属性为后续 Playwright E2E 留 selector（刻晴 review 建议） | 切角色（前端 mock）能看到对应 menu 项 |
| **构建产物** | `npm run build` 产 dist/，部署路径与 nginx 配置兼容 | dist 体积 < 2MB gzip |
| **目录结构** | src/{features/companion-review, shared/{api,hooks,components,layout,types}, routes} | 8 项能力迁移时 features/<名> 就位即可 |

### 3.2 不交付（下迭代）

- 订单管理 / 用户管理 / 审计 / 退款审批 / 仪表盘 / OrderDetailDrawer / dashboard / 多角色 8 项业务能力（保留 admin-h5 v1 运行）
- 真实后端 RBAC 接入（B1 用前端 mock）
- Playwright E2E（B1 用单测 + 手动 smoke）
- 国际化 i18n（B1 中文写死）
- 主题切换（默认 antd 主题）

### 3.3 共存策略（v1 ↔ v2 并存）

- admin-h5 v1（vanilla）继续部署在 nginx `/admin/` 路径
- admin-v2 部署在 nginx `/admin-v2/` 路径
- 共用 backend `/api/v1/admin/*` 端点
- 共用 sessionStorage `yiluan.admin.token` key（同源 cookie/storage）
- 路由分流：v1 维护期间 v2 仅"陪诊师审核"页对外，其余 menu 项点击 **用 `window.location.assign('/admin/#/...')` 跳回 v1**（避免 SPA history 栈污染，刻晴 review 建议）
- 8 项能力按迭代逐个迁完后 v1 整体下线

---

## 4. 实施分阶段

### Phase 1（本周 D+5 内交付，本 ADR 范围）
- 项目脚手架 + 路由 + 登录 + 陪诊师审核样板 + 部署

### Phase 2-9（后续 8 个迭代，每迭代 1 项能力）
顺序建议（按业务风险 + 复杂度倒序）：
1. 仪表盘（最简，验证 React Query 模式）
2. 用户管理（CRUD 标准）
3. 订单管理 + OrderDetailDrawer（中型）
4. 审计日志（只读 + 过滤复杂）
5. 退款审批（资金线高危，需 Code Review 加严）
6. 多角色权限（接入真后端 RBAC）
7. dashboard 扩展 + 国际化
8. v1 下线 + Playwright E2E 全覆盖

每阶段独立 task + 独立 PR，不堆 batch。

---

### 4.1 每 feature page 标准动作：list + detail + mutation 三件套（r1 补充 2026-06-04）

> 动因：ADR-0044 实施 PR-A/B 过程中发现 PR-A 脚手架假设 backend `GET /admin/companions/{id}` detail endpoint 存在但实际没有，进入 admin 审核能力漏洞（胡桃 PR-A self-review + 魈 ADR-0044 追加）。为避免 Phase 2-9 拷贝同错误路径，本附录钉死 admin feature page 标准三件套。

**admin-v2 任何 feature page 必须齐 list + detail + mutation 三件套**：

| 件 | 责任 | 禁止省略场景 |
|---|---|---|
| **list** | 分页 + 过滤 + 跳页 + 排序，row 字段**仅含表格列**（精简，减请求体积） | 全场景不可省略 |
| **detail** | drawer / 独立页，**展开 row 不可见的所有审核 / 编辑必要字段**（含文件 / 图片 / 关联实体含字 / 历史指标等） | **不可省略**。例外：仅含 list row 同字段的纯本表场景（如纯查询表）可省 detail，但需在 ADR / task acceptance 明示该 feature 不含 detail 以及原因 |
| **mutation** | approve / reject / patch / delete / 开关切换等动词，**触发后必有 `admin_audit_log` 留痕**（action + target_id + operator + reason） | 只读 feature（仅 view_*_list/view_*_detail 审计）可无 mutation |

**实施前套检查清单**（胡桃 ADR 实施前契约核验 SOP，胡桃 MEMORY 已落）：

```bash
# 1. backend list endpoint 字段 vs UI 需求 gap 检
rg "class \w+Item.*BaseModel" backend/app/api/v1/admin/<feature>.py
rg "class \w+Detail.*BaseModel" backend/app/api/v1/admin/<feature>.py

# 2. mutation endpoint 实现 + audit 核
rg "@router\.(post|patch|delete).*<feature>" backend/app/api/v1/admin/<feature>.py
rg "AdminAuditLog" backend/app/api/v1/admin/<feature>.py
```

任一件缺失 → ping 架构师拍：
- 小 gap（字段多/少 2-3 个）→ 本 PR 补
- 全栈改动（模型迁移 / signed URL / PII 挡位策略变化）→ 拆 design task + ADR

**Phase 2-9 每 task acceptance 需钉三件套齐备**，避免 Phase 1 拷贝错误路径重现。Code Review checklist 加一项（已隶 docs/conventions/code-review-checklist.md）：“三件套齐？”

关联：
- ADR-0044 §3.4：本附录原上下文来源
- 胡桃 MEMORY SOP（ADR 实施前契约核验）：本附录三件套是 checklist 钉死点之一

---

## 5. 验收（B1）

- [ ] ADR-0042 落盘（本 ADR Accept）
- [ ] `admin-v2/` 目录脚手架 commit
- [ ] React/TS/Vite + AntD Pro + 4 角色路由守卫 + 陪诊师审核 4 个端点接通
- [ ] sessionStorage admin token 与 admin-h5 v1 同源共存
- [ ] nginx 配置 `/admin-v2/` 路径
- [ ] README.md 标注 v1 / v2 共存策略
- [ ] 单测覆盖：陪诊师审核 view + service（≥ 8 case，覆盖维度：list / mutation 成功+失败 / 权限 deny / loading / error boundary。刻晴 review 建议）
- [ ] 手动 smoke：登录 + 4 角色 menu 显隐 + 陪诊师审核走通

---

## 6. 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| AntD Pro 模板与 admin-h5 视觉风格差距大引发用户体验割裂 | 中 | v1/v2 并存期，新功能 v2 落，老功能仍 v1，逐步迁移 |
| nginx 路径分流 cookie/storage 冲突 | 低 | 同源 sessionStorage，key 一致 |
| React Query cache 与 v1 sessionStorage 数据不同步 | 中 | v2 不读 v1 数据，独立 fetch；v1 不读 v2 数据 |
| Ant Design Pro 引入构建产物体积大 | 中 | tree-shaking + 按需引入 antd 组件；目标 dist gzip < 2MB |
| 8 项能力下迭代时复制样板代码风格漂移 | 中 | 样板自身定 ESLint + Prettier + 模板生成器（`npx plop component`） |

---

## 7. 决定

**Draft → 待 review**

- Reviewer：胡桃（developer，作为下迭代 8 项能力的实施者）+ 刻晴（tester，作为 E2E + smoke 视角）
- Owner Approval：帝君（B1 边界已拍，本 ADR 是边界内的选型 + 骨架决策细化）

Accept 后立刻起手 Phase 1 实施（develop task 由胡桃 / 我评估）。

---

## 8. 反向引用

- ADR-0034 admin-v2 auth：本 ADR Phase 6（多角色权限）落地时反向引用
- ADR-0038 admin-h5 默认 token 加固：v2 继承同样的 token 安全约束
- BACKLOG-ADMIN-V2 task：本 ADR Accept = 该 task 设计阶段完成
