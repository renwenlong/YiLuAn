# Canary Rollback Runbook — W20 Top1 (S2-OPS-001)

当 `yiluan_canary_rollback` 组的任一 alert 触发（`action=rollback, gate=canary`），
执行本 runbook。三档阈值（帝君 2026-05-28 10:24 UTC 批准）：

| Alert | 触发条件 | PRD |
|---|---|---|
| `CanaryHttp5xxRateHigh` | 5xx 错误率 > 2% 持续 30min | §8.1 #1 |
| `CanaryShareAbuseRateHigh` | share token 滥用率 > 5% 持续 2h | §8.1 #2 |
| `CanaryAiDegradeRateHigh` | AI 摘要降级率 > 20% 持续 4h | §8.1 #3 |

## 1. 立即回滚（流量层，最快）

灰度由 nginx `split_clients` 控制，回滚 = 把 `backend_new` 权重打到 0%。

**位置**：生产 `/etc/nginx/conf.d/yiluan-canary.conf`
（模板 `ops/canary/nginx.canary.conf.template`，搜 `split_clients`）。

```nginx
# 把当前生效的 split_clients 块替换为 Rollback 块：
split_clients "${canary_key}" $canary_pool {
    *       "backend_stable";
}
```

应用：
```bash
sudo nginx -t && sudo nginx -s reload     # reload 不断连
```

> reload 后所有新请求走 `backend_stable`；带 `canary_bucket=new` cookie 的老用户
> 仍可能粘在 new — 如需强制全停，同时下线 `backend_new` upstream（见 §2）。

## 2. 强制全停 backend_new（粘性 cookie 也踢走）

把 `map $canary_key $final_pool` 默认值强制 stable：
```nginx
map $canary_key $final_pool {
    default              "backend_stable";   # was: $canary_pool
    "__force_new"        "backend_new";      # 仅保留 QA 显式覆盖
    "__force_stable"     "backend_stable";
}
```
`nginx -t && nginx -s reload`。

## 3. 验证回滚生效

- Grafana **YiLuAn / W20 Top1 Canary Rollback Gate**（`ops/grafana/yiluan-canary.json`）
  上三档曲线回落到阈值线下；
- `sum(rate(http_requests_total[5m]))` 中 `backend_new` 池流量归零
  （`Canary split (by pool label)` 面板）；
- alert 在 `resolve_timeout`（5m）后自动 resolved，Alertmanager 推 resolved 通知。

## 4. 通知链（自动）

Alert 触发即经 Alertmanager `canary-rollback-ops-pm` receiver fan-out：
- 运营企业微信群（`wechat-work-webhook?channel=ops-canary`）
- 运营 + PM 邮件（`CANARY_OPS_EMAIL` / `CANARY_PM_EMAIL`）

收到后由 **on-call 执行 §1**，并在群内同步「已回滚 + 触发 alert 名 + 当前指标值」。

## 5. 回滚后

1. 冻结 F2 再灰度，开 incident；
2. 按触发 alert 定位根因（5xx → 看 backend 日志 / Sentry；滥用率 → 看
   `share_token_auto_revoked_total{reason}`；AI 降级 → 看 `ai_summary_degraded_total{reason}`）；
3. 修复 + staging 复跑灰度逆向验证（5xx ≤ 0.5%/6h、滥用 ≤ 1%/12h、
   AI 降级 ≤ 5% 且日成本在 ¥50 预算内）达标后再重新放量。

## 附：相关文件
- alert rules: `deploy/prometheus/yiluan-canary.yml`
- alertmanager 路由: `prometheus/alertmanager.yml`（receiver `canary-rollback-ops-pm`）
- dashboard: `ops/grafana/yiluan-canary.json`
- 灰度流量: `ops/canary/nginx.canary.conf.template` / ADR-0028

---

## 附录 B：S2-OPS-011 feature flag 热切（W22+ 灰度通道）

> 配套：S2-OPS-011 灰度通道（接真 wxpay/aliyun_sms）+ `backend/app/config.py` feature flags
> 适用：灰度通道上 share/F2 链路异常但不需要整体回滚 backend 时的细粒度回滚

### ⚠️ B.0 回滚命令选型（必读 — 两条路径用不同命令，用错静默失败）

灰度回滚有两条物理路径，**改的东西来源不同，正确命令也不同**。用错命令（尤其 `restart`）会**静默失败**：运维以为关了 flag，实际容器内仍是旧值，灰度未真正回滚。

| 回滚动作 | 改的来源 | 正确命令 | 为什么 |
|---------|---------|---------|--------|
| **关 flag**（`CANARY_WHITELIST_ENABLED=false` / `FEATURE_SHARE_F2_ENABLED=false` / `READONLY_SHARE_SESSIONS=true`） | compose `environment:` 段对 `env.canary.local` 的 `${VAR}` 插值（passthrough PR #340 L142） | **`up -d`**（recreate 换 env，**不需** `--build`） | 改 env 文件值后，必须让 compose 重新插值 + recreate 容器才进容器 |
| **改白名单名单**（canary whitelist yaml 内容） | Dockerfile `COPY` 进镜像（#304 / #302 follow-up，`deploy/canary/`） | **`up -d --build`** | yaml 烤进镜像，`restart` / `up -d` 都只读旧镜像，必须 rebuild |

**❌ 绝不要用 `docker compose ... restart backend` 关 flag**：`restart` 只发 SIGTERM/SIGKILL 重启进程，**不读取新 config、不重新插值 `environment:` 段** → `env.canary.local` 改了根本不进容器。

> **实测来源**：刻晴 S2-OPS-A canary 灰度 e2e 回滚彩排实测（2026-06-18）证明 `restart` 不生效——只有 `up -d`（recreate）才会重新插值 env 换值。三方 evidence-first 实证（restart 行为 / flag 插值来源 / up -d 正确性）见 S2-OPS-A-ROLLBACK-RUNBOOK-RESTART-BUG。

> 注：`./up.sh canary` 内部是 `up -d --build`（`deploy/up.sh` L76），是 rebuild superset——跑回滚演练用它绝对安全（关 flag 也会一并生效），但全量 rebuild 慢；**紧急回滚关 flag 用 `up -d` 即可，快很多**。

### B.1 关 F2 入口（CanaryShareAbuseRateHigh 触发推荐）

```bash
echo "FEATURE_SHARE_F2_ENABLED=false" >> ~/repo/YiLuAn/deploy/env.canary.local
cd ~/repo/YiLuAn/deploy
# ✅ up -d 才会重新插值 env + recreate 容器换值；restart 不生效（见 B.0）
docker compose --env-file env.staging --env-file env.canary \
  --env-file env.canary.local up -d backend

# 验证 503 + SHARE_F2_DISABLED
curl -X POST -H "Authorization: Bearer <token>" -d '{"share_scope":"full"}' \
  https://canary.yiluan.cn/api/v1/orders/<id>/shares
```

效果：拒新建 share_token；已发 share_token 继续有效（家属仍可用旧链接，但不产新链接）。

### B.2 冻结新 share session（异常严重时）

```bash
echo "READONLY_SHARE_SESSIONS=true" >> ~/repo/YiLuAn/deploy/env.canary.local
# ✅ up -d 才会重新插值 env + recreate 容器换值；restart 不生效（见 B.0）
docker compose --env-file env.staging --env-file env.canary \
  --env-file env.canary.local up -d backend
```

效果：
- 拒新换 share_session（POST `/shares/{token}/session` → 503 + `SHARE_SESSIONS_READONLY`）
- WS share upgrade 直接 close 4015
- **已发 share_session JWT 仍可拉 GET `/shares/session/order` 读视图**（不影响读，仅冻结新会话）

### B.3 反向回滚（取消 flag）

故障修复 + 验证通过后：

```bash
sed -i '/^FEATURE_SHARE_F2_ENABLED/d' ~/repo/YiLuAn/deploy/env.canary.local
sed -i '/^READONLY_SHARE_SESSIONS/d' ~/repo/YiLuAn/deploy/env.canary.local
# ✅ up -d 才会重新插值 env + recreate 容器换值；restart 不生效（见 B.0）
docker compose --env-file env.staging --env-file env.canary \
  --env-file env.canary.local up -d backend
```

### B.4 反向引用

- S2-OPS-011 task 配套
- backend feature flags 真源：`backend/app/config.py` `feature_share_f2_enabled` / `readonly_share_sessions`
- 拦截点：`backend/app/api/v1/share.py` create_share + exchange_session / `backend/app/api/v1/ws.py` websocket_share
- error_code 真源：`backend/app/core/error_codes.py` `SHARE_F2_DISABLED` / `SHARE_SESSIONS_READONLY`
- 配套部署：`docs/ops/canary-deployment.md`
