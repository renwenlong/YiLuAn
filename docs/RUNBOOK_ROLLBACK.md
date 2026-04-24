# RUNBOOK: 回滚预案 (Rollback)

> **配套文档:** `docs/decisions/ADR-0028-canary-release-and-rollback.md`
> **适用阶段:** 灰度发布期间 + 上线后 24h 观察窗口
> **目标 SLA:** 流量层回滚 ≤ 30 秒；代码回滚 ≤ 5 分钟；DB 回滚 ≤ 30 分钟

---

## 0. 通用前置

- 值班 Ops **必须**已登录跳板机, 持有 sudo 权限
- 值班 Backend **必须**能访问 git 仓库 + 镜像仓库
- 企业微信值班群至少 1 名 PM / Arch 在线
- 操作前: 截图 Grafana 告警面板 + Alertmanager 当前 firing 列表, 存入 `release-log-YYYY-MM-DD.md`

---

## 场景 A：流量层回滚（首选, 最快）

**适用:** 新版本只是部分指标恶化, 代码与 DB schema 都还能跑, 但需要立即把用户从新版本拉走。

### 触发条件（任一即触发）

| 来源 | 条件 |
|---|---|
| 自动 | HTTP 5xx 错误率 > **1%** 持续 **2 分钟**（按 `X-Canary-Pool=backend_new` 维度统计） |
| 自动 | Prometheus 告警 `ReadinessProbeFailure` 触发（P0, /readiness 失败 > 2 分钟） |
| 手动 | 任一 P1 告警持续 **5 分钟**未自愈 |
| 手动 | 业务指标异常但未到自动阈值（如订单创建率下跌 50%, 客户端用户大规模反馈 ≥10 起） |

### 精确命令

```bash
# 1. 登录 nginx 主机
ssh ops@nginx-prod-01

# 2. 编辑灰度配置, 启用 "Rollback" 段, 注释当前 Stage 段
sudo vi /etc/nginx/conf.d/yiluan-canary.conf
# 把当前激活的 split_clients 块全部注释,
# 启用文件末尾的 "Rollback (紧急回滚)" 块, 即:
#   split_clients "${canary_key}" $canary_pool {
#       *       "backend_stable";
#   }

# 3. 校验语法
sudo nginx -t

# 4. 平滑 reload (不丢现有连接)
sudo nginx -s reload

# 5. 立即记录到 release log
echo "$(date -Iseconds)  ROLLBACK A executed by $(whoami)" \
    | sudo tee -a /var/log/yiluan/release-events.log
```

### 验证（必须 3 项全过才算回滚成功）

```bash
# V1: 100 次请求采样, backend_new 出现率应 ≈ 0
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{header_x-canary-pool}\n" \
       https://api.yiluan.example.com/api/v1/health
done | sort | uniq -c
# 期望: backend_stable 100, backend_new 0

# V2: 5xx 率 5 分钟内回落到基线
# 在 Grafana "YiLuAn / Canary" dashboard 看 backend_new 维度的 5xx
# 应观测到 RPS -> 0 (无新请求进新版本)

# V3: Alertmanager 告警自愈
# 进入 Alertmanager UI, 确认触发的 P0/P1 告警进入 resolved
```

### 通知模板（企业微信值班群）

```
[ROLLBACK / 场景A 流量层]
时间: 2026-XX-XX HH:MM CST
触发: <自动/手动> + <告警名 / 业务现象>
执行人: @<ops-name>
当前状态: 流量已 100% 切回 backend_stable
影响窗口: ~<X> 分钟, 估算受影响用户 <Y> 人
后续: <复盘人> 将于 1h 内产出初步根因分析, 暂停灰度直至 ADR-0028 升级版 watcher 上线
```

---

## 场景 B：代码回滚（流量层回滚后仍出现问题, 或新代码污染 stable）

**适用:** 流量切回 stable 后问题仍未消除（可能 stable 也共享了新版本写入的脏数据 / 配置 / 缓存）。也用于灰度结束后才发现的退化。

### 触发条件

- 场景 A 执行后, 5 分钟内业务指标未恢复
- 灰度已 100% 完成, 但发现新代码导致严重 bug（不影响 schema）
- 安全漏洞需立即下线新代码

### 精确命令

```bash
# 0. 在值班群口头宣布 "进入场景 B, 需要 5 分钟"
# 1. 登录每台后端主机
ssh ops@backend-prod-01   # 重复 backend-prod-02, backend-prod-03 ...

# 2. 切到部署目录
cd /opt/yiluan/backend

# 3. 拉上一稳定版镜像 tag (从 release-log 中查找上个 stable tag, 例如 v1.4.2)
export PREV_TAG=v1.4.2
docker pull registry.example.com/yiluan/backend:${PREV_TAG}

# 4. 更新 docker-compose 中 stable 与 new 都指向 PREV_TAG
sudo sed -i "s|yiluan/backend:.*|yiluan/backend:${PREV_TAG}|g" docker-compose.prod.yml

# 5. 滚动重启 (per host, 避免同时全停)
docker compose -f docker-compose.prod.yml up -d --no-deps backend_stable_1 backend_stable_2
sleep 10
docker compose -f docker-compose.prod.yml up -d --no-deps backend_new_1 backend_new_2

# 6. 清 Redis 缓存 (如果新版本写入了不兼容的 cache schema)
redis-cli -h redis-prod-01 --scan --pattern "v2:*" | xargs -r redis-cli -h redis-prod-01 DEL
```

### 验证

```bash
# V1: 镜像版本回滚成功
for h in backend-prod-01 backend-prod-02 backend-prod-03; do
  ssh ops@$h "docker ps --format '{{.Image}}' | grep yiluan/backend"
done
# 期望: 全部输出 yiluan/backend:v1.4.2

# V2: /version (或 /health 中 version 字段) 显示旧版本号
curl -s https://api.yiluan.example.com/health | jq .version
# 期望: "1.4.2"

# V3: 后端测试基线一致
# 由 QA 在 staging 验证: pytest -q 应与 v1.4.2 基线 (xxx passed) 完全一致
```

### 通知模板

```
[ROLLBACK / 场景B 代码层]
时间: 2026-XX-XX HH:MM CST
触发: 场景A 后业务指标未恢复 / <其他原因>
执行人: @<ops-name>, 协助: @<backend-name>
回滚版本: 新版本 vX.Y.Z -> 上一稳定版 vA.B.C
受影响窗口: 约 <N> 分钟
后续: 1) Backend 起 hotfix 分支调查根因; 2) 本周不再尝试灰度; 3) 复盘会议 24h 内
```

---

## 场景 C：数据库回滚（最重, 最慎)

**适用:** 新版本伴随了破坏性 schema 变更, 且确认问题源于 schema / 数据。**优先选择前向修复**（hotfix migration）, 只有在前向修复明显不可行时才执行 alembic downgrade。

### 触发条件

- 场景 A + B 都执行后, 旧代码无法兼容新 schema 导致持续 5xx
- alembic upgrade 后出现数据损坏（如外键不匹配、enum 值未识别）
- 安全或合规要求立即回退某次 schema 变更

### ⚠️ 前置必读

1. **先看 `docs/MIGRATION_REVERSIBILITY_REPORT.md`**, 确认目标 revision 是否标记为 `reversible`。
   - 标记 `reversible`: 可执行 `alembic downgrade`
   - 标记 `irreversible` / `manual`: **不要**直接 downgrade, 走"前向修复 + 数据补偿"
2. **必须有最近一次 PG 全量备份**, 否则禁止任何破坏性 DDL。
3. **执行前对 PG 主库做一次 `pg_dump`**（差异备份）, 用于事故复盘。
4. ADR-0028 §4.5 定义的 Expand-Contract 已要求"破坏性变更两步发布", 因此**正常情况下灰度期内不会出现破坏性变更**, 此场景仅作兜底。

### 精确命令（仅当目标 revision 可逆）

```bash
# 0. 锁住写入 (避免回滚过程中出现新数据)
# 在 nginx 上把 backend_stable 也指向一个临时 maintenance upstream
# (返回 503 + Retry-After), 详见 nginx.canary.conf.template "maintenance" 段

# 1. 登录 backend 主机, 进入 alembic 上下文
ssh ops@backend-prod-01
cd /opt/yiluan/backend

# 2. 全量备份当前 PG (差异)
PGPASSWORD=*** pg_dump -h pg-prod-01 -U yiluan -d yiluan_prod \
    --format=custom \
    --file=/var/backups/yiluan/pre-rollback-$(date +%Y%m%d-%H%M%S).dump

# 3. 查看当前 head
docker compose exec backend_stable_1 alembic current
# 假设当前: b7c8d9e0f1a2 (head)
# 目标回滚到: a50c6c117291

# 4. 执行 downgrade
docker compose exec backend_stable_1 alembic downgrade a50c6c117291

# 5. 立即重启所有 backend 进程 (清 SQLAlchemy 元数据缓存)
docker compose restart backend_stable_1 backend_stable_2 backend_new_1 backend_new_2

# 6. 解除维护页, 流量切回 backend_stable
sudo vi /etc/nginx/conf.d/yiluan-canary.conf  # 启用 Rollback 段
sudo nginx -t && sudo nginx -s reload
```

### 验证

```bash
# V1: alembic current 是回滚目标
docker compose exec backend_stable_1 alembic current
# 期望: a50c6c117291

# V2: pytest 关键路径冒烟 (在 staging 跑一次)
cd backend && python -m pytest -q tests/test_health.py tests/test_orders.py

# V3: 业务流冒烟
# 用 QA 提供的 smoke account 走完: 登录 -> 下单 -> 支付回调 -> 订单详情
# 全程 200 + 状态机正确
```

### 通知模板

```
[ROLLBACK / 场景C DB层] *** P0 ***
时间: 2026-XX-XX HH:MM CST
触发: <场景A+B 失败 / 数据损坏 / 合规>
执行人: @<ops-name>, DBA: @<dba-name>, 决策: @<arch-name> + @<pm-name>
回滚 revision: <from> -> <to>
全量备份: /var/backups/yiluan/pre-rollback-XXXXXX.dump (大小 <Z>GB)
维护窗口: HH:MM - HH:MM (用户侧返回 503 + Retry-After)
影响数据: <说明丢失的数据范围, 如 "HH:MM 之后的新订单 N 条已隔离, 待人工补偿">
复盘会议: 24h 内, 由 Arch 主持
```

---

## 附录：常用查询

```bash
# 当前流量灰度比例 (按桶统计 5 分钟 RPS)
curl -s "http://prometheus:9090/api/v1/query" \
  --data-urlencode 'query=sum by (pool) (rate(http_requests_total[5m]))'

# 查看上一稳定 release tag
git tag --sort=-creatordate | grep '^v' | head -3

# 查看 Alertmanager 当前 firing
curl -s http://alertmanager:9093/api/v2/alerts | jq '.[] | {alertname: .labels.alertname, status: .status.state}'
```

---

**版本:**
- 2026-04-24 v1 初版（ADR-0028 配套）
