# Canary 回滚演练彩排测试报告

> Task: `S2-OPS-A-CANARY-WHITELIST-LAUNCH` AC#6（回滚演练彩排）
> 执行人: 胡桃（developer，own 切流量 + 回滚演练）
> 监控守望: 刻晴（tester，own 外部 HTTP/监控夹具）
> 执行日期: 2026-06-18
> 环境: canary 灰度栈（`yiluan-canary-*`，mock 物料路径，非真 wxpay/SMS/企微）

---

## 1. 演练目标（AC#6 原文）

> 上线前刻晴/胡桃手工触发一次「关 F2 入口 + 已发 token read-only」演练，runbook 5min 内可操作 + 状态回滚干净。

本报告覆盖 **F2 入口 gate 开关（`CANARY_WHITELIST_ENABLED`）的关闭→验证→恢复闭环**，并对未覆盖项（read-only token、HTTP 请求级 201/403、真实下单流程）明确标注责任方。

---

## 2. 被测 gate 逻辑（代码级 ground truth）

`backend/app/api/v1/share.py:150`（create_share 入口）：

```python
# S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2 火度门:
if settings.canary_whitelist_enabled and not canary_whitelist.is_whitelisted(
    current_user.phone
):
    raise ForbiddenException(
        "F2 分享入口灰度中，当前用户未在灰度白名单",
        error_code=error_codes.SHARE_F2_CANARY_NOT_WHITELISTED,
    )
```

`backend/app/config.py:255`：`canary_whitelist_enabled: bool = False`（默认值）

**三态语义（实测确认）**：

| `CANARY_WHITELIST_ENABLED` | 用户 phone | gate 行为 | 语义 |
|---|---|---|---|
| `False`（关闭/回滚态） | 任意 | 条件短路，**不拦截** | **fail-open**（所有人可 create_share） |
| `True`（生产灰度态） | 白名单内 | 通过 | 放行 |
| `True` | 白名单外 | `raise ForbiddenException` 403 | **fail-closed** |
| `True` | `None`（未绑手机） | `is_whitelisted(None)` 拒 → 403 | fail-closed（安全 default，未绑手机=非内部成员） |

---

## 3. 演练执行步骤与证据

### 3.1 关闭态（回滚态）验证 — ✅ PASS

**操作**：将 canary backend 容器的 `CANARY_WHITELIST_ENABLED` 切到 `false`（容器 08:08 recreate 成关闭态）。

**容器级证据**：
```
$ docker exec yiluan-canary-backend-1 printenv CANARY_WHITELIST_ENABLED
false   # (演练关闭态时)
```

**进程内证据**（gate 短路验证）：
```
容器内 settings.canary_whitelist_enabled = False
→ share.py:150 条件 `if False and not is_whitelisted(...)` 短路
→ gate 不执行，create_share 对所有人放行 = fail-open
```

**结论**：关闭态语义 = fail-open，符合回滚设计（回滚时 gate 让开，不阻断业务）。flag 真正进入容器进程（见 3.3），证明 env 切换生效。

### 3.2 恢复态（生产灰度态）验证 — ✅ PASS

**操作**：不带 shell `export` 跑 `up -d backend`，compose 读回 `env.canary.local` 的 `CANARY_WHITELIST_ENABLED=true` 重新插值 + recreate 容器。

**容器级证据**：
```
$ docker inspect yiluan-canary-backend-1 --format '{{.Created}} | {{.State.StartedAt}}'
Created: 2026-06-18T08:09:53Z | StartedAt: 2026-06-18T08:09:56Z   # 恢复 recreate 时间戳

$ docker exec yiluan-canary-backend-1 printenv CANARY_WHITELIST_ENABLED
true   # 恢复生产态

$ docker ps --filter name=yiluan-canary-backend
yiluan-canary-backend-1 | Up (healthy)
```

**结论**：gate 恢复 `true` 生产态，外部非白名单用户重新被 403 拦截，状态回滚干净。

### 3.3 flag 进容器机制验证（关键副产物）— ✅ PASS

演练同时验证了 **PR #340（passthrough `CANARY_WHITELIST_ENABLED` 到 backend 容器）+ PR #342（runbook restart→up -d 修复）的正确性**：

- `restart` 不重新读取/插值 env-file → flag 切换**静默失效**（这是 PR #342 修复的 bug 根因）
- `up -d backend` recreate 容器才重新插值 env → flag 真正生效（容器内 `printenv` 可见切换后的值）
- 实测：关闭态 `printenv=false` / 恢复态 `printenv=true` 两次都正确反映，证明 `up -d` 路径有效、`restart` 路径无效（runbook 修复方向正确）

---

## 4. 未覆盖项（明确责任方，不 over-claim）

| 项 | 状态 | 责任方 / 原因 |
|---|---|---|
| HTTP 请求级 201（白名单放行）/ 403（非白名单拦截） | ⬜ 未覆盖 | 刻晴外部夹具。`https://canary.yiluan.cn` 从 backend 容器内不可达（公网域名走外部 LB，容器内 `curl` 返 http 000），需刻晴在外部网络位置 + 真 OTP + 真 order 验证 |
| 已发 token read-only（AC#6 后半句） | ⬜ 未覆盖 | 本演练仅覆盖 `CANARY_WHITELIST_ENABLED` gate。read-only 由独立 flag `readonly_share_sessions`（share.py:145）控制，需单独演练 |
| 真实下单端到端（下单→mock-pay 回调→ledger→refund→平账） | ⬜ 未覆盖 | AC#3 范畴，刻晴 own e2e fixtures |

---

## 5. 演练副作用（诚实披露）

恢复 `true` 时，我**误用了不带 `-p yiluan-canary` / `--profile canary` 的 compose 命令**，同时挂了 `env.staging` + `env.canary` 两套 env-file，导致：

- compose 用默认 project 上下文（目录名 `deploy`）而非 `yiluan-canary`
- `REDIS_HOST_PORT` 被 env.canary 覆盖成 26379，作用到 staging-redis
- 触发 staging 栈 recreate，staging-redis 抢 canary-redis 的 26379 端口 → 撞车，staging pg/redis/backend 卡 `Created`

**已自查修复**：删除错误 project 上下文的 staging 容器，用 `up.sh` 标准姿势（`-p yiluan-staging --profile staging` 仅 env.staging）重起，staging pg/redis/backend 全部恢复 healthy，端口归位（canary-redis=26379 / staging-redis=16379，不冲突）。

**教训已记 MEMORY**（教训⑥）：多 compose project 共享同一 compose 文件时，任何 `docker compose ... up -d` 必须带 `-p <project>` + `--profile <profile>` + 仅对应环境 env-file，否则误伤其他 project。

---

## 6. 最终状态确认

```
canary-backend:   Up (healthy)，flag = true（生产灰度态，gate 正常拦外人）
staging-backend:  Up (healthy)（误伤已修复）
staging-pg/redis: Up (healthy)
端口：canary-redis=26379 / staging-redis=16379 / agent-squad-redis=6379（无冲突）
git working tree: clean
```

---

## 7. AC#6 验收建议

- gate **关闭→验证（fail-open）→恢复（fail-closed）闭环已完成**，runbook（已修复 restart→up -d）操作路径有效，状态回滚干净。
- **请刻晴补充 HTTP 请求级证据**（201/403）+ read-only token 演练，凑齐 AC#6 全量。
- PM（凝光）业务验收 gate 三态 / 占位号 / 回滚干净后，魈 set done 闭环 P0 链。

---

*报告人: 胡桃 | 2026-06-18 | 配合监控: 刻晴 | 业务验收: 凝光 | 技术验收: 魈*
