# YiLuAn Grafana Dashboards

> 配套:`docs/runbook-go-live.md` §6 灰度监控指标 + `deploy/prometheus/alerts.yml`
>
> 当前状态:**骨架(scaffold)**。真实 dashboard JSON 应在 Grafana UI 编辑完成后用 `Share → Export → Save to file` 落到本目录。本目录的 `yiluan-overview.json` 仅给出最小可导入骨架,带占位 panel,实际部署需在 Grafana 中调整阈值、单位、数据源 UID。

## 关键面板清单(必须有)

| # | Panel | PromQL(参考) | 阈值 | 关联告警 |
|---|---|---|---|---|
| 1 | API QPS(by route) | `sum by (handler) (rate(http_requests_total[1m]))` | — | — |
| 2 | API p99 latency | `histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))` | > 1s 5min → P1 | latency-high |
| 3 | API 5xx rate | `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))` | > 1% / 2min 自动回滚 | (ADR-0028 watcher) |
| 4 | DB connections | `pg_stat_activity_count` (postgres-exporter) | > 80% pool | DBConnExhausted |
| 5 | DB query p99 | `pg_stat_statements_mean_exec_time_seconds` | > 200ms | — |
| 6 | Redis ops/s | `rate(redis_commands_processed_total[1m])` | — | — |
| 7 | Redis hit rate | `rate(redis_keyspace_hits_total[5m]) / (rate(redis_keyspace_hits_total[5m])+rate(redis_keyspace_misses_total[5m]))` | < 80% 报警 | — |
| 8 | Queue depth(APScheduler 任务积压) | `sum(yiluan_scheduler_jobs_pending)` | > 100 | SchedulerBacklog |
| 9 | WS 连接数 / 断连率 | `yiluan_ws_active_connections`, `rate(yiluan_ws_disconnect_total[5m])` | 断连 > 30% → P1 | WSDropHigh |
| 10 | Order created rate | `rate(order_created_total[5m])` | 比 1h 前下跌 80% → P1 | OrderCreationDrop(已存在) |
| 11 | Payment callback success | `rate(payment_callback_received_total{status="success"}[5m])` | 失败 > 10% → P1 | PaymentCallbackFailureRateHigh(已存在) |
| 12 | SMS send fail rate | `rate(sms_send_fail_total[5m]) / rate(sms_send_total[5m])` | > 5% / 10min | (待加 alerts.yml) |
| 13 | /readiness availability | `avg_over_time(probe_success{job="readiness"}[1m])` | < 1 持续 2min | ReadinessProbeFailure(ADR-0028) |
| 14 | Canary pool split(by `pool` label) | `sum by (pool) (rate(http_requests_total[5m]))` | — | (灰度过程中可视化) |
| 15 | Outbound circuit breaker state | `outbound_circuit_breaker_state` | == 1 持续 1min → P1 | CircuitBreakerOpen(已存在) |

## 导出/导入流程

1. 在 Grafana 中复用上面 PromQL 创建 dashboard,标题 `YiLuAn / Overview`。
2. UID 固定为 `yiluan-overview`(便于跨环境引用)。
3. 导出 JSON 时勾选 `Export for sharing externally`,把数据源占位为 `${DS_PROMETHEUS}`。
4. 提交到 `ops/grafana/yiluan-overview.json`。
5. 部署侧用 `grafana-cli` 或 Grafana provisioning(`/etc/grafana/provisioning/dashboards/`)自动加载。

## 二级 dashboard(后续)

- `yiluan-canary.json` — 仅在灰度期看,按 `X-Canary-Pool` label 拆分 5xx / latency
- `yiluan-business.json` — 业务漏斗:登录 → 浏览 → 下单 → 支付 → 评价
- `yiluan-infra.json` — host metrics(CPU/MEM/Disk)+ k8s/Container Apps pod 状态

## TODO(prod)

- [ ] 接入真 Grafana 实例后导出真实 JSON
- [ ] alert.yml 增加 SMS/p99/queue depth 三条规则
- [ ] 添加 Anomaly detection(基于 holt-winters / 30d 基线)
