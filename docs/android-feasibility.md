# YiLuAn 安卓版本可行性调研

> 调研人：刻晴（测试员）　日期：2026-07-15　git HEAD `5c106e2`
> 视角：以现有 iOS(SwiftUI) + 微信小程序 + FastAPI 后端为基线，评估新增原生 Android 客户端的可行性与工作量。

## 结论：可行，风险可控

后端为 client-agnostic REST + WebSocket 架构，已预留 Android 接入点。Android 是纯新增客户端工程，**不需要改后端核心**（仅需补 FCM 推送派送实现）。主要成本在客户端从零实现 13 个 Feature 模块的 UI + ViewModel。

## 一、后端就绪度（高）

| 维度 | 现状 | Android 影响 |
|------|------|-------------|
| API 契约 | 92 个 APIRouter / 102 REST+WS 路由，`/api/v1` 统一前缀，JWT HS256 | ✅ 直接复用，无改动 |
| 登录 | **手机 OTP**(`/send-otp`+`/verify-otp`) / 微信 / Apple Sign-In | ✅ **OTP 是跨平台主路径，Android 直接用，无需平台 SDK** |
| 设备类型 | `device_token` schema `allowed = {ios, android, wechat}` 已含 android | ✅ 后端已预埋 |
| 推送 token | schema 注释明确 "APNs/**FCM**/微信 OpenID" | ✅ 契约已支持 FCM token 注册 |
| WebSocket | JWT query 参数认证的订单聊天室 / precheck | ✅ 协议无关，OkHttp WebSocket 可接 |
| 支付 | 微信支付 v3 + mock 双 provider（provider 抽象 + 回调幂等） | ⚠️ Android 需接微信支付 SDK 或支付宝，回调后端已幂等 |
| 设计 token | `design/tokens.json` 是唯一事实源，`generate.py` 输出器模式 | ✅ 团队已明确 "新增端只需写一个 generate.py 输出器" |

## 二、需要新建 / 补齐的部分

### 后端（小）
- **FCM 推送派送实现**：当前只有 `StubSubscribeMessageProvider`（写日志），APNs/微信真实派送尚未落地，Android 需并行补 `FcmProvider`。属既有 Provider 抽象下的新增，不改架构。

### Android 客户端（大 — 主要成本）
从零工程，需对齐 iOS 13 个 Feature：Auth / Chat / Companion / Legal / Notifications / Order / Patient / Payment / Precheck / Profile / Review / Settings / Share。
- iOS 端参照规模：124 个 swift 文件 / ~16k LOC（SwiftUI + MVVM）。Android 对等（Kotlin + Jetpack Compose + MVVM）量级相当。
- 网络层可平移 iOS `APIClient`/`APIEndpoint`/`WebSocketClient` 结构 → Retrofit + OkHttp。
- 设计 token 需给 `generate.py` 加 Android 输出器（Compose 常量 / XML resources）。
- i18n：iOS 用 `Localizable.xcstrings`，当前团队正大规模 i18n 补抽 key（近 10 个 PR），Android 需同步接同一套 key 事实源。

## 三、技术选型建议

| 项 | 建议 | 理由 |
|----|------|------|
| UI | Jetpack Compose + MVVM | 与 iOS SwiftUI+MVVM 架构对称，便于对齐 |
| 网络 | Retrofit + OkHttp（含 WebSocket） | 复用现有 REST/WS 契约 |
| 推送 | FCM（Google Play）+ 国内厂商推送兜底（华为/小米，无 GMS 场景） | 国内 Android 无 GMS 是最大坑点 |
| 登录 | 手机 OTP 为主，微信登录为辅 | 规避 Apple Sign-In（Android 无对应） |
| 安全存储 | EncryptedSharedPreferences | 文档 AUTHENTICATION.md 已指定 |

## 四、主要风险 / 待决策项（需产品/架构拍板）

1. **国内推送碎片化**：无 GMS 机型 FCM 不可达，需接华为 HMS Push / 小米 / OPPO / vivo 多厂商，工作量与后端派送分发都翻倍。这是安卓最大工程风险。
2. **支付渠道**：Android 侧走微信支付 SDK 还是支付宝？影响 Payment 模块与后端 provider。
3. **原生 vs 跨端（RN/Flutter）**：design README 提到 RN 可能性。若选跨端可省一套 UI，但团队现有 iOS 是纯原生 SwiftUI，无跨端基建，需权衡。
4. **i18n 时序**：建议等当前 i18n 补抽 key 收敛后再启 Android，避免边抽 key 边译。

## 五、测试视角（我的关注点）
- API 契约测试可复用后端现有 pytest（92 router 已覆盖），Android 端只需契约对齐验证。
- Android E2E 需新建：Espresso（原生）或 Maestro/Appium（跨端），落 `ios/` 同级 `android/e2e/`。
- 回归重点：多端 device_token 注册冲突、同用户多端 WS 连接数限制（D-019）、支付回调幂等在新支付渠道下的表现。
- 兼容性矩阵：Android 机型碎片化（design README 已列 0.5x~4x 屏幕范围），需真机/云测覆盖主流厂商 ROM。

## 六、工作量粗估
- 后端（FCM provider + 多厂商分发）：中
- Android 客户端全量：大（对标 iOS ~16k LOC 从零）
- 设计 token 输出器 + i18n 对接：小
- 建议分期：先 OTP 登录 + 核心下单/订单/聊天 MVP，再补 Precheck/Share/Legal 等。
