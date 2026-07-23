# 安卓 Epic PM 验收 Checklist（覆盖完整性核查表）

> 编制：凝光（PM）· 2026-07-16 · 用于 test 全绿后的 epic 终验
> **MEMORY 铁律**：PM 项目级终验必核「覆盖完整性」——逐页/逐模块核全部目标被 develop 触及，不只核子 task done。子批全 done ≠ 覆盖完整。
> golden 基线：小程序 **34 页**（app.json 声明，legal 拆 2）· design：docs/design/android-epic-design.md

## 一、覆盖完整性核查（逐页，安卓侧）

终验时逐行核「安卓已建对应 Compose 页 + 后端契约一致」。核法：`git ls-tree` 列 android/features 全目录树 + 逐页核，非只信 test done。

| # | 小程序页 | 批次 | 安卓建成核查 | 状态 |
|---|---------|------|-------------|------|
| 1 | login | B1 | features/auth login | ⬜ |
| 2 | role-select | B1 | features/auth role-select | ⬜ |
| 3 | patient/home | B2 | features/patient home | ⬜ |
| 4 | patient/create-order | B2 | features/patient create-order | ⬜ |
| 5 | patient/order-detail | B2 | features/patient order-detail（含 Precheck 信任卡） | ⬜ |
| 6 | patient/pay-result | B2 | features/patient pay-result（mock） | ⬜ |
| 7 | companion/home | B3 | features/companion home | ⬜ |
| 8 | companion/available-orders | B3 | available | ⬜ |
| 9 | companion/today-orders | B3 | today | ⬜ |
| 10 | companion/orders | B3 | orders | ⬜ |
| 11 | companion/order-detail | B3 | detail | ⬜ |
| 12 | companion/chat | B4 | features/chat room | ⬜ |
| 13 | companion/profile | B3 | companion profile | ⬜ |
| 14 | companion/setup | B3 | setup | ⬜ |
| 15 | companion-detail | B3 | companion-detail | ⬜ |
| 16 | orders（通用） | B2 | order-list 角色态复用 | ⬜ |
| 17 | chat/list | B4 | features/chat list | ⬜ |
| 18 | chat/room | B4 | features/chat room + WS | ⬜ |
| 19 | notification | B4 | features/notification WS+REST | ⬜ |
| 20 | review/write | B6 | features/review | ⬜ |
| 21 | profile | B6 | features/profile | ⬜ |
| 22 | profile/setup | B1/B6 | profile setup | ⬜ |
| 23 | profile/edit | B6 | edit | ⬜ |
| 24 | profile/about | B6 | about | ⬜ |
| 25 | profile/bind-phone | B6 | bind-phone | ⬜ |
| 26 | profile/wallet | B6 | wallet | ⬜ |
| 27 | profile/family-members | B6 | family | ⬜ |
| 28 | profile/emergency-contacts | B6 | emergency | ⬜ |
| 29 | profile/followup-reminders | B6 | followup | ⬜ |
| 30 | profile/settings | B6 | settings | ⬜ |
| 31 | settings/delete-account | B6 | delete-account | ⬜ |
| 32 | legal/privacy | B6 | legal privacy | ⬜ |
| 33 | legal/terms | B6 | legal terms | ⬜ |
| 34 | (Precheck 强制) | B5 | features/precheck Screen+WS | ⬜ |
| 35 | (Share 强制) | B5 | features/share Order+OTP+WS | ⬜ |

> 34 页 + Precheck/Share 强制项（design 单列）。序号 34/35 是帝君一期强制的对齐轴，非小程序独立页但必建。

## 二、三条线覆盖核查

### B0 地基前置核（2026-07-16 PM evidence-first 核 origin/main #397）

B0-CORE 已合入 main（cd72033），design 要求地基项**全建齐**：
- network: ApiEndpoint / AuthApi / AuthInterceptor(401并发防护) / WebSocketClient ✅
- storage: TokenStore(DataStore) / ShareSessionStore(Encrypted) ✅
- DI: NetworkModule(Hilt) ✅
- 导航: Routes / YiLuAnNavHost ✅
- 单测: AuthInterceptorTest / ShareSessionStoreTest ✅
- ⚠️ 关联 bug `ANDROID-BUG-B0-TEST-COVERAGE-GAP`(P1, in-progress): 刻晴测出测试覆盖缺口(WebSocketClient/TokenStore 等无测), 胡桃补测中 — 终验前须核此 bug done。

### 三条线

| 线 | 批次 | 核查 | 状态 |
|---|------|------|------|
| 安卓全量 | B0-B6 | 上表 35 项全建 | ⬜ |
| iOS 补齐 | B7 | design 细核出的 iOS 相对小程序缺口全补（或白名单豁免留痕） | 🔵 进行中：B7 iOS Share 发起入口 #400 已 ratify 待合（三端 Share 发起端齐） |
| 小程序入口 | WX-SHARE | Share 页入口补齐（患者订单详情「分享给家属」） | ✅ done |

## 三、AC 门槛核查（帝君四约束 + 刻晴 review）

| AC | 门槛 | 核法 | 状态 |
|----|------|------|------|
| AC1/AC7 | 三端一致=后端契约层断言（小程序 golden），不比 UI | test 报告有后端断言 trail | ⬜ |
| AC2 | 支付走 mock，下单→支付→结果→订单流转全链路 | git diff backend/ 空 + payment_provider=mock 双证 | ⬜ |
| AC3 | WS 在线收通知 + 断开 REST 拉不丢 + 重连不重复推 | 边界测试点 | ⬜ |
| AC4 | Precheck 4 信任卡 + WS 刷新 + 轮询兜底阈值 | design §3.3 阈值已定 | ⬜ |
| AC5 | 后端零改动 | git diff backend/ 空 | ⬜ |
| AC6 | i18n 中英切换无硬编码 | 静态扫描 + 切换实测 | ⬜ |

## 四、白名单豁免（合理专属差异，非缺口）

- ⚪ Apple Sign-In（iOS 专属，安卓不做）—— 不计入安卓缺口

## 验收结论区（终验时填）

### 🔴 PM 终验前置预核发现的覆盖缺口（2026-07-22，evidence-first git ls-tree+grep+NavHost）→ ✅ 已全部补齐

安卓 31 Screen（补漏后，27→31）vs 小程序 34 页，4 真漏均已补入 main（evidence-first 核 origin/main）：
| 页面 | 原判定 | 现状 |
|---|---|---|
| profile/followup-reminders | 🔴 真漏 | ✅ FollowupRemindersScreen 入 main (#409) |
| profile/edit | 🔴 真漏 | ✅ ProfileEditScreen 入 main (#410) |
| profile/about | 🔴 真漏 | ✅ AboutScreen 入 main (#410) |
| patient/pay-result | 🔴 真漏 | ✅ PaymentResultScreen 入 main (#411) |

**已合理合并（非缺口、checklist 豁免）**：安卓 PatientHomeScreen 主界面 + SettingsScreen 个人中心枢线（承载小程序 profile/index + profile/setup + settings）；companion/orders 复用 OrderList；companion/profile 由 CompanionDetail/Setup 承载。

**🔒 FULL ratify 前提**：✅ 4 真漏全补入 main + ✅ B8 审计产物进 repo (#408) + ✅ 31 Screen 覆盖 34 页（含合并豁免）。待：ANDROID-TEST-GAP-PAY-RESULT（最后一棒 test，刻晴 in-progress）done → 签 FULL ratify。
