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
