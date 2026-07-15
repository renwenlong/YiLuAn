# ADR-0064: 安卓客户端可行性调研

- 状态: 已定向（帝君 2026-07-15 拍板方向 A + 4 约束），待 PM 立 epic
- 日期: 2026-07-15
- 决策者: 帝君
- 调研: 魈（架构师）

## 帝君拍板约束（2026-07-15 13:12 UTC）

1. **方向 A（Kotlin + Jetpack Compose 原生）** — 已选定
2. **支付走微信支付** — 但**支付资质申请搁置**（一期不落地支付资质流程，支付路径设计保留、申请后置）
3. **产品功能三端完全对齐** — 安卓 + iOS 功能面必须与小程序侧完全一致（以小程序 33 页面为功能基线）
4. **FCM 一期后置** — 系统级离线推送降级为一期后置增强项，一期只做 App 内通知 + WebSocket 实时推

## 背景

现有三端：iOS 原生（SwiftUI，~16k 行 Swift，13 Feature 模块）、微信小程序（~3k 行）、admin。无安卓端。帝君要求调研支持安卓版本的可行性。

## 现状核验（evidence-first，基于 main HEAD `5c106e2`）

| 维度 | 事实 | 对安卓的影响 |
|---|---|---|
| **后端契约** | REST + WebSocket，platform-agnostic；`device_tokens.device_type` **已含 `android` 枚举** | ✅ 后端契约层已预留安卓，无需大改 |
| **推送分发** | `SubscribeMessageProvider` 抽象接口已建，但**仅 StubProvider**，真实 APNs/FCM 均未实现（`providers/` 只有 payment/sms，无 push 子目录） | ⚠️ FCM 与 APNs 需一并实现，非安卓独有成本 |
| **通知解耦** | `notification_outbox` 模式已落地（OUTBOX epic），通知派发与业务事务解耦 | ✅ 加 FCM 只需接 Provider，不碰业务 |
| **支付** | 微信支付走**后端回调**（微信服务端调用，非 App 端 IAP） | ✅ 安卓无 Apple IAP 30% 抽成/审核障碍，直接复用微信支付 |
| **i18n** | `Localizable.xcstrings` 已 zh-Hans/en 双语，近期大量 I18N commit | ✅ 文案 key 体系可复用（iOS 抽 key 成果可迁移） |
| **iOS 架构** | 标准分层 Core(Networking/Models/Storage) + Features 13 模块，UI 与网络层分离 | 契约模型可 1:1 映射，UI 需重写 |

## 方案对比

### 方案 A：Kotlin 原生（Jetpack Compose）

- **优势**：与 iOS SwiftUI 对称（声明式 UI，团队心智模型一致）；性能/体验最优；Compose ↔ SwiftUI Feature 模块可 1:1 对应移植
- **劣势**：全量重写 UI 层（~16k 行 iOS UI 无法复用）；需新增 Android 工程能力；双端各自维护
- **成本**：高（UI 全重写），但**架构风险最低**（复用 backend 契约 + 分层模式）

### 方案 B：跨端框架（Flutter / KMP）

- **优势**：一套 UI 码覆盖双端，长期维护成本低
- **劣势**：现有 iOS 已是成熟原生 SwiftUI，引入跨端 = **iOS 端也要重写或双轨**；团队无 Flutter/KMP 积累；与现有 13 Feature 原生模块冲突（同反案 #8 类型：假设跨端复用但物理上 iOS 已原生化）
- **成本**：极高（动摇已交付的 iOS 端），不推荐

## 决定（推荐）

**推荐方案 A（Kotlin + Jetpack Compose 原生）。**

理由：
1. 后端契约已 platform-agnostic 且预留 `android` 枚举，安卓接入不需后端大改
2. 支付走微信后端回调，规避 Apple IAP 障碍——安卓支付路径反而更简单
3. iOS 已深度原生化（13 Feature 模块），方案 B 会反噬已交付 iOS 端
4. Compose 与 SwiftUI 对称，Feature 模块可按 iOS 结构 1:1 移植，降低设计不确定性

## 后果

**前置依赖（阻塞项，安卓无法绕过）**：
- 🔴 **推送 FCM Provider 必须先实现**：当前仅 StubProvider，安卓推送依赖 FCM。此为 iOS/安卓共性缺口，建议独立 task 先补（走 `SubscribeMessageProvider` 接口）
- device_type 虽有 android 枚举，但 backend 业务无 android 分支逻辑——需核 push 派发按 device_type 分流 FCM/APNs

**移植范围（Feature 级）**：Auth / Chat / Companion / Legal / Precheck / Patient / Review / Settings / Payment / Share / Profile / Order / Notifications——13 模块按 iOS 结构 1:1 建 Compose。

**可复用（不重写）**：backend 全部契约、i18n key、通知 outbox、微信支付回调。

**不在本 ADR 范围**：具体 task 拆分、工时估算（需帝君批方向后由 PM 立 epic）。

## 三端功能对齐基线（小程序 33 页面 = SSoT）

**帝君约束 3「完全对齐」的落地口径：以小程序页面为功能基线，安卓 + iOS 逐页对齐。**

小程序功能面（33 页，物理核验 main HEAD `5c106e2`）：
- **患者端**：home / create-order / order-detail / pay-result
- **陪诊员端**：home / available-orders / today-orders / orders / order-detail / chat / profile / setup / companion-detail
- **通用**：login / role-select / orders / notification / chat(list/room) / review/write / settings/delete-account
- **Profile**：profile / edit / about / bind-phone / wallet / family-members / emergency-contacts / followup-reminders / settings / setup
- **Legal**：terms / privacy

iOS 现状核验：13 Feature 模块已覆盖上述功能面（Auth/Chat/Companion(7)/Order/Patient/Profile(8)/Review/Precheck/Notifications/Settings/Payment/Share/Legal）——iOS 与小程序**已高度对齐**，无重大缺页。

**安卓落地要求**：按小程序 33 页面 1:1 建 Compose 页，同时对齐 iOS 已实现的 Feature 结构。任何三端功能差异需在 epic 拆分时逐页核对（对齐审计）。

## 一期 scope（帝君 4 约束固化后）

**做**：
- 13 Feature 模块 Compose 页（对齐小程序 33 页 + iOS 结构）
- App 内站内信 + 未读数 + WebSocket 实时通知
- 微信支付路径设计（**资质申请搁置**，代码走通但不落地资质流程）

**不做（后置）**：
- 🔵 FCM 系统级离线推送（一期后置，补时 APNs 共性一起）
- 🔵 支付资质申请流程（搁置，待帝君后续启动）

## 待 PM 立 epic

方向已定，交 PM（凝光）立安卓 epic：
1. 按小程序 33 页面基线拆 Feature-level 安卓 task（每 develop 配 test）
2. 三端对齐审计 task（逐页核 iOS/小程序/安卓功能一致）
3. FCM Provider + 支付资质 = 独立后置 backlog（不入一期）
