# ADR-0030 Blocker 等待期内网 staging（mock provider 全栈联调）

- 日期：2026-04-27
- 状态：Accepted
- 决议来源：D-044
- 参与角色：DevOps / Arch / Backend / QA

## 背景

5 个 P0 Blocker（B-01 微信支付商户号 / B-02 阿里云短信 / B-03 ACR + 服务器 /
B-04 域名 / SSL / ICP / B-05 Apple Developer 账号）已等待 15 天没有任何外部
推进。期间核心代码在快速演进，存在以下风险：

1. **回归手感丢失**：研发只在 dev 环境内跑，没有"完整启停 + 端到端流量"的
   手工肌肉记忆，等 Blocker 解决后再开始 staging 演练会发现一堆陈年 bug。
2. **Provider 抽象层 drift**：`payment.providers.mock` 与 `sms.providers.mock`
   功能很少（永远 success），与生产真接口的请求/响应形状差距正在悄悄扩大，
   等切到 real provider 时才发现"形状不对"为时已晚。
3. **运维剧本未演练**：`docs/runbook-go-live.md` / `RUNBOOK_ROLLBACK.md` 没人
   实际跑过 docker compose 起栈 → alembic upgrade → 端到端 → 失败回滚的全流程。

D-044 决议：**外部 Blocker 未到位前，每周三 14:00 跑一次完整 staging 演练**，
用 mock provider + 真实端到端流量回放，覆盖患者下单 → 支付 → 接单 → 完成 →
评价 → 退款全闭环。

## 决策

### 1. 拓扑

```
                       host:18080
                            │
                  ┌──────── ▼ ────────┐
                  │  nginx-staging    │  反代 + 路径路由
                  └─┬─────────────────┘
                    │  upstream backend-staging:8000
                    ▼
            ┌───────────────┐
            │ backend-staging│ environment=staging
            │  (uvicorn)     │ PAYMENT_PROVIDER=mock
            │                │ SMS_PROVIDER=mock
            └─┬───┬───┬──────┘
              │   │   │
   pg-staging │   │   └── http→ mock-pay-stub:8001
              │   │              (FastAPI, 注入支持)
              │   └────── http→ mock-sms-stub:8002
              │                  (FastAPI, 注入支持)
              ▼
         redis-staging:6379

network: yiluan-staging-net (bridge, internal)
仅 nginx-staging 暴露 18080 给本机；其余服务彻底内网隔离。
```

### 2. 网络隔离原则

- 所有服务挂在自定义 bridge 网络 `yiluan-staging-net`。
- **只有** `nginx-staging` 发布端口（`127.0.0.1:18080:80`）。
- mock-pay / mock-sms / pg / redis / backend 一律不发布端口，调试时用
  `docker compose exec` 进入。
- 与 dev 环境（`backend/docker-compose.yaml` 用 5432/6379/8000）完全隔离，
  不共用任何 volume，避免污染。

### 3. Mock provider 行为契约

两个 stub（mock-pay-stub / mock-sms-stub）都遵循同一行为契约：

| 端点 | 含义 |
| --- | --- |
| 业务端点 | 模拟真实第三方 API 的请求/响应形状 |
| `POST /__inject` | 注入下一个（或下 N 个）业务请求的响应行为 |
| `POST /__reset` | 清空注入与历史 |
| `GET /__sent` | 历史调用日志，给 e2e 校验用 |

**注入参数**：`{success: bool, delay_ms: int, error_code: str | null, repeat: int}`

- `success=false` 配合 `error_code` 让 backend 命中错误分支。
- `delay_ms` 模拟慢响应，验证 `outbound_call` 的 timeout / retry。
- `repeat` 控制注入对未来 N 个请求生效（默认 1）。

mock-pay-stub 额外提供 `POST /__trigger-callback`：手动触发"支付成功"回调
到 `backend-staging` 的 `/api/v1/payments/wechat/callback`，便于 e2e 控制
回调时序。

### 4. 与生产差异表

| 组件 | staging | production | 备注 |
| --- | --- | --- | --- |
| FastAPI backend | ✅ 真品（同镜像） | ✅ 真品 | 仅环境变量差异 |
| PostgreSQL 15 | ✅ 容器（独立 volume） | ✅ 托管/自建 | 数据不互通 |
| Redis 7 | ✅ 容器 | ✅ 托管/自建 | |
| 微信支付 | 🔶 mock-pay-stub | ✅ wechatpay v3 | provider 切换 |
| 阿里云短信 | 🔶 mock-sms-stub | ✅ aliyun dysmsapi | provider 切换 |
| Apple SignIn | ❌ 不演练 | ✅ 真品 | B-05 解锁后专项 |
| Azure Storage | ❌ 跳过上传链路 | ✅ 真品 | e2e 不覆盖 |
| OSS / CDN | ❌ 跳过 | ✅ 真品 | 同上 |
| ICP / SSL / nginx | 🔶 自签 / 内网 | ✅ 真品 | 仅校验 nginx 配置语法 |
| 监控（Prometheus） | ❌ 复用现有 | ✅ 真品 | 不在本 staging 启停 |

### 5. 演练频率与负责人

- **频率**：每周三 14:00 GMT+8。
- **执行人**：本周值班 DevOps（轮值表见 `TEAM.md`）。
- **报告归档**：`deploy/staging/reports/rehearsal-YYYY-MM-DD.md`。
- **失败处理**：见 `docs/STAGING_REHEARSAL_RUNBOOK.md` §回滚 / 上报路径。

### 6. 退场条件

当所有 5 个 P0 Blocker 解决并完成首次 production go-live 后，本 staging 改为
**月度演练**（用真 provider 的沙箱环境），mock provider stub 保留作为
CI 集成测试 fixture，不再删除。

## 后果

### 正面

- 每周强制刷新"完整启停 + 端到端"肌肉记忆，防止演练日 0 → 1 失败。
- mock provider 形状被注入测试持续约束，与真接口 drift 早暴露。
- runbook 被反复执行，文档质量自然提高。

### 负面

- 每周占用约 1 人 1 小时（演练 + 报告归档）。
- mock-pay-stub / mock-sms-stub 需要随真接口契约变化跟进维护。

### 中性

- staging compose 与 dev compose 并存，新人需明确"本机 5432 是 dev、
  18080 是 staging"。
