# Android 端技术设计（Design: Support Android Version）

- 项目: support-android-version
- 关联: AND-REQ-001（已批准）· ADR-0064（方向 A + 四约束）
- 三端对齐 SSoT: `docs/requirements/three-end-alignment-matrix.md`
- 架构师: 魈 · 日期: 2026-07-15
- 状态: 提议（待凝光 review）

## 0. golden 基线数字钉正（evidence-first）

物理核 `wechat/app.json`：**12 主包 pages + 21 分包 pages = 33 页**（非矩阵头注的 34）。凝光头注「22 分包」系笔误（实际 21），矩阵表体正确列 33 行。**golden 基线 = 33 页**，测试 AC 引用页数以 33 为准。ADR-0064「33」正确。

## 1. 技术选型（帝君方向 A 已锁，本节定实现栈）

| 层 | 选型 | 理由 |
|---|---|---|
| 语言 | Kotlin | 方向 A |
| UI | Jetpack Compose | 声明式，对齐 iOS SwiftUI 心智 |
| 网络 | **Retrofit + OkHttp + kotlinx.serialization** | Retrofit 契约清晰，与 openapi.json 映射直接；kotlinx.serialization 官方 KMP-ready |
| 契约对接 | openapi.json 手工映射 DTO（不引 codegen） | 125 路由规模可控，codegen 引入维护黑盒；手工 DTO 对齐 iOS Core/Models 结构，便于三端 diff |
| WS | **OkHttp WebSocket**（复用网络层 OkHttp 实例） | 对齐 iOS/小程序 ws-base 语义，避免双栈 |
| DI | **Hilt** | Android 官方，编译期校验，团队上手成本低 |
| 状态 | Compose `ViewModel` + `StateFlow` | 对齐 iOS `@Observable`/ObservableObject 单向数据流 |
| 本地存储 | DataStore（token/session）+ EncryptedSharedPreferences（share_session/敏感） | 对齐 iOS Keychain（ShareSessionStore） |
| 导航 | Navigation-Compose | 单 Activity + Compose 导航 |

### 备选对比（Retrofit vs Ktor Client）
- Retrofit：注解式契约、生态成熟、拦截器（401 refresh）成熟 → **选**
- Ktor Client：KMP 友好，但本期纯 Android，无 KMP 需求，Retrofit 更省心
- 结论：Retrofit（本期无跨端共享 KMP 场景，不为将来不需要的扩展点买单）

## 2. 工程结构（对齐 iOS Core + Features 分层）

```
android/app/src/main/java/com/yiluan/
├── core/
│   ├── network/        # ApiClient, AuthInterceptor(401 refresh), ApiEndpoint, WebSocketClient
│   ├── model/          # DTO（对齐 iOS Core/Models：Order/Share/Review/Notification/...）
│   ├── storage/        # TokenStore(DataStore), ShareSessionStore(Encrypted)
│   ├── components/     # 复用 Composable（信任卡/错误引导卡/...）
│   └── util/           # 扩展、格式化
├── features/           # 逐模块对齐 iOS 13 Feature
│   ├── auth/           # login + role-select
│   ├── patient/        # home/create-order/order-detail(含 Precheck 信任卡)/pay-result
│   ├── companion/      # home/available/today/orders/detail/chat/profile/setup
│   ├── order/          # 通用 order-list(角色态复用) + ShareService
│   ├── chat/           # list + room(WS)
│   ├── notification/   # 列表(App 内 + WS)
│   ├── review/
│   ├── profile/        # profile/edit/about/bind-phone/wallet/family/emergency/followup/settings
│   ├── precheck/       # PrecheckScreen + PrecheckWebSocket（一期强制）
│   ├── share/          # ShareOrderScreen + ShareOTPScreen + ShareWebSocket（一期强制）
│   ├── settings/       # delete-account
│   └── legal/          # privacy + terms
├── di/                 # Hilt modules
└── YiLuAnApp.kt        # Application + Hilt entry
```

## 3. 需凝光交底的 4 个技术判定点（AC 待定项，测试执行依赖）

### 3.1 AC1/AC7 三端一致性断言层
**判定：锚定后端契约层**（采纳刻晴口径 + 凝光矩阵定稿）。
- 断言 = 同一业务操作三端各自触发后：**请求契约一致（method/path/body schema）+ 返回状态/DB 变更一致 + WS 推送事件一致**
- UI 呈现不做三端肉眼比对，交各端模块 develop task 的 AC 单验
- golden 端 = 小程序（帝君定的事实源），iOS/安卓比对小程序的后端交互序列
- **可测实现**：test 层录小程序对每个操作的 API 调用序列（golden trace），安卓/iOS 比对同操作产出的 trace 一致

### 3.2 WS 断开重连后消息补推策略
**判定：仅 REST 拉补，不做 WS 补推**（一期）。
- WS 重连后不要求 backend 补推断线期间 miss 的事件
- 断线期间消息一致性由 REST 列表拉取兜底（notification 列表 / chat 历史 / precheck status 全走 REST 可拉全量）
- **一期不测 WS 补推**（明写）：WS 定位为「在线实时增强」，非「可靠投递通道」；可靠性由 REST 兜底保证
- 理由：backend 零改动约束下，WS 补推需 backend 加断线重放逻辑（违约束）；REST 拉取足够保证不丢消息（AC3）

### 3.3 Precheck WS 无响应轮询兜底阈值 + 间隔
**判定（对齐 iOS PrecheckWebSocket 现有语义）**：
- WS 连接建立超时：**5s** → 超时降级轮询
- 轮询间隔：**3s**，最多 **10 次**（30s 窗口），拿到终态（4 cert 全 resolved 或永久失败码 4001/4003/4004/4011）即停
- WS 中途断开：立即切轮询（同上参数），WS 重连成功则停轮询回 WS
- （需 design review 时与 iOS 实测参数二次核对；若 iOS 现值不同以 iOS 为准，三端统一）

### 3.4 mock/wechat provider 切换口径
**判定：配置项切换，非改代码**（已实证成立）。
- backend `config.payment_provider`（env）默认 `mock`，切真支付改 `wechat`，`factory.py` 据此实例化
- 安卓端**无感知**：安卓只调统一下单 endpoint，provider 差异在 backend
- 安卓一期开发/联调全程 `payment_provider=mock`，资质下来 backend 改 env 即切真，安卓端零改动
- **后端零改动成立**：mock provider 已存在，安卓不触发任何 backend 代码变更

## 4. 三端 Share/Precheck 对齐轴（帝君一期强制）

| 功能 | 后端 API（三端共用） | 小程序 | iOS | 安卓一期 |
|---|---|---|---|---|
| Precheck | `users_precheck.py` REST + `ws.py` precheck event | ✅ 订单详情信任卡+WS | ✅ PrecheckView+WS | 🆕 PrecheckScreen+WS |
| Share | `send_share_otp`/`get_share_session_order` + shareWs | ⚠️ service 层齐**缺页面入口** | ✅ ShareOrderView+OTP+WS | 🆕 ShareScreen+OTP+WS |

**对齐动作**：
1. 安卓 Precheck/Share：按 iOS 完整实现 1:1 建（含 OTP 流程 + WS + session 存储）
2. **小程序补 Share 页面入口**（`ANDROID-DEV-WX-SHARE-ENTRY`，接现有 service，对齐 iOS ShareOrderView 交互）— 入口位置建议：患者订单详情页「分享给家属」按钮 → Share 页（与 iOS 一致）
3. 三端 Share/Precheck 后端交互序列一致 = AC7 门槛

## 5. 分批排期（按 Feature 模块，参照 i18n Epic 分批经验）

**批次划分原则**：先地基（core 网络/DI/存储）→ 核心闭环（登录+下单+支付+订单）→ 实时（chat/notification WS）→ 强制对齐项（Precheck/Share）→ 长尾（profile 子页/legal）。

| 批次 | 内容 | 依赖 |
|---|---|---|
| B0 地基 | core/network(Retrofit+401拦截器) + DI(Hilt) + storage + WS client 基座 + 工程骨架 | 无 |
| B1 认证 | login + role-select + token/session 存储 | B0 |
| B2 患者核心闭环 | patient home/create-order/order-detail/pay-result(mock) + 通用 order-list | B1 |
| B3 陪诊员闭环 | companion home/available/today/orders/detail/setup/profile + companion-detail | B1 |
| B4 实时 | chat list/room(WS) + notification(WS+REST) | B2 |
| B5 强制对齐 | **Precheck(WS)** + **Share(OTP+WS)** + 小程序 Share 入口补齐 | B2,B4 |
| B6 长尾 | profile 子页(edit/about/bind-phone/wallet/family/emergency/followup/settings) + review + legal + delete-account | B1 |
| B7 iOS 补齐线 | design 逐页细核发现的 iOS 相对小程序缺口（独立 develop+test，与安卓并行） | 并行 |
| B8 三端对齐审计 | 逐模块核 AC7 后端契约一致 | 全部 |

每个 develop task 配对 test task（depends_on），三条线（安卓全量 / iOS 补齐 / 小程序入口）刻晴按此备 test。

## 6. 待 design review 后的 task 拆分

design 通过后按 B0-B8 拆 develop+test task。安卓主体 develop 等本 design 定稿，胡桃先做小程序 Share 页入口（独立补齐，已交底）。
