# 医路安 架构与代码评审报告

- 日期：2026-05-28
- 评审人：架构与代码评审师（独立第三方视角）
- 评审范围：`backend/`、`wechat/`、`ios/`、`admin-h5/`、`docs/adr/`、`docs/`
- 采样原则：抽样 backend 8 个核心模块（OrderService 全套、PaymentService、outbound 装饰器、ChatService、IdempotencyService、PaymentProvider/SMSProvider、WsPubSubBroker、distributed_lock、scheduler）、wechat 的 api.js / store / notificationWs，iOS APIClient / OrderViewModel，admin-h5 index.html。
- 与既有 `docs/REVIEW_2026-04-20.md`（4 月全角色 Review）相比，本报告聚焦"代码已实现、但仍存在的结构性问题"，给出独立判断、不复述已修复项。

---

## 0. TL;DR

工程素质已经明显高于一般 MVP：分层、ADR、TECH_DEBT 登记、幂等、状态机、Provider 抽象都到位，1217 个后端 test、1357 端到端测试数量是真材实料。`utils/outbound.py`、`ws/pubsub.py`、`services/payment_service.py`、`tasks/scheduler.py` 这几个关键文件，可读性和注释密度甚至超过很多商业项目。

但要"敢上线真实流量"，仍然有 3 类风险必须先解决：

1. **熔断器与重试存在状态正确性 bug** —— `outbound_call` 装饰器在重试中把"熔断打开"也算成可重试，并且 CircuitBreaker 一次成功就清零（无 half-open 阶段评估），生产真出故障会被它放大或抖动。
2. **iOS `APIClient` 的 401 并发刷新形同虚设** —— `isRefreshing` guard 直接 `return`，并发 401 既不等结果也不重发，会把短时间内的 N 个并发请求悄悄丢一半。
3. **测试覆盖维度单一** —— 数字漂亮，但跨端 E2E、负载/压测、Chaos（PSP 超时/熔断/退款失败）、WebSocket 多副本真集成、iOS UI 测试这些"上线生死维度"几乎是空的。

下文逐项展开。

---

## 1. 架构优点（具体）

1. **OrderService Mixin 拆分干净**（`backend/app/services/order/`）
   `_base.py` 注入仓储/服务，`lifecycle / cancel / payment / query / expiry` 五个 mixin 各管一段，组合在 `__init__.py`。在 PR review 中这种拆法极容易演化成"循环 import 沼泽"，但本项目通过共享 `_OrderServiceBase` 把构造和依赖收口到一个地方，五个 mixin 全部互不 import，是教科书式的合理拆分。

2. **Provider 抽象 + outbound 装饰器分层正确**（`services/providers/payment/*` + `utils/outbound.py`）
   `PaymentProvider` / `SMSProvider` 是 pure interface，wechat / aliyun 实现负责协议编码，`@outbound_call(provider=...)` 负责 timeout/retry/circuit breaker/Prometheus 指标。三层职责切干净，新增 provider（比如换成支付宝）只要实现接口，不会污染主业务路径。ADR-0026 写得也很清楚。

3. **状态机 `ORDER_TRANSITIONS` 显式建模**（`backend/app/models/order.py:67-91`）
   状态转换写成 `dict[OrderStatus, set[OrderStatus]]`，`_OrderServiceBase._validate_transition` 一行 check，加上 `_recon_guard._check_recon_block` 在前向转换前阻断异常订单——状态机和金钱安全在同一个钩子上，是少有的把"状态正确性"和"资金正确性"绑死的设计。

4. **支付回调幂等 + 终态订单回调的"补偿退款"**（`payment_service.py:handle_pay_callback`）
   两层防御：`record_callback_or_skip` 用 `(provider, transaction_id)` 唯一约束去重；当 callback 命中"订单已终态"分支时，自动 issue refund（`TD-PAY-01`），保证用户不会"钱没了订单也没了"。这是大多数支付项目第一年最容易踩的坑，这里已经被显式建模并且写了注释解释来由。

5. **PG advisory lock + 同 session 持锁**（`tasks/scheduler.py:69-76` + `core/distributed_lock.py`）
   注释里明确"持锁与业务工作必须在同一个 AsyncSession 内"——这是 PG advisory lock 多数项目用错的地方（锁拿了就 release 回池子，等于没拿）。能把这个细节放进生产路径并写进注释，说明 D-018 的升级是真的被理解了，不是抄文档。

6. **HTTP `Idempotency-Key` 用 SAVEPOINT 处理并发**（`services/idempotency.py:97-117`）
   不是简单的 try/except，而是 `begin_nested()` 包住 `add+flush`，让 UNIQUE 冲突只回滚到 SAVEPOINT，外层 FastAPI 事务不被污染。同样的 SAVEPOINT 模式在 `payment_service.record_callback_or_skip` 也用了——这套模式在 codebase 内一致，说明是有意识的工程习惯。

7. **WS Pub/Sub 双通道 + origin 去重**（`ws/pubsub.py:130-158`）
   "本地立即投递 + Redis publish；envelope 带 instance_id 避免本机自己收自己"——这是分布式 WS 广播的标准做法，但 90% 的实现会忘 origin 字段导致消息双发，这里做对了。降级路径（Redis 不可用 → 单机模式 + warning）也写齐。

8. **小程序 401 队列刷新是真"队列"**（`wechat/services/api.js:_ensureRefresh`）
   用单 `_refreshPromise` 让所有并发 401 共享同一次 refresh，settle 后 `then(clear, clear)` 清缓存。错误路径（refresh 网络失败 vs refresh 被服务端拒）区分清楚，避免把"短网络抖动"误判成"token 失效"导致强制登出。注释里点名了曾经的"forever spinner" bug——说明这是有人踩过坑修过的代码。

9. **金额全链路 Decimal（ADR-0030）**
   `models/order.py:21` `SERVICE_PRICES` 是 `Decimal("299.00")`，`provider.base._to_decimal` 做边界归一化，`payment_service.create_prepay` 第一步就 `quantize(Decimal("0.01"))`。这条线从 model → service → provider → DB(Numeric(10,2)) 全部 Decimal，再没有 float 漏点。`TD-MONEY-01` 提到的 schema `_ser_price` 主动 `float()` 是兼容老客户端的 *输出* 妥协，不影响计算正确性。

10. **`PROVIDER_FREEZE.md` + `REQUIRED_PRODUCTION_SETTINGS` 常量**（`providers/payment/wechat.py:35-46`）
    Provider 把"上线所需的最小凭证集"以常量形式 export，让 readiness/部署脚本能编程式校验，而不是依赖人读 README。这是少见的"自描述"工程习惯。

---

## 2. 架构隐患 / 技术债（按严重度）

### 🔴 P0-1：`outbound_call` 装饰器熔断 + 重试组合不正确
**位置**：`backend/app/utils/outbound.py:128-178`

具体问题：
1. **熔断打开计入重试**（line 138-149）：在 retry 循环里第一件事是 `if not cb.allow_request(): raise RetryableError(...)`。配合 `for attempt in range(max_retries + 1)`，意味着如果 CB 在 attempt#0 触发打开，attempt#1 / #2 仍然进入循环，再次撞到 `allow_request() == False`，连续抛出 `RetryableError`——但每次都不调用 `cb.record_failure()`，所以**熔断 timeout 计时点是第一次失败时间，不是最后一次**，等同于浪费了两次重试但没产生任何 backoff 价值（中间的 `await asyncio.sleep` 也不会跑，因为没进入 except 分支）。
2. **half-open 状态没有真"半开"语义**（line 71-91）：`record_success` 直接清零，`record_failure` 直接重新打开。一次成功就把熔断关闭——典型的 half-open 应当至少要求 N 次连续成功才回到 closed，否则一旦下游间歇性故障，熔断会在 open / closed 之间"扑闪"，反而让流量持续打到不健康下游。
3. **重试只看 `RetryableError | TimeoutError`**：`httpx` 抛的 `httpx.HTTPError` / `httpx.RequestError` 不在白名单，会绕过重试和熔断直接 propagate 出去（落到外层 `except Exception` 才被吞）——和声称的"统一可靠性"承诺不一致。

**影响**：生产真出现 PSP 抖动时，熔断会过早打开、过早关闭，重试间隔失效，并且 httpx 网络错直接穿透。这是当前最大的"看起来安全其实不安全"的地方。

**修复成本**：S（同一文件 ~50 行调整）+ M（重写 `tests/utils/test_outbound.py` 覆盖 half-open / httpx 错的 case）。

---

### 🔴 P0-2：iOS `APIClient.refreshTokenIfNeeded` 并发保护无效
**位置**：`ios/YiLuAn/Core/Networking/APIClient.swift:299-323`

```swift
private func refreshTokenIfNeeded() async throws {
    guard !isRefreshing else { return }       // ← 关键 bug
    isRefreshing = true
    defer { isRefreshing = false }
    ...
}
```

`actor` 保证了 `isRefreshing` 的内存可见性，但 `guard !isRefreshing else { return }` 在并发 401 时的语义是 **"别人在刷我就直接成功返回"**——返回后调用方 `execute()` 立即用**旧 token**重发请求（line 271-278），再次拿 401，再次进 refresh，要么死循环、要么把第一个 refresh 抢占。

对比 wechat 端的 `_ensureRefresh` 用了共享 promise + 等待，iOS 这边等价于"我假装刷新成功了"。和 `wechat/services/api.js` 的对比尤其讽刺——同一份契约，两端实现完全不在一个等级。

**修复**：改成 `Task<Void, Error>` 缓存：`if let task = refreshTask { try await task.value; return }`，类似 Swift 社区标准写法。

**修复成本**：S（30 行）+ S（actor 并发测试）。

---

### 🟠 P1-1：`record_callback_or_skip` 没拿到 transaction_id 时直接放行
**位置**：`payment_service.py:194-198`

```python
if not transaction_id:
    return True  # caller proceeds with business processing
```

注释承认"无法去重"，但生产 webhook 几乎不可能不带 transaction_id，**如果真出现一定是攻击或上游 bug**。直接 `return True` 让 caller 走完整 callback 流程意味着同一个空 transaction_id 可以被回放任意次。

**建议**：要么 401，要么走第二维度去重（`out_trade_no + callback_type`），至少打 metric `payment_callback_missing_txn_id_total` 并接告警。

**修复成本**：S。

---

### 🟠 P1-2：`OrderRepository.has_unpaid_orders` 语义和 UX 不一致
**位置**：`backend/app/repositories/order.py:142-159`

判定"未支付"=`status == created AND id NOT IN (SELECT order_id FROM payments WHERE payment_type='pay')`。即只要存在 *任何* pay 行（哪怕 status='failed' / 'closed'）就算"已尝试支付"，于是 `create_order` 拒绝下单的提示"您有未支付的订单，请先完成支付"在用户取消支付后还会触发——因为 `payments` 表还留有 closed 行。

**建议**：where 条件加 `Payment.status IN ('pending','success')`。

**修复成本**：S（一行 + 测试用例）。

---

### 🟠 P1-3：APScheduler `coalesce + max_instances=1` 不足以替代锁
**位置**：`backend/app/tasks/scheduler.py`

注释说得清楚分布式锁覆盖 `scan_expired_orders` 一项，但 `cleanup_payment_callback_log` / `cleanup_sms_send_log` / `cleanup_emergency_pii` / `reconcile_money_t1` 多个任务**没有走 `acquire_scheduler_lock`**，仅靠 `max_instances=1` 进程内防护。生产多副本时这些会同时跑，至少：
- 清理类任务重复扫描 → DELETE 撞行锁、放大 IO
- `reconcile_money_t1` 在 02:00 GMT+8 同时启动多副本，可能两次进 autofix 队列

**建议**：所有 cron 任务统一走 `acquire_scheduler_lock`，给每个任务独立 key。

**修复成本**：S（5 个 job 各加一段 with-lock）。

---

### 🟠 P1-4：`wechat/store/index.js` 多订阅者抛错只有 `warn`，没有失败计数 / 上报
**位置**：`wechat/store/index.js:55-77`

`try { listener(_state) } catch (e) { _log('warn', ...) }` 静默吞掉所有 listener 异常。这是 store 类设计的合理选择，但小程序生产环境下没有 sentry 类的兜底——意味着某个页面 listener 持续抛错只会在本地 console 显示，**线上一无所知**。

**建议**：累加 `_listenerErrorCount`，超过阈值或固定窗口通过 wx 上报系统通道。

**修复成本**：S。

---

### 🟡 P2-1：`OrderService` 仍然偏大，单一 `OrderService.__init__` 实例化 8 个 repo + service
**位置**：`backend/app/services/order/_base.py:48-58`

5 个 mixin 共用 8 个依赖。如果将来需要为"陪诊师视角订单查询"或"运营视角订单批量操作"另开 service，会重复构造这一坨依赖。Mixin 拆分是好开端，但 DI 容器或 per-mixin 懒加载会更利落。

**修复成本**：M。当前不紧急，先记账。

---

### 🟡 P2-2：`Order` 模型反规范化字段缺一致性约束
**位置**：`backend/app/models/order.py:131-151`

`hospital_name / companion_name / patient_name / family_member_name / family_member_relation / family_member_phone` 都是从源表快照过来的反规范化字段，DB 层只是 `nullable=True`。如果以后 admin 修改 hospital 名称，订单上的快照不会更新——这是有意为之（注释解释了），但缺少：
- 一个 `materialized_at` 字段记录快照时间
- 或者一条文档/测试明确"snapshot 不回写"是契约

不是 bug，是"半年后接手的人会困惑"的事。

**修复成本**：S。

---

### 🟡 P2-3：`PaymentService._set_payment_state` / `_set_refund_state` 静默吞错
**位置**：`payment_service.py:526-577`

注释说"fund-side state is auxiliary; missing orders or DB hiccups must not break the payment write path"。理由站得住，但 `except Exception` + `logger.warning` 没有 metric/告警挂钩。这意味着 `payment_state` 长期和 `payments` 表偏离时，运营完全感知不到，直到对账 sweeper 发现差异。

**建议**：加 Prometheus counter `payment_state_sync_failed_total`，对账系统已经在跑，把它接进去成本极低。

**修复成本**：S。

---

### 🟡 P2-4：WebSocket 旧路径 `?token=` query 参数仍可用
**位置**：`backend/app/api/v1/ws.py:7-18`

docstring 写明"旧客户端的 ?token= 查询参数仍兼容，但会打 deprecated metric"。问题是 JWT 出现在 URL 里会被反向代理 / Nginx access log 持久化，是经典的安全反模式。docstring 只承诺"将在客户端全量升级后下线"——但没有时间表，没有看到对应 task。

**建议**：在 TECH_DEBT.md 立项并设 deadline；CI 增加一条"deprecated path 调用占比 > 1% 阻断发布"门禁。

**修复成本**：S（流程）。

---

### 🟡 P2-5：`admin-h5` 单文件 1073 行 `app.js` + 627 行 `index.html`
**位置**：`admin-h5/app.js`、`admin-h5/index.html`

CSP 写得很严，sessionStorage 也对（`TD-ADMIN-H5-CSP` 已修复）。但整个 admin 是单文件无构建脚手架，9 个测试文件都是手写的纯函数级测试。审计/财务页要长期演化，会越积越乱。`docs/admin-mvp-scope.md` 强调"MVP"——但 MVP 走过两个 sprint 仍是 MVP 的话该考虑投入框架（Preact/Vue 都行）。

**修复成本**：L（重构）。可延后，需要明确产品决策。

---

## 3. 代码质量评分（按模块）

| 模块 | 架构 | 可读性 | 测试 | 可观测性 | 安全 | 综合 |
|------|-----|--------|------|----------|------|------|
| backend / order 域 | 9 | 9 | 8 | 7 | 8 | **8.2** |
| backend / payment 域 | 9 | 9 | 8 | 7 | 7 | **8.0** |
| backend / provider 抽象 + outbound | 8 | 9 | 5（半开/httpx 漏） | 8 | 6（P0-1） | **7.2** |
| backend / WS + pubsub | 9 | 9 | 6（缺多副本真集成测试） | 7 | 7（旧 ?token=） | **7.6** |
| backend / scheduler + cron | 8 | 9 | 7 | 7 | 7（部分 cron 无锁） | **7.6** |
| backend / idempotency + dead_letter | 9 | 9 | 8 | 7 | 8 | **8.2** |
| backend / repositories | 8 | 8 | 8 | 6 | 8 | **7.6** |
| backend / models | 9 | 9 | n/a | n/a | 8 | **8.7** |
| wechat / services + store | 8 | 8 | 7 | 5（store 错误无上报） | 8 | **7.2** |
| wechat / pages（抽样） | 7 | 7 | 6 | 5 | 8 | **6.6** |
| ios / Networking | 7 | 8 | 5（refresh 并发缺测试） | 5 | 5（P0-2） | **6.0** |
| ios / Features ViewModel（抽样） | 8 | 8 | 6 | 4 | 8 | **6.8** |
| admin-h5 | 5（单文件） | 7 | 6（覆盖窄） | 5 | 8（CSP 强） | **6.2** |
| docs / ADR / DECISION_LOG | 9 | 9 | n/a | n/a | n/a | **9.0** |

> 维度定义：架构=分层/边界；可读性=命名/注释/复杂度；测试=单测覆盖+质量；可观测性=日志/metric/告警；安全=认证/授权/敏感数据/抗滥用。每项 1-10。

---

## 4. 测试盲区分析

后端 1217 case、wechat 54 文件、ios 17 文件——**数量充足但维度集中在"单元 + 同进程集成"**，以下盲区直接关联生产风险：

### 🔴 缺失 1：跨端真实 E2E
- 现有 `backend/tests/e2e/` 全是后端到后端，缺"小程序 → 后端 → wechat pay mock → 回调"链路真跑。
- 微信支付沙箱、SMS 阿里云 mock 环境（ADR-0030 已有 staging mock）都搭起来了，但 CI 里没有"端到端冒烟"job。
- **后果**：CSRF / cookie domain / CORS / Idempotency-Key 头传播这类只有跨进程才暴露的问题，现在靠人手测。
- **建议**：每个发布周一次自动跑"小程序 e2e（Jest + miniprogram-automator）+ 后端 staging"全链路；至少覆盖：下单→支付→陪诊师接单→完成→评价→退款这 6 步。

### 🔴 缺失 2：负载 / 压力 / Chaos 测试
- `find` 找不到任何 locust / k6 / wrk / 性能 baseline 数据。
- `outbound_call` 装饰器的熔断、`PG advisory lock` 在副本扩到 3-5 个时的实际表现、PostgreSQL 连接池在 200 RPS 下的耗尽时间，都没有数据。
- **后果**：上线第一天遇到的是"未知的未知"，不是"已知的已知"。
- **建议**：在 `infra/` 下添加 k6 脚本，目标"下单→支付→回调"链路 100 RPS / 5min P99 < 800ms；CI 跑一次冒烟（10 RPS / 30s）即可。

### 🟠 缺失 3：WS Pub/Sub 多副本真集成
- 当前 ws 测试都是单进程 / mock broker。`docker-compose` 没看到"两副本 + 共享 Redis"的测试 fixture。
- `WsPubSubBroker._listen_loop` 的 origin 去重、断线重连后旧消息丢失重补、Redis 短时宕机导致 listen_loop 退出等场景，需要真起两个进程才能测。
- **建议**：增加 `tests/integration/ws_two_replicas/` 用 pytest-xdist 起两个 uvicorn worker 通过同一个 Redis。

### 🟠 缺失 4：iOS UI 测试 + 网络层并发测试
- 17 个测试文件全部是 model decoding / endpoint 拼接 / formatter 等纯函数，**零 ViewModel 测试、零 XCUITest**。
- P0-2 的 refreshToken 并发 bug 之所以没被发现，就是因为没有一个 `actor` 并发调用测试。
- **建议**：至少补齐 OrderViewModel / AuthViewModel / ChatViewModel 三个核心 VM 的状态流转测试；APIClient 写 3 条：单 401 / 并发 5×401 / refresh 本身 401。

### 🟠 缺失 5：退款资金安全场景覆盖不足
- TD-PAY-01 的 happy path 有测试，但以下分支未看到专项 case：
  - `_append_refund_ledger_safe` 拺错但订单只走 warn log（财务上帐丢失）
  - `create_refund` 中 provider 抛 `BadRequestException` 与抛一般 `Exception` 两条路径的 dead_letter 可观察性
  - 多次退款请求同时抵达（UNIQUE (order_id, payment_type) 收招是对的，但需要一条并发测试 快照）
- **建议**：以资金安全为主题加一组 ~10 个 contract test，CI 独立 mark（`pytest -m money_safety`），必须通过才允许 deploy。

### 🟡 缺失 6：小程序覆盖率门禁
- `wechat/jest.config.js` 默认只跑测试，未配 coverage threshold，与 C-17 多言重复。
- **建议**：`coverageThreshold.global.branches: 60` 入门线，后续逐步括 75。

---

## 5. 重构 / 优化建议清单

> P0 = 上线前必修；P1 = 上线后两周内修；P2 = 可调度。
> 工作量 S ≤ 1d / M = 1-3d / L ≥ 3d。

| ID | 优先级 | 工作量 | 事项 | 负责 |
|----|--------|--------|------|-----|
| R-01 | **P0** | S+M | 修 `utils/outbound.py`：half-open 需要 N 次连续成功才返 closed；熜断打开后不进重试循环；whitelist 增加 `httpx.RequestError`/`httpx.TimeoutException` | Backend |
| R-02 | **P0** | S | iOS `APIClient.refreshTokenIfNeeded` 改为 `Task` 缓存 + `await task.value`；补 actor 并发测试 | iOS |
| R-03 | **P0** | S | `payment_callback.record_callback_or_skip` 对空 `transaction_id` 拒收 + Prometheus counter | Backend |
| R-04 | **P0** | M | 资金安全 contract test 集（点名在缺失 5），`pytest -m money_safety` 纳入 release gate | Backend + QA |
| R-05 | P1 | S | `OrderRepository.has_unpaid_orders` 增加 `Payment.status IN ('pending','success')` | Backend |
| R-06 | P1 | S | 所有 APScheduler job 统一走 `acquire_scheduler_lock` | Backend |
| R-07 | P1 | M | `tests/integration/ws_two_replicas/`：pytest-xdist + 共享 Redis，覆盖 origin去重 / listen_loop 重启 / Redis 闪断 | Backend |
| R-08 | P1 | M | k6 脚本 + CI 冷烟（下单 → 支付 → 回调，10 RPS / 30s）；发布前由 SRE 跑 100 RPS / 5min 压测 | Ops |
| R-09 | P1 | M | 小程序 e2e：mini-program-automator + staging 后端，上线前跑完 6 步主路径 | Frontend + QA |
| R-10 | P1 | S | iOS 补 OrderViewModel/AuthViewModel/ChatViewModel 状态测试，列入 CI | iOS |
| R-11 | P1 | S | `PaymentService._set_payment_state` / `_set_refund_state` 加 Prometheus counter 接告警 | Backend |
| R-12 | P1 | S | WS 旧 `?token=` 退场计划入杯：TECH_DEBT 立项 + CI 占比门禁 | Backend + Frontend |
| R-13 | P2 | S | 小程序 `wechat/jest.config.js` 加 `coverageThreshold.global.branches: 60` | Frontend |
| R-14 | P2 | S | `wechat/store/index.js` listener 错误加计数器 + wx 上报 | Frontend |
| R-15 | P2 | S | `Order` 模型增加 `snapshot_materialized_at`，文档明确“快照不回写”契约 | Backend + PM |
| R-16 | P2 | M | `OrderService` Mixin 依赖走轻量 DI 容器，为后续 admin/companion 独立 service 预留空间 | Backend |
| R-17 | P2 | L | admin-h5 重构到 Vue/Preact + Vite；需要 PM 决策 admin 是否长期发展 | Frontend + PM |
| R-18 | P2 | S | `docs/TECH_DEBT.md` 里的 `TD-MSG-02 / TD-MSG-03 / TD-MSG-06` 列入下一迷代 backlog，避免长期诡异 | PM + Tech Lead |

---

## 6. 一句话总结

医路安是个看得出“有人认真在做”的项目，架构分层、状态机、Provider 抽象、ADR 体系、幂等防护都是商业代码库的水准。但 outbound 装饰器的熜断逻辑 bug、iOS APIClient 的并发刷新 bug、以及“1357 测试但缺 E2E/压测/并发”的结构性缺口，足以让上线首日遇到不可预期的顽疾。
**先修 R-01 / R-02 / R-03 / R-04，再谈发布。**
