# 医路安 (YiLuAn) 部署文档

## 1. 项目概述

医路安是一个医疗陪诊服务平台，技术栈：

| 组件 | 技术 |
|------|------|
| 后端 API | Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL 15 (asyncpg) |
| 缓存 | Redis 7 |
| 前端 | 微信小程序 (原生 WXML/WXSS/JS) |
| iOS 客户端 | SwiftUI (iOS 17+) |
| 容器化 | Docker (python:3.11-slim) |
| CI/CD | GitHub Actions → Azure Container Registry → Azure Container Apps |

## 2. Azure Container Apps 配置

### 推荐配置

| 环境 | CPU | 内存 | 最小实例 | 最大实例 |
|------|-----|------|----------|----------|
| Staging | 0.5 vCPU | 1 Gi | 1 | 3 |
| Production | 1.0 vCPU | 2 Gi | 2 | 10 |

### 部署命令参考

```bash
# 创建 Container Apps 环境
az containerapp env create \
  --name yiluan-env \
  --resource-group yiluan-rg \
  --location eastasia

# 部署应用
az containerapp create \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --environment yiluan-env \
  --image yiluanacr.azurecr.io/yiluan-backend:latest \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 --memory 2Gi \
  --min-replicas 2 --max-replicas 10 \
  --secrets "jwt-secret=keyvaultref:jwt-secret,identityref:/subscriptions/.../identity" \
  --env-vars "ENVIRONMENT=production" "DATABASE_URL=secretref:database-url" "REDIS_URL=secretref:redis-url"
```

### 自动缩放规则

```yaml
scale:
  minReplicas: 2
  maxReplicas: 10
  rules:
    - name: http-scaling
      http:
        metadata:
          concurrentRequests: "50"
```

## 3. Azure Database for PostgreSQL Flexible Server

### 推荐配置

| 环境 | SKU | 存储 | 高可用 |
|------|-----|------|--------|
| Staging | Burstable B1ms (1 vCore, 2 GiB) | 32 GiB | 否 |
| Production | General Purpose D2ds_v5 (2 vCore, 8 GiB) | 128 GiB | 区域冗余 |

### 关键参数

```bash
az postgres flexible-server create \
  --name yiluan-db \
  --resource-group yiluan-rg \
  --location eastasia \
  --sku-name Standard_D2ds_v5 \
  --storage-size 128 \
  --version 15 \
  --high-availability ZoneRedundant \
  --admin-user yiluan_admin \
  --admin-password <from-keyvault>

# 启用必要的扩展
az postgres flexible-server parameter set \
  --name shared_preload_libraries \
  --server-name yiluan-db \
  --resource-group yiluan-rg \
  --value "pg_stat_statements"
```

### 数据库迁移

```bash
# 在 CI/CD 流程中或手动执行
docker run --rm \
  -e DATABASE_URL="$PROD_DATABASE_URL" \
  yiluanacr.azurecr.io/yiluan-backend:latest \
  python -m alembic upgrade head
```

## 4. Azure Cache for Redis

### 推荐配置

| 环境 | SKU | 大小 |
|------|-----|------|
| Staging | Basic C0 | 250 MB |
| Production | Standard C1 | 1 GB |

```bash
az redis create \
  --name yiluan-redis \
  --resource-group yiluan-rg \
  --location eastasia \
  --sku Standard \
  --vm-size C1 \
  --enable-non-ssl-port false
```

连接字符串格式：`rediss://:ACCESS_KEY@yiluan-redis.redis.cache.windows.net:6380/0`

（注意：Azure Redis 使用 `rediss://`，启用 TLS）

## 5. 域名 + SSL

### 方案：Azure Front Door

推荐使用 Azure Front Door 作为全局负载均衡和 CDN：

```bash
# 创建 Front Door profile
az afd profile create \
  --profile-name yiluan-fd \
  --resource-group yiluan-rg \
  --sku Standard_AzureFrontDoor

# 添加自定义域名
az afd custom-domain create \
  --profile-name yiluan-fd \
  --resource-group yiluan-rg \
  --custom-domain-name api-domain \
  --host-name api.yiluan.com \
  --certificate-type ManagedCertificate
```

### DNS 配置

| 记录 | 类型 | 值 |
|------|------|-----|
| api.yiluan.com | CNAME | yiluan-fd.azurefd.net |
| _dnsauth.api.yiluan.com | TXT | (Front Door 验证值) |

SSL 证书由 Azure Front Door 自动管理，自动续期。

## 6. 环境变量注入（Azure Key Vault → Container Apps）

### Key Vault 设置

```bash
# 创建 Key Vault
az keyvault create \
  --name yiluan-kv \
  --resource-group yiluan-rg \
  --location eastasia

# 存储 secrets
az keyvault secret set --vault-name yiluan-kv --name "database-url" --value "postgresql+asyncpg://..."
az keyvault secret set --vault-name yiluan-kv --name "redis-url" --value "rediss://..."
az keyvault secret set --vault-name yiluan-kv --name "jwt-secret-key" --value "<generated>"
az keyvault secret set --vault-name yiluan-kv --name "wechat-app-id" --value "<appid>"
az keyvault secret set --vault-name yiluan-kv --name "wechat-app-secret" --value "<secret>"
```

### Container Apps 引用 Key Vault

```bash
# 启用 managed identity
az containerapp identity assign \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --system-assigned

# 授权 identity 访问 Key Vault
az keyvault set-policy \
  --name yiluan-kv \
  --object-id <identity-principal-id> \
  --secret-permissions get list

# 配置 secrets 引用
az containerapp secret set \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --secrets "database-url=keyvaultref:https://yiluan-kv.vault.azure.net/secrets/database-url,identityref:<identity-id>"
```

### 完整环境变量列表

| 变量名 | 来源 | 说明 |
|--------|------|------|
| `DATABASE_URL` | Key Vault | PostgreSQL 连接字符串 |
| `REDIS_URL` | Key Vault | Redis 连接字符串 |
| `JWT_SECRET_KEY` | Key Vault | JWT 签名密钥 |
| `WECHAT_APP_ID` | Key Vault | 微信小程序 AppID |
| `WECHAT_APP_SECRET` | Key Vault | 微信小程序 AppSecret |
| `WECHAT_PAY_MCH_ID` | Key Vault | 微信支付商户号 |
| `WECHAT_PAY_API_KEY_V3` | Key Vault | 微信支付 v3 API 密钥 |
| `ENVIRONMENT` | 明文 | `production` / `staging` |
| `SMS_PROVIDER` | 明文 | `aliyun` (生产) |

## 7. 蓝绿部署 / 滚动更新

### 策略：Container Apps Revision 模式

使用 **多修订版 (multiple revision)** 模式实现蓝绿部署：

```bash
# 启用多修订版模式
az containerapp revision set-mode \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --mode multiple

# 部署新版本（0% 流量）
az containerapp update \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --image yiluanacr.azurecr.io/yiluan-backend:v2.0.0

# 验证新版本健康
curl https://yiluan-api--new-revision.eastasia.azurecontainerapps.io/api/v1/health

# 逐步切换流量
az containerapp ingress traffic set \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --revision-weight yiluan-api--v1=80 yiluan-api--v2=20

# 完全切换
az containerapp ingress traffic set \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --revision-weight yiluan-api--v2=100

# 停用旧版本
az containerapp revision deactivate \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --revision yiluan-api--v1
```

### 回滚流程

```bash
# 快速回滚：将流量切回旧版本
az containerapp ingress traffic set \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --revision-weight yiluan-api--v1=100
```

### 数据库迁移注意事项

- 迁移必须向前兼容（additive-only），确保新旧版本都能正常运行
- 先执行迁移，再部署新代码
- 破坏性变更（删列、改类型）分两次部署完成

## 8. 日志采集

### Azure Monitor + Application Insights

```bash
# 创建 Log Analytics workspace
az monitor log-analytics workspace create \
  --workspace-name yiluan-logs \
  --resource-group yiluan-rg \
  --location eastasia

# 创建 Application Insights
az monitor app-insights component create \
  --app yiluan-insights \
  --resource-group yiluan-rg \
  --location eastasia \
  --workspace yiluan-logs
```

### 应用日志配置

Container Apps 自动将 stdout/stderr 发送到 Log Analytics。

结构化日志查询示例 (KQL)：

```kql
// 查看最近错误
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "yiluan-api"
| where Log_s contains "ERROR"
| order by TimeGenerated desc
| take 50

// 请求延迟分布
ContainerAppConsoleLogs_CL
| where Log_s contains "request_time"
| parse Log_s with * "request_time=" latency:double *
| summarize percentiles(latency, 50, 95, 99) by bin(TimeGenerated, 5m)
```

## 9. 告警规则

### 关键告警

```bash
# 错误率 > 1%
az monitor metrics alert create \
  --name "high-error-rate" \
  --resource-group yiluan-rg \
  --scopes "/subscriptions/.../yiluan-api" \
  --condition "avg Requests where StatusCode >= 500 > 1" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action "/subscriptions/.../actionGroups/ops-team"

# 响应时间 > 2s (P95)
az monitor metrics alert create \
  --name "high-latency" \
  --resource-group yiluan-rg \
  --scopes "/subscriptions/.../yiluan-api" \
  --condition "avg ResponseTime > 2000" \
  --window-size 5m \
  --action "/subscriptions/.../actionGroups/ops-team"

# Pod 重启
az monitor metrics alert create \
  --name "pod-restart" \
  --resource-group yiluan-rg \
  --scopes "/subscriptions/.../yiluan-api" \
  --condition "count RestartCount > 3" \
  --window-size 15m \
  --action "/subscriptions/.../actionGroups/ops-team"
```

### 告警通知渠道

| 级别 | 触发条件 | 通知方式 |
|------|----------|----------|
| P0 (Critical) | 服务不可用、Pod 持续重启 | 短信 + 企业微信 |
| P1 (High) | 错误率 > 1%、延迟 > 2s | 企业微信 |
| P2 (Medium) | 磁盘/内存使用率 > 80% | 邮件 |

## 10. CI/CD 流程

### 流程概览

```
代码提交 → GitHub Actions
  ├── 运行测试 (pytest + jest)
  ├── Docker 构建验证
  ├── 构建镜像 → 推送 ACR
  ├── 部署到 Staging
  ├── Staging 冒烟测试
  └── 手动审批 → 部署到 Production
```

### GitHub Actions 核心步骤

```yaml
# 参考 .github/workflows/test.yml 中的完整配置
steps:
  # 1. 测试
  - run: cd backend && python -m pytest tests/ -v

  # 2. Docker 构建
  - run: docker build -t yiluan-backend:test ./backend

  # 3. 登录 ACR
  - uses: azure/docker-login@v1
    with:
      login-server: yiluanacr.azurecr.io
      username: ${{ secrets.ACR_USERNAME }}
      password: ${{ secrets.ACR_PASSWORD }}

  # 4. 推送镜像
  - run: |
      docker tag yiluan-backend:test yiluanacr.azurecr.io/yiluan-backend:${{ github.sha }}
      docker push yiluanacr.azurecr.io/yiluan-backend:${{ github.sha }}

  # 5. 部署到 Container Apps
  - uses: azure/container-apps-deploy-action@v1
    with:
      containerAppName: yiluan-api
      resourceGroup: yiluan-rg
      imageToDeploy: yiluanacr.azurecr.io/yiluan-backend:${{ github.sha }}
```

### 分支策略

| 分支 | 触发 | 部署目标 |
|------|------|----------|
| `main` | Push | Staging → (手动审批) → Production |
| `develop` | Push | 仅运行测试 |
| `feature/*` | PR | 仅运行测试 |

## 11. CD 自动化流水线

完整的 CD 流水线定义在 `.github/workflows/deploy.yml`，流程如下：

```
git push main
    │
    ▼
┌──────────┐   ┌──────────────┐   ┌─────────────────┐   ┌───────────────────┐
│  Tests   │──▶│ Build & Push │──▶│ Deploy Staging  │──▶│ Deploy Production│
│ (门禁)   │   │  to ACR      │   │ (自动)          │   │ (手动审批)       │
└──────────┘   └──────────────┘   └─────────────────┘   └───────────────────┘
                                    ↓ 含DB迁移             ↓ 含DB迁移
                                    ↓ 含健康检查           ↓ 含健康检查
```

### 11.1 流水线阶段说明

| 阶段 | 触发条件 | 动作 |
|------|---------|------|
| **test** | 每次 push main | 运行后端 pytest + 前端 jest |
| **build-push** | test 通过 | 构建 Docker 镜像，推送到 ACR（tag: YYYYMMDD-commit8） |
| **migrate-staging** | build-push 完成 | 对 Staging DB 执行 `alembic upgrade head` |
| **deploy-staging** | 迁移完成 | 更新 Staging Container App，健康检查 |
| **migrate-production** | Staging 部署成功 + 人工审批 | 对 Production DB 执行迁移 |
| **deploy-production** | 迁移完成 | 更新 Production Container App，健康检查 |

### 11.2 所需 GitHub Secrets

| Secret | 用途 |
|--------|------|
| `ACR_USERNAME` | Azure Container Registry 用户名 |
| `ACR_PASSWORD` | ACR 密码 |
| `AZURE_CREDENTIALS` | Azure Service Principal JSON（用于 az login） |
| `STAGING_DATABASE_URL` | Staging PostgreSQL 连接串 |
| `PRODUCTION_DATABASE_URL` | Production PostgreSQL 连接串 |

### 11.3 GitHub Environment Protection Rules

在 GitHub 仓库设置中配置：

- **staging** 环境：无保护规则（自动部署）
- **production** 环境：
  - ✅ Required reviewers（至少 1 人审批）
  - ✅ Wait timer: 0 分钟（审批后立即执行）

## 12. 灾备方案

### 12.1 数据库备份策略

| 类型 | 频率 | 保留期 | 方式 |
|------|------|--------|------|
| 自动备份 | 每日 | 35 天 | Azure PostgreSQL 内置（默认启用） |
| 事务日志备份 | 持续 | 同上 | Azure 自动管理，支持时间点恢复 (PITR) |
| 手动快照 | 重大发版前 | 90 天 | `az postgres flexible-server backup create` |

```bash
# 创建手动备份
az postgres flexible-server backup create \
  --resource-group yiluan-rg \
  --name yiluan-db \
  --backup-name pre-release-$(date +%Y%m%d)

# 时间点恢复（回滚到指定时间）
az postgres flexible-server restore \
  --resource-group yiluan-rg \
  --name yiluan-db-restore \
  --source-server yiluan-db \
  --restore-time "2026-04-15T10:00:00Z"
```

### 12.2 Redis 备份

| 策略 | 说明 |
|------|------|
| RDB 持久化 | Azure Cache for Redis 默认每小时快照 |
| 数据丢失影响 | 低 — Redis 仅用于缓存和临时数据（readiness_check、rate_limit 等），丢失后自动重建 |

### 12.3 镜像版本管理

- ACR 保留最近 30 个版本 tag
- 每个 tag 格式：`YYYYMMDD-<commit-sha-8>`
- `latest` 始终指向最新构建

## 13. 日志收集

### 13.1 Azure Monitor 配置

```bash
# 创建 Log Analytics Workspace
az monitor log-analytics workspace create \
  --resource-group yiluan-rg \
  --workspace-name yiluan-logs \
  --location eastasia \
  --retention-in-days 90

# 关联到 Container Apps 环境
az containerapp env update \
  --name yiluan-env \
  --resource-group yiluan-rg \
  --logs-workspace-id <workspace-id> \
  --logs-workspace-key <workspace-key>
```

### 13.2 日志查询示例（KQL）

```kusto
// 最近1小时的错误日志
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where Log_s contains "ERROR" or Log_s contains "Exception"
| order by TimeGenerated desc
| take 50

// API 响应时间分布
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(24h)
| where Log_s matches regex "\\d+ms"
| summarize avg(extract("(\\d+)ms", 1, Log_s, typeof(real))),
           percentile(extract("(\\d+)ms", 1, Log_s, typeof(real)), 95)
  by bin(TimeGenerated, 5m)
```

### 13.3 应用日志格式

后端使用 Python `logging` + JSON 格式化输出：

```python
# 建议在 app/main.py 配置
import logging, json_logging
json_logging.init_fastapi(enable_json=True)
```

## 14. 告警规则

### 14.1 推荐告警

| 指标 | 阈值 | 严重级别 | 动作 |
|------|------|----------|------|
| HTTP 5xx 错误率 | > 5% (5分钟窗口) | P1 Critical | 邮件 + 短信通知 |
| 平均响应时间 | > 2s (5分钟窗口) | P2 Warning | 邮件通知 |
| CPU 使用率 | > 80% (10分钟窗口) | P2 Warning | 触发自动扩容 |
| 内存使用率 | > 85% (10分钟窗口) | P2 Warning | 邮件通知 |
| 数据库连接池耗尽 | active > 90% max | P1 Critical | 邮件 + 短信通知 |
| Redis 连接失败 | 连续 3 次 | P1 Critical | 邮件通知 |
| 健康检查失败 | /readiness 返回 503 | P1 Critical | 自动重启实例 |

### 14.2 Azure Alert Rule 配置示例

```bash
# 创建 Action Group
az monitor action-group create \
  --resource-group yiluan-rg \
  --name yiluan-alerts \
  --short-name yiluan \
  --email-receivers name=ops email=ops@yiluan.com

# 创建 5xx 错误率告警
az monitor metrics alert create \
  --resource-group yiluan-rg \
  --name high-error-rate \
  --scopes <container-app-resource-id> \
  --condition "avg Requests where StatusCodeClass == 5xx > 5" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 1 \
  --action yiluan-alerts
```

## 14.3 监控告警最小集（生产上线 P0）

上线第一周必须配齐以下 4 类告警，缺一不可：

| # | 告警项 | 触发条件 | 通知渠道 | 建议响应 SLA |
|---|--------|----------|----------|--------------|
| 1 | **Readiness 失败** | `/readiness` 或 `/api/v1/readiness` 连续 2 次返回非 200（DB 或 Redis 不通） | 短信 + 企业微信 | 5 分钟内介入 |
| 2 | **支付回调失败** | 微信支付 notify 接口 5 分钟错误率 > 5% 或连续 3 笔失败 | 短信 + 企业微信 | 10 分钟内介入（资金影响） |
| 3 | **SMS 发送异常** | 阿里云 SMS provider 5 分钟失败率 > 20%，或日发送配额触顶 | 邮件 + 企业微信 | 30 分钟内介入 |
| 4 | **WebSocket / Redis 异常** | Redis 连接池耗尽 / WS 连接掉线率突增 / pub-sub 中断 | 邮件 + 企业微信 | 30 分钟内介入 |

> 详细 KQL 查询与 Action Group 配置见 14.1 / 14.2 节。所有告警接入同一个 Action Group `yiluan-alerts`，避免遗漏。

## 15. 回滚流程

### 15.1 应用回滚（Container Apps）

```bash
# 查看历史 revision
az containerapp revision list \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --output table

# 激活之前的 revision（蓝绿切换）
az containerapp ingress traffic set \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --revision-weight <previous-revision>=100

# 或直接部署指定版本的镜像
az containerapp update \
  --name yiluan-api \
  --resource-group yiluan-rg \
  --image yiluanacr.azurecr.io/yiluan-backend:20260414-5689685f
```

### 15.2 数据库回滚

```bash
# Alembic 降级（回退一个版本）
cd backend && alembic downgrade -1

# 如果迁移不可逆，使用时间点恢复（见 12.1 灾备方案）
```

### 15.3 回滚决策矩阵

| 场景 | 回滚方式 | 预估耗时 |
|------|---------|----------|
| 新版本 API 报错 | revision 流量切换 | < 2 分钟 |
| 数据库迁移有误 | alembic downgrade | 5-10 分钟 |
| 数据损坏 | PostgreSQL PITR 时间点恢复 | 15-30 分钟 |
| 全面故障 | 恢复到最后已知良好 revision + DB PITR | 30-60 分钟 |

### 15.4 迁移降级注意事项 ⚠️

Alembic `downgrade` 不是万能的，执行前必须确认：

1. **不可逆迁移识别** — 检查目标 revision 的 `downgrade()` 是否为 `pass`。若为 `pass`，则**严禁直接 downgrade**，必须走 PITR。
2. **Drop column / drop table 类迁移** — `downgrade` 会重建空列/表，但**原数据已永久丢失**；必须先从备份恢复数据，再执行业务回滚。
3. **数据迁移脚本（data migration）** — 若 `upgrade` 中有 `op.execute("UPDATE ...")`，`downgrade` 通常无法还原原值，必须从快照恢复。
4. **多版本回退** — 跨多个 revision 回退时，逐个 `downgrade -1` 并记录日志；不要直接 `downgrade <old_rev>` 跳跃执行，避免中间状态错误。
5. **生产回退前必做** —
   ```bash
   # 1. 立即创建当前状态的手动备份
   az postgres flexible-server backup create \
     --resource-group yiluan-rg --name yiluan-db \
     --backup-name pre-rollback-$(date +%Y%m%d-%H%M%S)
   # 2. 在 Staging 完整演练一次 downgrade 路径
   # 3. 准备前向修复脚本（forward-fix），若 downgrade 失败立即切到前向修复
   ```
6. **应用与迁移版本对齐** — 回滚镜像后必须确认数据库 schema 与该镜像兼容；若 schema 已超前，应用启动会因为 ORM 校验失败而 readiness 持续 503。

## 16. 环境变量清单（按环境分组）

所有 secret 通过 Azure Key Vault 注入，明文配置直接写在 Container App `env-vars`。

### 16.1 通用变量（dev / staging / prod 都需要）

| 变量名 | 类型 | dev 默认值 | staging | prod | 说明 |
|--------|------|-----------|---------|------|------|
| `ENVIRONMENT` | 明文 | `development` | `staging` | `production` | 控制日志级别、CORS、debug 路由 |
| `APP_VERSION` | 明文 | `dev` | git tag | git tag | 显示在 `/health` 响应里 |
| `DATABASE_URL` | secret | `postgresql+asyncpg://yiluan:yiluan@localhost:5432/yiluan` | Key Vault `staging-database-url` | Key Vault `prod-database-url` | 必须使用 `+asyncpg` 驱动 |
| `REDIS_URL` | secret | `redis://localhost:6379/0` | Key Vault `staging-redis-url`（`rediss://`） | Key Vault `prod-redis-url`（`rediss://`） | Azure Redis 必须用 TLS |
| `JWT_SECRET_KEY` | secret | 本地随机 | Key Vault | Key Vault | 至少 32 字节随机 |
| `JWT_ALGORITHM` | 明文 | `HS256` | `HS256` | `HS256` | — |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 明文 | `60` | `60` | `30` | 生产更短 |
| `LOG_LEVEL` | 明文 | `DEBUG` | `INFO` | `INFO` | — |

### 16.2 微信小程序与支付（staging / prod）

| 变量名 | dev | staging | prod | 说明 |
|--------|-----|---------|------|------|
| `WECHAT_APP_ID` | mock 值 | 测试号 AppID | 正式 AppID | — |
| `WECHAT_APP_SECRET` | mock 值 | Key Vault | Key Vault | — |
| `WECHAT_PAY_MCH_ID` | — | 测试商户号 | 正式商户号 | dev 走 mock provider |
| `WECHAT_PAY_API_KEY_V3` | — | Key Vault | Key Vault | APIv3 密钥 |
| `WECHAT_PAY_CERT_SERIAL` | — | Key Vault | Key Vault | 商户证书序列号 |
| `WECHAT_PAY_PRIVATE_KEY` | — | Key Vault（PEM 内容） | Key Vault | 注意换行符 |
| `WECHAT_PAY_NOTIFY_URL` | — | `https://yiluan-api-staging.../api/v1/payments/notify` | `https://api.yiluan.com/api/v1/payments/notify` | 必须 HTTPS 公网可达 |

### 16.3 短信服务（staging / prod）

| 变量名 | dev | staging | prod | 说明 |
|--------|-----|---------|------|------|
| `SMS_PROVIDER` | `mock` | `aliyun` | `aliyun` | dev 走控制台输出验证码 |
| `ALIYUN_SMS_ACCESS_KEY_ID` | — | Key Vault | Key Vault | — |
| `ALIYUN_SMS_ACCESS_KEY_SECRET` | — | Key Vault | Key Vault | — |
| `ALIYUN_SMS_SIGN_NAME` | — | 测试签名 | 正式签名 | 需提前审核 |
| `ALIYUN_SMS_TEMPLATE_CODE_VERIFY` | — | 测试模板 | 正式模板 | 验证码模板 |

### 16.4 监控与可观测（staging / prod）

| 变量名 | staging | prod | 说明 |
|--------|---------|------|------|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Key Vault | Key Vault | App Insights 接入 |
| `SENTRY_DSN` | （可选） | （可选） | 若启用 Sentry |

## 17. 数据库迁移操作手册

### 17.1 标准升级流程（部署管线已自动化）

```bash
# Staging
DATABASE_URL=$STAGING_DATABASE_URL alembic upgrade head

# Production（必须在新镜像部署 *之前* 执行，因为迁移要求向前兼容）
DATABASE_URL=$PRODUCTION_DATABASE_URL alembic upgrade head
```

管线对应 step 见 `.github/workflows/deploy.yml` 中的 `migrate-staging` / `migrate-production` job。

### 17.2 迁移失败处理

```bash
# 1. 立即查看 alembic 报错与 DB 当前 revision
alembic current
alembic history --verbose | head -30

# 2. 若失败发生在 schema 变更阶段（事务未提交），通常 DB 还在旧 revision —— 直接修复迁移脚本重跑即可

# 3. 若失败发生在数据迁移阶段（部分提交），按以下顺序处置：
#    a) 先 STOP 部署管线（取消后续 deploy job）
#    b) 评估是否可手动补全：alembic stamp <expected_rev> 标记完成
#    c) 不可补全则走 15.4 的 PITR 流程
```

### 17.3 迁移评审 checklist（写迁移时必查）

- [ ] 是否纯 additive？（新增列、新增表、新增索引并 `CREATE INDEX CONCURRENTLY`）
- [ ] 破坏性变更（drop / rename / type change）是否拆成两次部署？
- [ ] `downgrade()` 是否实现？不可逆请显式注释 `# IRREVERSIBLE: requires PITR`
- [ ] 大表是否避免长事务锁？（>100 万行的 backfill 拆成批处理脚本，迁移里只改 schema）
- [ ] 已在本地 + Staging 演练通过

## 18. 部署后 Smoke 验证清单 ✅

每次 production 发版完成后**必须**逐项勾选，缺一项都不算上线成功。

- [ ] **1. Liveness** — `curl https://api.yiluan.com/health` 返回 200，且 `version` 字段是新版本号
- [ ] **2. Readiness** — `curl https://api.yiluan.com/api/v1/readiness` 返回 200，`db.ok=true` 且 `redis.ok=true`
- [ ] **3. 登录链路** — 用测试账号走 `/api/v1/auth/login` → 拿到 JWT → `/api/v1/users/me` 返回正确用户
- [ ] **4. 核心读 API** — `/api/v1/escorts`（陪诊员列表）返回非空，分页字段正确
- [ ] **5. 核心写 API** — 用测试账号下一单 `/api/v1/orders`，订单写入成功
- [ ] **6. 支付链路（沙箱）** — 触发一笔测试支付 → 微信回调 notify 命中 → 订单状态变为 `paid`
- [ ] **7. 短信链路** — 请求一次 `/api/v1/auth/sms/send`，确认收到 SMS（或回调日志显示成功）
- [ ] **8. WebSocket** — 客户端 `wss://api.yiluan.com/ws/...` 能建连，能收到一条心跳/广播
- [ ] **9. 日志可见** — Log Analytics 中能查到本次部署后的请求日志，无大量 ERROR
- [ ] **10. 告警通道** — 手动触发一次 P1 告警（如临时改 readiness 阈值），确认企业微信/短信收到通知

> 任一项失败立即按 §15 回滚，不要带病上线。


## 19. 监控指标端点（/metrics）

> 决策：**D-037（2026-04-23）** — `/metrics` 端点不对公网暴露，只允许内网 Prometheus / 运维白名单 IP 访问，外网一律 403。

### 19.1 背景

后端在 `app/api/v1/metrics.py` 暴露 Prometheus exposition format 指标：

- 请求计数 / 延迟直方图 / 错误计数
- 业务指标：订单状态转移、SMS 发送结果、WebSocket 在线连接
- 任务指标：log_retention 清理行数、payment 回调处理耗时

默认未做鉴权，如果直接暴露公网会泄露内部接口列表、业务量级等敏感信息，因此所有环境必须在反向代理层加 IP 白名单。

### 19.2 nginx 配置示例

在 nginx 站点配置中加入以下 location 块，放在 `/` 通用 location 之前：

```nginx
# /metrics: 仅内网 Prometheus 可访问，外网 403
location = /metrics {
    # 允许的来源
    allow 10.0.0.0/8;       # 示例：内网 Prometheus 子网
    allow 172.16.0.0/12;    # 示例：Docker / K8s 内网段
    allow 127.0.0.1;        # 本机
    # allow <Prometheus 公网出口 IP>;  # 如果 Prometheus 在另一 region，单独放行其出口 IP

    deny  all;

    proxy_pass         http://backend_upstream;
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;

    # /metrics 不需要长连接，收敛超时
    proxy_read_timeout 5s;
    proxy_connect_timeout 3s;
    access_log off;
}
```

**要点：**

1. 使用 `location = /metrics` 精确匹配，避免子路径意外命中。
2. `allow` / `deny` 规则 nginx 按顺序匹配，第一条命中即生效；把 `deny all` 放最后。
3. `access_log off` 避免 Prometheus 每 15 秒一次的 scrape 把 access log 撑爆。
4. 如果 Prometheus 走外网访问（例如托管在另一云厂商），**不要**简单放开所有 IP，应该：
   - 走 VPN / Wireguard 隧道，只放行隧道出口 IP；或
   - 在 Prometheus 侧配置 basic auth，同时在 nginx 加 `auth_basic`。

### 19.3 Prometheus scrape 配置

参考样例：`deploy/prometheus/scrape.yml.example`

```yaml
scrape_configs:
  - job_name: yiluan-backend
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /metrics
    scheme: https
    static_configs:
      - targets:
          - api.yiluan.com:443
        labels:
          env: prod
          service: backend

  - job_name: yiluan-backend-staging
    scrape_interval: 30s
    metrics_path: /metrics
    scheme: https
    static_configs:
      - targets:
          - api-staging.yiluan.com:443
        labels:
          env: staging
          service: backend
```

实际生产环境应结合服务发现（Consul / K8s SD / file_sd）替代 static_configs。

### 19.4 上线验证

部署完 nginx 配置后，在**公网任意机器**执行：

```bash
# 外网应返回 403
curl -I https://api.yiluan.com/metrics
# 期望：HTTP/1.1 403 Forbidden

# 内网 / VPN 内应返回 200，Content-Type: text/plain
curl -I https://api.yiluan.com/metrics
# 期望：HTTP/1.1 200 OK
#       Content-Type: text/plain; version=0.0.4; charset=utf-8
```

如果外网仍返回 200，说明 nginx 白名单配置未生效，**立即回滚或改为 maintenance 模式**，避免 Prometheus scrape 接口长时间暴露。

### 19.5 告警规则

`/metrics` 本身也应被 Prometheus 监控（项目内规则见 `deploy/prometheus/alerts.yml`）：

```yaml
# prometheus/alerts.yml（节选）
- alert: MetricsEndpointDown
  expr: up{job="yiluan-backend"} == 0
  for: 2m
  annotations:
    summary: "YiLuAn backend /metrics scrape failed for 2m"
```

scrape 失败本身就是一级告警，因为所有其它 Prometheus 规则都依赖于 `/metrics` 能被拉取。

---

Last updated: 2026-04-23 (D-037)


---

## 健康检查 — `/health` (liveness) 与 `/readiness` (readiness)

**TD-OPS-01 闭合后**（2026-04-24, commit `ebe84b9`）项目暴露两类探针，请按 K8s/ACA 标准分别配置：

### `/health` — liveness（就活着吗）

- 路径：`GET /health`（root） + `GET /api/v1/health`
- 行为：进程能响应即返回 200，**不**查任何外部依赖
- 用途：K8s `livenessProbe` / ACA startup-style probe — 失败时调度器会**重启 Pod**
- 示例响应：`{"status": "healthy", "version": "0.1.0"}`

### `/readiness` — readiness（能接流量吗）

- 路径：`GET /readiness`（root） + `GET /api/v1/readiness`
- 行为：并行串 5 项依赖检查，全过（或仅 `skipped`/`degraded`）→ 200；**任一 `error` → 503**
- p99 延迟预算 **< 1.5s**（每项均带严格 timeout）
- 用途：K8s `readinessProbe` / ACA ingress 健康检查 — 失败时**只摘流量**，不重启 Pod

#### 5 项依赖检查

| 检查 | Timeout | Mock 行为 | Real 行为 |
|---|---|---|---|
| `db` | 1.0s | — | `SELECT 1` |
| `redis` | 0.5s | FakeRedis ok | `PING` + roundtrip |
| `alembic` | 1.0s | — | `alembic_version` ↔ 脚本 head 比对（drift → 503） |
| `payment` | 0.8s | `skipped` | wechatpay sandbox HEAD（外部不可达 → `degraded`，**不**阻塞 readiness） |
| `sms` | 0.2s | `skipped` | 仅校验 4 项配置完整性（**不**发付费短信） |

#### curl 示例

```bash
$ curl -s http://localhost:8000/readiness | jq
{
  "ready": true,
  "status": "ready",
  "checks": {
    "db":      {"status": "ok", "latency_ms": 3},
    "redis":   {"status": "ok", "latency_ms": 1},
    "alembic": {"status": "ok", "current": "d1e2f3a4b5c6", "head": "d1e2f3a4b5c6", "latency_ms": 30},
    "payment": {"status": "skipped", "mode": "mock", "latency_ms": 0},
    "sms":     {"status": "skipped", "mode": "mock", "latency_ms": 0}
  }
}
```

依赖故障示例（DB 挂掉 → 503）：

```bash
$ curl -i http://localhost:8000/readiness
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "ready": false,
  "status": "not_ready",
  "checks": {
    "db": {"status": "error", "latency_ms": 1002, "error": "timeout >1000ms"},
    "redis": {"status": "ok", "latency_ms": 1},
    "alembic": {"status": "ok", "current": "...", "head": "..."},
    "payment": {"status": "skipped", "mode": "mock"},
    "sms": {"status": "skipped", "mode": "mock"}
  }
}
```

### Kubernetes Deployment 样例

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yiluan-api
spec:
  template:
    spec:
      containers:
        - name: api
          image: yiluanacr.azurecr.io/yiluan-backend:latest
          ports:
            - containerPort: 8000
          # liveness：失败 → 重启 Pod；不查 DB/Redis（避免依赖闪断把 Pod 杀光）
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          # readiness：失败 → 摘流量；查 5 项依赖
          readinessProbe:
            httpGet:
              path: /readiness
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 2   # 必须 ≥ readiness 内部 1.5s 预算 + 余量
            failureThreshold: 2
            successThreshold: 1
          # startup：冷启动慢时给一段缓冲（lifespan 加 scheduler/pubsub 启动）
          startupProbe:
            httpGet:
              path: /health
              port: 8000
            failureThreshold: 30
            periodSeconds: 2
```

### Azure Container Apps 样例

```yaml
properties:
  configuration:
    ingress:
      external: true
      targetPort: 8000
  template:
    containers:
      - image: yiluanacr.azurecr.io/yiluan-backend:latest
        name: api
        probes:
          - type: Liveness
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 10
            failureThreshold: 3
          - type: Readiness
            httpGet:
              path: /readiness
              port: 8000
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          - type: Startup
            httpGet:
              path: /health
              port: 8000
            failureThreshold: 30
            periodSeconds: 2
```

### Nginx 上游健康检查样例

如果 nginx 直连后端做被动/主动检查：

```nginx
upstream yiluan_backend {
    zone yiluan_backend 64k;
    server 10.0.0.10:8000 max_fails=2 fail_timeout=10s;
    server 10.0.0.11:8000 max_fails=2 fail_timeout=10s;
}

# 主动检查（nginx-plus 或 ngx_http_upstream_check_module）
match readiness_ok {
    status 200;
    body ~ '"ready":\s*true';
}

server {
    location = /healthz {
        proxy_pass http://yiluan_backend/readiness;
        proxy_read_timeout 2s;
        access_log off;
    }
}
```

### 监控建议

- Prometheus 抓 `/metrics`（已有），同时把 `/readiness` 接 blackbox-exporter 做端到端探测
- 告警：连续 3 次 readiness 503 → P1 page；`checks.alembic.status == "error"` 单独告警（说明发版漏跑迁移）
- 不要把 `/readiness` 接到面向用户的 LB 健康检查（短暂 DB 闪断 → 全摘流量风暴）；只接 K8s/ACA 内部调度器即可
