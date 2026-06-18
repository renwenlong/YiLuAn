# Canary Mock 灰度演练 — F2 白名单 Gate E2E 测试报告

> Task: `S2-OPS-A-CANARY-WHITELIST-LAUNCH`（A 选项内部白名单 mock 灰度上线）
> 测试员: 刻晴 ⚡
> 执行时间: 2026-06-18（切流量生效 ~17:10Z 后）
> 性质: **placeholder mock 演练（drill）**，占位号走 dev-OTP，不碰真支付/真短信
> 验证目标: 白名单 gate 切换 + 监控守望 + 回滚机制本身

---

## 0. 结论速览

| 验证项 | 结果 | 对应 AC |
|---|---|---|
| 切流量后基线（gate 三层 + 10 容器 healthy） | ✅ PASS | AC-3 |
| 3 白名单号 F2 create_share 全路径 | ✅ PASS | AC-2 |
| 外人 403 SHARE_F2_CANARY_NOT_WHITELISTED | ✅ PASS | AC-2 |
| phone=None fail-closed（单测覆盖） | ✅ PASS | AC-2 |
| 监控 403 metrics 取证 | ✅ PASS | AC-6 |
| 回滚彩排（关 flag → gate 关闭 → 恢复） | ✅ PASS | AC-7 |

**总判定**：✅ **全 PASS**。e2e 主体 + 监控守望 + 回滚彩排闭环全部通过，AC-2/3/6/7 测试证据齐备。

---

## 1. 测试环境

- **canary API 入口**: `http://127.0.0.1:18090`（nginx → backend）
- **canary 栈**: 10 容器（backend/nginx/pg/redis/prometheus/grafana/alertmanager/alertmanager-webhook/mock-pay/mock-sms）
- **数据库**: `yiluan_canary`（pg 容器 `yiluan-canary-pg-1`）
- **OTP**: mock 不真发短信，从 Redis 读（`docker exec yiluan-canary-redis-1 redis-cli GET otp:{phone}`，TTL 300s）
- **镜像版本**: 17:10Z rebuild（含 PR #340 passthrough `${VAR:-false}` + PR #338 whitelist 4 号）

---

## 2. 切流量后基线确认（AC-3）

```
canary backend: Up (healthy)  ← 17:10Z rebuild
10 容器全 healthy ✅
```

**gate 三层真开**：
| 层 | 验证 | 结果 |
|---|---|---|
| env | `CANARY_WHITELIST_ENABLED=true` | ✅ 真注入 |
| 白名单 load | 容器内 yaml 4 号（13800000001/2/3 + 13800000000） | ✅ rebuild 烤进镜像 |
| is_whitelisted | True×3（白名单）+ False（外人） | ✅ 判定正确 |

**三档告警基线**：CanaryHttp5xxRateHigh / CanaryShareAbuseRateHigh / CanaryAiDegradeRateHigh — 全部 `inactive`·`health=ok`（规则有效、无误触发）✅

---

## 3. E2E 全路径：3 白名单号 create_share（AC-2 正向）

路径：`send-otp → Redis 读真码 → verify-otp 拿 token → 造 order → POST /orders/{id}/shares`

| 号 | 造单 | create_share | share_token |
|---|---|---|---|
| 13800000001 | 用现有 accepted order `f445cb2d...` | ✅ 201 | `O22LlZs9hRqTTjgEYdPAsutSjZdfwf5X` |
| 13800000002 | ✅ 201（full_accompany + 协和 hospital） | ✅ 201 | `1JPDceXK...` |
| 13800000003 | ✅ 201 | ✅ 201 | `nybyU3BB...` |

**关键证明**：胡桃只验到 gate 放行（404 order 不存在），本报告补全了 **gate 放行后 create_share 真创建 share_token** 全链路（201 + share_url + share_active_count=1）。

响应样本（1 号）：
```json
{"id":"19ee00f3-...","share_token":"O22LlZs9hRqTTjgEYdPAsutSjZdfwf5X",
 "share_url":"https://m.yiluan.cn/s/O22LlZs9hRqTTjgEYdPAsutSjZdfwf5X",
 "share_scope":"full","share_active_count":1}
```

---

## 4. 外人 403 拦截（AC-2 反向）

非白名单号 `19999999999` 登录后调 create_share：

```json
HTTP 403
{"detail":{"error_code":"SHARE_F2_CANARY_NOT_WHITELISTED",
  "message":"F2 分享入口灰度中，当前用户未在灰度白名单"}}
```

- error_code 精确命中 ✅
- 连打 3 次稳定复现 ✅
- gate 在 owner 检查之前（share.py:150 gate → :157 ensure_owner），外人即使无 order 也先吃 403（非 404）✅

---

## 5. phone=None fail-closed（AC-2 边界）

phone=None 是代码层 fail-closed 分支，OTP 用户运行时必带 phone（不可达），由单元测试覆盖（CI 是 source of truth）：

- `test_ac2_create_share_403_when_flag_on_and_phone_is_none`（share gate 测试）：gate 开 + 无 phone → 403 ✅
- `is_whitelisted(None) is False` / `("") is False` / `("   ") is False` ✅
- malformed/missing yaml → empty whitelist fail-closed ✅

设计确认：`is_whitelisted(None)` 返回 False → gate 条件 `not False = True` → 进 403 分支（安全 default）。

---

## 6. 监控守望 — 403 metrics 取证（AC-6）

gate 拒绝是否进 Prometheus metrics（可被告警消费）：

| 时点 | POST 4xx 计数 |
|---|---|
| 操作前 | 14 |
| 打 3 次外人 403 后 | 18（+4）|

- gate 拒绝实时计入 Prometheus `http_requests_total{method="POST",status_class="4xx",pool="canary"}` ✅
- metric label = `status_class`（2xx/3xx/4xx 粗粒度），无细分 `SHARE_F2_CANARY_NOT_WHITELISTED` 专用 counter，但 4xx 增量足以反映 gate 命中
- 监控端点：Prometheus `:9091`（Healthy+Ready）/ Alertmanager `:9094` / Grafana `:13001`（200, v11.3.0）

---

## 7. 回滚彩排（AC-7）✅ PASS

> 执行点：在带 #340 passthrough 的 checkout（`/home/wenlongren/repo/YiLuAn-hutao`, main, docker-compose.yml L142 `${CANARY_WHITELIST_ENABLED:-false}`）执行。
> 方案：shell `export` 覆盖 compose 默认值，**不改 `env.canary.local`**（实测后 worktree git 干净、`.local` L11 仍 true，零污染）。

**执行命令**：
```bash
cd /home/wenlongren/repo/YiLuAn-hutao/deploy
export CANARY_WHITELIST_ENABLED=false && ./up.sh canary    # 关 flag recreate
# 恢复：
unset CANARY_WHITELIST_ENABLED && ./up.sh canary          # 读回 .local 的 true
```

**完整闭环结果**（同一外人号 19999999999 + 白名单号 13800000001 跨三态对照）：

| 阶段 | env | 外人 19999999999 | 白名单 13800000001 | 容器 |
|---|---|---|---|---|
| gate-ON 基线 | true | **403** SHARE_F2_CANARY_NOT_WHITELISTED | 放行 | Up 15h |
| **关 flag recreate** | **false** | **404** Order not found（放行到 owner） | 放行 | **Up 30s**（真 recreate）|
| **恢复 unset recreate** | **true** | **403** SHARE_F2_CANARY_NOT_WHITELISTED（精确回归）| **404**（放行到 owner）| **Up 12s**（真 recreate）|

**验证点（全通过）**：
- [x] **env 随 recreate 真翻转** true→false→true，证明 `up -d` recreate 换 env 生效（**对照 runbook `restart` bug：restart 不换 env**）—— 容器启动时长 15h→30s→12s 佐证确实 recreate 而非 restart
- [x] **关 flag 后 gate 整体关闭**：外人从 403→**404**（gate 不再拦截，放行到 owner 检查；因 order 不存在才 404）。语义 = F2 入口门不设防，回到无灰度状态
- [x] **恢复后精确回归**：外人 403 + error_code `SHARE_F2_CANARY_NOT_WHITELISTED` 完全一致；白名单号 404 放行正常
- [x] **零污染**：用 export 覆盖，未改 `.local`；彩排后 worktree git status 干净、`.local` L11 仍 true、10 容器全 healthy

**runbook 5min 可操作性（AC-7 要求）**：关→验→恢复全程 < 2min（两次 recreate 各 ~20-30s + 验证），满足「5min 内可操作 + 状态回滚干净」。

> ⚠️ **语义修正记录**：彩排前我口头预期写过「关 flag 后白名单号也被拒」，实测+读 `share.py:150` gate 逻辑（`if canary_whitelist_enabled and not is_whitelisted(phone)`）确认这是**错的**——flag=false 时 `and` 短路，所有人放行（门不设防），不是都被拒。结论以实测代码语义为准。

---

## 附录：关键技术点（演练沉淀）

1. **rebuild vs restart**：whitelist yaml 由 Dockerfile COPY 进镜像（#304），改 yaml 必须 `up -d --build`；改 env flag 只需 `up -d`（recreate 换 env，不需 --build）。runbook 附录 B 原写 `restart` 是 P0 隐患（静默失败），魈已立 task `S2-OPS-A-ROLLBACK-RUNBOOK-RESTART-BUG` 修。
2. **gate 在 owner 检查前**：`share.py:150`（gate 403）→ `:157`（ensure_owner 404/403）。白名单验证不依赖 order 完成状态。
3. **OTP 60s 频控**：`otp:rate:{phone}`，连测同号需清 rate key 或换号。
4. **执行点铁律**：dirty 分支只读不部署；回滚/部署验证必须在带对应 commit 的 checkout 跑。

---

*报告状态：✅ **终稿**。AC-2/3/6/7 全 PASS，回滚彩排闭环验证完成（刻晴自主执行，2026-06-18 08:xx UTC）。real 物料路径仍 pending（AC-8/9，另起 S2-TEST-004-REAL）。*
