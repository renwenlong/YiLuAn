# 手动验收测试用例：陪诊师拒单 + 订单过期

> 覆盖：D-014（拒单机制）+ D-015（订单超时自动取消）的端到端验收。
> 执行环境：开发/预发；测试账号见 `docs/TEST_ACCOUNTS.md`（或 seed.sql）。
> 统一验证点：订单状态、支付/退款状态、通知是否下发、WebSocket 实时到达、日志无异常。

---

## A. 拒单

### A-1 陪诊师拒单成功（独家派单）

**前置条件**
- 患者 P1 创建订单 O1 → 已支付 → `status=created` → 派给陪诊师 C1（独家，非广播）。
- C1 登录 App；P1 处于订单详情页或已连接全局通知 WS。

**步骤**
1. C1 在「新订单」入口点击 O1 → 选择「拒接」→ 填写理由「时间冲突」→ 提交。
2. 等待 ≤3s。

**预期**
- C1 端：toast「已拒单」，O1 从待接列表消失。
- P1 端：
  - 全局通知 WS 实时到达一条 `order_status_changed`，标题含「陪诊师暂时无法为您服务」。
  - 订单详情页 onShow 刷新后 `status=rejected_by_companion`，状态副标题显示建议重新预约。
  - 支付状态变为 `refunded`（自动全额退款）。
- 后端日志：无 ERROR；`OrderService.reject` + `refund` 事件按顺序出现；PII 已脱敏。

**验证点**
- DB：`orders.status='rejected_by_companion'`、`payment_status='refunded'`；`refunds` 有新记录。
- `notifications` 表 P1 下新增 1 条 `order_status_changed`，`is_read=false`。

### A-2 拒单失败：非自己单

**前置条件**：O1 派给 C1；另一陪诊师 C2 通过接口构造请求（或测试工具）尝试拒 O1。

**步骤**：C2 调用 `POST /orders/{O1}/reject`。

**预期**：HTTP 403 或 404（按实现，当前为权限拒绝）；O1 状态不变；P1 不收通知。

### A-3 拒单失败：非 created 态

**前置条件**：O1 状态为 `accepted`（已被 C1 接过了）。

**步骤**：C1 再次调用 `POST /orders/{O1}/reject`。

**预期**：HTTP 409 或 400，body 含「当前状态不允许拒单」；无副作用。

### A-4 广播单拒单（多陪诊师可抢）

**前置条件**：O2 为广播单（未指定 companion_id），`status=created`。

**步骤**：C1 打开 O2 → 点击「拒绝」（或「不感兴趣」）。

**预期**（当前策略）：
- 广播单拒绝仅对 C1 自身隐藏（写入 `order_rejects` 日志或本地隐藏表）；其他陪诊师仍可接。
- O2 全局状态保持 `created`；P1 无通知（无状态变更）。
- 验证：`orders` 无变化；`notifications` 下 P1 无新记录。

### A-5 拒单后患者重下单

**前置条件**：A-1 完成后。

**步骤**：P1 点「重新预约」→ 依据 O1 的医院/服务类型复用 → 生成 O3。

**预期**：O3 可正常派单流转；O1 保持 `rejected_by_companion` 终态。

---

## B. 订单过期

### B-1 订单自动过期（APScheduler 触发）

**前置条件**
- 开发环境设置订单 `expires_at = now + 2min`（或通过 seed 插入即将过期订单 O4）。
- `SCHEDULER_ENABLED=true`；单副本或启用 PG advisory lock（D-018）。

**步骤**
1. 等待 ≤2min + 一个 scheduler tick（默认 60s）。
2. 观察 backend 日志 `scheduler.expire_orders` 任务输出。

**预期**
- O4 `status` 由 `created` → `expired`。
- `payment_status='refunded'`（若已支付），`refunds` 有记录；未支付则跳过退款。
- P1 收到 `order_expired` 通知（WS + DB）。
- 订单详情页副标题：「订单因超时未接单已自动取消，款项将原路退回」。

**验证点**
- DB：`orders.status='expired'`；`expires_at < NOW()`；`refunds.amount=orders.price`（若已支付）。
- 日志：`expired_orders_count=1`；无 ERROR。

### B-2 过期任务手动触发

**前置条件**：存在即将/已经到期但未被扫描的订单 O5。

**步骤**
1. 运行 `python -m app.scripts.expire_orders_once`（或测试钩子 `OrderService.expire_pending_orders()`）。
2. 观察输出。

**预期**
- 脚本输出处理数量；O5 立即过期；通知下发。
- 与 B-1 行为完全一致（手动 / 自动走同一 `OrderService.expire_pending_orders()` 实现）。

### B-3 过期已退款、不重复退

**前置条件**：O5 已过期并退款。

**步骤**：再次手动触发 `expire_pending_orders()`。

**预期**：O5 被过滤（`status != 'created'`），无新 refund；日志 `skipped_count+=1`。

### B-4 多副本分布式锁（可选回归）

**前置条件**：2 个后端副本同时运行；`SCHEDULER_ENABLED=true`。

**步骤**：观察 PG `pg_locks` + 日志。

**预期**
- 任一时刻只有一个副本持有 advisory lock `expire_orders_job`；另一个副本 tick 时取锁失败，日志打印 `scheduler.lock_busy, skip`。
- 无双重退款、无 DB 主键冲突。

**验证点（SQL）**
```sql
SELECT classid, objid, granted, pid FROM pg_locks WHERE locktype='advisory';
```

### B-5 过期后患者界面倒计时边界

**前置条件**：O6 `expires_at = now+30s`。

**步骤**：P1 打开 O6 详情页 → 观察倒计时。

**预期**
- 剩余 ≤ 30 分钟（本次任务 6）：倒计时数字转红（danger 样式）。
- 倒计时归零后页面自动 reload，状态刷新为 `expired`，副标题切换。

---

## C. 通用回归

- 通知数量：A-1、B-1 完成后 `notifications` 未读数 +1；打开消息页清零 + TabBar 角标同步。
- REST 兜底：关闭 WS（断网），重新打开应用 → `GET /notifications?unread_only=true` 仍能拉到上述通知。
- iOS（只读）：不验证交互，仅确认后端数据对 iOS 可消费（字段对齐 OpenAPI）。

## 执行产出

- 每条用例结果记录在 `docs/qa/2026-04-17-reject-expiry-run.md`（按需创建）。
- 若有失败，开 issue + 在 `TECH_DEBT.md` 追加条目。
