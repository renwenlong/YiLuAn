# YiLuAn Helm Chart（骨架）

> Action #10 — 生产 Helm Chart 骨架。当前版本仅保证 `helm lint` 通过 + YAML 语法正确，**不可直接 `helm install`**。
> 真实镜像仓库 / Secret / StorageClass 等待 B-03（ACR 资源）解锁后补齐。

## 设计要点

### 1. 为什么 Recon Cron 独立 Pod？
资金对账（recon）属于 **强一致 + 长耗时 + 低 QPS** 的工作，与 FastAPI 的高 QPS 在线请求模式截然不同。独立部署的好处：

- **资源隔离**：对账批处理可能阶段性吃 CPU / 内存，不会拖累在线 API 的 SLO；
- **独立排障**：发生异常时可单独重启 / 扩缩，不影响 API；
- **后续可演进为 K8s `CronJob`**：当前以常驻 worker（Deployment）形式跑，由 worker 内部 cron 调度（schedule 注解仅文档化），未来可平滑切到原生 `CronJob`；
- **独立镜像**：worker 镜像可裁剪不必要依赖，减小攻击面。

### 2. PostgreSQL 主从规划
当前骨架声明：

- **primary**：1 副本 `StatefulSet`，绑定持久卷；
- **replica**：2 副本 `StatefulSet`，承担读流量 / 灾备；
- 仅声明拓扑与 PVC，**未启用 streaming replication 配置**。生产化时建议替换为 [CloudNativePG](https://cloudnative-pg.io/) 或 [Bitnami PostgreSQL HA](https://github.com/bitnami/charts/tree/main/bitnami/postgresql-ha)，本骨架的 service / 标签 / 命名约定保持兼容。

### 3. Alertmanager 独立部署
Alertmanager 与 Prometheus 主进程解耦：

- **灰度升级**：Alertmanager 配置 / 版本变更频率高于 Prometheus，独立部署可避免重启抓取；
- **告警高可用**：Alertmanager 集群（gossip）可独立水平扩展；
- **职责分离**：Prometheus 负责采集 + 评估，Alertmanager 负责分组 / 抑制 / 通道路由。

## 目录结构

```
infra/helm/yiluan/
├── Chart.yaml
├── values.yaml
├── README.md
└── templates/
    ├── _helpers.tpl
    ├── api-deployment.yaml
    ├── api-service.yaml
    ├── recon-cron-deployment.yaml
    ├── postgres-statefulset.yaml
    ├── redis-sentinel.yaml
    ├── alertmanager-deployment.yaml
    ├── ingress.yaml
    ├── configmap.yaml
    └── serviceaccount.yaml
```

## Quick Start

### Lint & 渲染

```bash
helm lint infra/helm/yiluan -f infra/helm/yiluan/values.staging.yaml
helm template test infra/helm/yiluan \
  -f infra/helm/yiluan/values.staging.yaml > /tmp/staging.yaml
```

### Staging 安装

```bash
helm upgrade --install yiluan ./infra/helm/yiluan \
  -f infra/helm/yiluan/values.staging.yaml \
  -n yiluan-staging --create-namespace
```

### Production 安装

```bash
# 1. 先把生产凭证装到 Secret（强烈推荐 External Secrets Operator + KMS）
kubectl -n yiluan-prod create secret generic yiluan-prod-secrets \
  --from-literal=JWT_SECRET_KEY=... \
  --from-literal=DATABASE_URL=... \
  --from-literal=REDIS_URL=... \
  --from-literal=WECHAT_PAY_APIV3_KEY=... \
  --from-file=WECHAT_PAY_PRIVATE_KEY=./apiclient_key.pem \
  --from-literal=WECHAT_PAY_MCH_ID=... \
  --from-literal=WECHAT_PAY_SERIAL_NO=... \
  --from-literal=ALIYUN_SMS_ACCESS_KEY_ID=... \
  --from-literal=ALIYUN_SMS_ACCESS_KEY_SECRET=...

# 2. 安装（values.production.yaml 中已 existingSecret: yiluan-prod-secrets）
helm upgrade --install yiluan ./infra/helm/yiluan \
  -f infra/helm/yiluan/values.production.yaml \
  -n yiluan-prod --create-namespace
```

## HorizontalPodAutoscaler

v0.2 起加入 `templates/hpa.yaml`，作用于 api Deployment：

- 仅当 `autoscaling.enabled = true` 时渲染（staging 默认关闭，production 默认开启）；
- 默认目标 CPU 利用率 **70%**、内存利用率 **80%**；
- 默认副本区间 `minReplicas: 2 / maxReplicas: 10`，production overrides 升至 `3 / 20`；
- 支持 `autoscaling.behavior` 自定义 scaleUp/scaleDown 策略；
- 集群必须安装 `metrics-server`，否则内存/CPU 指标无法采集。

开启 HPA 后请确保 `api.replicaCount` 与 `autoscaling.minReplicas` 协调（首次发布以 `minReplicas` 为准）。

## ⚠️ 关于敏感凭证

**禁止**把 JWT_SECRET_KEY、DATABASE_URL、REDIS_URL、WECHAT_PAY_*、ALIYUN_SMS_* 等凭证以明文写入任何提交到 Git 的 `values*.yaml`。

推荐做法（按推荐度排序）：

1. **External Secrets Operator** + 阿里云 KMS / HashiCorp Vault：声明式管理，最易审计；
2. **SealedSecrets**：可加密提交到 Git；
3. **`kubectl create secret generic`** 手工创建一次性 Secret，然后在 values 中通过 `secrets.existingSecret` 引用。

Chart 中的 `secrets.data` 字段仅供本地 dev / staging 临时使用；production 必须使用 `existingSecret`。

## 待办（B-03 ACR 资源到位后）

- [ ] 替换 `values.yaml` 中 `PLACEHOLDER_REGISTRY/*` 为真实 ACR 仓库地址；
- [ ] 创建并填入 `imagePullSecrets`（ACR docker-registry secret）；
- [ ] 填入 `postgres.persistence.storageClass`（如 `alicloud-disk-essd`）；
- [ ] 创建 `postgres.auth.existingSecret` 与 `redis.auth.existingSecret`，包含规定 keys；
- [ ] 替换 `ingress.host` 为正式域名，开启 TLS（cert-manager / 自管证书）；
- [ ] 引入 PG HA operator（CNPG）替换骨架 StatefulSet，或显式配置 streaming replication；
- [ ] Alertmanager `config` 接入真实 receiver（飞书 / 钉钉 / 邮件 / PagerDuty）；
- [ ] 增补 `NetworkPolicy` / `PodDisruptionBudget` / `HorizontalPodAutoscaler`；
- [ ] CI 集成 `helm lint` + `helm template | kubeconform` 校验。

## Backend Environment Variables（Helm 期望清单）

本节梳理 **后端实际读取** 的全部环境变量（来源：`backend/app/config.py` `Settings(BaseSettings)` + `backend/.env.example` + `backend/app/api/v1/health.py`），用于编写生产 `values.yaml` 时按 secret / configmap 正确分桶注入。

> 命名规则：pydantic-settings 默认 **大小写不敏感** —— Python 字段 `jwt_secret_key` 对应环境变量 `JWT_SECRET_KEY`（`.env.example` 也是大写）。下表统一使用大写形式。
>
> 凡列出 `必需 = ✅` 的项，在 `ENVIRONMENT=production` 下由 `Settings.validate_production_config` 强校验，缺失或仍为开发默认值会拒绝启动。

### 1. 运行时基础

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `ENVIRONMENT` | ✅ | `development` | 运行环境，触发生产校验分支 | configmap | 否 |
| `DEBUG` | ✅（生产必须 `false`） | `true` | FastAPI / 异常细节开关 | configmap | 否 |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan` | 主库连接（asyncpg 异步驱动） | **secret** | 是（含密码） |
| `REDIS_URL` | ✅ | `redis://localhost:6379/0` | 缓存 / 限流 / Pub/Sub | **secret**（若含密码）/ configmap（无密码时） | 视情况 |
| `READINESS_SKIP_MIGRATION_CHECK` | 否 | 空 | `/readyz` 跳过 alembic 迁移检查（紧急回滚用） | configmap | 否 |
| `CORS_ORIGINS` | 否 | `["*"]` | 允许的跨域来源（JSON 数组） | configmap | 否 |
| `EMERGENCY_HOTLINE` | 否 | `4001234567` | F-03 紧急呼叫 fallback 号码 | configmap | 否 |
| `SENTRY_DSN` | 暂未使用，预留 | — | 后端代码尚未集成 Sentry SDK | （留空） | — |
| `LOG_LEVEL` | 暂未使用，预留 | — | 当前以 `DEBUG` 开关替代；如未来引入结构化日志再启用 | configmap | 否 |

### 2. 安全 / JWT / Admin / PII

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `JWT_SECRET_KEY` | ✅（生产禁止默认值） | `dev-secret-key-change-in-production` | JWT HS256 签名密钥（≥32 字符高熵） | **secret** | 是 |
| `JWT_ALGORITHM` | 否 | `HS256` | JWT 签名算法 | configmap | 否 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `30` | access token 过期分钟 | configmap | 否 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 否 | `7` | refresh token 过期天数 | configmap | 否 |
| `ADMIN_API_TOKEN` | ✅（生产应替换） | `dev-admin-token` | 管理 API 口令 | **secret** | 是 |
| `PII_ENVELOPE_KEY` | ✅（生产禁止默认值） | dev `b"x"*32` 的 base64 | ADR-0029 紧急联系人 AES-256-GCM 信封密钥 | **secret**（建议从 KMS 注入） | 是（最高） |
| `PII_HASH_SALT` | ✅（生产禁止默认值） | `yiluan-dev-salt-do-not-use-in-prod` | 手机号 HMAC-SHA256 hash salt | **secret** | 是 |

### 3. 微信支付（B-01 待解锁）

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `PAYMENT_PROVIDER` | ✅ | `mock` | 支付提供商：`mock` / `wechat` | configmap | 否 |
| `WECHAT_PAY_MCH_ID` | `provider=wechat` 时 ✅ | 空 | 微信支付商户号 | **secret** | 是 |
| `WECHAT_PAY_API_KEY_V3` | `provider=wechat` 时 ✅ | 空 | v3 API 密钥（32 字节） | **secret** | 是（最高） |
| `WECHAT_PAY_CERT_SERIAL` | `provider=wechat` 时 ✅ | 空 | 商户 API 证书序列号 | **secret** | 是 |
| `WECHAT_PAY_PRIVATE_KEY_PATH` | `provider=wechat` 时 ✅ | 空 | 商户私钥文件路径（pod 内） | configmap（路径） + **secret**（私钥文件经 secret volume 挂载） | 路径=否 / 文件内容=是 |
| `WECHAT_PAY_NOTIFY_URL` | 生产建议 ✅ | 空 | 异步回调 URL（公网 HTTPS） | configmap | 否 |
| `WECHAT_PAY_PLATFORM_CERT_PATH` | 否 | 空 | 微信平台证书路径（用于验签） | configmap（路径） + **secret**（证书文件经 secret volume 挂载） | 路径=否 / 文件内容=是 |

### 4. 阿里云 SMS（B-02 待解锁）

后端 SMS 字段在 `Settings` 中以通用前缀 `SMS_*` 命名（同时兼容 Aliyun / Tencent，由 `SMS_PROVIDER` 选择）。`.env.example` 中保留了 `ALIYUN_SMS_*` / `TENCENT_SMS_*` 兼容样例，**生产实际生效以 `SMS_*` 为准**。

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `SMS_PROVIDER` | ✅ | `mock` | 短信提供商：`mock` / `aliyun` / `tencent` | configmap | 否 |
| `SMS_ACCESS_KEY` | `provider!=mock` 时 ✅ | 空 | Access Key ID（阿里云）/ Secret ID（腾讯云） | **secret** | 是 |
| `SMS_ACCESS_SECRET` | `provider!=mock` 时 ✅ | 空 | Access Key Secret / Secret Key | **secret** | 是（最高） |
| `SMS_SIGN_NAME` | `provider!=mock` 时 ✅ | 空 | 短信签名名称 | configmap | 否 |
| `SMS_TEMPLATE_CODE` | `provider!=mock` 时 ✅ | 空 | OTP 模板编码（如 `SMS_xxxxxx`） | configmap | 否 |
| `SMS_SDK_APP_ID` | 仅腾讯云 | 空 | 腾讯云短信 SDK App ID | configmap | 否 |

### 5. 微信小程序

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `WECHAT_APP_ID` | 上线小程序后 ✅ | 空 | 小程序 AppID（前端 wx.login → code2session） | configmap | 否 |
| `WECHAT_APP_SECRET` | 上线小程序后 ✅ | 空 | 小程序 AppSecret | **secret** | 是 |

### 6. 对象存储 / CDN

后端目前使用 **Azure Blob Storage**（头像、聊天图片），未集成阿里云 OSS / CDN。

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `AZURE_STORAGE_CONNECTION_STRING` | 启用对象存储后 ✅ | 空 | Azure Blob 连接串（含 AccountKey / SAS） | **secret** | 是（最高） |
| `AZURE_STORAGE_CONTAINER_AVATARS` | 否 | `avatars` | 头像 container 名 | configmap | 否 |
| `AZURE_STORAGE_CONTAINER_CHAT` | 否 | `chat-images` | 聊天图片 container 名 | configmap | 否 |
| `OSS_*` / `CDN_*` | 暂未使用，预留 | — | 如未来切换阿里云 OSS / 接 CDN 时补充 | （留空） | — |

### 7. 资金对账 / Cron / Scheduler

后端的 cron 调度由 APScheduler 在进程内驱动（见 `Settings.scheduler_enabled`），并未通过环境变量配置 cron 表达式；Helm 层面 cron 周期由 `recon-cron-deployment` 模板内 worker 自身控制。

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `SCHEDULER_ENABLED` | 否 | `true` | 是否启用 APScheduler；CLI / 测试可关 | configmap | 否 |
| `RECONCILIATION_CUTOFF` | 否 | `2026-04-28T00:00:00+00:00` | ADR-0032 资金对账历史豁免 cutoff（ISO-8601） | configmap | 否 |
| `RECON_SCHEDULE_CRON` | 暂未使用，预留 | — | 后端未读取；当前由 worker 内置 schedule 控制 | （留空） | — |
| `RECON_ALERT_WEBHOOK` | 暂未使用，预留 | — | 对账异常告警 webhook（计划接入 Alertmanager） | configmap（URL） / **secret**（含 token 时） | 视情况 |
| `PRIVACY_CLEANUP_CRON` | 暂未使用，预留 | — | 后端未读取；隐私数据清理由 cron worker 内部调度 | （留空） | — |

### 8. WebSocket / Pub-Sub（运行时调优）

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `WS_MAX_CONNECTIONS_PER_USER` | 否 | `3` | 单用户最大并发 WS 连接（D-020） | configmap | 否 |
| `WS_PUBSUB_ENABLED` | 否 | `true` | 通知通道 Pub/Sub（多副本必开） | configmap | 否 |
| `WS_PUBSUB_CHANNEL` | 否 | `yiluan:ws:notifications` | 通知 Pub/Sub channel | configmap | 否 |
| `WS_CHAT_PUBSUB_ENABLED` | 否 | `true` | 聊天 Pub/Sub（多副本必开） | configmap | 否 |
| `WS_CHAT_PUBSUB_CHANNEL` | 否 | `yiluan:ws:chat` | 聊天 Pub/Sub channel | configmap | 否 |

### 9. Apple Sign-In / APNs

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `APPLE_TEAM_ID` | iOS 上线 ✅ | 空 | 10 字符 Apple Developer Team ID | configmap | 否 |
| `APPLE_CLIENT_ID` | iOS 上线 ✅ | 空 | Service ID / Bundle ID（JWT `aud`） | configmap | 否 |
| `APPLE_JWKS_URL` | 否 | `https://appleid.apple.com/auth/keys` | Apple JWKS 端点 | configmap | 否 |
| `APPLE_ISSUER` | 否 | `https://appleid.apple.com` | Apple JWT issuer | configmap | 否 |
| `APPLE_MOCK_VERIFY` | 否 | `false` | 跳过 JWKS 签名校验（仅 dev/test） | configmap | 否 |
| `APNS_KEY_ID` | 启用推送 ✅ | 空 | APNs Auth Key ID | **secret** | 是 |
| `APNS_TEAM_ID` | 启用推送 ✅ | 空 | APNs Team ID | configmap | 否 |
| `APNS_BUNDLE_ID` | 否 | `com.yiluan.app` | iOS Bundle ID | configmap | 否 |

### 10. 评分权重（F-04）

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `REVIEW_WEIGHT_PUNCTUALITY` | 否 | `0.25` | 守时维度权重 | configmap | 否 |
| `REVIEW_WEIGHT_PROFESSIONALISM` | 否 | `0.25` | 专业维度权重 | configmap | 否 |
| `REVIEW_WEIGHT_COMMUNICATION` | 否 | `0.25` | 沟通维度权重 | configmap | 否 |
| `REVIEW_WEIGHT_ATTITUDE` | 否 | `0.25` | 态度维度权重 | configmap | 否 |

### 11. 监控 / 可观测

后端 `prometheus_client` 直接以 `/metrics` HTTP 端点暴露指标，不主动推送，**未读取** `PROMETHEUS_PUSHGATEWAY_URL` / `METRICS_ENABLED` 环境变量。

| 变量名 | 必需 | 默认值 | 用途 | Helm 注入 | 敏感 |
| --- | --- | --- | --- | --- | --- |
| `PROMETHEUS_PUSHGATEWAY_URL` | 暂未使用，预留 | — | 当前走 pull 模式；如未来需要 Pushgateway（短任务）再启用 | configmap | 否 |
| `METRICS_ENABLED` | 暂未使用，预留 | — | 后端未读取；指标始终随 `/metrics` 暴露 | configmap | 否 |

---

## Helm values.yaml 注入示例

以下示例把上表全部变量分成 `secrets`（敏感、必须以 k8s Secret 注入）、`configMap`（非敏感、可入 ConfigMap / Git）、`env`（容器层 envFrom 装配）三段。占位符用 `__FILL__` 标注。

```yaml
# values.production.yaml（示例片段，不在本骨架内生效，仅供 B-03 后参考）

secrets:
  # 由 ops 或 sealed-secrets / external-secrets 创建，**不要进 git**
  yiluan-api-secrets:
    DATABASE_URL: "postgresql+asyncpg://yiluan:__FILL__@yiluan-postgres-primary:5432/yiluan"
    REDIS_URL: "redis://:__FILL__@yiluan-redis:6379/0"
    JWT_SECRET_KEY: "__FILL__base64-rand-64__"
    ADMIN_API_TOKEN: "__FILL__"
    PII_ENVELOPE_KEY: "__FILL__base64-32B__"
    PII_HASH_SALT: "__FILL__high-entropy__"
    # B-01 微信支付
    WECHAT_PAY_MCH_ID: "__FILL__"
    WECHAT_PAY_API_KEY_V3: "__FILL__"
    WECHAT_PAY_CERT_SERIAL: "__FILL__"
    # B-02 阿里云 SMS
    SMS_ACCESS_KEY: "__FILL__"
    SMS_ACCESS_SECRET: "__FILL__"
    # 微信小程序
    WECHAT_APP_SECRET: "__FILL__"
    # 对象存储
    AZURE_STORAGE_CONNECTION_STRING: "__FILL__"
    # APNs
    APNS_KEY_ID: "__FILL__"

  # 私钥 / 证书文件以 secret volume 形式挂载到 pod；仅 PATH 进 configmap
  yiluan-wechatpay-files:
    apiclient_key.pem: |
      -----BEGIN PRIVATE KEY-----
      __FILL__
      -----END PRIVATE KEY-----
    wechatpay_platform_cert.pem: |
      -----BEGIN CERTIFICATE-----
      __FILL__
      -----END CERTIFICATE-----

configMap:
  yiluan-api-config:
    # 运行时基础
    ENVIRONMENT: "production"
    DEBUG: "false"
    CORS_ORIGINS: '["https://app.yiluan.example.com","https://admin.yiluan.example.com"]'
    EMERGENCY_HOTLINE: "4001234567"
    # JWT
    JWT_ALGORITHM: "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: "30"
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: "7"
    # 支付
    PAYMENT_PROVIDER: "wechat"
    WECHAT_PAY_PRIVATE_KEY_PATH: "/etc/yiluan/wechatpay/apiclient_key.pem"
    WECHAT_PAY_PLATFORM_CERT_PATH: "/etc/yiluan/wechatpay/wechatpay_platform_cert.pem"
    WECHAT_PAY_NOTIFY_URL: "https://api.yiluan.example.com/api/v1/payments/wechat/notify"
    # SMS
    SMS_PROVIDER: "aliyun"
    SMS_SIGN_NAME: "医路安"
    SMS_TEMPLATE_CODE: "SMS_XXXXXXXXX"
    # 微信小程序
    WECHAT_APP_ID: "wx__FILL__"
    # Azure 容器名
    AZURE_STORAGE_CONTAINER_AVATARS: "avatars"
    AZURE_STORAGE_CONTAINER_CHAT: "chat-images"
    # Scheduler / Recon
    SCHEDULER_ENABLED: "true"
    RECONCILIATION_CUTOFF: "2026-04-28T00:00:00+00:00"
    # WebSocket
    WS_MAX_CONNECTIONS_PER_USER: "3"
    WS_PUBSUB_ENABLED: "true"
    WS_PUBSUB_CHANNEL: "yiluan:ws:notifications"
    WS_CHAT_PUBSUB_ENABLED: "true"
    WS_CHAT_PUBSUB_CHANNEL: "yiluan:ws:chat"
    # Apple
    APPLE_TEAM_ID: "__FILL__"
    APPLE_CLIENT_ID: "com.yiluan.app"
    APPLE_JWKS_URL: "https://appleid.apple.com/auth/keys"
    APPLE_ISSUER: "https://appleid.apple.com"
    APPLE_MOCK_VERIFY: "false"
    APNS_TEAM_ID: "__FILL__"
    APNS_BUNDLE_ID: "com.yiluan.app"
    # 评分权重
    REVIEW_WEIGHT_PUNCTUALITY: "0.25"
    REVIEW_WEIGHT_PROFESSIONALISM: "0.25"
    REVIEW_WEIGHT_COMMUNICATION: "0.25"
    REVIEW_WEIGHT_ATTITUDE: "0.25"

# api-deployment.yaml 中通过 envFrom 一次性装配
api:
  envFrom:
    - secretRef:
        name: yiluan-api-secrets
    - configMapRef:
        name: yiluan-api-config
  volumes:
    - name: wechatpay-files
      secret:
        secretName: yiluan-wechatpay-files
  volumeMounts:
    - name: wechatpay-files
      mountPath: /etc/yiluan/wechatpay
      readOnly: true

recon:
  envFrom:
    - secretRef:
        name: yiluan-api-secrets
    - configMapRef:
        name: yiluan-api-config
```

---

## 敏感变量清单（必须以 k8s Secret 注入；禁止进 ConfigMap、禁止进 Git）

下列变量包含密码、密钥、商户凭证、Access Key 或 PII 加密 key，**任一项泄漏都会造成严重事故**。生产部署 **必须** 满足：

1. 仅以 **k8s `Secret`**（或 sealed-secrets / external-secrets / KMS Secret Manager）注入；
2. 不写入 `values.yaml` 任何明文位置，更不可提交到 Git；
3. 容器内通过 `envFrom: secretRef` 或 `valueFrom: secretKeyRef` 装配；
4. 私钥 / 证书等 **文件型** 凭证以 `Secret` + `volumeMount` 挂载，环境变量仅传递路径。

敏感变量清单（按风险等级降序）：

- **🔴 Tier-1（最高）：泄漏即资金 / PII 灾难**
  - `PII_ENVELOPE_KEY` — ADR-0029 信封密钥，泄漏后历史紧急联系人手机号可被解密
  - `PII_HASH_SALT` — phone hash 反查盐
  - `WECHAT_PAY_API_KEY_V3` — 微信支付 v3 API 密钥
  - `WECHAT_PAY_PRIVATE_KEY_PATH` 指向的 **`apiclient_key.pem` 文件内容**
  - `SMS_ACCESS_SECRET` — 阿里云 / 腾讯云 Secret Key（拥有完整发送权限，可被刷量）
  - `AZURE_STORAGE_CONNECTION_STRING` — 含 AccountKey，泄漏即对象存储完全失守

- **🟠 Tier-2（高）：泄漏即账号 / 会话被劫持**
  - `JWT_SECRET_KEY` — 泄漏可伪造任意用户 token
  - `ADMIN_API_TOKEN` — 后台管理接口口令
  - `DATABASE_URL` — 含 Postgres 密码
  - `REDIS_URL` — 若启用 ACL / 密码，含 Redis 密码
  - `WECHAT_PAY_MCH_ID` / `WECHAT_PAY_CERT_SERIAL` — 与上述私钥/v3 key 组合后可冒充商户
  - `SMS_ACCESS_KEY` — 阿里云 / 腾讯云 Access Key ID
  - `WECHAT_APP_SECRET` — 小程序服务端凭证
  - `APNS_KEY_ID` 对应的 **APNs Auth Key (.p8) 文件内容**

- **🟡 Tier-3（中）：泄漏需配合其他凭证才造成损失，但仍应 Secret 化**
  - `WECHAT_PAY_PLATFORM_CERT_PATH` 指向的平台证书文件（公开半公开，但仍按 Secret 管理避免被替换）
  - 任何包含 token 的 `RECON_ALERT_WEBHOOK`（启用后）

**配套 ConfigMap 即可** 的变量（可入 Git，便于 review）：所有 `*_PATH`、`*_URL`（不含 token）、`SCHEDULER_*`、`WS_*`、`REVIEW_WEIGHT_*`、`APPLE_*`（除 APNs 私钥）、`APNS_TEAM_ID` / `APNS_BUNDLE_ID`、`SMS_PROVIDER` / `SMS_SIGN_NAME` / `SMS_TEMPLATE_CODE`、`PAYMENT_PROVIDER`、`ENVIRONMENT` / `DEBUG` / `CORS_ORIGINS` / `EMERGENCY_HOTLINE` / `RECONCILIATION_CUTOFF`、`AZURE_STORAGE_CONTAINER_*`、`WECHAT_APP_ID`、`JWT_ALGORITHM` / `JWT_*_EXPIRE_*`。
