# ADR-0029: 已支付订单的过期处理策略 (TD-PAY-01)

- **状态**：Accepted
- **日期**：2026-04-25
- **决策上下文**：TD-PAY-01

## 背景

调度器 `OrderService.check_expired_orders` 把超过 `expires_at` 的订单标 `expired`。但 `Payment` 行的清理一直缺位：

- `pay.status == "pending"` 时，订单 expire 后 PSP 仍可能把这笔 prepay 兑成 success（用户掐点付款），出现"订单 expired 但 PSP 已收款"的悬空。
- `pay.status == "success"` 时，调度器若把订单标 expired，相当于平台单方面判定患者爽约——但**钱已经收了**，没有自动退款，对用户不公平；若同时触发自动退款，又会破坏现有"用户/运维主导退款"的契约。

## 决策

### 1. `pending` 支付：尽力关单 + 强制 fail

- 调度器对 `pay.status == "pending"` 调 `PaymentService.close_pending_payment(order_id)` 在 PSP 侧关单。
- 关单成功 → 把本地 `pay` 行 status 从 `closed`/`pending` 收紧为 `failed`，并在 `callback_raw` 追加 `[order_expired]` 留痕。
- 关单失败（PSP 拒绝，用户已支付）→ 仍把本地 pay 行强制标 `failed`，追加 `[order_expired:close_failed]`；订单仍走 expired 流程。
- 之后到达的 SUCCESS 回调由 `PaymentService.handle_pay_callback` 的防御退款分支兜底（pay 行已是 terminal `failed`，回调走 refund 路径）。

### 2. `success` 支付（已付款）：**抛 `NotExpirableOrderError`，整批 expire 中止**

- 调度器遇到 `pay.status == "success"` 的 expired 订单时，立刻 `raise NotExpirableOrderError(订单 X 已支付成功，无法过期)`。
- 全局异常处理把它转为 HTTP **409 Conflict**，运维感知到 → 走人工/用户主导的 cancel/refund 流程。
- **不**自动 refund，**不**把订单状态从 `created` 翻到 `expired`，订单留在 `created` 由 ops/患者决策。

### 3. 拒绝的备选

- ❌ **paid → 自动退款 + expire**：违反 `tests/test_refund_e2e.py::test_expired_order_refund_to_wallet` 现有契约（用户主导退款），会让平台代替用户做财务决策。
- ❌ **paid → 静默 skip continue**：endpoint 不返 409，运维侧无法感知"有订单卡在 paid+expired 之间"，会沉默累积。

## 后果

- **优点**：保留了"已付款 = 用户已表明承诺，平台不擅自处置"的边界；pending 路径补齐了对账窗口；late SUCCESS 回调有兜底。
- **缺点**：endpoint 遇到 paid + expired 订单整批 abort（非幂等），需要运维手动介入；建议未来加 `--skip-paid` 参数让调度器跳过这类订单只处理其余的。

## 触发的代码改动

- `app/services/order.py::check_expired_orders`：加 `existing_pay.status == "success"` 分支 raise；`pending` 分支新增 close + fail + 留痕逻辑。
- `app/services/payment_service.py::handle_pay_callback`：late SUCCESS 防御分支（订单已 expired 时不复活 pay，走 refund）。
- `tests/test_payment_expire_interlock.py`、`tests/services/test_order.py::TestCheckExpiredOrders`：覆盖 pending fail / paid raise / late callback 防御。

## 后续

- TD-PAY-01 在 `docs/TECH_DEBT.md` 移入"已解决"段。
- 与微信支付真支付通道上线（B-01）联动验证 close_order + refund 实际行为。
