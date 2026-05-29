# 医路安 UI/UX 评审报告

**评审日期**：2026-05-28
**评审范围**：`design/`、`wechat/`（33 页面 / 11 组件）、`ios/YiLuAn/Features/`、`admin-h5/`、`polish-backlog.md`、`docs/empty-state-design.md`
**评审方法**：源码静态阅读，**不执行、不修改**；引用文件均为 repo 实际路径

> ⚠️ 任务简报中"品牌色 #FF6B35 / #FF7A45 橙色"的描述与代码不符。实际品牌主色是 **#1890FF（Ant Design 蓝）**，定义见 `design/tokens.json` 第 67 行 `"brand": "#1890FF"`，全仓 104 处引用；`#FF7A45` 是 `accent`（金额强调色），仅 6 处使用；`#FF6B35` 是 `order-card` 组件里的孤立笔误（3 处），需修复。

---

## 1. 设计系统成熟度评估

### 总体打分：6.5 / 10 — **"规范写得齐，落地有断层"**

| 维度 | 状态 | 证据 |
|---|---|---|
| Token 事实源 | ✅ 已建立 | `design/tokens.json` 涵盖 spacing / radius / typography / color / shadow / motion / z-index / 组件尺寸 |
| 跨端生成器 | ⚠️ 半成品 | `design/generate.py` 仅输出 `wechat/styles/tokens.wxss` + `wechat/utils/tokens.js`；iOS `DesignSystem.swift` 靠"手工同步"，README 明文承认（`design/README.md` 第 34 行） |
| 组件库 | ⚠️ 雏形 | 11 个微信组件覆盖核心场景（卡片/Tab/聊天气泡/空状态/骨架/网络条/评分/Loading）；iOS 端**没有等价共享组件层**，只有 `Core/Components/ErrorCodeGuideCard.swift` 一只孤儿 |
| Token 真实采纳率 | ❌ 不达标 | 见下表 |

#### Token 采纳分布（grep 实测）

| 区域 | `var(--color*)` 引用 | 硬编码 hex 颜色 | 评价 |
|---|---|---|---|
| `wechat/pages/**/*.wxss` | 253（44 个文件） | 普遍 | 页面级**基本走 token** |
| `wechat/components/**/*.wxss` | **0** | **69** | 组件层**完全没用 token**——`#fff`、`#999`、`#1890ff`、`#ff6b35` 等遍地 |
| `ios/YiLuAn/Features/**` | `Color.brand` / `Color.textPrimary` 等 | 大量 `.blue` / `.orange` / `.green` / `Color(.systemGray6)` | 各 View 各写各的，见后文 § 5 |
| `admin-h5/styles.css` | 0 | 通篇 Ant Design 调色板硬编码 | 与跨端 token 完全脱钩 |

#### 两套 token 文件并存（潜在事故）

- `wechat/styles/variables.wxss` —— 历史 v2.0，仍被 `wechat/app.wxss` 第 1 行 `@import`
- `wechat/styles/tokens.wxss` —— `tokens.json` 自动生成，**没有任何文件 import**

`design/README.md` 的迁移 backlog（W19+）写明"待迁完后把 tokens.wxss 重命名为 variables.wxss"，但**所有页面/组件目前还吃 v2.0**，自动生成的 token 实际形同虚设。命名差异（`--spacing-2xs` vs `--spacing-xxs`、`--font-size-h2` vs `--font-size-title`）让两套互不兼容，未来切换会全站红字。

#### Polish 类 ≠ Polish 落地

`polish-backlog.md` 标记 P-01..P-12 全部 ✅。源码层面：

- `app.wxss` 确实新增了 `.polish-amount`、`.polish-card`、`.polish-loading`、`.polish-icon-btn`、`.polish-form-error` 等工具类
- **实际被业务页面/组件 className 引用的只有 1 处**：`wechat/pages/orders/index.wxml` 的 `polish-loading`
- 金额组件 `order-card` 仍是 `font-size: 36rpx; color: #ff6b35;`（硬编码，且色号还是错的 — 应为 `#FF7A45`）

> **结论**：polish 工作做了"基建"未做"迁移"，验收时只看了 app.wxss 是否新增类、没看页面是否真的引用。属于**虚假完成**——backlog 应标记为"基建已就绪、业务页面 0/N 已采纳"。

---

## 2. 三端视觉一致性评估

### 总体打分：5 / 10 — **"色板一致、骨骼漂移"**

色板层面三端都围绕 `#1890FF / #FF7A45 / #52C41A / #FAAD14 / #FF4D4F` 这套 Ant Design 同款，第一眼一致；但**组件级尺寸、布局结构、交互模式三端各干各的**。

### 具体不一致点（按严重程度排序）

| # | 不一致点 | 微信 | iOS | admin-h5 | 严重度 |
|---|---|---|---|---|---|
| C-01 | **创建订单的交互模式** | 单页长表单（`pages/patient/create-order/index.wxml` 123 行，所有字段同屏） | 4 步向导（`CreateOrderView.swift` `step 1..4`，进度点 + 上/下一步按钮） | N/A | 🔴 高 |
| C-02 | **聊天输入区** | 自定义 `.quick-actions` + 黄底快捷动作条（`chat/room/index.wxss`） | 极简 `TextField + paperplane.fill`（`ChatRoomView.swift` 95 行，无快捷动作） | N/A | 🔴 高 |
| C-03 | **服务卡片色调** | `service-card` 用渐变蓝；`companion-card` 用 `linear-gradient(135deg, #1890FF, #36CFC9)` 按钮 | `PatientHomeView` serviceCard 用 `Color.brand.opacity(0.1)` 圆形底 + brand 图标 | N/A | 🟡 中 |
| C-04 | **CreateOrder 内部色彩** | 走 token | iOS 写死 `.blue` / `.orange` / `.green` / `Color(.systemGray6)`（`CreateOrderView.swift` 36/45/103/106 行） | N/A | 🔴 高 |
| C-05 | **金额展示** | `order-card` 写死 `#ff6b35`（错误色号）；其他页面已用 polish-amount `#FF7A45` | `OrderDetailView.infoRow(isPrice:true)` 已对齐 `.accent` + `monospacedDigit()` | 写死 `#1890ff` | 🟡 中 |
| C-06 | **主按钮高度** | `app.wxss .btn-primary` `padding: 24rpx 0` 实测高度 ≈ 80rpx；tokens.json 决议 96rpx (48pt) | `.buttonStyle(.borderedProminent)` 走系统默认（约 44pt） | `.btn-primary` 自定义 | 🟡 中 |
| C-07 | **TabBar** | 自绘 `patient-tab-bar` / `companion-tab-bar` 组件（高度 100rpx，硬编码 `#fff`/`#E8E8E8`） | 系统 `TabView` + `Label` | N/A | 🟢 低（系统差异可接受，但小程序组件应改用 token） |
| C-08 | **登录页视觉** | `gradient-hero` 12% 不透明背景 + 圆形 logo placeholder | 同思路（`LoginView.swift` 用 `AppGradient.primary` + `cross.case.fill` 系统图标） | 单卡片 `login-card` `max-width: 480px`，纯白 | 🟢 低（角色定位不同，可接受） |
| C-09 | **空状态规范** | `docs/empty-state-design.md` 定义了 160rpx 图标 + 主副标题 + 按钮；实际 `components/empty-state` 只有 160rpx 圆 + emoji + 一行文字 + hint，**没有 action 按钮位** | iOS `PatientHomeView` 第 80-90 行手写 `Image(systemName:) + Text`，**没有公共空状态组件** | 没有空状态规范 | 🟡 中 |
| C-10 | **聊天气泡** | `chat-bubble` 我方 `#1890ff` 蓝、对方白底；圆角 16rpx、尖角 4rpx | 未独立审计，但 ChatRoomView 调用 `ChatBubbleView`（需后续核查与小程序视觉是否对齐） | N/A | 🟢 低 |
| C-11 | **导航栏高度** | tokens.json 决议 88rpx (44pt)，旧页面有混用 | iOS 系统 navbar 44pt | admin 自定义 56px topbar 深蓝 `#001529` | 🟡 中（admin 是 Ant Design 经典色，可接受） |

---

## 3. 关键用户流程评审

### 3.1 患者流程：登录 → 选角色 → 创建订单 → 支付 → 聊天 → 评价

#### 体验断点 & 摩擦点

| 节点 | 问题 | 文件证据 |
|---|---|---|
| 登录 | 微信端"微信一键登录"和"手机号 + 验证码"两套并存，切换逻辑用 `wx:if="{{!showPhoneLogin}}"` 单向切，**没有"用其他方式登录"的回退入口**（看 `pages/login/index.wxml` 9-49 行） | 🟡 |
| 角色选择 | 文案"后续可在设置中更改"——但 `pages/settings/` 下没有切换角色入口，**承诺无法兑现**（`role-select/index.wxml` 第 4 行 vs `pages/settings/` 目录只有 `delete-account`） | 🔴 |
| 创建订单 | 微信单页表单 vs iOS 4 步向导：**同一产品两端心智模型完全不同**，培训/客服话术无法复用 | 🔴 |
| 创建订单 | 微信端"指定陪诊师"加载失败时只显示"加载中..."占位（`create-order/index.wxml` 第 44 行），**没有错误状态、没有重试** | 🟡 |
| 创建订单 | iOS 第 1 步选服务时价格 `Text("¥\(service.price as NSDecimalNumber)")` —— `NSDecimalNumber` 直接 toString 可能输出 `100.00000000`，缺少 `CurrencyFormatter`（与 `OrderDetailView` 不一致） | 🟡 |
| 支付 | `pages/patient/pay-result/index.wxml` 存在；iOS `PaymentResultView.swift` 139 行——未深入抽样，但**没有"支付中"loading 中间态共享 spec** | 🟡 |
| 聊天 | 微信端有 `.quick-actions`（快捷动作条 `#FFF8E6` 黄底），iOS 端没有 → **iOS 用户失去能力** | 🔴 |
| 聊天 | iOS `ChatRoomView` 用 `.textFieldStyle(.roundedBorder)` 系统样式；微信端走自绘 → 视觉差异明显 | 🟡 |
| 评价 | `review/write/index.wxml` 4 维度评分（守时/专业/沟通/态度）UI 清晰；**未在 iOS Features/Review 中确认是否实现 4 维度同款**（需追加抽查） | 🟡 |
| 通用 | 全流程几乎没有 aria 语义（全仓 `aria-label` 仅 1 处出现在 `empty-state` 组件） | 🔴 |

### 3.2 陪诊师流程：登录 → 申请 → 接单 → 服务 → 收款

| 节点 | 问题 | 文件证据 |
|---|---|---|
| 申请 | `wechat/pages/companion/setup/index.wxml` 209 行长表单，**未见分步引导**；iOS `CompanionSetupView.swift` 同名页面，需后续对齐 | 🟡 |
| 接单 | 微信 `companion/available-orders/` 与 `companion/today-orders/` 两个独立页面；iOS `AvailableOrdersView` 只有一个，**信息架构两端不一致** | 🔴 |
| 服务流程 | 没找到"接单 → 出发 → 到达 → 服务中 → 完成"的状态机 UI 规范文档；`patient/order-detail` 用 `status-{{order.status}}` class 染色，但状态文案/图标的跨端一致性无 spec | 🟡 |
| 紧急呼叫 | 仅微信 `patient/order-detail` 有 `.emergency-fab`（`in_progress` 时浮动按钮 + modal），iOS `EmergencyCallSheet.swift` 存在但未对齐验证 | 🟡 |
| 收款 | `pages/profile/wallet/` 存在；金额展示走 `--color-accent` 与 `polish-amount` 仍未对齐 | 🟡 |

---

## 4. 微信小程序 UI — 优点 / 问题

### 优点
1. **页面级 token 覆盖好**：44 个 wxss 文件、253 处 `var(--color*)`，大部分页面间距/圆角/字号走规范
2. **组件齐**：11 个组件覆盖核心交互（订单卡、陪诊师卡、聊天气泡、骨架屏、空状态、loading 遮罩、网络条、评分星、两套 TabBar、服务卡）
3. **首页升级**：`pages/patient/home/` 用 `gradient-hero` 作搜索英雄区，视觉有层次（`patient/home/index.wxss` 14-21 行）
4. **动效有节制**：`login` / `role-select` 用 keyframes 入场动画，时长 300ms，不过度
5. **骨架屏**：`pages/patient/order-detail/index.wxml` 有真实骨架（不是 Loading 转圈），首屏体验好
6. **暗黑模式骨架就位**：`app.wxss` P-12 `@media (prefers-color-scheme: dark)` 全局覆盖

### 问题（按严重度）
1. 🔴 **组件层 0 token 采纳**：69 处硬编码 hex；改一次品牌色要扫 11 个组件
2. 🔴 **两套 token 文件并存**：`variables.wxss`（在用）vs `tokens.wxss`（生成不用），命名互不兼容，迁移会爆炸
3. 🔴 **polish 工具类近 0 业务采纳**：只有 1 处实际引用，backlog 标记"全部完成"误导
4. 🟡 **金额色号笔误**：`order-card` `#ff6b35`（设计 token 是 `#FF7A45`），patient/companion 两套 order-detail 也有 P-02 注释但实际值需复核
5. 🟡 **`#FFF8E6` 等聊天页硬编码黄色背景**没有 token 来源
6. 🟡 **空状态组件无 action 按钮位**：`docs/empty-state-design.md` 设计有按钮，组件实现没有 → 引导链断
7. 🟡 **z-index 硬编码**：`orders/index.wxss` 用 `var(--z-sticky, 10)`，但 `tokens.json` z_index.sticky=100，fallback 与事实源不符
8. 🟢 **`navigationBarBackgroundColor`** 部分 page 是否 override 需巡检（P-09 说已修，但未抽到反例验证）

---

## 5. iOS UI — 优点 / 问题

### 优点
1. **`DesignSystem.swift` 设计扎实**：Color / Font / Spacing / CornerRadius / AppGradient 完整，命名清晰
2. **登录、首页走规范**：`LoginView`、`PatientHomeView` 全程 `Color.brand / .textPrimary / Spacing.* / .dsHero` 等，**这两个页面是模范**
3. **OrderDetailView 金额对齐**：P-02 落地真实——`infoRow(isPrice:true)` → `.title2.bold().foregroundColor(.accent).monospacedDigit()`（行 216-226）

### 问题
1. 🔴 **CreateOrderView 视觉脱节**：327 行里散落 `.blue` / `.orange` / `.green` / `Color(.systemGray6)` / `.font(.headline)` / `.cornerRadius(8/12)` —— 与 DesignSystem **完全没接触**。这是流程主页面，权重最大、问题最严重
2. 🔴 **ChatRoomView 极简到失能**：95 行，**没有快捷回复**（微信端有 `.quick-actions`）、输入框是 `.textFieldStyle(.roundedBorder)` 系统默认、发送按钮 `Image(systemName: "paperplane.fill").foregroundColor(.blue)` 硬蓝
3. 🔴 **CreateOrder 多步 vs 微信单页**：两端心智模型分裂（详见 § 3.1）
4. 🟡 **iOS 没有共享 UI 组件层**：`Core/Components/` 只有一个 `ErrorCodeGuideCard`，订单卡、陪诊师卡、空状态、骨架屏都在各 View 里重写
5. 🟡 **无障碍空白**：全 Features 目录只有 2 处 `.accessibility*` 调用，VoiceOver 体验未做
6. 🟡 **CurrencyFormatter 使用不统一**：OrderDetailView 用 `CurrencyFormatter.cnyWithUnit`；CreateOrderView serviceSelectionStep 直接 `NSDecimalNumber` toString
7. 🟢 **TabBar 用系统组件**：可接受，但 tab 图标全是 SF Symbols（`house.fill` 等），缺少品牌识别

---

## 6. admin-h5 UI — MVP 是否够用？

### 评估：**够 MVP，但要早期立规矩**

#### 优点
1. 单 HTML + 单 CSS + JS，**无框架依赖**，CSP 严格（`index.html` 第 7 行 `default-src 'self'` + `frame-ancestors 'none'`）
2. 视觉走 **Ant Design Pro 风格**（`#001529` 深蓝 topbar、`#1890ff` 主蓝、`status-pill--*` 状态色板），对运营/技术用户认知零成本
3. 路由用 hash + `route-view` 切换，简单可控
4. Token 用 `X-Admin-Token` 只缓存在 sessionStorage（关闭标签页失效）—— **安全意识好**
5. `[hidden] { display: none !important; }` 全局兜底注释清楚（`styles.css` 第 23 行）—— 有反思过往坑

#### 问题
1. 🟡 **零设计 token 体系**：231 行 CSS 全硬编码 hex，未来若品牌色调整需手动改全部
2. 🟡 **登录卡片有泄露调试痕迹**：`index.html` 第 27 行 `当前环境默认 Token：<code>staging-admin-token</code>` —— **生产环境必须删**
3. 🟡 **响应式弱**：`main { max-width: 1200px }` 在 < 1024px 平板上侧栏 + 内容会挤
4. 🟡 **可访问性 0 投入**：表格/按钮无 `aria-*`、无键盘焦点环
5. 🟢 **无空状态规范**：列表空时表现未定义（需运行时确认）

#### MVP 判定
- 内部运营临时用 → ✅ 够
- 半年内会上 100+ 商户/客服多角色 → ❌ 需要重写为框架版（React + Ant Design Pro 或 Vue + Vben），现在的单文件结构扩展不动
- **建议**：admin-h5 **冻结现状**，B5 立项重写时再做 token 化与权限分层

---

## 7. UI/UX 改进建议清单

> 工作量：S ≤ 1 天 / M ≤ 1 周 / L ≤ 1 sprint

### P0（阻塞品牌一致性 / 阻塞主流程）

| ID | 建议 | 涉及文件 | 工作量 |
|---|---|---|---|
| R-01 | **iOS `CreateOrderView` 全量迁到 DesignSystem**：替换所有 `.blue/.orange/.green/Color(.systemGray6)/.font(.headline)/.cornerRadius` 为 `Color.brand/.accent/.success/.bgInput/.dsTitle/CornerRadius.lg` | `ios/YiLuAn/Features/Order/Views/CreateOrderView.swift` | M |
| R-02 | **统一创建订单交互模式**（产品决策先行）：定 iOS 也走单页 / 微信也走多步 / 都走"折叠式分步"中的一种，写进 `docs/design/create-order-spec.md` | 决策 + 双端实现 | L |
| R-03 | **微信组件层 token 化**：11 个组件的 `index.wxss` 把硬编码 hex 全替换为 `var(--color-*)` / `var(--radius-*)` / `var(--spacing-*)` | `wechat/components/**/*.wxss`（69 处） | M |
| R-04 | **修 `#ff6b35` → `#FF7A45`**：`order-card`、`patient/order-detail`、`companion/order-detail` 三处金额色号，统一走 `var(--color-accent)` | 3 个 wxss | S |
| R-05 | **role-select 的"设置中可改"承诺要么兑现要么删文案**：在 `pages/settings/` 加切换角色入口，或改文案 | `role-select/index.wxml` + `pages/settings/` | S |
| R-06 | **删 admin-h5 默认 token 文案**：`当前环境默认 Token：staging-admin-token` 生产泄露风险 | `admin-h5/index.html` 第 27 行 | S |

### P1（影响一致性 / 影响关键流程体验）

| ID | 建议 | 涉及文件 | 工作量 |
|---|---|---|---|
| R-07 | **统一 wechat 两套 token**：定时间表把所有页面/组件迁到 `tokens.wxss`，删 `variables.wxss`；先 alias 兼容（`--spacing-2xs → --spacing-xxs` 等） | `wechat/styles/*` + 全站 wxss | L |
| R-08 | **iOS 建共享组件层** `Core/Components/`：抽出 `OrderCard`、`CompanionCard`、`EmptyStateView`、`SkeletonRow`、`ChatBubble`、`PrimaryButton`（包高度 48pt、`AppGradient.primary`、按下 scale 0.98） | 新建 6 个 swift 文件 | M |
| R-09 | **iOS ChatRoomView 补齐快捷动作条**：与微信 `.quick-actions` 对齐（出发提醒/到达提醒/上传材料） | `ChatRoomView.swift` + ViewModel | M |
| R-10 | **业务页面真正引用 `polish-*` 类**：金额位 `class="polish-amount"`、加载位 `polish-loading`、错误位 `polish-form-error`、图标按钮 `polish-icon-btn`；扫一遍 33 页/11 组件 | wechat 全站 | M |
| R-11 | **空状态组件加 action slot**：让 `empty-state` 支持 `<slot name="action">`，对齐 `docs/empty-state-design.md` 的按钮规格，避免引导链断 | `wechat/components/empty-state/*` | S |
| R-12 | **金额格式统一**：iOS `CreateOrderView` 服务价格走 `CurrencyFormatter.cnyWithUnit`；微信端确认所有金额来源经 `formatCurrency.js` | iOS + wechat | S |
| R-13 | **微信 `pages/login` 双登录方式加切换回退入口**：从手机号登录回到微信登录 | `pages/login/index.wxml` | S |
| R-14 | **统一陪诊师订单 IA**：决定是合并 `available-orders + today-orders` 还是 iOS 拆分；写进 spec | 决策 + 双端 | M |
| R-15 | **iOS `ChatBubbleView` 视觉与微信 `chat-bubble` 对齐**：圆角 16rpx ≈ 8pt、尖角 4rpx ≈ 2pt、我方 brand 蓝、对方白底带浅阴影 | iOS `ChatBubbleView.swift`（待找） | S |

### P2（机会式打磨 / 长期收益）

| ID | 建议 | 工作量 |
|---|---|---|
| R-16 | **无障碍专项**：微信所有图标按钮加 `aria-role="button" aria-label="..."`；iOS 所有 `Image(systemName:)` 当按钮用时加 `.accessibilityLabel`；评审验收 VoiceOver / 朗读 | L |
| R-17 | **`design/generate.py` 增加 iOS 输出器**：自动生成 `DesignSystem.swift`，去掉"手工同步"风险；Xcode 工程引用相对路径文件，pbxproj 不动 | M |
| R-18 | **建立视觉回归基线**：用 `wechat-devtools` 截图 + iOS XCUITest snapshot，每个主流程页面截一张存 `docs/design/screenshots/baseline/`，PR 自动 diff | L |
| R-19 | **admin-h5 设计 token 化**（如果还会维护 6+ 个月）：抽 `:root { --color-* }`，否则等 B5 重写 | S（局部）/ L（重写） |
| R-20 | **status pill 跨端统一**：admin-h5 已经有 `status-pill--paid/serving/completed/cancelled/refunded`，微信和 iOS 的订单状态色应与之对齐成全局事实源 | M |
| R-21 | **写《医路安设计语言 v1》一页 PDF**：放品牌色、字号阶梯、按钮三种、卡片三种、状态色，发给所有开发者作信仰对齐 | S |
| R-22 | **聊天 `#FFF8E6` 等孤色 token 化**：补 `--color-warm-bg` 到 tokens.json | S |
| R-23 | **暗黑模式抽查**：微信全站打开暗黑切一遍，捕捉 P-12 之外漏掉的低对比度文字 | S |

---

## 附录：评审依据文件清单

- `design/README.md`、`design/tokens.json`、`design/generate.py`
- `polish-backlog.md`、`docs/empty-state-design.md`、`docs/admin-mvp-scope.md`
- `wechat/app.wxss`、`wechat/styles/variables.wxss`、`wechat/styles/tokens.wxss`、`wechat/app.json`
- `wechat/pages/`：login / role-select / patient/home / patient/create-order / patient/order-detail / orders / chat/room / companion/home / companion/setup / profile / review/write
- `wechat/components/`：order-card / companion-card / empty-state / chat-bubble / patient-tab-bar / loading-overlay / network-banner
- `ios/YiLuAn/SharedViews/MainTabView.swift`
- `ios/YiLuAn/Core/Extensions/DesignSystem.swift`
- `ios/YiLuAn/Features/Auth/Views/LoginView.swift`、`Patient/Views/PatientHomeView.swift`、`Order/Views/CreateOrderView.swift`、`Order/Views/OrderDetailView.swift`、`Chat/Views/ChatRoomView.swift`
- `admin-h5/index.html`、`admin-h5/styles.css`

**评审人**：UI/UX 评审师子代理
**评审标准**：基于源码事实而非主观偏好；所有断言均给出文件路径 + 行号 / grep 数据支撑
