# ADR-0035: 团队接管 — 架构现状与风险盘点

- **状态**：Accepted（2026-05-28，魈）
- **范围**：S1-DES-001 收窄版（优化方向收口给凝光 PRD-001 + ADR-0036）
- **背景**：璃月团队接手 YiLuAn 持续迭代，需要一份"架构地图 + 真风险盘点"作为后续所有迭代的判断基准
- **关联**：S1-REQ-001 凝光对标分析；S1-TEST-001 刻晴测试盲点；ADR-0036 家庭陪诊授权

---

## 1. 三端架构地图

```mermaid
flowchart TB
  subgraph Client[客户端]
    WX[微信小程序 30页/9组件<br/>原生 + Observer]
    IOS[iOS App<br/>SwiftUI + MVVM + @MainActor]
    AdminH5[admin-h5<br/>纯静态 HTML/JS — 待 admin-v2 重构]
  end

  subgraph Edge[FastAPI]
    API[api/v1/* REST<br/>JWT HS256 + slowapi 60/min]
    WS[/ws/chat/{order_id}<br/>auth handshake + per-user cap/]
    WSShare[/ws/share/{token}<br/>ADR-0036 新增/]
  end

  subgraph Service[Service 层]
    OrderSvc[OrderService<br/>lifecycle/cancel/payment/query/expiry Mixin]
    PaySvc[PaymentService<br/>状态机+幂等+补偿退款]
    ChatSvc[ChatService<br/>ADR-0031 统一 WS 写路径]
    NotifSvc[NotificationService]
    IdempSvc[IdempotencyService<br/>SAVEPOINT 并发]
  end

  subgraph Outbound[出站可靠性]
    OutboundDec[utils/outbound.py<br/>⚠️ P0-04 待修]
    WxPay[wechat pay v3]
    AliSMS[Aliyun SMS]
    DeepSeek[DeepSeek<br/>ADR-0036 新增]
  end

  subgraph Infra[基础设施]
    PG[(PostgreSQL 15<br/>Alembic)]
    Redis[(Redis 7<br/>OTP+Pub/Sub+Cache)]
    OSS[(Azure Blob<br/>avatars+chat-images)]
    Sched[APScheduler<br/>PG advisory lock]
  end

  WX & IOS --> API & WS
  WX --> WSShare
  AdminH5 --> API
  API --> OrderSvc & PaySvc & ChatSvc & NotifSvc & IdempSvc
  WS --> ChatSvc
  WSShare --> OrderSvc
  OrderSvc & PaySvc --> OutboundDec
  OutboundDec --> WxPay & AliSMS & DeepSeek
  OrderSvc & PaySvc & ChatSvc & IdempSvc --> PG
  ChatSvc --> Redis
  Sched --> PG
  API --> OSS
```

---

## 2. 已落地决策盘点（key ADR/D-编号）

| 编号 | 主题 | 状态 | 备注 |
|---|---|---|---|
| ADR-0001 | 微信支付集成 | ✅ | Provider 抽象 + 回调幂等 |
| ADR-0026 | Outbound 可靠性（timeout/retry/CB） | ⚠️ 需修订 | 凝光评审发现 3 处真 bug，本 ADR §3 列入 |
| ADR-0029 | Emergency PII 留存 | ✅ | — |
| ADR-0030 | Staging mock 环境 + Decimal 全链路 | ✅ | TD-MONEY-01 兼容期 |
| ADR-0031 | WS + ChatService 统一 | ✅ | 写路径单点 |
| ADR-0032/0033 | Money 对账 + scale | ✅ | — |
| ADR-0034 | Admin v2 鉴权 | ✅ | 鉴权框架就绪，前端待 admin-v2 重构 |
| ADR-0036 | 家庭陪诊家属端分享授权 | 📝 Draft | 本周交付 |
| D-018 | APScheduler PG advisory lock | ✅ | — |
| D-019 | WS Redis Pub/Sub 多副本 | ✅ | — |
| D-027 | callback log TTL + OSS 归档 | ✅ | — |

---

## 3. 真风险盘点（按严重度）

> 仅记录"已验证、未修复、需要后续 task 兜底"的风险。已在 TECH_DEBT 登记的 TD-* 不重复。

### 🔴 P0-A：`utils/outbound.py` 熔断器 + 重试组合不正确（凝光子 agent 评审 + 魈独立验证）

**位置**：`backend/app/utils/outbound.py:60-178`

三处问题：
1. CircuitBreaker `record_success` 一次成功即 CLOSED，half-open 无 N 连胜门槛——故障下游会扑闪
2. `httpx.HTTPError` / `httpx.RequestError` 不在 retry 白名单——绕过熔断 propagate
3. retry loop 中 `cb.allow_request() == False` 抛 `RetryableError` 但**未 record_failure**，attempt#1#2 退化空转，浪费 retry slot

**影响放大点**：ADR-0036 引入 DeepSeek 第 4 条 outbound 链路，与微信支付/SMS/Redis Pub/Sub 共用同一 CB 实现，bug 会在金钱+体验+合规三条链路同时放大。

**修复**：W19 必修，胡桃执行；新建 ADR-0026r1（或合并到本 ADR follow-up）记录修订。

### 🔴 P0-B：iOS `APIClient.refreshTokenIfNeeded` 并发 401 形同虚设

**位置**：`ios/YiLuAn/Core/Networking/APIClient.swift:299-323`

`guard !isRefreshing else { return }` —— 并发 401 不等待结果也不重发，N 个并发请求悄悄丢一半。

**修复**：改 `Task<Token, Error>` 缓存，所有并发 401 共享同一次 refresh，W19 必修。

### 🔴 P0-C：`record_callback_or_skip` 空 transaction_id 直接放行

**位置**：`backend/app/services/payment_service.py` 幂等键 `(provider, transaction_id)`，但 transaction_id 为 None/空字符串时 UNIQUE 约束不生效，并发 callback 可重复入账。

**修复**：服务层显式拒收空 tx_id + Prometheus counter `payment_callback_invalid_total`。W19 必修。

### 🟡 P1-A：`tasks/scheduler.py` 部分 job 未走 `acquire_scheduler_lock`

多副本时 callback log TTL 清理、订单过期扫描有 PG advisory lock；但新增 job（如 ADR-0036 的 AI 摘要触发）易遗漏。建议统一基类装饰器。

### 🟡 P1-B：admin-h5 安全裸奔

`admin-h5/index.html:27` 明文露 staging admin token；纯静态 HTML 无 CSRF / RBAC / 审计。**P0-11 删 token 文案是创可贴，长期解法 = admin-v2 重构（帝君已定 A 长期发展）**。

### 🟡 P1-C：跨端 schema 契约漂移风险

后端 schema `_ser_price` / `_ser_amount` 主动 `float()` 兼容老客户端（TD-MONEY-01），三端任何一端先升 Decimal-aware parser 都不会触发 break；但缺**跨端契约测试**（刻晴 S1-TEST-001 已列盲点）。

### 💭 P2-A：OrderService Mixin 共享 `_OrderServiceBase` 注入

当前依赖在 `__init__` 集中收口，工程实践干净；但随 mixin 增加（如 ADR-0036 会加 share token 子服务）会膨胀。**P2 引入轻量 DI 容器**，本期不动。

### 💭 P2-B：design tokens 三端同步靠手工

`design/tokens.json` + `generate.py` 只输出小程序 CSS，iOS Swift 端手工同步。建议给 generate.py 加 Swift 输出器，**P2 排期**（凝光建议清单）。

---

## 4. 与凝光 PRD / ADR-0036 的衔接点

| 衔接 | 内容 |
|---|---|
| Top1 字段契约 | ADR-0036 §2.7 跨端字段表 → PRD-001 §4 回填 |
| AI 摘要合规 | ADR-0036 §2.6 prompt + post-check 双护栏；PRD-001 显性免责声明 |
| 隐私脱敏 | ADR-0036 §2.5 字段表；PRD-001 家属端展示规范对齐 |
| outbound 修复硬依赖 | ADR-0036 §4 风险 #1 → W19 P0-04 是 ADR-0036 的前置条件 |

---

## 5. 不在本 ADR 范围

- 优化方向 / 战略级建议 —— 全部收口到凝光 `docs/team-handover/competitive-analysis.md`（已修订为 Top1 单聚焦版）
- Top1 具体技术设计 —— ADR-0036
- 测试盲点 —— 刻晴 `docs/team-handover/test-gap-analysis.md`
- 代码细节地图 —— 胡桃 `docs/team-handover/code-walkthrough.md`（in-progress）

---

## 6. 后果

- **+**：风险有显式分级 + owner + 修复入口，W19 排期可直接 cherry-pick
- **+**：架构地图作为后续任意新 task 的"读这一份就够"入口
- **−**：本 ADR 未覆盖完整优化方向（按收窄约定，故意）；需配合凝光建议清单一起读
