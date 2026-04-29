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

## 安装命令示例（仅文档，当前不可运行）

```bash
# 1. lint
helm lint infra/helm/yiluan/

# 2. 渲染查看
helm template yiluan infra/helm/yiluan/ \
  --namespace yiluan --create-namespace \
  --set api.image.repository=registry.cn-beijing.aliyuncs.com/yiluan/api \
  --set api.image.tag=0.1.0

# 3. 安装（B-03 解锁后）
helm upgrade --install yiluan infra/helm/yiluan/ \
  --namespace yiluan --create-namespace \
  --values values.production.yaml
```

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
