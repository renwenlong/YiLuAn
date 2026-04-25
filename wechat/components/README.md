# 公共组件库

> 微信小程序公共组件清单。本文档随组件演进同步维护，新增组件须更新此处。

## 分类

### 1. 业务卡片 (business)
| 组件 | 路径 | 用途 | 主要 props |
|---|---|---|---|
| `service-card` | `/components/service-card/index` | 患者首页"3 档服务"展示卡 | `type, price, title, desc` |
| `companion-card` | `/components/companion-card/index` | 患者首页/搜索结果"陪诊师卡片" | `companion, distance` |
| `order-card` | `/components/order-card/index` | 订单列表项（患者&陪诊师双角色复用） | `order, role` |

### 2. 通用 UI (common, 已提升为全局组件)
> 已在 `app.json` 的 `usingComponents` 中全局注册，**页面 json 无须再声明**。

| 组件 | 路径 | 用途 | 主要 props |
|---|---|---|---|
| `loading-overlay` | `/components/loading-overlay/index` | 全屏加载遮罩 | `visible, text` |
| `empty-state` | `/components/empty-state/index` | 列表空状态占位 | `text, icon, ctaText, bind:tap` |

### 3. 角色 Tab Bar (role-tab, 已提升为全局组件)
> 业务上不用原生 tabBar — 因为患者/陪诊师两套底栏完全不同。

| 组件 | 路径 | 用途 |
|---|---|---|
| `patient-tab-bar` | `/components/patient-tab-bar/index` | 患者底栏：首页 / 订单 / 消息 / 我的 |
| `companion-tab-bar` | `/components/companion-tab-bar/index` | 陪诊师底栏：今日 / 订单 / 消息 / 我的 |

### 4. 即时聊天 (chat)
| 组件 | 路径 | 用途 |
|---|---|---|
| `chat-bubble` | `/components/chat-bubble/index` | 聊天气泡（自/对方两种态） |
| `rating-stars` | `/components/rating-stars/index` | 评分星星（既评分又只读） |

---

## 全局 vs 局部组件原则

- **全局**（提升到 `app.json.usingComponents`）：跨 5+ 页面 / 跨业务 / 不依赖业务上下文。当前：`loading-overlay`、`empty-state`、`patient-tab-bar`、`companion-tab-bar`。
- **局部**（页面 json 单独声明）：业务耦合卡片、有较重渲染开销且不是每个页面都需要的（如 `chat-bubble` 仅聊天室用）。

> 提升为全局会让所有页面（含分包）都加载该组件代码 — 仅在确实跨包高频使用时才提升。

---

## 新增组件流程

1. `components/<name>/index.{js,wxml,wxss,json}` 四件套，`Component()` 顶层导出。
2. props 用 `properties: {}`、事件用 `triggerEvent('xxx', detail)`，避免 page-bus 强耦合。
3. 写 `__tests__/<name>.test.js`（参考 `companion-card.test.js`）— 至少覆盖 props 渲染 + 主要事件。
4. 在本 README 对应分类追加一行。
5. 若评估为高频跨包使用，再考虑写入 `app.json.usingComponents` 提升为全局。

---

## 性能注意事项

- 全局组件会被打入主包，节制使用。
- 业务卡片（`order-card`、`companion-card`、`service-card`）当前都被多个分包页面复用 — 微信会自动把跨包共享组件打进主包，不必手动提升。
- `lazyCodeLoading: requiredComponents` 已在 `app.json` 开启，未引用的组件代码不会加载。
