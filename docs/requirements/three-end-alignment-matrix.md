# 三端功能对齐矩阵（医路安 Android Epic 验收 SSoT）

> 编制：凝光（PM）· 日期：2026-07-15 · 基线 commit `5c106e2`
> 基线口径（帝君约束 3）：**以小程序页面为功能事实源，安卓 + iOS 逐页对齐**
> **对齐判定口径（采纳刻晴 review 2026-07-15）：不比 UI（三端 UI 天生不同：Compose/SwiftUI/WXML），而是『同一操作后三端调用相同 API 得到相同后端状态/响应』。UI 层一致性交由各端逐模块 develop task 的 AC 承载。**
> 页面基线：PM evidence-first 物理核 `wechat/app.json` = **33 页**（12 主包 + 21 分包页）。legal 的 privacy/terms 已各自作为独立页计入主包 12 页，无需额外 +1。**订正**：本矩阵头注原写「34（22 分包，legal 拆 2 页 +1）」系重复计数错误（legal 2 页本已含在主包内），经架构师魈 evidence-first 复核 + PM 二次物理核 app.json 确认 = 33 页，ADR-0064「33」正确，golden 基线以 33 为准。

## 图例
- ✅ 已覆盖 · 🟡 部分/需核 · ❌ 缺口 · 🔵 一期后置 · ⚪ 合理专属差异（豁免）

## 矩阵（小程序 33 页为行基线）

| # | 小程序页面 | 功能 | iOS 现状 | 安卓待建 |
|---|-----------|------|---------|---------|
| 1 | login | 登录（手机 OTP / 微信） | ✅ LoginView + OTPInputView | ❌ 待建 Compose |
| 2 | role-select | 角色选择（患者/陪诊员） | ✅ RoleSelectionView | ❌ 待建 |
| 3 | patient/home | 患者首页 | ✅ PatientHomeView | ❌ 待建 |
| 4 | patient/create-order | 患者下单 | ✅ CreateOrderView | ❌ 待建 |
| 5 | patient/order-detail | 患者订单详情 | ✅ OrderDetailView | ❌ 待建 |
| 6 | patient/pay-result | 支付结果 | ✅ PaymentResultView（支付走 mock 一期） | ❌ 待建（mock provider） |
| 7 | companion/home | 陪诊员首页 | ✅ CompanionHomeView | ❌ 待建 |
| 8 | companion/available-orders | 可接订单 | ✅ AvailableOrdersView | ❌ 待建 |
| 9 | companion/today-orders | 今日订单 | ✅ TodayOrdersView | ❌ 待建 |
| 10 | companion/orders | 陪诊员订单列表 | ✅ OrderListView | ❌ 待建 |
| 11 | companion/order-detail | 陪诊员订单详情 | ✅ OrderDetailView | ❌ 待建 |
| 12 | companion/chat | 陪诊员聊天 | ✅ ChatRoomView | ❌ 待建 |
| 13 | companion/profile | 陪诊员资料 | ✅ CompanionSelfProfileView | ❌ 待建 |
| 14 | companion/setup | 陪诊员入驻 | ✅ CompanionSetupView | ❌ 待建 |
| 15 | companion-detail | 陪诊员详情（患者视角） | ✅ CompanionDetailView | ❌ 待建 |
| 16 | orders | 通用订单列表 | ✅ OrderListView | ❌ 待建 |
| 17 | chat/list | 聊天会话列表 | ✅ ChatListView | ❌ 待建 |
| 18 | chat/room | 聊天室（WS 实时） | ✅ ChatRoomView + WebSocket | ❌ 待建（WS 前台实时） |
| 19 | notification | 通知列表 | ✅ NotificationListView | ❌ 待建（App 内通知，一期不含 FCM 离线派送🔵） |
| 20 | review/write | 评价 | ✅ ReviewViews | ❌ 待建 |
| 21 | profile | 个人中心 | ✅ ProfileView | ❌ 待建 |
| 22 | profile/setup | 资料初始化 | ✅ ProfileSetupView | ❌ 待建 |
| 23 | profile/edit | 编辑资料 | ✅ ProfileEditView | ❌ 待建 |
| 24 | profile/about | 关于 | ✅ AboutView | ❌ 待建 |
| 25 | profile/bind-phone | 绑定手机 | ✅ BindPhoneView | ❌ 待建 |
| 26 | profile/wallet | 钱包 | ✅ WalletView | ❌ 待建 |
| 27 | profile/family-members | 家庭成员 | ✅ FamilyMembersView | ❌ 待建 |
| 28 | profile/emergency-contacts | 紧急联系人 | ✅ EmergencyContactsView | ❌ 待建 |
| 29 | profile/followup-reminders | 随访提醒 | ✅ FollowupRemindersView | ❌ 待建 |
| 30 | profile/settings | 设置 | ✅ SettingsView | ❌ 待建 |
| 31 | settings/delete-account | 注销账号 | ✅ DeleteAccountView | ❌ 待建 |
| 32 | legal/privacy | 隐私政策 | ✅ PrivacyPolicyView | ❌ 待建 |
| 33 | legal/terms | 服务条款 | ✅ TermsOfServiceView | ❌ 待建 |

> 注：小程序主包 pages 声明含 `pages/orders/index` 与陪诊员端 orders 复用同一列表逻辑，iOS 用 OrderListView 统一承载——安卓按角色态复用一个列表组件。

## iOS 相对小程序的缺口盘点

**结论：iOS 已高度对齐小程序，无重大功能缺页。** 13 Feature / 33 View 逐页可映射，未发现小程序有而 iOS 缺的核心页面。

**iOS 独有（小程序无对应，属合理专属差异 ⚪，非缺口）：**
- Apple Sign-In（iOS 平台登录，安卓不做）
- Precheck（预问诊，iOS 有 PrecheckView + WS；需核小程序是否有对应入口——见下待确认项）
- Share OTP 分享会话（iOS 有 ShareOrderView + WS；小程序侧分享形态不同）

## 帝君已拍口径（2026-07-15 14:48）

1. **iOS 补齐本期一起做** — iOS 相对小程序缺的功能点纳入本 epic 并行线，design 阶段据矩阵拆独立 develop+test。
2. **Precheck / Share 安卓纳入一期（强制项）** — 非 backlog，安卓首版必含。

### Precheck / Share 三端归属（一期强制）

| 功能 | 小程序 | iOS | 安卓 | 一期 |
|------|-------|-----|------|------|
| Precheck 预问诊（4 信任卡 + WS） | 🟡 待核入口 | ✅ PrecheckView+WS | ❌ 待建 | ✅ 强制 |
| Share OTP 分享会话 | 🟡 入口待补（刻晴 review） | ✅ ShareOrderView+WS | ❌ 待建 | ✅ 强制 |

> Share/Precheck 三端共用同一套后端 API（刻晴代码核实：`send_share_otp`/`get_share_session_order`/`users_precheck.py`/`ws.py`）。小程序 Share 入口缺口需配对新增 develop `ANDROID-DEV-WX-SHARE-ENTRY` + test。

### iOS 补齐线

iOS 已高度对齐小程序 33 页，本矩阵未发现重大缺页。design 阶段逐页细核若发现 iOS 缺小程序功能，均纳入本期 iOS 补齐线（独立 develop+test）。

### 三端一致性判定口径（AC7，采纳刻晴第二轮 review）

**锅定后端契约层断言，不做 UI 三端肉眼比对。** 判定 = 同一操作在三端各自触发后，落到后端的**请求契约一致 + 返回状态/DB 变更一致 + WS 推送事件一致**。UI 呈现各端按端内 AC 单验。基准端：**小程序为 golden**（帝君定的事实源），iOS/安卓比对小程序的后端交互序列。

## 一期 vs 二期边界（帝君四约束落地）

**一期（本 epic）**：安卓 33 页 Compose 全量建 + Precheck/Share（强制）+ iOS 补齐线 + 小程序缺口补齐 + 三端对齐审计。支付走 mock provider。推送仅 WS 前台实时 + App 内通知。
**二期 backlog**：🔵 FCM 离线推送派送 · 🔵 真实微信支付资质+回调。
