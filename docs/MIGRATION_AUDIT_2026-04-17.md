# 迁移审计 · 2026-04-17

## 背景
今日 model 层改动（payments 扩展字段、orderstatus 新枚举值）未同步至 alembic 迁移链。
pytest 走 SQLite + `Base.metadata.create_all`，绕过 alembic，导致 PG 容器 schema 不完整。

## 阶段 1：Model vs PG Schema 差异表

| 表 / 枚举 | Model 字段数 | DB 字段数 | 差异 |
|---|---|---|---|
| **payments** | 11 | 7 | ❌ 缺 `trade_no`, `prepay_id`, `refund_id`, `callback_raw` + 索引 `ix_payments_trade_no` |
| users | 12 | 12 | ✅ |
| hospitals | 11 | 11 | ✅ |
| orders | 17 | 17 | ✅ |
| companion_profiles | 15 | 15 | ✅ |
| patient_profiles | 8 | 8 | ✅ |
| reviews | 8 | 8 | ✅ |
| chat_messages | 7 | 7 | ✅ |
| notifications | 8 | 8 | ✅ |
| order_status_history | 7 | 7 | ✅ |
| device_tokens | 5 | 5 | ✅ |

### Enum 对比

| Enum | Model 值 | DB 值 | 差异 |
|---|---|---|---|
| **orderstatus** | created, accepted, in_progress, completed, reviewed, cancelled_by_patient, cancelled_by_companion, rejected_by_companion, expired | 同 | ✅ 已在 02bfe73 commit (f1a2b3c4d5e6 revision) 对齐；新迁移中保留 idempotent `ADD VALUE IF NOT EXISTS` 作双保险 |
| notificationtype | 6 值 | 同 | ✅ |
| userrole | patient, companion | 同 | ✅ 管理员不走枚举，而以 `users.roles='admin'` 文本标记 |
| messagetype | text, image, system | 同 | ✅ |
| servicetype | 3 值 | 同 | ✅ |
| verificationstatus | 3 值 | 同 | ✅ |

## 阶段 2：补齐迁移

- Revision: **`b7c8d9e0f1a2`** (align payments columns & verify enums)
- Down revision: `a50c6c117291`
- 手写（未用 autogenerate），操作：
  1. `ALTER TABLE payments ADD COLUMN trade_no VARCHAR(64) NULL`
  2. `ALTER TABLE payments ADD COLUMN prepay_id VARCHAR(128) NULL`
  3. `ALTER TABLE payments ADD COLUMN refund_id VARCHAR(64) NULL`
  4. `ALTER TABLE payments ADD COLUMN callback_raw TEXT NULL`
  5. `CREATE INDEX ix_payments_trade_no ON payments(trade_no)`
  6. `ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'rejected_by_companion'` (autocommit block)
  7. `ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'expired'` (autocommit block)
- Downgrade：丢 4 列 + 索引；enum 值按 PG 约束保留（无 DROP VALUE）
- 所有 DDL 均 idempotent（检查后再增/减）

## 阶段 3：seed.sql 修改统计

- **UUID 非法字符**：扫描 `[g-zA-Z]` 字符出现在 UUID 格式 (8-4-4-4-12) 的情况，**命中 0 条** — seed 已全部合法。
- **列对齐**：payments INSERT 列 `(id, order_id, user_id, amount, payment_type, status, created_at)` 均为 NOT NULL 基础列，新增列 nullable，无需修改。
- seed 未做任何内容修改（0 替换）。

## 阶段 4：验证结果

### 表行数 (清卷重建后灌 seed)

```
users                | 28
hospitals            | 22
patient_profiles     | 10
companion_profiles   | 15
orders               | 35
payments             | 16
reviews              | 10
chat_messages        | 65
notifications        | 36
order_status_history | 25
device_tokens        | 0
```

灌 seed 输出：`INSERT 0 22 / 1 / 10 / 15 / 2 / 10 / 15 / 35 / 65 / 36 / 16 / 10 / 25` — **0 ERROR**

### Enum 验证

```
SELECT enum_range(NULL::orderstatus);
{created,accepted,in_progress,completed,reviewed,cancelled_by_patient,
 cancelled_by_companion,rejected_by_companion,expired}
```

### 服务健康

- `GET /health` → `{"status":"healthy","version":"0.1.0"}` ✅
- `GET /readiness` → 404 （路径不存在，见遗留问题）
- `GET /api/v1/health` 存在但本次未细查

### 7 个测试账号 OTP 登录

| 手机 | 角色 | 登录 | 拿到 token | /users/me 验证 |
|---|---|---|---|---|
| 13800000001 | patient | ✅ | ✅ | roles=patient, display=测试患者A |
| 13800000002 | patient | ✅ | ✅ | roles=patient, display=测试患者B |
| 13800000003 | patient | ✅ | ✅ | roles=patient, display=测试患者C |
| 13900000001 | companion | ✅ | ✅ | roles=companion |
| 13900000002 | companion | ✅ | ✅ | roles=companion |
| 13900000003 | companion | ✅ | ✅ | roles=companion |
| 13700000001 | admin | ✅ | ✅ | roles=admin |

（13900000003 / 13700000001 初次被 IP 级 send-otp 429 限流，等 60s 后成功 — 非 bug。）

## 阶段 5：后端测试

`python -m pytest -q` → **392 passed**（migration 前快照）

## 遗留问题

1. `/readiness` 路径不存在；只有 `/health` 与 `/api/v1/health`。部署文档/TOOLS.md 里若引用 /readiness 需更正。
2. send-otp 接口对同一客户端 IP 有 60s 限流，脚本化批量测试需 sleep。
3. pytest 仍走 SQLite + create_all；建议新增 PG-alembic CI 任务保证两条轨道同步（后续工作）。
