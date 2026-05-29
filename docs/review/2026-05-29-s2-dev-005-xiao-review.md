# 魈 — S2-DEV-005 AI 摘要骨架 Code Review

**结论**：✅ **通过 set done**。金钱链路 4 个 critical 点全 verified，工程取舍判断硬。

S2-DEV-005 是 Top1 唯一直接花钱的链路，胡桃这版 8 文件 1259 行 + 8 测试全绿，下面逐点说。

---

## ✅ 4 个 critical 点 verified

### 1. Reserve-first 而非 charge-after（消 TOCTOU）

`budget.check_and_reserve()`：Redis `INCRBYFLOAT` 预扣 → 超限 `INCRBYFLOAT(-x)` 回滚。

**对**——经典并发金钱安全模式。`charge-after-success` 在 N 并发都看到 `spent=49.95` 时各自决定花 ¥0.05，最终 spent=50+(N×0.05) 越线；reserve-first 把 race 收到 Redis 原子操作内。配套 `commit(delta=actual-reserved)` 让"truncate 实际花得少"时退差额，counter 始终是 ground truth。

`release(refund full reserved)` 在 LLM 失败时调用，防止失败请求白白吃日预算 —— 与 commit 对偶完整。

### 2. Fail-closed on Redis down

`budget.py:90-99`：`redis is None` 或 `incrbyfloat` 异常 → `BudgetExhausted(reason="redis_unavailable")` 拒绝继续。

**强同意**——金钱链路 fail-closed 是底线。Redis 宕了允许 LLM 自由跑 = ¥50 防线变假，灰度第一周一次 Redis 主从切换可能直接打爆日预算。胡桃宁可家属看模板也不让防线倒，**架构师视角加分**。

`reason="redis_unavailable"` 归并到 `daily_budget` metric label 而不另开 reason —— 监控面板少一条线，降级仍能溯源到 budget 类别，对 SRE 友好（与 PRD §F2 监控基线对齐）。

### 3. Per-order cap = 算 max_tokens 而非事后剪

`deepseek_client.estimate_max_completion_tokens_for_budget`：解方程 `(per_order_cap - prompt_cost) / out_price * 1000` → `max_tokens` 传给 DeepSeek API。

**完美**。事后剪的问题是"花了 ¥0.08 才发现要剪到 ¥0.05" → 已经超 cap。先算 max_tokens 让 DeepSeek 自己在 token 边界停 + `finish_reason="length"` 时入 DEGRADED+`per_order_truncated` reason，**钱根本没花出去**。

prompt 单独超 cap 时返 0 + 上层降级（`digester.py:84-98`）—— 边界处理对（不调用 API 不计费）。

### 4. post_check mtime 热更新

`BlocklistChecker._reload_if_changed`：每次 check 前 `os.stat` 比 `mtime_ns`，变化则原地重载。

**O(1) 开销 + 无 watcher 进程**判断准。再加上 **解析失败保留旧词典 + 不更新 mtime → 下一轮再试**（`post_check.py:137 注释`），fail-safe 写法到位 —— 运营改 yaml 写错语法不会让 post_check 整个塌成"什么都拦"或"什么都放"。

`stat → 读 → re-stat` 二次校验（line 100-111）防 mtime race（读到一半文件被改）—— 这是细节，胡桃想到了。

---

## 💭 4 处加分（ADR 没要求但主动做的）

1. **`AI_SUMMARY_GENERATED_TOTAL{status="failed"}` + dead_letter 写一行 + DB 标 FAILED**（digester docstring + 实现）—— 任何 unexpected error 都被收口，背景 job 不会"消失"，运维可查
2. **`@outbound_call` 装饰 deepseek `chat_completion`** —— 与 S2-DEV-007 CB 链路自动联动，DeepSeek API 故障走 retry + CB；`finish_reason="length"` 时返 `truncated=True` 不当失败
3. **DeepSeek API key 未配 → `NonRetryableError`**（`deepseek_client.py:93`）—— 不浪费 CB budget 重试 misconfig
4. **Decimal `quantize(0.0001)` + `ROUND_HALF_UP`** 全链路 —— 与 `AIDigest.cost_yuan Numeric(10,4)` 严丝合缝对齐，金钱字段精度无漂移

---

## 🟡 2 个 follow-up（不挡 done）

### 1. Decimal → float Redis 转换精度

`budget.py:91` `await redis.incrbyfloat(key, float(estimated_cost_yuan))` —— Redis `INCRBYFLOAT` 用 IEEE 754，¥0.05 累 1000 次有 ~1e-13 漂移。limit ¥50 长期累计偏差到 ~1e-10，**金融语义可忽略**。

**判断**：Redis 没有 INCRBYDECIMAL，float 包 Decimal 是工程最优解。**不修**。但建议在 budget.py 模块 docstring 末尾加一行 note："accumulator uses IEEE 754; drift bounded at ~1e-10 for typical workloads, accepted." —— 未来 SRE 看 spent=49.9999999998 不会惊慌。1 行注释。

### 2. order.completed → enqueue 触发链 + `@with_scheduler_lock` 绑死

胡桃显式标 TODO 归 S2-DEV-006，**判断对** —— 触发链路是 cron / scheduler 层关注点，本 task 专注 digester pipeline 取舍清晰。

**S2-DEV-006 实施时必收**（否则 PRD-001 §F4 「`@with_scheduler_lock` 首版即走」red line 不满足）。

---

## 💭 关于 DeepSeek 价格表

`settings.deepseek_price_input_per_1k_yuan=0.001 / output=0.002` 是公开报价。**通过 env override 不动代码**，运维拿到合同价直接改 env。本期不动。

但建议你在 `digester` log 一次启动时的 effective 价格（INFO 级），灰度 D+1 复评成本时可对账：
```python
logger.info("AI summary cost model: in=%s out=%s per_order_cap=%s daily_cap=%s",
            settings.deepseek_price_input_per_1k_yuan, ...)
```
1 行改，灰度运维加分。可放 S2-DEV-006 一起。

---

## ❌ 不采纳/反对

无。

---

## Set done 路径

直接 set done。两个 follow-up 都不挡。

**Follow-up 列表（不挡 done）**：
1. 💭 budget.py docstring 加 IEEE 754 漂移 note（1 行）
2. ⚠️ S2-DEV-006 必收：order.completed enqueue + `@with_scheduler_lock` 绑死 + 启动 log effective 价格

**今日 5/29 状态**：胡桃 8 task done + S2-DEV-005 + 1 micro，W20 D1+D2+D3 关键路径 87.5%（剩 S2-DEV-004 OpenAPI baseline + S2-DEV-006 cron 调度），**比 PRD 提前 1 天**。

**Review 完成时间**：2026-05-29 02:42 UTC
**Reviewer**：魈
