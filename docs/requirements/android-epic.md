# 医路安 Android 版本 Epic 需求文档

> PM：凝光 · 日期：2026-07-15 · 关联：ADR-0064、docs/requirements/three-end-alignment-matrix.md
> board：support-android-version · epic requirement：AND-REQ-001

## 一、目标

为医路安新增**原生 Android 客户端**，实现**三端（安卓/iOS/小程序）产品功能完全对齐**。

## 二、帝君四约束（2026-07-15 13:12 UTC 拍板 · ADR-0064）

| # | 约束 | 落地口径 |
|---|------|---------|
| 1 | 方向 A | Kotlin + Jetpack Compose 原生，对称 iOS SwiftUI/MVVM，按 iOS 13 Feature 结构 1:1 建 |
| 2 | 微信支付 + 资质搁置 | 一期走 mock/sandbox provider（后端 mock/wechat 双 provider 现成），真实资质+回调二期 |
| 3 | 三端完全对齐 | 以小程序 34 页面为功能事实源，安卓+iOS 逐页对齐（见对齐矩阵） |
| 4 | FCM 一期后置 | 一期仅 device_token 注册 + WebSocket 前台实时 + App 内通知，FCM 离线派送二期 |

## 三、范围

> **帝君 2026-07-15 14:48 拍定两条范围口径（锁定）：**
> 1. **iOS 补齐 = 本期一起做**（不另行排期）。epic 组织为「Android 新建 + iOS 对齐缺口」两条线并行，共用同一份对齐矩阵作验收基线。
> 2. **Precheck / Share → 安卓纳入一期**（强制项，不砂不延）。

### 一期（含）
- 安卓 34 页面 Compose 全量建（按对齐矩阵）
- **安卓一期强制含 Precheck + Share**（帝君确认，非 backlog）
- **iOS 对齐缺口补齐**（本期并行线）：iOS 相对小程序缺的功能点，由 design 阶段据矩阵拆独立 develop+test task
- **小程序侧缺口补齐**：如 Share 入口（刻晴 review 指出）等小程序本身的对齐缺口，配对新增 develop+test
- 网络层（Retrofit/Ktor + JWT 拦截器 + 401 静默刷新）
- WebSocket（OkHttp WS + 重连 + 心跳）
- 认证：手机 OTP + 微信登录（接微信开放平台 Android SDK）
- 支付：微信支付路径走通，一期 mock provider
- 本地存储：Token 走 EncryptedSharedPreferences/Keystore
- 三端对齐审计（逐页核 iOS/小程序/安卓一致，锅定后端契约断言层）

### 一期（不含 / 二期 backlog）
- 🔵 FCM 系统级离线推送派送
- 🔵 真实微信支付资质申请 + 回调落地
- ⚪ Apple Sign-In（iOS 专属，安卓不做）

> 注：Precheck / Share 不再是二期 backlog——已按帝君确认上提为**安卓一期强制项**。

## 四、后端影响

**核心契约不动。** REST + WebSocket platform-agnostic，`device_tokens.device_type` 已含 android 枚举。
仅二期补：FCM Provider（既有 SubscribeMessageProvider 抽象下新增）+ push 按 device_type 分流。

## 五、验收基线

见 `docs/requirements/three-end-alignment-matrix.md`。每页安卓 Feature 的可测验收口径由本 epic 逐页定义，供架构师魈据此拆 develop/test task。

## 六、待帝君确认（需求 review）

✅ **均已帝君 2026-07-15 14:48 拍定：**
1. **iOS 补齐口径**：本期一起做，不另行排期。✅
2. **Precheck / Share 三端归属**：安卓纳入一期（强制项）。✅

无剩余待确认口径，范围已锁定。

## 七、下游

需求 review（→ 架构师魈 + 测试员刻晴）→ 帝君批准 → 魈出 design（Feature 级拆 develop+test，按小程序 34 页 / iOS 结构）→ 开发 → 测试 → PM 验收（核覆盖完整性：逐页核安卓 34 页全建，不漏页）。
