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
