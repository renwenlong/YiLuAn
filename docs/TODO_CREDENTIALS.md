# 医路安待办事项（需用户提供）

## 微信支付凭证（P0 - 阻塞真实上线）
- [ ] 微信支付商户号（mch_id）
- [ ] APIv3 密钥
- [ ] 商户证书序列号
- [ ] 商户私钥文件（.pem）
- [ ] 支付回调通知 URL（需公网域名 + HTTPS）
- [ ] 微信小程序 AppID（已有配置项，待填入真实值）

## 短信服务凭证（P0）
- [ ] 阿里云/腾讯云 SMS AccessKey
- [ ] 短信签名
- [ ] 短信模板 ID

## 生产环境（P0）
- [ ] Azure 订阅 / 资源组
- [ ] 域名（已备案）
- [ ] SSL 证书（或 Azure 自动签发）

## 应用发布（P1）
- [ ] 微信小程序 AppID + AppSecret（真实值）
- [ ] Apple Developer 账号（iOS 发布）

## 运维 / 生产部署凭证（P0-3 追加，2026-04-18）

> 来源：今日晨会 Action Item #3。所有项**负责人 = 用户**，状态默认 ❌ 未提供。
> 凭证就位后，将本节对应项打勾并填入 Azure Key Vault；GitHub Secrets 同步配置。

### Azure 资源凭证

- [ ] ❌ Azure 订阅 ID（`AZURE_SUBSCRIPTION_ID`） — 负责人：用户
- [ ] ❌ Azure 资源组名称（建议 `yiluan-rg`，区域 `eastasia`） — 负责人：用户
- [ ] ❌ Azure Service Principal JSON（`AZURE_CREDENTIALS`，用于 GitHub Actions `azure/login`） — 负责人：用户
- [ ] ❌ ACR 名称 + 登录用户名（`ACR_USERNAME`） — 负责人：用户
- [ ] ❌ ACR 密码 / token（`ACR_PASSWORD`，建议改用 managed identity） — 负责人：用户
- [ ] ❌ Azure Key Vault 名称（建议 `yiluan-kv`） — 负责人：用户
- [ ] ❌ Container Apps 环境名（建议 `yiluan-env`） — 负责人：用户
- [ ] ❌ PostgreSQL Flexible Server 管理员账号 + 初始密码 — 负责人：用户
- [ ] ❌ Staging DB 连接串（`STAGING_DATABASE_URL`，写入 GitHub Secrets） — 负责人：用户
- [ ] ❌ Production DB 连接串（`PRODUCTION_DATABASE_URL`，写入 GitHub Secrets） — 负责人：用户
- [ ] ❌ Azure Cache for Redis 实例名 + access key（写入 Key Vault） — 负责人：用户

### 域名 / SSL / 网络

- [ ] ❌ 生产 API 域名（建议 `api.yiluan.com`，需已 ICP 备案） — 负责人：用户
- [ ] ❌ Staging API 域名（建议 `api-staging.yiluan.com`） — 负责人：用户
- [ ] ❌ 域名 DNS 控制权（用于配置 CNAME 到 Front Door / Container Apps） — 负责人：用户
- [ ] ❌ SSL 证书来源决策（Azure Front Door 托管证书 / 自带证书） — 负责人：用户

### 微信小程序后台域名配置

> 域名确定后必须在微信公众平台 → 开发设置中加入白名单，否则小程序请求失败。

- [ ] ❌ request 合法域名：`https://api.yiluan.com`、`https://api-staging.yiluan.com` — 负责人：用户
- [ ] ❌ socket 合法域名：`wss://api.yiluan.com`、`wss://api-staging.yiluan.com` — 负责人：用户
- [ ] ❌ uploadFile 合法域名（如有 OSS/Blob 直传）：待补 — 负责人：用户
- [ ] ❌ downloadFile 合法域名：待补 — 负责人：用户
- [ ] ❌ 微信支付 notify_url 域名（`https://api.yiluan.com/api/v1/payments/notify`）已在商户平台登记 — 负责人：用户
- [ ] ❌ 业务域名校验文件已上传到根目录（如商户平台要求） — 负责人：用户

### 监控 / 告警接入

- [ ] ❌ Application Insights 连接串（`APPLICATIONINSIGHTS_CONNECTION_STRING`） — 负责人：用户
- [ ] ❌ Log Analytics Workspace ID + Key — 负责人：用户
- [ ] ❌ 告警接收人邮箱（建议至少 2 人） — 负责人：用户
- [ ] ❌ 告警接收手机号（P0/P1 级短信） — 负责人：用户
- [ ] ❌ 企业微信群机器人 Webhook URL（用于自动推送告警） — 负责人：用户
- [ ] ❌ Sentry DSN（如启用） — 负责人：用户

### GitHub Secrets 汇总（运维需一次性写入）

| Secret 名 | 用途 |
|-----------|------|
| `AZURE_CREDENTIALS` | `azure/login` Service Principal |
| `ACR_USERNAME` / `ACR_PASSWORD` | 推送镜像到 ACR |
| `STAGING_DATABASE_URL` | Staging Alembic 迁移 |
| `PRODUCTION_DATABASE_URL` | Production Alembic 迁移 |

---

> 以上信息准备好后通知团队，Phase 2 真实接入可随时切换。
> 当前所有开发使用 mock provider 先行推进，架构已预留切换能力。
> 运维段对齐 `docs/deployment.md` §16 环境变量清单 与 `.github/workflows/deploy.yml`。
