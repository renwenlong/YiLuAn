# 医路安代码通读 — 程序员视角 (S1-DEV-001)

> 作者：胡桃 (developer) · 2026-05-28 · 范围：W18 Release Wrap-Up snapshot
> 配套：`docs/team-handover/test-gap-analysis.md`（刻晴）/ `docs/team-handover/competitive-analysis.md`（凝光）/ `docs/adr/ADR-0035`（魈）
> 目的：给后续接手 / 迭代的工程师一份「不读源码也能知道哪里有坑哪里能复用」的导览。

---

## 0. TL;DR — 3 件可复用 + 3 个坑

**值得复用（接 ADR-0036 Top1 时直接套）：**

1. **Provider 抽象 + factory + outbound 装饰器三件套**（payment/sms 已经做完一遍）—— DeepSeek/OSS 接入照抄即可
2. **WsPubSubBroker（ADR-0031）+ Redis Pub/Sub**：`share:{order_id}` 只读 topic 直接加 channel 就行，broker 已经多副本验证
3. **OrderService 的 mixin 切分（5 mixin + `_base`）**：share/AIDigest 加业务时按相同套路，不要回 god class

**容易踩坑（评审 / 实施时盯紧）：**

1. **outbound 装饰器 ADR-0026 v1 的三大遗留**（half-open 单成功 close / 无 httpx 白名单 / CB 不空转）—— ADR-0035 P0-A，已分到 `S2-DEV-007`
2. **SMS rate_limiter 有 in-proc fallback**（`_inproc_store` 模块级 dict），生产**必须** Redis；本地多 worker 用 fallback = 限流穿透
3. **OrderService.lifecycle 状态机 + `_check_recon_block`**：每次新写 transition 必须显式调 `_check_recon_block`，漏调一处资金对账门槛就破（ADR-0032 / 0033 强约束）

---

## 1. 后端 backend/app — 模块地图

### 1.1 services/ —— 业务编排层（24 个 service + provider）

| 模块 | 行数 | 职责 | 复用/坑 |
|---|---|---|---|
| `order/` (mixin 切分 5 个文件) | ~1000 | 订单全生命周期：query / lifecycle / cancel / payment / expiry + `_recon_guard` | ✅ mixin 套路；⚠ `_check_recon_block` 必须每个 transition 显式调，否则资金对账 unfreeze 失效 |
| `payment_service.py` | 739 | 编排支付/退款，幂等 + 回调审计 + WalletLedgerWriter | ✅ provider 抽象；⚠ 体积过大，CR 难，下一轮可拆 prepay / callback / refund 三 mixin |
| `providers/payment/` (base + factory + mock + wechat 426 行) | ~650 | WeChat Pay v3 真实实现 + DTO `OrderDTO`/`RefundDTO`（amount = Decimal yuan，ADR-0030） | ✅ Decimal 全链路；⚠ `wechat.py` 426 行集中证书缓存 + 验签 + 加解密，单元测试覆盖密但 mock 桩多，新人难快速 onboard |
| `providers/sms/` (base+factory+mock+aliyun+rate_limit+logging_wrapper) | ~700 | Aliyun SMS provider + 限流 + 日志包装 | ✅ rate_limit decorator 可直接套 OTP / share token send；⚠ fallback dict 跨进程不安全（已注释说明） |
| `wallet.py` + `wallet_ledger_writer.py` | 80 + 286 | 钱包余额 + 不可篡改账本 | ✅ ledger 写入和资金对账绑定（M1）；⚠ 任何动钱的地方都要走 ledger_writer，不要 raw update wallet.balance |
| `reconciliation/` (autofix/diff/incremental) | ~960 | T+1 资金对账 + 增量 + 自动修复 | ✅ ADR-0032/0033 已落；⚠ `incremental.py` 392 行复杂度高，跨 boundary（diff 表 + autofix + admin worklist）改一处影响多处 |
| `idempotency.py` | 132 | 幂等键（IdempotencyKey 表） | ✅ 支付回调、AI 摘要 enqueue 都可套；⚠ TTL 默认 24h，share token 24h 滚动窗口 distinct 计数另起 scanner（已规划 S2-DEV-006），不要混用 |
| `notification.py` | 284 | 通知触发器，覆盖 order/chat/emergency 各类事件 | ✅ 直接拓展 `notify_share_*` 系列；⚠ 通知触发与业务事务在同一 session，长链路通知失败会污染主事务 commit—— 应该考虑拆 outbox |
| `emergency.py` (115) + `dead_letter.py` (81) | - | 紧急联系人 + 失败任务死信 | ✅ AI 摘要失败入 dead_letter 直接套；⚠ dead_letter 目前没有 retry worker，只是落库 |
| `auth.py` + `wechat.py` + `refresh_tokens.py` | ~250 | OTP + JWT + 微信 jscode2session + refresh | ✅ share_session JWT 复用 `core/security`；⚠ refresh token 队列里 401 并发刷新已实现，前端模仿这套做（wechat/services/api.js 已做） |
| `family_member.py` + `patient_profile.py` + `companion_profile.py` + `hospital.py` + `review.py` + `chat.py` + `upload.py` + `user.py` + `subscribe_message.py` | 各几十~200 行 | 各域 CRUD | 常规，不展开 |

**通用设计点（值得遵循）：**
- 所有 service 构造 `__init__(self, session: AsyncSession)`，自己 new repository；DI 边界清晰
- service 永远 ack `AsyncSession`，不在 service 里 commit（commit 由 FastAPI dependency 边界控制）
- 异常体系：`app/exceptions.py` 的 `AppException` 子类 → HTTP code 自动映射；新 share 错误应继承同套（避免 raw `raise HTTPException`）

### 1.2 repositories/ —— 数据访问层（11 个 repo + base）

- `BaseRepository[T]`：通用 CRUD（`get_by_id` / `create` / `update` / `delete` / `list`）
- 每个 repo 加自己的查询（`OrderRepository.list_expired` / `PaymentRepository.get_by_order_and_type`）
- **设计决策**：**不用 ORM relationship**，FK 都是裸 UUID，join 手工写在 service / repo —— 学习曲线友好，CR 友好；代价是聚合查询要多两行
- ✅ Top1 加 `OrderShareTokenRepository` 直接照搬

### 1.3 providers/ —— 外部服务抽象

```
providers/
├── payment/  base.py(125) + factory.py(24) + mock.py(59) + wechat.py(426)
└── sms/      base.py(122) + factory.py(37) + mock.py(71) + aliyun.py(210) + rate_limit.py(150) + logging_wrapper.py(262)
```

**套路**：abstract base + concrete 实现 + factory（settings 切换）。AI 摘要的 DeepSeek client 应该按这个套路放到 `providers/ai/`，不要塞 `services/` 平铺。

### 1.4 utils/outbound.py — 可靠性装饰器（⚠ 待修复）

- 当前实现：timeout + retry（指数退避）+ circuit breaker
- Prometheus metric：`outbound_call_total` / `outbound_call_duration_seconds` / `outbound_circuit_breaker_state`
- **3 个遗留**（ADR-0035 §3 P0-A → ADR-0026r1 → `S2-DEV-007`）：
  1. half-open 单成功 close → 真实场景下「闪回」机率高，应改 N 连胜（默认 N=3）
  2. 没有 httpx 白名单 → 每个服务用同一组 timeout/retry/CB，DeepSeek 慢 / 微信支付快需要分别配
  3. CB 长时间 idle 不 reset → 半夜首请走 open 态直接降级，体验差
- F2 灰度前必须修，已在 `S2-DEV-007` 锁死为硬依赖

### 1.5 core/ —— 横切关注点

| 模块 | 用途 | 复用提示 |
|---|---|---|
| `security.py` (43) | JWT 签发 / 解析 | share_session JWT (TTL 30min) 直接复用 `create_access_token` 加 audience claim 区分 |
| `admin_auth.py` + `admin_jwt.py` (45 + 170) | admin 后台 token | admin-v2 重构（ADR-0034）继续走这个 |
| `distributed_lock.py` (185) | PG advisory lock | AI 摘要 `@with_scheduler_lock` 装饰器实现来源；S2-DEV-006 直接复用 |
| `pii.py` (265) | PII 脱敏 helper | F2 家属端落地页脱敏直接套（姓名 / 电话 / 身份证已有 mask 函数） |
| `error_codes.py` (63) | 业务错误码常量 | share token 加 `SHARE_TOKEN_EXPIRED` / `SHARE_TOKEN_REVOKED` / `SHARE_SCOPE_FORBIDDEN` 三条即可 |
| `rate_limit.py` (4) | slowapi limiter 配置 | 单点引用；share token send OTP 可加专项 limiter |
| `redis.py` (14) | redis 实例 + getter | share:loc:{order_id} TTL 60s 直接用 |

### 1.6 api/v1/ —— 路由层

22 个 router（auth/users/patients/companions/hospitals/orders/chats/reviews/notifications/payment_callback/wallet/emergency/family_members/followup_reminders/auth_apple/admin/ws/...）：
- 每个 router 引用对应 service，方法签名薄
- 已经有 `openapi_meta.py` —— OpenAPI baseline 冻结（S2-DEV-004）改这里加 metadata
- `telemetry.py` + `health.py`：`/readiness` 双探活（DB + Redis），K8s 用

### 1.7 models/ —— 27 个 SQLAlchemy 模型

设计决策：
- UUID 主键 + UTC timestamps + denormalization（`hospital_name` / `patient_name` / `companion_name` 冗余到 order 防 join）
- 状态机用 enum + `ORDER_TRANSITIONS` dict（`app/models/order.py`）
- `payment_callback_log` 有 TTL（D-027，5y 保留 freeze 由 D-052 锁死）

新增 `OrderShareToken` / `AIDigest` 严格遵循上述约定。

---

## 2. 微信小程序 wechat/

### 2.1 状态管理 — 观察者模式 store

`store/index.js` (178 行)：`getState` / `setState` / `subscribe` / `reset`。简单粗暴但够用，不上 Mobx / Redux。
**坑**：subscribe 没有自动 unsubscribe（页面 onUnload 需要手动调），漏一个会内存泄漏。F1~F6 新页面建议封 mixin 处理。

### 2.2 网络层 — `services/api.js`

- wx.request Promise 封装 + Bearer 注入
- **401 并发刷新队列**：多个并发请求遇 401 时只发 1 次 refresh，其他等待 ——后端 `refresh_tokens.py` 配套
- ✅ share_session 401 处理可参照同样模式（家属端独立 token，不与下单人 access_token 混用）

### 2.3 常量同步 — `utils/constants.js`

`SERVICE_TYPES` + `ORDER_STATUS` **必须**与后端 `app/models/order.py` 同步（CLAUDE.md 已列 cross-stack sync point）。Top1 加 `SHARE_SCOPE` enum 时也要双端同步。

### 2.4 utils 工具集（19 个）

值得复用 / 注意：
- `degradation.js`（203 行）：客户端降级策略 —— F2 家属端断网 / WS 断线 UI 提示套这个
- `haptic.js`：触感反馈统一入口（P-03 已落），新增交互直接调
- `formatCurrency.js` + `tokens.js`：货币 / 设计 token —— 巨字号模式（F5）走 tokens.js 加 scale 变量
- `telemetryReporter.js` + `analytics.js`：埋点 / 上报，新功能必埋
- `logger.js`：日志统一入口（带 PII mask），不要直接 console.log

### 2.5 27 页面布局

`pages/patient/*` + `pages/companion/*` + `pages/chat/*` + `pages/profile/*`。F1（下单人侧）落 `pages/patient/share-manage/`，F2（家属侧无注册）落 `pages/share/` 平行根目录（独立鉴权域）。

**坑**：customs `tabBar`（不用原生），导航走 `wx.reLaunch`；家属端是否要独立 tabBar 要在 PRD 评审前定。

---

## 3. iOS YiLuAn/

### 3.1 MVVM + SwiftUI + iOS 17+

- `Core/Networking/APIClient.swift` —— async/await HTTP，按 `APIEndpoint` enum 派发
- `Core/Networking/WebSocketClient.swift` —— 实时聊天；F3 家属端只读 topic 在 iOS App 内不需要（F2 是 H5），iOS 本期不动 share 端
- `Features/` 按域组织：Auth / Patient / Companion / Order / Chat / Payment / Review / Notifications / Profile / Legal / Settings

### 3.2 Top1 影响面

- **F5 巨字号模式**（下单人侧）：iOS 端走 `@Environment(\.dynamicTypeSize)` + 自适应 layout，相对成本低
- **F6 一键呼叫紧急联系人**：`UIApplication.shared.open(tel:)`，iOS 已有 EmergencyView 可扩
- **F2 家属端不入 iOS App**（H5 落地页），iOS 仅消费 `share_active_count` 字段在订单详情显示「2 位家属正在查看」

### 3.3 坑

- `APIEndpointTests` 反序列化断言要扩展 7 个 share 字段（S2-DEV-004 acceptance #24）
- iOS CI 动态 simulator 探测已落（commit b989b27），新增 test 不需要再配
- iOS 没有 lint config，依赖人工 review；F5 / F6 实施时建议加 SwiftLint baseline（可后置）

---

## 4. admin-h5（独立子项目）

纯静态 HTML/JS + Jest，目前只做陪诊师审核 MVP。**ADR-0034 已规划 admin-v2**（React/Vue 正式重构）—— 帝君批 A 长期发展，新 backlog `BACKLOG-ADMIN-V2` 等 BD/客服/财务扩编触发。本 task 范围不动。

---

## 5. 跨端同步点（再次强调，新功能必读 CLAUDE.md）

| 概念 | 后端 | 微信 | iOS |
|---|---|---|---|
| ServiceType / Price | `app/models/order.py` `SERVICE_PRICES` | `utils/constants.js` `SERVICE_TYPES` | `Core/Models/Order.swift` `ServiceType` |
| OrderStatus | `app/models/order.py` `OrderStatus` | `utils/constants.js` `ORDER_STATUS` | `Core/Models/Order.swift` `OrderStatus` |
| API 端点 | `app/api/v1/router.py` | `services/*.js` | `Core/Networking/APIEndpoint.swift` |
| WS 消息 | `app/api/v1/ws.py` | `services/websocket.js` | `Core/Networking/WebSocketClient.swift` |
| **【新增】Share 7 字段** | ADR-0036 §2.7 | F2 落地页 | iOS 订单详情只读取 share_active_count |

S2-DEV-004 OpenAPI baseline 闸门会兜底字段漂移，但**口口相传时也要先看这张表**。

---

## 6. 接下来 W20 实施提示（给自己）

按 S2-DEV-001 → 002 → 003 → 007 → 005 → 006 顺序 in-progress，004 (OpenAPI baseline) 等 002 端点骨架定型后再起：

- **S2-DEV-001 数据模型**：先 alembic 迁移上 + repo + helper（active token 上限 3 / expires_at 计算）—— 002/003/005/006 全部依赖
- **S2-DEV-007 outbound 修复**：F2 灰度硬依赖，与 002/003 并行，但 005 (DeepSeek) 需要它的修复版本
- **S2-DEV-002 6 端点**：依赖 001；OpenAPI 标记 done 前必须先过 004 baseline 闸门
- **S2-DEV-003 WS**：依赖 001 (token model) + 002 (DELETE 触发 close 4013)；E2E 10s/90s 重连用例不能省
- **S2-DEV-005 AI 摘要**：依赖 001 (AIDigest) + 007 (outbound 修复) + 006 (scheduler lock)
- **S2-DEV-006 调度锁 + scanner**：依赖 001；005 需要锁

D1 并行：001 / 002 / 003 / 007；D2 起 005 / 006；D3 收 004 baseline + 跨端契约 wire。

---

## 7. 一句话

> 后端架构成熟度高、provider 抽象 + outbound 装饰器是真正可复用的资产；Top1 实施按现有套路扩，不要新建并行体系；W20 D1 三件套（模型 / 端点 / WS）并行起手最快。
