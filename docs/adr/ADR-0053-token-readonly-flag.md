# ADR-0053：已发 token read-only flag 设计（S2-OPS-A 灰度 real 路径）

- **状态**：Draft（2026-06-10，魈）
- **范围**：S2-OPS-A-TOKEN-READONLY-FLAG（design/P2），S2-OPS-A 灰度 real 路径上线前必 close
- **关联**：ADR-0038（admin h5 token hardening）/ S2-OPS-A 套件 §B.2（回滚演练 / 紧急只读）

---

## 1. 问题

S2-OPS-A 灰度 real 路径上线前，必须支持「紧急只读」动作：

- **场景**：灰度某 region 出问题 / 某用户群陷入异常写入循环 / 数据正确性疑虑 → 需要立刻让这部分用户**只读不写**，但不强制 revoke (revoke = 强迫重登 = 用户体验损失 + 客诉)
- **当前 mock 灰度**走 `revoke_all(user_id)` + `token_version += 1` → 用户瞬间 401 → 必须重登。mock 可接 (内部用户), real 不可接
- **必须 design**：要么补 read-only flag，要么 design 决定 real 仍走 revoke + 接受 30s 窗口损失

---

## 2. 现状（evidence-first）

实测 `backend/app/`：

- **access token**：JWT，TTL **30min**，含 `v` (token_version) claim。每请求 `get_current_user` 校验 `v == user.token_version`，不一致 = 401（已有 per-user revocation cursor）
- **refresh token**：JWT，TTL 7d，含 `jti` claim。Redis `RefreshTokenStore` 维护 per-user 白名单
- **revoke 全 user**：`user.token_version += 1` + `revoke_all(user_id)` 清 redis jti → 现有 access 立刻 401，refresh 立刻 401
- **代价**：用户必须**全部** session 重登；30min 内已发的 access 全失效

**关键**：`v` 是已有的 per-user 整数 cursor，read-only flag 设计**可以复用同一类机制**而不发明新方案。

---

## 3. 候选方案

### A. JWT claim 内嵌 `r` (read_only) flag

机制：access token mint 时含 `"r": false`；用户进入只读态时 mint 新 token `"r": true`，旧 token 失效（bump `v`）。

| 维度 | 评价 |
|---|---|
| 实施复杂度 | 🟢 低 — 直接在 `create_access_token` data 里加 `r` claim，dependency 加 `require_writeable` |
| 标记生效速度 | 🔴 慢 — 必须等用户**主动** refresh 或 mint 新 token；现有 access 30min 窗口仍可写 |
| 已发 token 标记 | ❌ 做不到 — 已发出 JWT 是无状态的，不能后改 claim |
| 解除只读 | 🟢 mint 新 token `"r": false` |
| 用户体验 | 🔴 30min 窗口期实际不只读，与 mock revoke 相比无改善 |

**结论**：单独不能用。已发 token 标记不到 = 设计目标失败。

### B. Redis session flag (user level)

机制：Redis 增 key `readonly:user:{user_id} = 1`，`get_current_user` 后查这个 flag，true → 注入 `request.state.is_read_only = True`；所有 mutating endpoint dependency 加 `require_writeable` check。

| 维度 | 评价 |
|---|---|
| 实施复杂度 | 🟡 中 — 加 1 redis key + dependency hook + 标记 mutating endpoint |
| 标记生效速度 | 🟢 立刻 — 下一次请求就生效 (worst case <1s, 即 redis propagation + request roundtrip) |
| 已发 token 标记 | 🟢 完美 — token 本身不变，flag 在 redis 单独维护 |
| 解除只读 | 🟢 `redis DEL readonly:user:{user_id}` |
| 用户体验 | 🟢 无重登；只读期 GET 全正常，POST/PUT/DELETE 返回 403 + 友好提示 |
| 失败模式 | 🔴 redis 挂 → flag check fail → 必须 fail-open (放行写入) 或 fail-closed (全 401) — 高风险 |

**结论**：实用性最强，但 redis 依赖是 SPOF 需 design。

### C. DB column `users.is_read_only`

机制：`users` 表加 `is_read_only BOOL DEFAULT FALSE`，`get_current_user` 已查 user row, 顺手 propagate flag。

| 维度 | 评价 |
|---|---|
| 实施复杂度 | 🟡 中 — alembic migration + 顺手 propagate (重 query 已存在) |
| 标记生效速度 | 🟢 立刻 — `get_current_user` 每请求查 DB row, 下一次请求生效 |
| 已发 token 标记 | 🟢 完美 — token 不变，标记在 DB row |
| 解除只读 | 🟢 `UPDATE users SET is_read_only = FALSE WHERE id = ...` |
| 用户体验 | 🟢 同 B，无重登 |
| 持久性 | 🟢 DB 持久 — 重启 / 灾备恢复后状态保留 |
| 批量标记 | 🟡 batch UPDATE 影响 DB 写吞吐（视体量） |

**结论**：最稳，但 DB write 是较重的运维动作。

### D. Hybrid (B+C)：DB 持久 + Redis 缓存

机制：DB `users.is_read_only` 为 source of truth；redis `readonly:user:{user_id}` 为 hot path 缓存 (TTL 60s)，cache miss 时回查 DB + 重写 cache。批量标记 = 批 UPDATE DB + 批 SET redis (异步).

| 维度 | 评价 |
|---|---|
| 实施复杂度 | 🟠 高 — DB + Redis 双层一致性 |
| 标记生效速度 | 🟢 立刻 (主写 DB + 同步擦 cache) |
| 已发 token 标记 | 🟢 完美 |
| 解除只读 | 🟢 DB UPDATE + redis DEL |
| 用户体验 | 🟢 |
| 失败模式 | 🟢 redis 挂 → fallback 查 DB（性能降级但功能 OK） |
| 一致性风险 | 🟡 cache stale 风险 60s 窗口；可接受 (紧急只读不要求亚秒级一致) |
| 性能影响 | 🟢 hot path 命中 cache，零 DB 查 |

**结论**：生产级最优，但实施量大。

---

## 4. 拍板

**采用方案 D (Hybrid: DB + Redis cache)** 为 real 上线方案。

理由：
1. **DB 持久** = 灾备/重启 source of truth (B 单独 redis 挂 = 灾)
2. **Redis cache** = 不增 DB 查询压力 (hot path 仍 zero-DB-hit)
3. **失败模式干净** = redis 挂 fall back DB, 不 fail-closed (业务连续性优先)
4. **生效速度 <1s** = 业务方期望 (灾难响应窗口)

**短期 mvp 简化**：先实施 **方案 C (DB only)**，后续观察 DB 查询压力是否成瓶颈再加 Redis cache → 形态 D。**理由**：避免一上来引入 redis cache 一致性复杂度，先稳后优。

### AC#2: read-only flag 加在哪一层 — **DB (users.is_read_only) + 后续 Redis cache 形态 D**

### AC#3: 已发 token 如何快速标记 — **后端 DB UPDATE**

- 批量标记: `UPDATE users SET is_read_only = TRUE WHERE id IN (...) AND ...` — 单 SQL DDL 完成
- 单用户标记: 同 UPDATE 单行 = 1ms
- 不需要 reactive check on each request (现有 `get_current_user` 已 per-request load user row, propagate flag 零额外 query)

### AC#4: fallback 边界

| 场景 | 动作 |
|---|---|
| mock 灰度 (现行) | revoke + 重发 |
| real 上线后日常灰度异常 (本 ADR 目标) | **set read-only flag** (POST/PUT/DELETE → 403 + 提示) |
| 真凭据泄露 / 安全事件紧急吊销 | `token_version += 1` + revoke_all + read-only flag 同时设 (最大化保护) |
| 单用户被举报但需保留只读访问 (合规) | set read-only flag |

### AC#5: real 上线 token revoke 30s 窗口对用户体验的可接受度评估

- 现行 revoke 路径不变 (用于真凭据泄露/紧急吊销), 30s 窗口 = JWT 解码 → next get_current_user → 401 (实际接近瞬时, 因 access token 30min TTL + per-request 校验)
- **绝大多数灰度异常场景应走 read-only flag 而非 revoke**, 不存在重登成本
- Metric guard (real 上线后埋点):
  - 重登成功率 ≥ 99% (revoke 用户)
  - 灰度期 session 中断率 < 0.5% (read-only flag 路径 = 0%)
  - 客诉率上限 = 紧急吊销不计入 (合规事件), 灰度异常 < 0.1%
- **Baseline 来源**: S2-OPS-A 套件 mock 灰度日志 (回看 `revoke_all` 事件 + 用户重登成功率 query, S2-OPS 监控面板 read), real 上线 T+7 天首轮回测对比, baseline 不达 → 阻 real 全量推广.
- **配套 follow-up**: `S2-OPS-A-METRIC-DASHBOARD-READONLY` (P3, OPS) — 加 read-only flag 触发率 / 灰度异常 session 中断率 / 客诉率 三个监控指标, 不阻 ADR close.

### AC#6: design 拆 implement task

→ **拆 implement task 给 developer**:
- `S2-DEV-016-READ-ONLY-FLAG-DB` (hutao P2): alembic migration + `users.is_read_only` + dependency + 403 response shape
- `S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` (hutao P2): admin endpoint `POST /api/v1/admin/users/{id}/read-only` + 批量 endpoint `POST /api/v1/admin/users/batch-read-only`
- `S2-TEST-016-READ-ONLY-FLAG-E2E` (keqing P2): E2E 覆盖 set/unset/batch/dependency check/admin audit log

→ **后续 follow-up**: `S3-OPS-READ-ONLY-FLAG-REDIS-CACHE` (P3, 视 DB 压力决定是否实施)

---

## 5. Implementation 提示

### 5.1 DB schema

```sql
ALTER TABLE users ADD COLUMN is_read_only BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN read_only_reason TEXT;
ALTER TABLE users ADD COLUMN read_only_set_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN read_only_set_by UUID REFERENCES admins(id);

CREATE INDEX ix_users_is_read_only ON users (is_read_only) WHERE is_read_only = TRUE;
```

partial index = 只索引 read_only=TRUE (少数), 不影响日常 query plan.

### 5.2 Dependency 注入

```python
# backend/app/dependencies.py

async def require_writeable_user(
    user: CurrentUser,
) -> User:
    if user.is_read_only:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "USER_READ_ONLY",
                "message": "Account is in read-only mode",
                "reason": user.read_only_reason,
            },
        )
    return user

WriteableUser = Annotated[User, Depends(require_writeable_user)]
```

mutating endpoint (POST/PUT/DELETE) 用 `WriteableUser` 替 `CurrentUser`. GET endpoint 不变 = 只读不影响.

### 5.3 admin endpoint

```python
# backend/app/api/v1/admin/users.py

@router.post("/users/{user_id}/read-only")
async def set_user_read_only(
    user_id: UUID,
    payload: SetReadOnlyRequest,
    admin: CurrentAdmin,
    session: AsyncSession,
):
    user = await UserRepository(session).get_by_id(user_id)
    user.is_read_only = True
    user.read_only_reason = payload.reason
    user.read_only_set_at = datetime.now(timezone.utc)
    user.read_only_set_by = admin.id
    await session.commit()
    
    # 写 admin audit log (复用 PR #238 AdminAuditLog 机制)
    await AdminAuditLog.create(
        admin_id=admin.id,
        action="set_user_read_only",
        target_user_id=user_id,
        details={"reason": payload.reason},
    )
    return {"ok": True}
```

### 5.4 frontend / iOS 处理 403

iOS / 微信小程序 / admin-h5 三端均需:
- 检查 response status 403 + `error_code == "USER_READ_ONLY"`
- 弹 toast: "账户当前处于只读模式: <reason>. 请联系客服"
- 不强制跳登录页

---

## 6. 后果

### 正面
- 灰度异常 / 数据正确性疑虑场景下: **零用户体验损失**
- 紧急吊销 (revoke) 路径保留, 不互斥
- DB 持久 = 灾备恢复 / cold start 后状态保留
- 复用已有 AdminAuditLog (PR #238 a9a8206)

### 负面
- 增 users 表 4 列 + 1 partial index (alembic 不可逆但小)
- 所有 mutating endpoint 必须改用 `WriteableUser` dependency — 改造工作量约 30-50 endpoint (S2-DEV-016 task 范围)
- frontend 三端必须 catch 新 error_code `USER_READ_ONLY` — 三端联调 (iOS/wxapp/admin-h5)

### 风险与缓解
- **风险 1**: 漏改 mutating endpoint 导致只读用户仍能写 → **缓解**: lint script grep `CurrentUser` + 人工 review S2-DEV-016 PR
- **风险 2**: read-only flag 误设导致大规模用户被锁 → **缓解**: admin endpoint 强制 reason + audit log + 批量 API 限制单次 ≤ 100 user
- **风险 3**: DB 查询压力升 (每请求 +1 列读) → **缓解**: 已有 `user = repo.get_by_id(user_id)`, 增列读零成本; 监控 + 后续视情况上 Redis cache (形态 D)

---

## 7. Follow-up

- `S2-DEV-016-READ-ONLY-FLAG-DB` (hutao P2) - alembic + dependency + 403 shape
- `S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` (hutao P2) - admin set/unset/batch endpoint  
- `S2-TEST-016-READ-ONLY-FLAG-E2E` (keqing P2) - E2E 覆盖
- `S3-OPS-READ-ONLY-FLAG-REDIS-CACHE` (P3, conditional) - 视 DB 压力上 cache 形态 D
- `S2-OPS-A-METRIC-DASHBOARD-READONLY` (P3 OPS) - read-only flag 监控指标埋点 (AC#5 metric guard 配套)

---

## 8. Refs

- ADR-0038 admin-h5 default token hardening
- S2-OPS-A 灰度上线套件 §B.2 (回滚演练)
- PR #238 (AdminAuditLog 复用)
- `backend/app/core/security.py` (token_version cursor 设计学借鉴)
- `backend/app/services/refresh_tokens.py` (RefreshTokenStore - 不复用, 不同 scope)
