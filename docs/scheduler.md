# APScheduler 部署与运维指南

> 适用版本：YiLuAn backend ≥ 0.1.0（D-018 起引入）。
> 本文档解释 APScheduler 定时任务的启停开关、多副本并发控制、以及故障排查。

## 1. 当前调度任务清单

| 任务 ID | 调度方式 | 周期 | 说明 |
|---|---|---|---|
| `expire_orders_job` | interval | 60s | 扫描 `status=created` 且 `expires_at < NOW()` 的订单，置为 `expired` 并自动退款（如已支付）。同步下发通知。 |

任务实现：`backend/app/scheduler.py` → `OrderService.expire_pending_orders()`。

## 2. 开关与配置

- 环境变量 `SCHEDULER_ENABLED`（默认 `true`）控制调度器是否启动。
- 生产默认开启；本地/测试/CLI 场景通常关闭，避免污染数据。
- 代码位置：`backend/app/config.py::Settings.scheduler_enabled`。

典型部署配置：

```bash
# 生产（ACA / K8s Deployment）
SCHEDULER_ENABLED=true
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...

# 本地 / CI
SCHEDULER_ENABLED=false
```

## 3. 多副本并发与分布式锁（D-018）

### 背景
APScheduler 默认是进程内调度。在 K8s Deployment / ACA 多副本场景下，每个副本都会独立触发同一任务 → 重复处理（重复退款、重复通知）。

### 方案
使用 **PostgreSQL advisory lock** 做互斥：

- 任务函数内先取 `pg_try_advisory_lock(classid, objid)`（非阻塞）
- 成功（`granted=true`）→ 执行真实业务
- 失败 → 记录 `scheduler.lock_busy, skip`，本 tick 退出

此方案零外部依赖（和 DB 同生命周期），无需 Redis / zookeeper / consul。

### 关键代码
`backend/app/scheduler.py` 内部使用 context manager：

```python
async with pg_advisory_lock(session, key="expire_orders_job") as acquired:
    if not acquired:
        logger.info("scheduler.lock_busy, skip")
        return
    await OrderService(session).expire_pending_orders()
```

锁标识（classid, objid）映射：任务名经过 `hash()` → 2 个 int32。

## 4. 部署注意事项

### 4.1 ACA (Azure Container Apps)
- 多副本情况下：每个 pod 都运行调度器，依赖 advisory lock 互斥。
- 扩容 min=1 / max=N 皆可；锁保证同一时刻最多一个副本执行任务。
- 冷启动副本启动瞬间会尝试取锁，正常失败 skip；下一 tick 竞争。

### 4.2 K8s Deployment
- 与 ACA 类似；Deployment replicas>1 时锁机制同样生效。
- 不要用 StatefulSet「仅 index=0 启用调度器」这种 hack —— advisory lock 已经给出了 cleaner solution。
- HPA / VPA 不影响（任务短、幂等，被中断可下一 tick 重跑）。

### 4.3 单副本场景
- 锁依然会走一遍 try_acquire → release，成本可忽略（本地 PG 调用）。

### 4.4 时区
- APScheduler 按机器/容器时区跑；容器镜像应固定 `TZ=Asia/Shanghai`（或 UTC）。
- `OrderService.expire_pending_orders` 使用 `datetime.utcnow()` 比较 `expires_at`，与时区无关。

## 5. 故障排查

### 5.1 观察锁持有情况

```sql
-- 查看当前所有 advisory lock
SELECT classid, objid, granted, pid,
       (SELECT query FROM pg_stat_activity WHERE pid = pg_locks.pid) AS query
FROM pg_locks
WHERE locktype = 'advisory';
```

预期：正常情况下稳态 **0 条**（锁是在 tick 内短暂持有，tick 结束即释放）；tick 中捕获则可能看到 1 条。

### 5.2 调度器未运行
症状：过期订单堆积、日志无 `expire_orders_job` 输出。

排查：
1. `SCHEDULER_ENABLED` 是否为 `true`。
2. 启动日志是否出现 `scheduler.started` / `scheduler.job_added`。
3. 检查 `lifespan` 是否正常（APScheduler 挂在 `app.state.scheduler`）。

### 5.3 重复处理 / 重复退款
症状：同一订单被标记 expired 两次、或者 refund 记录 2 条。

排查：
1. advisory lock 是否实际生效 —— 跑 `pg_locks` 查询在 tick 瞬间观察。
2. 日志搜索 `scheduler.lock_busy`：多副本应偶现「某副本 skip」。若从未出现 skip，说明锁配置错了。
3. `OrderService.expire_pending_orders` 内部 SQL 应使用 `WHERE status='created'`（幂等前提）——重复调用不会产生重复 refund。

### 5.4 tick 卡住 / 执行超时
- APScheduler 默认 `max_instances=1`（任务自身互斥），过期任务若执行 >60s 会告警。
- 默认单 tick 处理批次要分页，避免一次性扫百万条。当前实现使用 `limit=500`。

## 6. 未来扩展：新增定时任务的模板

```python
# backend/app/scheduler.py

from app.scheduler_lock import pg_advisory_lock

async def my_new_job():
    async with async_session() as session:
        async with pg_advisory_lock(session, key="my_new_job") as acquired:
            if not acquired:
                logger.info("scheduler.my_new_job.lock_busy, skip")
                return
            # 业务逻辑
            await MyService(session).do_work()

def create_scheduler(app):
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(expire_orders_job, "interval", seconds=60, id="expire_orders_job")
    scheduler.add_job(my_new_job, "interval", minutes=10, id="my_new_job")  # ← 新任务
    return scheduler
```

**规则**：
1. 每个新任务必须用唯一的 `key=` 申请 advisory lock。
2. 业务函数自身应具备幂等性（即使锁失效也不至于毁坏数据）。
3. 周期越短，越要关注锁释放成本（<1s 周期不建议用 advisory lock，改用单副本 StatefulSet / CronJob）。
4. 新任务加入本文档 §1 表格。

## 7. 相关决策

- **D-018**：APScheduler + advisory lock 方案选型。
- **D-019**：WebSocket Pub/Sub 多副本方案（与本调度器正交，但同为多副本场景的基础设施）。
- **D-019 Update**：聊天通道迁移到 Pub/Sub；调度器与 WS 架构独立运行。
