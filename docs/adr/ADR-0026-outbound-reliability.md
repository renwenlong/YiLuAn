# ADR-0026 外呼统一可靠性装饰器（timeout / retry / circuit breaker）

- 日期：2026-04-20
- 状态：Proposed
- 参与角色：Arch / Backend / QA

## 背景

医路安项目已通过 Provider 模式（D-023）完成外呼能力抽象：

- `services/payment/provider.py` — 支付外呼（mock / wechat）
- `services/sms/provider.py` — 短信外呼（mock / aliyun）

`PROVIDER_MODE=mock|real` 切换路径清晰（D-024），mock 模式在测试和开发环境中运行良好。

**问题**：当 `PROVIDER_MODE=real` 时，真实 Provider 直接裸调第三方 API，缺乏统一的可靠性策略：

1. 无超时控制 — 第三方接口慢响应可能拖垮整个请求链路
2. 无重试 — 偶发网络抖动直接返回失败，用户体验差
3. 无熔断 — 第三方宕机时持续调用，浪费资源并延长恢复时间
4. 无统一日志与指标 — 运营侧无法感知外呼健康度

D-025 Readiness 四件套已将"外呼可靠性策略不得为空壳"列为发布阻塞项，必须正式落定方案。

## 决策

### 统一入口

所有外呼调用必须通过 `backend/app/utils/outbound.py` 暴露的装饰器 `@outbound_call(...)` 包装。禁止在 Provider 实现中裸调第三方 API。

### 接口契约

```python
@outbound_call(
    provider="wechat_pay",       # provider 名称，用于日志和指标
    timeout=5.0,                 # 超时秒数，默认 5s，可按调用点覆盖
    max_retries=2,               # 最大重试次数，默认 2
    backoff_base=0.2,            # 退避基数秒，默认 200ms
    backoff_factor=4,            # 退避因子，默认 4（200ms → 800ms）
    circuit_threshold=5,         # 连续失败阈值，默认 5
    circuit_timeout=60,          # 熔断恢复时间秒，默认 60
)
async def create_prepay(self, order_id: str, amount: int) -> PrepayResult:
    ...
```

### 默认参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| timeout | 5s | 单次调用超时 |
| max_retries | 2 | 指数退避重试：200ms → 800ms |
| circuit_threshold | 5 | 连续失败 5 次触发熔断 |
| circuit_timeout | 60s | 熔断后 60 秒进入 half-open |

### 可重试 vs 不可重试错误

装饰器必须区分两类错误：

**应当重试**（RetryableError）：
- 网络超时（ConnectionTimeout / ReadTimeout）
- HTTP 5xx 服务端错误
- HTTP 429 限流

**不应重试**（NonRetryableError）：
- HTTP 4xx 客户端错误（签名失败、参数错误、余额不足等）
- 业务逻辑拒绝（如订单已支付）

遇到不可重试错误时，装饰器立即抛出，不消耗重试次数，也不计入熔断计数。

### 结构化日志

每次外呼完成（成功或失败）必须产出结构化日志，包含：

- `provider`: provider 名称
- `method`: 被装饰函数名
- `duration_ms`: 调用耗时（含重试）
- `retries`: 实际重试次数
- `circuit_state`: open / closed / half-open
- `outcome`: success / retry_exhausted / circuit_open / non_retryable

### Prometheus 指标

装饰器必须暴露以下指标：

| 指标名 | 类型 | 标签 |
|--------|------|------|
| `outbound_call_total` | Counter | provider, method, outcome |
| `outbound_call_duration_seconds` | Histogram | provider, method |
| `outbound_circuit_breaker_state` | Gauge | provider (0=closed, 1=open, 0.5=half-open) |

## 备选方案

### A. 不做统一装饰器，各 Provider 自行实现

- 优点：改动范围小
- 缺点：各 Provider 策略不一致，维护成本高，新增 Provider 容易遗漏
- **结论：否决**

### B. 直接暴露 tenacity / pybreaker 第三方库 API

- 优点：零开发成本
- 缺点：各调用点配置分散，日志和指标无法统一，库升级影响面大
- **结论：部分采纳** — 装饰器内部实现可复用 tenacity 和 pybreaker 的能力，但对外接口由我们自己定义，屏蔽第三方库细节

## 影响

### 正面

- 统一所有外呼可靠性策略，发布前消除空壳风险
- 运营侧通过 Prometheus 指标实时监控外呼健康度
- 新增 Provider 只需加装饰器即可获得完整可靠性保障
- 熔断机制保护系统在第三方宕机时快速失败

### 负面

- 所有现有 Provider 调用点都需包装装饰器，存在改造成本
- 测试需要 mock 时间和熔断状态，测试复杂度略增
- 引入 tenacity / pybreaker 依赖（如选择复用）

## 实施计划

| 步骤 | 内容 | 优先级 |
|------|------|--------|
| Step 1 | 实现 `backend/app/utils/outbound.py` + 6+ 单测 | A5 |
| Step 2 | 接入 `services/payment/provider.py` 和 `services/sms/provider.py` | A5 |
| Step 3 | 回归测试 459 → ≥465 全绿 | A5 |
| Step 4 | 补 Prometheus 指标文档到 `observability.md` | A7 |

## 关联决策

- D-023 — Provider 抽象模式
- D-024 — mock / real 切换机制
- D-025 — Readiness 四件套（发布阻塞项）
- D-027 — callback log TTL（待评估）
