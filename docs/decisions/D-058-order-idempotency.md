# D-058: 订单 / 支付链路幂等性 Audit + 加固

- **状态**：Accepted
- **日期**：2026-05-25
- **决策上下文**：feat/order-idempotency-audit（PR feat(backend): order idempotency hardening — D-058）
- **决策者**：后端工程师（subagent，受文龙委托）

## 背景

下单 → 支付发起 → 支付回调三条链路，任一节点重复请求都可能造成
脏数据（重复订单、重复 PSP prepay、重复回调误改状态）。本次任务先 audit
出三条链路当前的幂等机制，再按 audit 结果补齐缺口。

## Audit：当前各链路的幂等机制

### 1) 下单 `POST /api/v1/orders`

入口：`app/api/v1/orders.py::create_order` → `OrderService.create_order`
（`app/services/order/lifecycle.py`）。

当前防重机制：

- ✅ 业务层 `OrderRepository.has_unpaid_orders(user.id)` 拦截「同一用户存在
  `pending_payment` 订单」时再次下单，抛 `ORDER_HAS_UNPAID`。
- ❌ **没有真正的客户端 idempotency key**。客户端网络抖动 / 用户多次点击 →
  在前序订单还未落库的窗口内，仍可能创建出两条 `created` 订单（间隔毫秒级，
  `has_unpaid_orders` 看不到尚未 commit 的兄弟事务）。
- ❌ HTTP 层无 `Idempotency-Key` 支持。

**风险评估**：中。重复下单虽然不会重复扣款（支付发起需用户主动二次操作），
但会污染陪诊师抢单大厅，运营侧需要手动清理。

### 2) 支付发起 `POST /api/v1/orders/{order_id}/pay`

入口：`OrderService.pay_order` → `PaymentService.create_prepay`
（`app/services/payment_service.py`）。

当前防重机制：

- ✅ `existing = repo.get_by_order_and_type(order_id, "pay")`
  - `existing.status == "success"` → 抛 `订单已支付，请勿重复操作`（400）。
- ⚠️ `existing.status == "pending"` 分支：仍会**重新调一次** `provider.create_prepay`，
  然后用新 trade_no / prepay_id 覆盖原行。这在 WeChat 侧虽然按 `out_trade_no`
  幂等（同一笔会返回同一 `prepay_id`），但白白多打一次 HTTP，且 `sign_params`
  每次都重新计算 → 客户端拿到的签名串不稳定，App 端缓存会失效。
- ❌ 没有"返回首次结果"的快路径。

**风险评估**：低-中。线上不会重复扣款，但 PSP 调用次数被放大、客户端体验差。

### 3) 支付回调 `POST /api/v1/payments/wechat/callback`（含 refund-callback）

入口：`app/api/v1/payment_callback.py`。

当前防重机制：

- ✅ `PaymentService.record_callback_or_skip`：以
  `payment_callback_log (provider, transaction_id)` 唯一约束去重，
  通过 `SAVEPOINT + IntegrityError` 捕获重复投递并直接返回
  `{"code":"SUCCESS"}`。
- ✅ `handle_pay_callback` 内部还有第二道防御：若 `payment.status in
  ("success", "failed")` 直接 short-circuit，不再改状态。
- ✅ `handle_refund_callback` 同样的 terminal 短路防御。
- ✅ TD-PAY-01 late-callback 防御：terminal 订单上的 SUCCESS 回调会触发
  自动退款（不复活订单）。

**风险评估**：低。三层防御（log 唯一约束 + payment terminal 短路 + late-callback
自动退款），覆盖比较完备。本次主要补一个端到端「重复 POST 回调」用例
保证回归。

## 决策（修复方案）

### F1 — 下单：`Idempotency-Key` Header

- 客户端可在 `POST /api/v1/orders` 上携带 `Idempotency-Key: <uuid>` Header。
- 后端用一张新表 `idempotency_keys` 存
  `(user_id, endpoint, key) → (response_status, response_body, created_at)`。
- 首次请求：照常处理，事务成功后写入 idempotency 行（**同一事务**，确保订单与
  idempotency 行原子）。
- 重复请求（同 `user_id + endpoint + key`）：直接回放上次的 `response_status` +
  `response_body`，**不再触发任何下单副作用**。
- key 缺失时 → 走原有流程（向后兼容）。
- TTL 24h，定时任务（独立 task，后续补）回收。

Schema：

```
idempotency_keys
  id              UUID PK
  user_id         UUID NOT NULL
  endpoint        VARCHAR(64) NOT NULL  -- 'POST /api/v1/orders' 等
  key             VARCHAR(128) NOT NULL
  response_status INTEGER NOT NULL
  response_body   TEXT NOT NULL          -- JSON
  created_at      TIMESTAMPTZ NOT NULL
  expires_at      TIMESTAMPTZ NOT NULL
  UNIQUE (user_id, endpoint, key)
```

迁移 PG 兼容（用 `op.create_table` + `sa.Column`，无方言特化语法）。

### F2 — 支付发起：pending 返回首次签名

- `PaymentService.create_prepay`：
  - `existing.status == "success"` → 维持 400（防误付）。
  - `existing.status == "pending"` 且已缓存 `sign_params_cache` → 直接返回
    `PrepayResult(payment_id=existing.id, prepay_id=existing.prepay_id,
    sign_params=existing.sign_params_cache, ...)`，**不调 provider**。
  - 首次/缓存缺失 → 走原路径，并把 `result["sign_params"]` 持久化到新列
    `payments.sign_params_cache (TEXT, JSON-encoded)`。

迁移：在 `payments` 上 `ADD COLUMN sign_params_cache TEXT NULL`（PG/SQLite 双兼容）。

### F3 — 回调：补一个端到端重复回调用例

回调机制本身已经达标，本次仅在
`tests/test_d058_idempotency.py` 加一个直观的「同一 transaction_id 调两次
endpoint，第二次不改 Payment.status，且 `payment_callback_log` 只有一行」
的端到端用例（覆盖 endpoint 层而非 service 层）。

## 拒绝的备选

- ❌ **以 `(user_id, hospital_id, appointment_date, appointment_time)` 做下单
  natural key 去重**：业务上允许同患者同医院同日多笔订单（陪两个家人），
  会误杀合理订单。
- ❌ **直接让重复 `pay_order` 返回 200 + cached params 而不是 400 (success
  分支)**：会让 UI 误以为重新支付仍待支付，反而引导用户重复掏钱。保留 400
  的"已支付"语义更安全。
- ❌ **把 sign_params 重算放在 provider 层**：会污染 provider 抽象（每个
  provider 都得实现 cache），不如在 service 层一处搞定。

## 验证

- 三条链路各至少 1 个"重复请求"单测（见 PR）。
- `pytest -q` 全绿；CI 全绿。
- alembic upgrade/downgrade 在 PostgreSQL 上对称（本地 yiluan_smoke 库已验过）。

## 后续

- idempotency_keys 的 TTL 清理任务（独立 cron / TD 项，本次 PR 不带）。
- 同样的 Idempotency-Key 中间件可推广到 `/pay`、`/refund`、`/cancel` 等高危
  写接口（先观察下单链路稳定性再推广）。
