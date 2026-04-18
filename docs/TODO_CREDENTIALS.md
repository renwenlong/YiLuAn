# 医路安待办事项（需用户提供）

## 微信支付凭证（P0 - 阻塞真实上线）

下列字段是 `WechatPaymentProvider` 切换到 `settings.payment_provider="wechat"`
后正常工作所需的**全部**配置项。环境变量名与 `app.config.Settings`
中的字段对应。也可通过常量
`app.services.providers.payment.wechat.REQUIRED_PRODUCTION_SETTINGS`
程序化获取。

| 环境变量 | settings 字段 | 说明 |
| --- | --- | --- |
| `WECHAT_APP_ID` | `wechat_app_id` | 微信小程序 AppID |
| `WECHAT_PAY_MCH_ID` | `wechat_pay_mch_id` | 微信支付商户号 |
| `WECHAT_PAY_API_KEY_V3` | `wechat_pay_api_key_v3` | APIv3 32 字节密钥（用于回调 AES-GCM 解密） |
| `WECHAT_PAY_CERT_SERIAL` | `wechat_pay_cert_serial` | 商户 API 证书序列号 |
| `WECHAT_PAY_PRIVATE_KEY_PATH` | `wechat_pay_private_key_path` | 商户 API 私钥 PEM 文件绝对路径（容器内挂载点） |
| `WECHAT_PAY_NOTIFY_URL` | `wechat_pay_notify_url` | 公网 HTTPS 回调 URL，例：`https://api.example.com/api/v1/payments/wechat/callback` |
| `WECHAT_PAY_PLATFORM_CERT_PATH` | `wechat_pay_platform_cert_path` | 微信平台证书 PEM 路径（用于校验回调签名） |

切换步骤：
1. 上述字段全部填入生产环境（推荐 Azure Key Vault + 容器环境变量挂载）。
2. 设置 `PAYMENT_PROVIDER=wechat`。
3. `Settings` 自带启动期校验（见 `config.py`）：缺任一字段会在进程启动失败，不会出现 silent fallback。
4. 部署后跑回归冒烟：下单 → 支付 → 回调 → 退款。回调幂等保护见 `payment_callback_log` 表。

## 短信服务凭证（P0）
- [ ] 阿里云/腾讯云 SMS AccessKey
- [ ] 短信签名
- [ ] 短信模板 ID

### 阿里云 SMS（P0-2 追加，2026-04-18）

下列字段是 `AliyunSMSProvider` 切换到 `settings.sms_provider="aliyun"` 后正常工作所需的**全部**配置项。
环境变量名与 `app.config.Settings` 中的字段对应。也可通过常量
`app.services.providers.sms.aliyun.REQUIRED_PRODUCTION_SETTINGS` 程序化获取。

| 环境变量 | settings 字段 | 默认 | 说明 |
| --- | --- | --- | --- |
| `SMS_ACCESS_KEY` | `sms_access_key` | `""` | 阿里云 RAM 子账号 AccessKey ID（最小权限：仅 Dysmsapi） |
| `SMS_ACCESS_SECRET` | `sms_access_secret` | `""` | 阿里云 AccessKey Secret，写入 Azure Key Vault |
| `SMS_REGION` | `sms_region` | `cn-hangzhou` | Dysmsapi 区域 |
| `SMS_SIGN_NAME` | `sms_sign_name` | `""` | 已审核通过的短信签名（如「医路安」） |
| `SMS_TEMPLATE_CODE` | `sms_template_code` | `""` | OTP 模板 ID（如 `SMS_123456789`） |
| `SMS_NOTIFY_TEMPLATE_CODE` | `sms_notify_template_code` | `""` | 通用通知（订单状态、提醒）模板 ID |
| `SMS_RATE_LIMIT_PER_MINUTE` | `sms_rate_limit_per_minute` | `1` | 单号 60 秒内最多发送条数 |
| `SMS_RATE_LIMIT_PER_HOUR` | `sms_rate_limit_per_hour` | `5` | 单号 1 小时内最多发送条数 |

切换步骤：
1. 上述字段全部填入生产环境（推荐 Azure Key Vault + 容器环境变量挂载）。
2. 设置 `SMS_PROVIDER=aliyun`。
3. `Settings` 自带启动期校验（见 `config.py`，`validate_production_config`）：缺任一字段会在进程启动失败，不会出现 silent fallback。
4. **当前 `AliyunSMSProvider` 仍是占位实现**：`send_otp` / `send_notification` 会抛 `NotImplementedError` 并把 `REQUIRED_PRODUCTION_SETTINGS` 列表写入 ERROR 日志（手机号已脱敏）。激活前必须实现真实 Dysmsapi HMAC-SHA1 调用 + 结构化错误映射（见模块底部 TODO）。
5. 部署后跑回归冒烟：登录 → 收 OTP → 验证。注意验证 60s + 1h 限频在 Redis 集群中跨副本生效。

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
> Provider 抽象详见 `backend/app/services/providers/payment/`。
> 运维段对齐 `docs/deployment.md` §16 环境变量清单 与 `.github/workflows/deploy.yml`。
