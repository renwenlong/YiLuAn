# 医路安 Android 版本可行性调研

> 调研人：甘雨（协调者）　日期：2026-07-15　基线：最新 code（README 标 HEAD `013cecf`，实际 code 已推进到 S2/S3 sprint，含合同存储/salt 轮换）

## 一、结论先行

**可行，且成本可控。** 后端是完全平台无关的 REST + WebSocket 服务，Android 端本质上是「再写一个客户端」的问题，不触碰后端与数据模型。当前已有 iOS(SwiftUI) + 微信小程序两个客户端，Android 是第三个客户端，无架构性障碍。

**主要工作量集中在前端新建，不在后端改造。** 后端预计仅需少量适配（推送、设备类型、微信开放平台配置），核心业务 API 零改动。

## 二、现状盘点

| 层 | 现状 | 与 Android 关系 |
|----|------|------|
| 后端 | FastAPI async，102 路由（REST + 3 WS），JWT HS256，平台无关 | ✅ 直接复用，无需改造 |
| 认证 | 手机 OTP / 微信登录 / Apple Sign-In / JWT 刷新 | ⚠️ 微信登录需接微信开放平台 Android SDK；Apple Sign-In 是 iOS 专属，Android 不用 |
| 实时 | WebSocket（JWT query 参数认证，含心跳/重连语义） | ✅ Android 侧照抄客户端逻辑即可 |
| 推送 | `device_tokens.device_type` 已支持 `ios/android/wechat`；Phase 6 APNs **已跳过** | ⚠️ Android 需接 FCM（国内需厂商推送 / 个推等替代，FCM 在国内不可用） |
| 已有客户端 | iOS SwiftUI（7 大模块）、微信小程序（21 页面） | 📐 可作为 Android UI/交互与 API 契约的 1:1 参照 |
| API 契约 | OpenAPI 有 drift 门禁（`docs/api/openapi.json`） | ✅ Android 可直接按 OpenAPI 生成/对齐 model |

## 三、技术选型建议（三选一，附利弊）

| 方案 | 技术栈 | 优点 | 缺点 |
|------|--------|------|------|
| **A. 原生 Kotlin** | Kotlin + Jetpack Compose + MVVM | 与 iOS SwiftUI 架构对称、性能最佳、原生推送/微信 SDK 接入最顺 | 与 iOS 完全独立两套代码，人力翻倍 |
| **B. Flutter** | Dart + Flutter | 一套代码可覆盖 Android+iOS，长期维护成本低 | 需重写现有 iOS（沉没成本），团队 Dart 经验待评估 |
| **C. KMP（Kotlin Multiplatform）** | 共享 business/网络层，UI 各自原生 | 可复用 iOS 已有 model 契约、渐进式 | 生态相对新、iOS 侧需改造接入 |

**协调者初步倾向 A（原生 Kotlin + Compose）**：现有 iOS 是 SwiftUI/MVVM，Compose 架构一一对应，迁移心智负担最小，且不打扰已上线的 iOS/小程序。是否引入跨端框架属于战略取舍，建议帝君拍板。

## 四、主要工作项（按方案 A 估算）

1. **网络层**：Retrofit/Ktor + JWT 拦截器 + 401 静默刷新（对齐小程序 api.js 的排队刷新语义）
2. **WebSocket**：OkHttp WS + 指数退避重连 + 心跳（对齐 iOS WebSocketClient）
3. **7 大功能模块 UI**：Auth / Patient / Companion / Order / Chat / Review / Notifications / Profile（参照 iOS Features 目录）
4. **认证适配**：手机 OTP（复用）、微信登录（接微信开放平台 Android SDK，需申请移动应用 AppID）、去掉 Apple Sign-In
5. **推送**：国内 Android 需厂商推送/第三方（个推/极光），非 FCM；后端 `device_type=android` 已就位，需补下发通道
6. **本地存储**：Token 用 EncryptedSharedPreferences/Keystore（对齐 iOS Keychain）

## 五、需帝君决策的关键点

1. **技术选型**：原生 Kotlin（推荐）/ Flutter（未来 iOS 也重写）/ KMP——战略级取舍
2. **微信开放平台移动应用资质**：Android 微信登录需单独申请移动应用 AppID + 企业审核（有前置周期）
3. **推送方案**：国内 Android 无 FCM，需定厂商推送或第三方，有采买/接入成本
4. **是否纳入 taskboard 正式立项**：目前是调研，若推进需架构师出 ADR + 拆 develop/test task

## 六、风险与前置依赖

| 风险/依赖 | 说明 | 建议 |
|-----------|------|------|
| 微信移动应用资质 | 审核有周期，是关键路径 | 若确定做，尽早并行申请 |
| 国内推送生态 | FCM 不可用，需厂商推送矩阵或第三方 | 立项时单列一个 spike |
| iOS 契约漂移 | Android 需跟 OpenAPI，避免手抄 model 过期 | 复用 OpenAPI drift 门禁 |
| 人力 | 原生方案与 iOS 独立两套 | 评估程序员带宽 |

---

## 七、帝君拍板决策（2026-07-15 13:09 UTC）

- ✅ **技术选型 = 方案 A（原生 Kotlin + Jetpack Compose）** — 与 iOS SwiftUI 架构对称，不打扰已上线 iOS/小程序。
- ✅ **支付渠道 = 微信支付** — 复用后端现有微信支付契约，Android 接微信支付 SDK。
  - 🔶 **2026-07-15 13:12 帝君追加：支付接入 + 微信开放平台移动应用资质申请先搜置（backlog）**。安卓 MVP 阶段支付走 mock/占位，资质解冻后再接真实微信支付。
- ✅ **推送 = MVP 先不接**。FCM = Firebase Cloud Messaging（谷歌官方安卓推送通道，依赖 Google Play Services，国内送达率不稳，故不选纯 FCM）。MVP 阶段靠 **WebSocket(/ws) 前台实时**兜住聊天/通知（iOS 本就无 APNs 耦合，核心闭环不依赖推送）；**离线推送拆为二期独立 task**，届时走国内厂商推送聚合（个推/极光/华为 HMS）。

**待枛立项（出 ADR + 拆 design→develop→test）：**技术脚手架、MVP 功能范围与排期。（微信支付/资质申请已搜置，不入本轮立项。）

## 八、三端功能完全对齐指令（2026-07-15 13:12 UTC 帝君）

帝君明拍：**安卓 + iOS 的产品功能要跟小程序侧完全对齐**。
- 小程序现有 12 页面：chat / companion / companion-detail / legal / login / notification / orders / patient / profile / review / role-select / settings。
- 安卓（新建）→ 功能面 1:1 覆盖小程序全部能力。
- iOS（已有 13 Feature）→ 反向核对拉平。
- 待帝君拍对齐口径：以小程序为唯一基准 vs 三端并集拉平。定后出三端功能对齐矩阵。
