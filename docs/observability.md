# 医路安可观测性规范（Observability Spec）

> 版本：v1.0 | 创建日期：2026-04-20 | 状态：草案

---

## 1. 概述

医路安生产环境可观测性基于**三大支柱**构建：

| 支柱 | 目标 | 工具栈 |
|------|------|--------|
| **Metrics** | 实时监控系统与业务健康度 | Prometheus + Grafana |
| **Logs** | 结构化日志，支撑故障排查与审计 | structlog (JSON) + 阿里云 SLS |
| **Traces** | 请求级链路追踪（P2 预留） | OpenTelemetry SDK |

**核心原则：**

- 关键告警 5 分钟内触达值班人员
- 日志默认结构化 JSON，禁止纯文本打印
- 指标命名遵循 Prometheus 命名规范（`snake_case`，带 `_total` / `_seconds` 后缀）

---

## 2. Metrics（Prometheus）

### 2.1 已实现指标（ADR-0026 outbound 装饰器）

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `outbound_call_total` | Counter | `provider`, `method`, `outcome` | 外呼调用计数，outcome = success / failure / timeout |
| `outbound_call_duration_seconds` | Histogram | `provider`, `method` | 外呼调用耗时分布 |
| `outbound_circuit_breaker_state` | Gauge | `provider` | 熔断器状态：0=closed, 1=half_open, 2=open |

### 2.2 建议补充的业务指标（TODO）

| 指标名 | 类型 | Labels | 说明 |
|--------|------|--------|------|
| `order_created_total` | Counter | `service_type` | 订单创建量 |
| `order_paid_total` | Counter | `service_type` | 订单支付量 |
| `order_completed_total` | Counter | `service_type` | 订单完成量 |
| `payment_callback_failure_rate` | Gauge | — | 支付回调失败率（滑动窗口 5min） |
| `sms_send_failure_rate` | Gauge | `provider` | 短信发送失败率 |
| `websocket_connections_active` | Gauge | — | 当前活跃 WebSocket 连接数 |

### 2.3 Grafana Dashboard 规划

**Dashboard 1：系统总览**

- API QPS / 错误率（按 endpoint）
- P50 / P95 / P99 响应延迟
- 活跃 WebSocket 连接数
- 订单漏斗（创建 → 支付 → 完成）
- PostgreSQL 连接池使用率
- Redis 命中率 / 内存使用

**Dashboard 2：外呼健康**

- 各 provider 调用成功率趋势
- 各 provider P95 延迟趋势
- 熔断器状态时间线
- 超时 / 重试次数分布
- 失败调用 Top 5 provider × method

---

## 3. Logs（结构化）

### 3.1 技术栈

- 框架：Python `logging` + `structlog`
- 输出格式：JSON（生产） / Console colored（开发）
- 聚合：阿里云 SLS（生产） / 本地文件 `logs/app.log`（开发）

### 3.2 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 UTC | 日志产生时间 |
| `level` | string | DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `logger` | string | 模块名（如 `app.services.order`） |
| `trace_id` | string | 请求级追踪 ID（从 X-Request-ID 或 OTel 获取） |
| `span_id` | string | 跨度 ID（OTel 启用后生效） |
| `user_id` | UUID | 当前请求用户（认证后） |
| `order_id` | UUID | 业务相关时附加 |

### 3.3 日志级别规范

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| **DEBUG** | 开发调试，生产关闭 | SQL 查询、变量值 |
| **INFO** | 关键业务状态变更 | 订单创建、支付成功、用户登录 |
| **WARNING** | 可恢复的异常情况 | 重试成功、缓存未命中、令牌即将过期 |
| **ERROR** | 需关注/告警的错误 | 外呼失败、支付回调异常、数据库连接超时 |
| **CRITICAL** | 影响核心交易链路 | 数据库不可用、Redis 全部断连、熔断器 open |

### 3.4 日志规则

- 禁止记录敏感信息：手机号需脱敏（`138****1234`）、密码 / token 禁止出现
- ERROR 及以上级别必须包含异常堆栈（`exc_info=True`）
- 单条日志不超过 4KB，防止 SLS 截断

---

## 4. Traces（OpenTelemetry — P2 预留）

当前未启用分布式链路追踪。计划 P2 阶段接入：

- 接入 OpenTelemetry Python SDK（`opentelemetry-instrumentation-fastapi`）
- 自动注入 `trace_id` / `span_id` 到 structlog context
- Exporter 暂定 Jaeger 或阿里云 ARMS
- 预留接入点：FastAPI middleware、outbound 装饰器、数据库查询层

---

## 5. 告警规则（最小集）

以下为首批上线的 5 条核心告警：

| # | 告警名称 | 触发条件 | 严重度 | 通知渠道 | SOP |
|---|---------|---------|--------|---------|-----|
| 1 | API 5xx 错误率过高 | 5xx rate > 1%，持续 5min | **P1** | 钉钉值班群 + 短信 | [SOP-001](TODO) |
| 2 | Readiness 探针失败 | `/readiness` 返回非 200，连续 2 次 | **P0** | 钉钉值班群 + 短信 + 电话 | [SOP-002](TODO) |
| 3 | 支付回调失败激增 | 支付回调失败 > 3 次/min | **P1** | 钉钉值班群 + 短信 | [SOP-003](TODO) |
| 4 | 订单创建失败激增 | 订单创建失败 > 5 次/min | **P1** | 钉钉值班群 + 短信 | [SOP-004](TODO) |
| 5 | 外呼熔断器打开 | `outbound_circuit_breaker_state == 2`（任一 provider） | **P1** | 钉钉值班群 + 短信 | [SOP-005](TODO) |

**告警通用配置：**

- 恢复通知：告警恢复后自动发送"已恢复"消息
- 静默窗口：同一告警 15 分钟内不重复发送
- 升级机制：P1 告警 15 分钟未 ack 自动升级为 P0

---

## 6. 值班 SOP（占位）

### 6.1 值班轮值

- 周粒度轮值，每周一 10:00 自动交接
- 值班表维护于钉钉值班日历
- 节假日提前一周确认排班

### 6.2 故障升级链路

```
L1 值班工程师（5min 内响应）
  ↓ 15min 未解决
L2 对应模块 Owner
  ↓ 30min 未解决
L3 架构师 / Tech Lead
```

### 6.3 待完善（TODO）

- [ ] 各告警详细 SOP 文档（SOP-001 ~ SOP-005）
- [ ] 值班交接 Checklist
- [ ] 故障复盘模板
- [ ] 告警规则的 Prometheus AlertManager YAML 配置

---

## 7. 参考链接

- [ADR-0026：统一外呼可靠性装饰器](../docs/adr/ADR-0026-unified-outbound-reliability-decorator.md)
- [D-025：Readiness 四件套](../docs/DECISION_LOG.md)
- [部署文档](../docs/deployment.md)
