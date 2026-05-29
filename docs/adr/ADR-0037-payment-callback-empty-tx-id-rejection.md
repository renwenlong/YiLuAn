# ADR-0037: W19 P0-06 — `record_callback_or_skip` 空 transaction_id 拒收

- **状态**：Accepted（2026-05-28，魈）
- **范围**：W19 生产安全五件套之一，S 体量直接实施
- **关联**：ADR-0035 §3 P0-C（已 verified）；TD-PAY-01

---

## 1. 问题

`backend/app/services/payment_service.py::record_callback_or_skip` 使用 `(provider, transaction_id)` 作为幂等键，靠 `UNIQUE(provider, transaction_id)` 约束去重。

**当 `transaction_id` 为 `None` 或空字符串时**：
- PG 的 UNIQUE 约束对 NULL 不去重（每个 NULL 视为不同值）
- 空字符串虽然能去重但语义错误（多条不同回调被 collapse 成同一条）

**触发场景**：上游 PSP 异常 / 测试桩 / 攻击者构造畸形回调，可让同笔订单被多次入账或多次退款。

## 2. 修订决策

### 2.1 服务层拒收

```python
async def record_callback_or_skip(
    self, provider: str, transaction_id: str | None, ...
) -> bool:
    if not transaction_id or not transaction_id.strip():
        logger.warning(
            "payment_callback_invalid_tx_id",
            extra={"provider": provider, "raw_tx_id": repr(transaction_id)},
        )
        payment_callback_invalid_total.labels(provider=provider).inc()
        # 显式 raise NonRetryableError，不写库、不回放业务事务
        raise NonRetryableError(
            f"empty transaction_id from {provider} callback"
        )
    # 后续原有逻辑不变（SAVEPOINT + UNIQUE 去重）
    ...
```

### 2.2 API 层兜底（防御性）

`backend/app/api/v1/payment_callback.py`（或对应路由）在 dispatch 前校验：
- 解出 transaction_id 为空 → 直接 4xx + log + metric
- 不进入 service 层（少一次事务开销 + 更清晰的攻击面）

### 2.3 Prometheus metric

新增 `payment_callback_invalid_total{provider, reason="empty_tx_id"}` counter，对接已有的 outbound metric 命名规范。

### 2.4 DB 约束加固（次要）

Alembic 迁移加 CHECK 约束（可选）：

```sql
ALTER TABLE payment_callback_logs
ADD CONSTRAINT ck_transaction_id_nonempty
CHECK (transaction_id IS NOT NULL AND length(trim(transaction_id)) > 0);
```

**注意**：若历史数据已存在空 tx_id 行，迁移会失败 → 先 cleanup 再加约束；或加 `NOT VALID` 仅约束新数据。胡桃实施时先 `SELECT count(*) WHERE transaction_id IS NULL OR transaction_id = ''` 确认历史状况。

## 3. Acceptance（直接给胡桃实施 task）

1. ✅ 空字符串 / None / 全空白 transaction_id → service 层 raise `NonRetryableError`
2. ✅ API 层兜底：空 tx_id 回调直接 400
3. ✅ `payment_callback_invalid_total` metric 上报
4. ✅ 单测覆盖：①空字符串 ②None ③只含空白 "   " ④正常 tx_id 不受影响
5. ✅ 现有 wxpay 回调路径回归（mock + 真实 fixture）通过
6. ✅ Alembic CHECK 约束按数据现状决定加 / 不加（说明在 PR description）

## 4. 实施提示

- 体量：~30 行代码 + ~50 行单测，1-2 小时
- 与 P0-04 (outbound 修复) 同 PR 还是分开：**分开**，互无依赖、review focus 清晰
- 不需要新 ADR，本 ADR 即实施手册
