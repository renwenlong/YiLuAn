# ops/scripts/metrics_baseline.sh

24 小时 Prometheus `/metrics` 基线采集脚本（Action Item **A-2604-06**，2026-04-24 晨会）。

## 目的

为后端 `/metrics` 暴露的 5 个核心业务计数器（订单 / 支付 / SMS / WS / 5xx）建立
**24 小时基线**，用于校准 `prometheus/alerts.yml` 中 5 条告警的触发阈值。

## 用法

```bash
# 前台跑（适合本地观察）
bash ops/scripts/metrics_baseline.sh

# 后台跑（推荐生产/staging）
nohup bash ops/scripts/metrics_baseline.sh > /tmp/metrics_baseline.out 2>&1 &
```

## 可调环境变量

| 变量            | 默认值                              | 说明                              |
|-----------------|-------------------------------------|-----------------------------------|
| `METRICS_URL`   | `http://localhost:8000/metrics`     | 抓取目标                          |
| `INTERVAL_SEC`  | `30`                                | 采样间隔（秒）                    |
| `DURATION_SEC`  | `86400` (24h)                       | 总运行时长                        |
| `OUT_DIR`       | `<scriptdir>/../baselines`          | 输出目录（自动 `mkdir -p`）       |

## 输出

`ops/baselines/metrics-YYYY-MM-DD.log`，追加模式。每个样本以注释头分隔：

```text
# === sample @ 2026-04-24T10:00:00Z ===
# HELP yiluan_orders_created_total ...
# TYPE yiluan_orders_created_total counter
yiluan_orders_created_total 0.0
...

# === sample @ 2026-04-24T10:00:30Z ===
...
```

24 小时跑完约产出 2880 个样本，单文件量级在 100~500 MB（视后端 metrics 数量）。

## 信号

- `SIGINT` / `SIGTERM` 会优雅退出并打印已采样次数。
- 单次 `curl` 失败仅记录 `# WARN:`，不中断主循环。

## 后续分析（Backend / Ops）

跑完 24h 后用 `awk` 或简单 Python 脚本聚合每个 metric 的 P50/P95/P99，对照
`prometheus/alerts.yml` 的 5 条告警阈值校准：

1. 5xx 错误率 > 1% / 5min
2. 支付回调失败率 > 5% / 10min
3. SMS 发送失败率 > 10% / 10min
4. WS 在线连接数 < 1
5. /readiness 失败 / 2min

## 关联

- Action Item：A-2604-06
- 晨会决策：2026-04-24（`Q:\OpenClaw\yiluan-standup\2026-04-24.md`）
- 相关文件：`prometheus/alerts.yml`、`docs/deployment.md`（D-037 /metrics 安全收口）
