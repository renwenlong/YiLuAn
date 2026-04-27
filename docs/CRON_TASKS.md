# Cron Tasks Registry

后端调度器（APScheduler，UTC）注册的定时任务清单。生产入口见
`backend/app/tasks/scheduler.py::create_scheduler`。

## 已注册任务

| Job ID | 触发 | 入口 | 说明 |
| --- | --- | --- | --- |
| `scan_expired_orders` | 每 60s | `app.tasks.scheduler.scan_expired_orders_job` | 扫描 `created` 状态订单到期则置 `expired` + 联动支付收尾（ADR-0029）。 |
| `cleanup_payment_callback_log` | 每日 03:30 UTC | `app.tasks.log_retention.cleanup_payment_callback_log` | D-027：按 `expires_at` 硬删过期支付回调日志。 |
| `cleanup_sms_send_log` | 每日 03:30 UTC | `app.tasks.log_retention.cleanup_sms_send_log` | D-033：SMS 发送日志保留期清理。 |
| `cleanup_emergency_pii` | 每日 03:00 UTC | `app.cron.cleanup_emergency_pii.cleanup_emergency_pii` | **ADR-0029 / D-043**：硬删 `emergency_contacts.expires_at < now`（90d grace）+ `emergency_events.triggered_at < now-180d`，写 `AdminAuditLog(action="cron_cleanup_emergency_pii")`。 |

## 测试

每个 job 入口都应可注入 `session` + `now_fn` 以支持 fake clock 单测。
对应回归用例：

- `tests/test_scheduler.py::test_create_scheduler_registers_expired_order_job`
- `tests/test_cron_cleanup_emergency_pii.py`
- `tests/test_log_retention*.py`
