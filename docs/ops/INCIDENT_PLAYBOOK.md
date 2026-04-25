# YiLuAn 应急 Playbook (Incident Playbook)

> **配套:** `docs/runbook-go-live.md`, `docs/RUNBOOK_ROLLBACK.md`, ADR-0028
> **适用:** 灰度发布期 + 上线后任意时刻
> **目标 SLA(端到端):**
> - DB 主库挂 → 切从库:**RTO ≤ 10 min, RPO ≤ 5 min**(异步同步窗口)
> - Redis 挂 → 降级路径:**RTO ≤ 2 min**(应用侧 fail-open)
> - 第三方支付(微信)不通:**用户感知 ≤ 30s**(限流 + 排队 + 提示)
> - 第三方 SMS(阿里云)不通:**降级到 mock OTP / 备用通道,RTO ≤ 5 min**

每个场景统一结构:**识别信号 → 决策树 → 执行命令 → 验证 → 通报模板**。

---

## §1 DB 主库挂(PG primary down)

### 识别信号

| 来源 | 信号 |
|---|---|
| Alertmanager | `BackendReadinessFail`(/readiness checks.db.status=error)持续 ≥2 min |
| Prometheus | `up{job="postgres-exporter",role="primary"} == 0`(若已部署) |
| 应用日志 | `connection refused` / `OperationalError: server closed the connection` 暴增 |
| 业务 | 全部写接口 503,只读旁路也 503(无 read replica fallback 时) |

### 决策树

```
信号确认 ≥2min?
├─ 是 → 进入"切从库"流程(下方"执行命令")
└─ 否 → 先排查网络/磁盘/连接池,5 min 内未自愈再切
切从库前必须确认:
├─ 从库延迟 (pg_stat_replication) ≤ 5min ?
│   ├─ 是 → 直接切
│   └─ 否(或主库已无法连接) → RPO 超标,需 PM 决策"接受丢数据"或"等主库回血"
└─ 是否有近期 schema 变更? → 若刚 alembic upgrade,优先核对从库已同步到 head
```

### 执行命令(假设阿里云 RDS 主备版,真实命令以云厂商控制台为准)

```bash
# 0. 群里口头宣布:进入应急 §1, 预计 10 分钟
# 1. 切应用入口到"维护页"(503 + Retry-After: 60),避免雪崩写入失败
ssh ops@nginx-prod-01
sudo vi /etc/nginx/conf.d/yiluan-canary.conf  # 启用 maintenance 段
sudo nginx -t && sudo nginx -s reload

# 2. 阿里云 RDS:控制台手动主备切换(或 aliyun cli)
#   - 控制台路径:RDS 实例 → 服务可用性 → 主备切换
#   - CLI: aliyun rds SwitchDBInstanceHA --DBInstanceId <id> --NodeId <slave>
#   实测耗时 30-90s

# 3. 等待新主库可写,更新 backend secret(若 DATABASE_URL 是直连而非 VIP)
#   - 推荐:用 RDS VIP/读写分离地址,这样应用无需重启
#   - 若用直连:更新 KMS 中 DATABASE_URL → 触发 rolling restart

# 4. /readiness 自检(逐台 backend 主机)
for h in backend-prod-01 backend-prod-02 backend-prod-03; do
  ssh ops@$h 'curl -s http://localhost:8000/readiness | jq .checks.db.status'
done
# 期望: 全部 "ok"

# 5. 解除维护页,流量 100% 回到 stable
sudo vi /etc/nginx/conf.d/yiluan-canary.conf  # 启用 stable 段
sudo nginx -t && sudo nginx -s reload
```

### 验证

```bash
# V1: /readiness 全绿
curl -s https://api.yiluan.example.com/readiness | jq '.ready'  # true

# V2: 业务冒烟(QA 智能机或 staging 账号)
#   登录 → 下单 → 支付回调 → 订单详情,全 200

# V3: 复检 alembic_version 与代码 head 一致(避免主备 schema 偏移)
docker compose exec backend_stable_1 alembic current
```

### 通报模板

```
[INCIDENT / §1 DB 主库切换] *** P0 ***
时间: 2026-XX-XX HH:MM CST
触发: <告警名 / 现象>
执行人: @<ops>, DBA: @<dba>, 决策: @<arch> + @<pm>
RPO: <X> 分钟数据可能丢失(从库延迟 <Y>s)
维护窗口: HH:MM - HH:MM(用户侧 503 + Retry-After=60)
当前状态: 切换完成 / 流量已恢复
后续: 1) 复盘 24h 内; 2) 旧主库恢复后做一次 master-master diff 校对
```

---

## §2 Redis 挂(单点或集群整体 down)

### 识别信号

| 来源 | 信号 |
|---|---|
| Alertmanager | `/readiness checks.redis.status=error` ≥1 min |
| 应用日志 | `redis.exceptions.ConnectionError` 暴增 |
| 业务 | 登录 OTP / 排队 / 限流 / WS pubsub 失败;但下单/支付主链路**应该能继续**(取决于代码降级实现) |

### 决策树

```
Redis 影响范围?
├─ 仅 cache(orders detail 等)
│   └─ 应用降级到 DB 直查(QPS 翻 5-10x,DB 连接池要预先扩到 2x)
├─ rate limit / OTP 存储
│   └─ 影响登录 OTP;切换 SMS_PROVIDER=mock 是不可接受的(prod);改用"内存 fallback"或"DB 表 OTP"
└─ WebSocket pubsub
    └─ 实时通知失效,but 业务非阻塞;走"轮询降级"banner 提示 App 刷新
```

### 执行命令

```bash
# 0. 确认 Redis 真挂了(不是网络抖动)
for h in redis-prod-01 redis-prod-02 redis-prod-03; do
  ssh ops@$h 'redis-cli -h localhost ping' || echo "$h DOWN"
done

# 1. 应用层降级开关(需后端预先实现 — 如未实现,本次 prod 上线前必须补)
#   通过 ENV 或 admin API:
#     - REDIS_FAILOPEN=1     -> cache miss 直查 DB,不抛异常
#     - WS_PUBSUB_ENABLED=0  -> 关闭 ws fanout,客户端走轮询
#   触发方式: 改 KMS + rolling restart(估算 3-5 min)

# 2. 重启 Redis(或切到备用实例)
#   阿里云 Tair/Redis 控制台 → 主备切换;或改 REDIS_URL 到备用 endpoint

# 3. /readiness 自检
curl -s https://api.yiluan.example.com/readiness | jq '.checks.redis'
```

### 验证

- `/readiness checks.redis.status == "ok"`
- DB QPS / 连接池监控:确保不超过 80%
- 登录 OTP 真机测试一次

### 通报模板

```
[INCIDENT / §2 Redis 故障] P1
时间: 2026-XX-XX HH:MM CST
影响: 登录 OTP 短暂失败 / 实时通知降级为轮询(用户侧 30s 延迟)
执行人: @<ops>
降级动作: REDIS_FAILOPEN=1 已下发, WS_PUBSUB_ENABLED=0 已关
RTO: <N> 分钟
后续: Redis 恢复后,逐步关掉降级开关
```

> **TODO(prod 上线前):** 验证 backend 是否真的实现了 `REDIS_FAILOPEN` 与 cache 无 Redis 时的降级逻辑;当前代码 `app/main.py` 在 lifespan 中初始化 Redis,失败会让 app 起不来,**这是高风险点**,需后端确认。

---

## §3 第三方支付(微信支付)不通

### 识别信号

| 来源 | 信号 |
|---|---|
| Prometheus | `wechatpay_callback_signature_fail_total` 增长(签名验证失败) |
| 应用日志 | `wechatpayv3.exceptions.*` 5xx 上升 |
| 业务 | 下单后无法跳转支付 / 用户支付完成但订单状态卡在 pending |
| 微信支付平台 | 商户后台公告 "维护中" 或 API 返回 SYSTEM_ERROR |

### 决策树

```
是签名问题 还是 平台 API 真挂?
├─ 签名/证书问题(自家事故)
│   └─ 立即回滚最近一次证书相关 deploy(场景 B 代码层回滚)
└─ 平台真挂(对方事故)
    ├─ 发布"支付暂不可用"前端 banner
    ├─ 限流入口(下单接口 5 QPS,以免雪崩)
    └─ 对已下单未支付的订单延长 expires_at(默认 15min → 1h)
```

### 执行命令

```bash
# 1. 应用层把支付入口标记为"暂不可用"(需后端实现 feature flag)
#    通过 admin API: PATCH /api/v1/admin/feature-flags { "payment_enabled": false }
#    或 ENV: PAYMENT_PROVIDER=mock_unavailable (返回友好错误,不计 5xx)

# 2. 限流(slowapi 已在用):临时降下单 QPS
#    KMS: ORDER_CREATE_RATE_LIMIT="5/minute"
#    rolling restart 3 min 内生效

# 3. 前端 banner:小程序 + iOS 推送一条通知 / 顶部黄条
#    "支付服务暂时不可用,我们正在恢复,请稍后重试"

# 4. 已下单未支付订单延长 expires:
#    UPDATE orders SET expires_at = NOW() + interval '1 hour'
#      WHERE status='pending' AND expires_at > NOW();

# 5. 监控微信支付状态页 https://pay.weixin.qq.com/index.php/public/notice
#    平台恢复后:
#    - 关闭限流
#    - 关闭 banner
#    - 关闭 feature flag
#    - 抽样 10 笔订单做支付端到端复测
```

### 验证

- 真实 0.01 元订单端到端通过
- `wechatpay_callback_signature_fail_total` 不再增长
- 用户侧 banner 已下线

### 通报模板

```
[INCIDENT / §3 微信支付故障] P1
原因: <自家证书/签名 / 微信平台维护>
影响: 下单后支付失败,新订单 ~N 笔/分钟受影响
缓解: 1) 入口限流 5/min; 2) 前端 banner 已上; 3) 已下单延期至 1h
ETA: <平台公告/我方修复时间>
```

---

## §4 第三方 SMS(阿里云)不通

### 识别信号

| 来源 | 信号 |
|---|---|
| Prometheus | `sms_send_fail_total` rate > `sms_send_ok_total` |
| 应用日志 | `aliyunsdkcore.acs_exception.exceptions.ServerException` |
| 业务 | 用户登录 OTP 收不到,客服反馈集中 |

### 决策树

```
失败率 > 50% 持续 5min?
├─ 是 → 立即降级
│   ├─ 选项 A: 切到备用通道(腾讯云 SMS, 需提前备好 secret)
│   └─ 选项 B: 切到 mock(开发约定 OTP 000000) -- *** 仅在生产无备用通道时,且必须前端做强提示 ***
└─ 否 → 观察 + 限流登录入口
```

### 执行命令

```bash
# 1. 切换 provider(若已备好腾讯云 secret)
#    KMS: SMS_PROVIDER=tencent
#    KMS: TENCENT_SMS_SECRET_ID / TENCENT_SMS_SECRET_KEY / ...
#    rolling restart 3 min 内生效

# 2. 若无备用通道(本期 prod 实际情况):
#    - 限流登录入口到 10/min
#    - 前端登录页加提示:"短信服务异常,如未收到验证码请联系客服 <phone>"
#    - 客服通道开启"人工辅助登录"流程(发临时 token)
#    - *** 不要 *** 在生产开 SMS_PROVIDER=mock,会让所有 OTP 变 000000,有安全风险

# 3. 验证
curl -s https://api.yiluan.example.com/readiness | jq '.checks.sms.status'
# 真机拨测一次 OTP
```

### 验证

- `/readiness checks.sms.status == "ok"`
- 真机收 OTP < 30s
- `sms_send_ok_total` rate 恢复

### 通报模板

```
[INCIDENT / §4 SMS 故障] P1
原因: 阿里云短信平台 <现象>
缓解: 1) 切到备用 provider <tencent/none>; 2) 客服通道开启人工登录
影响: 新用户注册/登录受阻 ~N 用户/分钟
ETA: <恢复时间>
```

---

## 附录 A:通用应急沟通卡

```
[INCIDENT 通用模板]
事件号: INC-YYYYMMDD-NN
时间: <发生时间> CST
级别: P0 / P1 / P2
触发: <告警名 / 业务现象>
执行人: @<ops>
影响范围: <用户数 / QPS / 模块>
当前状态: 调查中 / 缓解中 / 已恢复
下一步: <动作 + 时间点>
复盘: 24h 内,owner @<arch>
```

## 附录 B:On-call 联系方式(模板,需 PM 填实)

| 角色 | 主 | 备 | 升级 |
|---|---|---|---|
| Ops | <name>/<phone> | <name>/<phone> | Arch |
| DBA | <name>/<phone> | -- | Arch |
| Backend | <name>/<phone> | <name>/<phone> | Arch |
| PM | <name>/<phone> | -- | -- |
| Arch | <name>/<phone> | -- | -- |

## 附录 C:关键命令速查

```bash
# 当前流量灰度比例
curl -s "http://prometheus:9090/api/v1/query" \
  --data-urlencode 'query=sum by (pool) (rate(http_requests_total[5m]))'

# /readiness 各项
curl -s https://api.yiluan.example.com/readiness | jq

# Alertmanager 当前 firing
curl -s http://alertmanager:9093/api/v2/alerts | jq '.[] | {alertname: .labels.alertname, status: .status.state}'

# 上一稳定 release tag
git tag --sort=-creatordate | grep '^v' | head -3

# webhook 适配器自检
curl -s http://<host>:5001/healthz | jq
```

---

**版本:** 2026-04-25 v1(GoLive dry-run 配套首发)
