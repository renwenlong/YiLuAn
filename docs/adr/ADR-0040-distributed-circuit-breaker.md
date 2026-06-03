# ADR-0040 — 分布式 Circuit Breaker（per-process → 跨进程协同）

> 状态：**Draft（D+1 起手版）** · 作者：魈 · 日期：2026-06-03
> 关联：ADR-0026r1（outbound reliability r1）/ ADR-0035 §3 / BACKLOG-DISTRIBUTED-CB
> 触发：本期帝君拍板 BACKLOG 5 条作废"触发条件未达不立项"门，本 ADR 起手设计

---

## 1. 背景

ADR-0026r1 已落地 per-process（单进程内 in-memory dict）异步 Circuit Breaker，含 N 连胜 HALF_OPEN 收敛 + idle reset + httpx 异常分类。

**当前架构假设硬伤**：
- `_circuit_breakers: dict[str, CircuitBreaker]` 是 process-local（`backend/app/utils/outbound.py:145`）
- 多副本部署下，N workers × M provider = N×M 个独立 CB 实例
- 同下游故障：每个 worker 各自累计 `threshold` 次失败才 OPEN —— 单 worker fail 不保护全局
- HALF_OPEN 探测：N workers 各自独立放行探测 —— **同一下游被 N 个并发探测打挂**（雪崩探测）
- 这是 BACKLOG-DISTRIBUTED-CB 的核心问题

---

## 2. 触发判定

| 项 | 触发条件 | 当前状态 |
|----|---------|---------|
| ADR-0026 acceptance "per-process CB 架构假设" | 单下游因 multi-worker 并发探测打挂 / 事故复盘点名 | ⚠️ 帝君 6/3 拍 BACKLOG 触发门作废，本周强推 |
| 业务驱动 | 灰度上线 → wxpay/DeepSeek 任一被探测击穿 | 未触发但理论存在 |

**ADR 设计原则**：当前以 **N=2 workers** 起步评估（gunicorn `-w 2`），后续若 N≥4 风险翻倍。

---

## 3. 方案对比

### 方案 A：Redis 协调锁 + 本地 CB（最小侵入）

```
local CB state（仍 in-memory）+ Redis SETNX 锁控制 HALF_OPEN 探测窗口
```

- 每 worker 仍维护本地 CB state
- HALF_OPEN 转换前 `SET cb:{provider}:probe_lock <worker_id> NX EX 5`，只有抢到锁的 worker 真探测，其他 worker 沿 HALF_OPEN 但不放流量
- 失败计数仍本地，但通过 `cb:{provider}:failure_pubsub` channel 广播让其他 worker 同步增加
- ✅ 改造小（~150 行代码）
- ✅ Redis 已是必备依赖
- ✅ 故障时仍可降级回纯本地 CB（Redis 挂了不影响业务）
- ⚠️ failure_count 仍是 eventual consistency，可能某 worker 短期算少了
- ⚠️ probe_lock TTL 调参敏感（探测请求超时 vs 锁释放）

### 方案 B：Redis 中心化 CB 状态机（强一致）

```
state / failure_count / opened_at 全在 Redis Hash，所有 worker 走原子 Lua
```

- CB 三态全在 Redis（`HSET cb:{provider} state failure_count opened_at half_open_success_count last_activity`）
- 每次 record_success/failure 走 Lua 脚本原子更新
- allow_request 也走 Lua
- ✅ 强一致，无歧义
- ❌ 每次 outbound call 多 1 次 Redis RTT（关键路径加 1-2ms）
- ❌ Redis 故障 = CB 不可用（需降级策略）
- ❌ Lua 脚本 ~80 行，复杂度高

### 方案 C：Resilience4j 风格 sliding window + Redis Sorted Set

- 用 Redis Sorted Set 记录每次 outcome（成功/失败 + ts）
- 滑动窗口内失败率 ≥ 50% 触发 OPEN
- ✅ 模型最准确，业界成熟
- ❌ 实施量最大（~400 行 + 大量测试）
- ❌ Sorted Set 性能开销 + GC 压力
- ❌ 本周交付周期不现实

---

## 4. 推荐方案：**A（Redis 协调锁 + 本地 CB）**

理由：
1. **本周可交付**：~150 行实现 + ~100 行测试，1.5 工作日
2. **解决核心问题**：probe_lock 杜绝雪崩探测（最危险的失效模式）
3. **降级路径完备**：Redis 挂回退本地 CB，不引入新单点
4. **改造最小**：CircuitBreaker 类签名不变，只在状态转换钩子插入 Redis 协调
5. **资金线安全**：Lua 脚本失败可观测 + 降级，不会引入新的 money_safety 风险

### 4.1 实施要点

```python
class DistributedCircuitBreaker(CircuitBreaker):
    """ADR-0040 — Redis-coordinated CB, falls back to local on Redis fail."""

    def __init__(self, provider, ..., redis_client=None):
        super().__init__(...)
        self.redis = redis_client
        self.probe_lock_key = f"cb:{provider}:probe_lock"
        self.failure_pubsub_channel = f"cb:{provider}:events"

    async def allow_request_distributed(self) -> bool:
        # OPEN → HALF_OPEN 转换前抢探测锁
        if self.state == self.OPEN and self._open_timeout_elapsed():
            if not await self._acquire_probe_lock():
                return False  # 其他 worker 在探测，本 worker 仍拒
            self.state = self.HALF_OPEN
            return True
        return self.allow_request()  # 复用本地逻辑

    async def _acquire_probe_lock(self) -> bool:
        if not self.redis:
            return True  # Redis 不可用 → 降级本地
        try:
            return await self.redis.set(
                self.probe_lock_key, WORKER_ID,
                nx=True, ex=PROBE_LOCK_TTL_SECONDS
            )
        except RedisError:
            return True  # Redis 故障 → 降级本地
```

### 4.2 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PROBE_LOCK_TTL_SECONDS` | 5 | 探测锁 TTL，应略大于 outbound timeout |
| `FAILURE_BROADCAST_BATCH` | 1 | 每 N 次本地 failure 广播一次，0 = 不广播 |
| `PROBE_LOCK_RETRY_INTERVAL` | 1.0s | 未抢到锁的 worker 复检间隔（沿 OPEN） |

### 4.3 测试覆盖

- 2 worker 同时进 OPEN_TIMEOUT_ELAPSED → 只 1 个抢到 probe lock，另 1 个拒
- probe_lock 持有 worker 探测成功 → 释放锁 → 其他 worker 下一周期复检看到 CLOSED
- probe_lock 持有 worker crash / 锁 TTL 到期 → 其他 worker 抢锁重试
- Redis 不可用 → 降级到本地 CB 行为不变
- failure_pubsub 异步广播延迟 → eventually consistent，最终一致

---

## 5. 验收标准（INT-005 同期交付）

- [ ] `backend/app/utils/distributed_circuit_breaker.py` 新增（继承 CircuitBreaker）
- [ ] `@outbound_call(distributed=True)` 参数开关，向后兼容
- [ ] wxpay / DeepSeek / aliyun_sms 切到 distributed=True
- [ ] 单测：5 类场景全绿（见 §4.3）
- [ ] 集成测试：2 worker docker-compose 起 staging，触发 OPEN → 验证只 1 worker 探测
- [ ] Prometheus metric：`outbound_circuit_probe_lock_acquired_total{provider}` + `outbound_circuit_probe_lock_rejected_total{provider}`
- [ ] 文档：本 ADR Accepted + 在 ADR-0026r1 末尾加 Supersedes-by 链接

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| probe_lock TTL 设置不当导致下游真被探测击穿 | 中 | 高 | TTL 默认 5s，可按 provider 调；监控 probe_lock_held_seconds histogram |
| Redis 故障时回退本地 CB → 雪崩探测复发 | 低 | 中 | Redis SLA 99.9%，且故障窗口短；可叠加全局熔断器（独立 trigger） |
| failure_pubsub 延迟导致某 worker 滞后 OPEN | 中 | 低 | eventually consistent 可接受；最坏单 worker 多撑几个失败请求 |
| 本周交付质量打折扣 | 高 | 高 | 已与帝君书面留痕：money_safety + share_security 双 gate 强制不绿不合 |

---

## 7. 后续

- 本 ADR Draft 提交 review（程序员+测试员，按 design type workflow）
- Owner 批准后拆 develop task 分胡桃实施（约 1.5 工作日）
- 实施完成后 ADR 状态 Draft → Accepted
- 灰度观察 1 个月后评估是否升级到方案 C（Resilience4j 风格）

---

## 8. 决定

**Accept 方案 A**（帝君 2026-06-03 拍 BACKLOG 触发门作废 + 全力冲刺，默认推荐方案执行）。

实施 owner：胡桃（developer）/ reviewer：魈（architect）/ Owner Approval：帝君（设计 type 完成 review 后批准）。本周 D+5 交付目标不变；超期立即抛群，不私下延期。
