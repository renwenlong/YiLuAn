# ADR-0063 — i18n 多语言切换技术方案（微信小程序 + iOS，中/英）

> **状态：** Proposed（I18N-DSN-001 设计交付，待 review + 帝君 awaiting-approval）
> **作者：** 魈（架构师）
> **创建：** 2026-07-09
> **上游：** PRD-I18N-001（done）、ADR-0062（后端错误本地化方案 C）
> **决策锚：** 帝君 2026-07-09 拍板 §6=方案 C、分支 `feature/i18n-multi-language`（合远端 main）、repoPath `/home/wenlongren/repo/YiLuAn`
> **证据仓：** `/home/wenlongren/repo/YiLuAn` @ `bef9ea8`（下述所有路径/行号均实测）

---

## 1. 背景与目标

PRD-I18N-001 要求微信 + iOS 两端界面支持中/英手动切换，选择持久化，首次默认取系统语言。两端均零 i18n 基础设施（实测：微信 wxml 中文 ~671 处、iOS View 内 `Text("中文")` ~124 处 / 全量字面量 ~690；iOS 无 `.lproj`/`.xcstrings`/`knownRegions`）。

本 ADR 定：①跨端 key 规范 + 字典 SSoT ②微信 i18n 运行时 ③iOS 本地化方案 ④后端错误本地化（承接 ADR-0062 方案 C）⑤FR-2 默认语言判定。并据此拆 develop/test。

---

## 2. 现状基线（实测证据，非印象）

| 维度 | 微信 | iOS |
|---|---|---|
| 框架 | 原生小程序（非 Taro/uni） | SwiftUI + XcodeGen |
| i18n 现状 | 无库无机制，wxml 内联中文 | 零本地化资源 |
| 全局状态落点 | `store/index.js`（178行，`_state={isAuthenticated,user}` 可扩 `language`） | `@AppStorage` 已用（`FontScale.swift`，范式现成） |
| 设置页落点 | `pages/profile/settings/index.{js,wxml}` | `Features/Settings/Views/SettingsView.swift`（`List`/`Section`） |
| 枚举映射落点 | `utils/constants.js`（`STATUS_MAP.created={label:'待接单'}...`） | `Core/Models/Order.swift`（`enum` case） |
| 文件接入 | 手动引 wxs/js | XcodeGen `sources:[{path:YiLuAn,excludes:['**/*.md']}]` → `YiLuAn/` 下文件**自动纳入**，`.xcstrings` 放对位置即可，无需手改 project.yml sources |
| error_code 消费 | ❌ 无 dispatcher（`wechat/services/request.js` 不存在） | ✅ `APIClient.swift` 已按 `error_code` switch dispatch |

**关键发现（§7.3 术语表需补齐）：** iOS `Order.swift` 订单状态含 `cancelledByPatient` / `cancelledByCompanion`（非 PRD §7.3 的单一 `cancelled`），微信 `constants.js` 亦有独立 STATUS_MAP。**两端 status 枚举实际集合大于 PRD §7.3 骨架，design 落地时以两端代码实际枚举为准补全译文。**

---

## 3. 跨端统一层：Key 规范 + 字典 SSoT

### 3.1 Key 命名规范（两端共用同一 key 集）

- **分层 namespace**（点分）：`common.*`（确认/取消/提交/返回/保存…）、`settings.*`、`order.*`、`orderStatus.*`、`serviceType.*`、`role.*`、`login.*`、`home.*`、`chat.*`、`error.*`（error_code 映射）。
- **动态占位**：统一 `{name}` 具名占位，函数签名 `t(key, params?)`，句式基线以 **PRD §7.5** 为准。例：`otp.sentTo = "验证码已发送至 +86 {phone}" / "Code sent to +86 {phone}"`。**禁止**中文语序直译——英文文案按目标语序独立撰写。
- **枚举 key**：以后端 `code` 为 key 后缀，两端一致。例：`orderStatus.created`、`serviceType.full_accompany`。
- **error_code key**：`error.<ERROR_CODE>`，如 `error.ORDER_TRANSITION_INVALID`。

### 3.2 字典 SSoT（single source of truth）

- **一份主字典**（JSON，中英并排），落 `docs/i18n/dictionary.md` 或仓库约定路径，含 PRD §7 术语 + §7.5 句式模板 + error_code 映射 + **§3.3 的 orderStatus 9-code 全集 + refundState**。
- **★orderStatus / refundState 字典条目以 §3.3 权威表为唯一基准★**：`orderStatus.*` = §3.3 列的 9 code（`created/accepted/in_progress/completed/reviewed/cancelled_by_patient/cancelled_by_companion/rejected_by_companion/expired`），**无 `orderStatus.in_service`（幻影）、无 `orderStatus.refunded`（归 `refundState.refunded`）**。DEV-001 照此落、TEST-001 照此核，不再参 PRD §7.3 旧骨架。
- 微信直接以 JS 对象消费；iOS 以 `.xcstrings` 消费。**主字典为人读 SSoT，两端各自生成/同步**（本期手工对齐，key 集强制一致；后续可加校验脚本比对两端 key 覆盖）。
- 术语译文强制一致（陪诊师=Companion、患者=Patient…），避免各端各译。

### 3.3 订单状态 / 退款状态 权威全集表（backend SSoT，解 刻晴 r2 三方对不齐）

**实测真源 `backend/app/models/order.py`**：`OrderStatus` 与 `RefundState` 是**两个独立枚举**（ADR-0041 支付域/业务域解耦），PRD §7.3 把二者混列且用了幻影 code `in_service`，据此修正：

**OrderStatus（业务状态机，9 codes — 唯一 SSoT）：**

| code（后端真源） | 中文 | English | iOS `Order.swift` | 微信 `constants.js` |
|---|---|---|---|---|
| `created` | 待接单 | Pending | ✓ | ✓ |
| `accepted` | 已接单 | Accepted | ✓ | ✓ |
| `in_progress` | 进行中 | In Progress | ✓（`inProgress`） | ✓ |
| `completed` | 已完成 | Completed | ✓ | ✓ |
| `reviewed` | 已评价 | Reviewed | ✓ | ✓ |
| `cancelled_by_patient` | 患者取消 | Cancelled by Patient | ✓ | ✓ |
| `cancelled_by_companion` | 陪诊师取消 | Cancelled by Companion | ✓ | ✓ |
| `rejected_by_companion` | 陪诊师拒单 | Rejected by Companion | ❌**缺** | ✓ |
| `expired` | 已过期 | Expired | ❌**缺** | ✓ |

**RefundState（退款子状态，独立维度，勿混入 orderStatus）：** `none/refunding/refunded/failed/manual_review`。仅 `refunded`=已退款 需前端展示译文，key 用 `refundState.refunded`（**不是** `orderStatus.refunded`）。

**三处硬修正（刻晴 r2 阻塞①）：**
1. **`in_service` 是幻影**——仅存在于 `api/v1/orders.py` doc 文字 + 一个 ws test mock，**非 enum 成员**。PRD §7.3 的 `in_service`/`created→Pending` 表作废，真 code 为 `in_progress`。
2. **`refunded` 归 RefundState**——PRD §7.3 与本 ADR 早稿误列为 order status，实为退款子状态（ADR-0041 解耦），字典分开建 `refundState.*`。
3. **iOS `Order.swift` 缺 `rejected_by_companion` + `expired`**（仅 7/9）——DEV-003 需补齐这两个 case（或与后端确认是否 iOS 不可达；本期至少字典/映射覆盖全 9 code，防 English 下拒单/过期订单显 raw code）。

> DEV-001 字典 `orderStatus.*` 以本表 9 code 为准；TEST-001 据此核对，不再用 PRD §7.3 骨架。

---

## 4. 微信端方案

### 4.1 运行时：store.language + 全局 t + setData 注入

- **方案对比**：
  - **A. 逐页 `wx:if` 双份 wxml**：改动爆炸、维护地狱。✗
  - **B. store 挂 `language` + 全局 `t()` 字典 + 页面 `onLoad`/`onShow` 把 `t` 结果注入 `setData`**（辅以 behavior/mixin 统一注入）：顺现有 store 架构（`subscribeSelector` 已支持按 selector 变化触发），wxml 用 `{{t.xxx}}` 数据绑定。✓（推荐）
- **决定**：方案 B。`store/_state` 加 `language: 'zh-Hans'|'en'`；新增 `utils/i18n.js`（持字典 + `t(key,params)`）；用 **behavior**（`i18nBehavior`）在页面 `attached`/`onShow` 时 `subscribeSelector(s=>s.language)`，变化即 `this.setData({ t: buildScopedDict(pages_keys) })` + `wx.setStorageSync('language', lang)`。
- **动态文案**：wxml 无函数插值 → 动态串在 js 层用 `t('otp.sentTo',{phone})` 算好再 `setData`。
- **分包覆盖**：i18n.js 放主包 `utils/`，分包页面同样通过 behavior 注入（behavior 主包可被分包引用）。**实测分包 20 个**（`create-order`/`order-detail`/`chat/room`/`profile/*` 等），behavior 逐页挂即可全覆盖。

### 4.2 设置入口 + 持久化

- `pages/profile/settings/index` 加「语言 / Language」项 → 弹选择器（简体中文 / English），选中态标识。
- 切换：`store.setState({language})` → `wx.setStorageSync('language', lang)`。冷启动 `app.js onLaunch` 读 `wx.getStorageSync('language')`，无则走 §6 默认逻辑。

### 4.3 已知 footgun（胡桃 review 实锤，必处理）

- **`store.reset()` 会静默丢 language**：实测 `store/index.js:107` 为 `_state = { isAuthenticated: false, user: null }`（**硬编码对象字面，非 spread**），且 reset() 会遍历触发 selector listener（:113-117）。登出调 reset() → language 被抹 → selector 触发 → UI 中途跳回默认语言。**处理（DEV-002 AC-1.1）**：二选一——reset() 后从 Storage 重读补回 language，或 language 不进 store reset 作用域（独立持有）。
- **i18nBehavior 订阅必 `fireImmediately:true`**：实测 `subscribeSelector(selector, listener, opts)` 支持 `opts.fireImmediately`（:98-100）。页面 `attached` 首屏即需正确语言，不能只在切换时刷。DEV-002 AC-2.1 钉入。
- **现状**：`subscribeSelector`→`setData` 目前 **无任何生产组件在用**（全 `getState()` 命令式，grep 仅 `store.test.js`）。i18nBehavior 是净新增（建在现成但无人用的 `subscribeSelector` 上）。DEV-002 为三个 dev 中最重（20 分包逐页挂 behavior + ~671 wxml 抽 key）。

### 4.4 抽 key 范围边界（胡桃 DEV-002 扫描实测触发，架构裁定 2026-07-10）

**胡桃扫描实测**：微信端硬编码中文 **970 行 / 76 文件**（比 §4 估的 671 高，因含 JS 层串 + 全文件，非矛盾——671 是 wxml-only 粗估）。其中 **legal/terms 48 行 + legal/privacy 63 行 = ~111 行是大段法律条款正文**（实样：“本协议是您与医路安平台运营方之间…”）。

**架构裁定（技术边界）：抽 key = UI 层文案，法律条款正文 body 白名单排除。**
- 理据：（a）法律正文是 **content 非 chrome**，与 UI 映射文案不同 cadence（按法务/合规节律变，非 UI）；（b）PRD §2.2-3 已明排除“图片/富文本/运营配置类内容…本期只做代码内静态/映射文案”，法律长文属富文本类；（c）法律英译有**合规含义**，开发不得直译，需法务/PM 背书。
- **边界精确**：legal 页的 **UI chrome 仍抽**（页标题栏、“同意/返回”按钮、section 导航标题如适用）；**仅条款 body 正文（`section-body`/`list-item` 内长文）白名单排除**。扫描脚本白名单加 legal body 选择器。
- **工作量**：降一档（~860 行 UI 层），规避法务风险。

**⚠ 产品/合规决策归凝光×帝君（非架构）**：“法律条款英文版本期要不要做”是产品/合规拍板。若要做 → **新立独立 task**，由**法务 review 过的英译稿**入字典，不走开发直译。本 ADR 只定技术边界（UI-only + legal body 白名单），不拍合规范围。

---

## 5. iOS 端方案

### 5.1 本地化载体：`.xcstrings`（String Catalog）

- **方案对比**：
  - **A. 传统 `Localizable.strings` + `.lproj`**：iOS17 起 Apple 主推 String Catalog 取代，多语言维护弱。✗
  - **B. `.xcstrings`（String Catalog，iOS17+，本项目 deploymentTarget=17.0 满足）**：单文件多语言、Xcode 原生提取、`String(localized:)` 直用。✓（推荐）
- **决定**：方案 B。新增 `YiLuAn/Resources/Localizable.xcstrings`（含 zh-Hans/en）；`Info.plist` 补 `CFBundleLocalizations=[zh-Hans,en]` + `CFBundleDevelopmentRegion`；XcodeGen `sources` 已 auto-include `YiLuAn/`（仅 excludes `*.md`），`.xcstrings` 放 `YiLuAn/Resources/` 自动纳入，**无需改 project.yml sources**（仅需确认 CI xcodegen regenerate 生效）。

### 5.2 语言状态 + 即时切换

- **方案对比（FR-3 即时性）**：
  - **A. 依赖系统语言 + 重启生效**：违背"App 内手动切换即时"，体验差。✗
  - **B. `@AppStorage("app_language")` 驱动 + 自建 `LocalizationManager`（`ObservableObject`）注入 `environment`，View 用 `manager.t("key")` 或 locale-override 的 `String(localized:)`**：无需重启即时刷新（SwiftUI 依赖变更自动重渲染）。✓（推荐，与现有 `@AppStorage("huge_font")` 范式一致）
- **决定**：方案 B。持久化 `@AppStorage("app_language")`；`LocalizationManager` 持当前 locale + `t()`；根视图 `.environment(\.locale, ...)` + `.environmentObject(manager)`。切换即时生效，**不需重启**（PRD FR-3 iOS 优先项达成，无需降级提示；见 §10-③ 最终定案）。
- **全量抽 key**：~124 处 View 内 `Text("中文")` + 其余字面量替换为 `t()`/String Catalog key。`SettingsView` 现有硬编码（`Section("通用")`/`Text("版本")`/`当前：患者` 等）一并抽。

### 5.3 设置入口

- `SettingsView` 加「语言 / Language」`Section`/`NavigationLink` → 选择「简体中文 / English」，选中态 checkmark。

---

## 6. FR-2 默认语言判定

- **微信**：`app.js onLaunch` 读 `wx.getStorageSync('language')`；无 → `wx.getSystemInfoSync().language`（`zh*`→zh-Hans，否则 en）→ 写回 Storage。
- **iOS**：`@AppStorage("app_language")` 无值 → 读 `Locale.preferredLanguages.first`（`zh*`→zh-Hans，否则 en）→ 落 AppStorage。
- 用户手动选择后以选择为准，不再被系统语言覆盖（FR-2）。

---

## 7. 后端错误文案本地化（承接 ADR-0062，帝君定案方案 C）

- **采方案 C**（复用既有 `error_code` 基础设施）：后端给 ~16 处用户可见中文 `raise` attach 既有 `error_codes.*`（`app/exceptions.py:AppException` 已支持 `error_code=`）；前端按 code → `error.<CODE>` 取译文。
- iOS `APIClient.swift` 已有 dispatch，扩 case + 用 `t()` 取译文替代硬编码中文 fallback；**微信新建 dispatcher**（`wechat/services/request.js` 或对齐现有 `services/api.js` 拦截层），按 error_code 映射译文。
- 未覆盖低频错误：回退显示后端 `detail`（中文），测试报告登记未覆盖清单（FR-6）。
- **§6 已由帝君 2026-07-09 定案走 C**（不再二选）。故 DEV-004（后端接线）+ DEV-005（微信 dispatcher）正式创建。

---

## 8. 开放决策点（提交帝君 awaiting-approval 时明列）

1. **§6 后端错误方案**：✅ 已定案 **方案 C**（帝君 2026-07-09）。
2. **iOS 即时性**：✅ §5.2 方案 B 达成**无需重启即时切换**，PRD §8-2 降级项不启用。
3. **Board config 缺口**：值已由 PM 明确（business / repoPath / `feature/i18n-multi-language`）；board 字段 `flowType/repoPath/branchName` 仍空（agent 无法设、init 对已存在 board 报 500），design 阶段以明确值为准，不阻塞。帝君可在 board 设置补齐，纯元数据完整性。

---

## 9. 实施任务映射

| develop task | 范围 | 配对 test |
|---|---|---|
| I18N-DEV-001 跨端字典基建 | key 规范落地 + 主字典 SSoT（术语+§7.5句式+error_code+status全集补齐） | I18N-TEST-001 |
| I18N-DEV-002 微信 i18n 运行时+抽key+设置入口 | store.language + i18n.js + i18nBehavior + 全量抽 wxml/js key + 设置页语言项 + 持久化 + FR-2默认 + 残留中文扫描脚本 | I18N-TEST-002 |
| I18N-DEV-003 iOS xcstrings+抽key+设置+持久化 | Localizable.xcstrings + LocalizationManager + @AppStorage + 全量抽key + SettingsView语言项 + FR-2默认 + Info.plist CFBundleLocalizations + 残留中文扫描脚本 | I18N-TEST-003 |
| I18N-DEV-004 后端 error_code 接线（方案C）| ~16处 raise attach error_codes + 补缺常量 | I18N-TEST-004 |
| I18N-DEV-005 微信 error_code dispatcher（对齐iOS）| 微信 request 层按 error_code 映射译文 + 未覆盖回退登记 + 更正 error_codes.py docstring stale 引用 | I18N-TEST-005 |

> DEV-001~005 均 depends_on I18N-DSN-001（设计批准后才开工）。DEV-004/005 承接 §6=方案 C（帝君 2026-07-09 定案）。

---

## 10. Review 决议（刻晴 §9 四点 + 帝君 §6 拍板，2026-07-09）

帝君拍板 §6=**方案 C**、分支 `feature/i18n-multi-language`（合远端 main）、repoPath 确认。刻晴 design review 挖出 §9 四点，逐条拍定写入 ADR（否则回归验收会卡）：

### ① AC-5 无回归基线手段（实测：iOS 无 snapshot/XCUITest，微信 automator 不在 CI）
- **实测证据**：`.github/workflows/` 有 `ios-ci.yml`/`ios-tests.yml` 但**无 snapshot/XCUITest/UITests**；微信无 automator CI 步骤（仅结构 `toMatchSnapshot`，无 jest-image-snapshot）。
- **决定（采 option a = 人工验收 + 基线协议，刻晴 r2 阻塞②要求定死）**：不新增快照设施（超本期，backlog），而是定一套**可复现的基线截图协议**写进 TEST-002/003 前置 + DEV 前置：
  - **基线 commit**：DEV 动工前的 `feature/i18n-multi-language` 基点（即本设计批准、DEV-002/003 开始前的 HEAD），测试员在此 commit 截中文态基线。
  - **截图清单**：8 核心页 × 中文态（登录/角色选择、首页、下单/服务选择、订单列表、订单详情、聊天、我的、设置），两端各一套。
  - **存放**：`tests/baseline/i18n/{wechat,ios}/<page>.png`（git 追踪）。
  - **判差异**：改造后中文态同 8 页逐屏目测比对基线，文案/布局无差异即 PASS（允许因抽 key 引入的等价改写，不允许文案错漏/串位/丢失）。
  - 两端原有单测/E2E（微信 Jest、iOS XCTest）必全绿。
  - 此协议写入 TEST-002/003 的前置步骤，并作为 DEV-002/003 开工前置（developer 不得在基线截图存档前改 UI）。

### ② 无残留中文检测手段
- **决定**：双层——（a）**开发期静态扫描**：DEV-002/003 交付含一个扫描脚本/测试（正则 `[\u4e00-\u9fff]` 扫 `wxml` / `.swift` View 层，白名单排除注释/品牌/不需译项），列出未抽 key 的残留硬编码；（b）**测试期人工抽检** English 模式 8 核心页无中文。后端低频错误文案例外（登记）。扫描脚本归 DEV-002/003 交付物。

### ③ iOS 即时/重启择一写进 ADR
- **决定**：采 §5.2 方案 B（`@AppStorage` + `LocalizationManager` 驱动），**即时切换无需重启**（SwiftUI 依赖变更自动重渲染）。PRD §8-2 降级项（重启后生效 + 提示）**不启用**。最终决定，不再二选。

### ④ 拆 test 点名 ≥3 处动态拼接文案 + 期望英文串（引 PRD §7.5）
- **实测定位（file:line）**，TEST AC 点名：
  - iOS `OTPInputView.swift:14` `验证码已发送至 +86 {phone}` → `Code sent to +86 {phone}`
  - iOS `ReviewViews.swift:124` `共 {total} 条` → `{total} total`
  - iOS `CompanionListView.swift:136` `({totalOrders}单)` → `{count} order(s)`（§7.5 单复数折中）
  - iOS `SettingsView.swift:89` `切换为{患者/陪诊师}` → `Switch to {Patient/Companion}`
  - iOS `ShareOTPView.swift:114` `{expiresIn/60} 分钟内有效` → `Valid for {n} minute(s)`
  - 微信 `pages/profile/settings/index.wxml:11` `切换为{{...}}` → `Switch to {targetRole}`；`:13` `当前：{{...}}` → `Current: {role}`
- 期望英文串以 PRD §7.5 句式模板为准（英文按目标语序，非中文直译）。TEST-002/003 AC 已点名 ≥3 处。

### ⑤ 刻晴 r2 二轮 review 阻塞两点处置（2026-07-09，evidence 实锤）
- **① status 全集不齐**：已在 §3.3 立 backend SSoT 全集表修正——`in_service` 幻影∪`refunded` 归 RefundState ∪ iOS 缺 `rejected_by_companion`/`expired`。TEST-001 重点查清单扩到 9 code 全集。【采纳】
- **② 无回归基线无协议**：已在 §10① 定死基线截图协议（commit/页单/存放/判差异）写入 TEST-002/003 前置 + DEV 前置。【采纳】
- **次要① 动态拼接点名**：已在 §10④ + TEST-002/003 AC 点名 ≥3 处 file:line + 期望英文（刻晴说“可 DEV 后补”，本轮已提前锁死）。
- **次要② DEV-004/005 悬空**：§6 已由帝君 2026-07-09 **定案=方案 C**（凝光中继），DEV-004/005 **非悬空**，已正式创建且 depends_on DSN-001。刻晴“拍板后再 add”的前提（未拍板）已不成立。

---

## 11. 后果

- PRD §2.2/§6 表述据 ADR-0062 修正（后端 error_code 基础设施已存在）。
- **PRD §7.3 status 表据 §3.3 修正**：删 `in_service`（幻影），`refunded` 移入 RefundState，补 `reviewed`/`rejected_by_companion`/`expired`；orderStatus 全集 = 9 code（backend SSoT）。DEV-001 据此落字典。
- **iOS `Order.swift` 缺 `rejected_by_companion`/`expired`**（仅 7/9），DEV-003 补齐映射全 9 code。
- **无回归基线截图协议**（commit/8页/`tests/baseline/i18n/`/逐屏判差）写入 TEST-002/003 前置，且为 DEV-002/003 开工前置。
- iOS 达成无需重启即时切换，FR-3 iOS 优先项满足。
- develop/test 共 5+5（DEV/TEST-001~005），均 depends_on I18N-DSN-001。
- error_codes.py docstring 关于 `wechat/services/request.js` 的 stale 引用在 DEV-005 一并更正。
