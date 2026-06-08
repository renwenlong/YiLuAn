# ADR-0047 — 电子合同 + 责任险独立领域模型与状态机

> 状态：**Accepted (r1 + r2 amend)** · 作者：魈 · 日期：2026-06-05 · Accept 日期：2026-06-06
> r1 amend：2026-06-08 · 胡桃 (S3-DOC-001-ADR-0047-CONTRACT-TRIGGER-CONSISTENCY) · 魈 review
> r2 amend：2026-06-08 · 魈 (S3-OPS-ADR-0047-R2-AMEND-WORM-COMPENSATION) — WORM compensation 专章对齐 PR #218 实现
> 关联：PRD-003 §3 S3-REQ-001 / ADR-0041 支付业务状态机解耦 / ADR-0046 contract storage / PRD-003 v0.3 §8 Q2 架构评估 + 刻晴 tester review §1 AC#5 强约束（补偿 cron）+ §3 AC-3 强约束（默认未勾选）+ AC-1 客服入口
> 触发：S3-REQ-001 陪诊责任险 + 电子服务合同 / 帝君 2026-06-05 09:52 UTC v0.3 Owner Accept
> Owner Approval：**Accepted by 帝君 @ 2026-06-06 03:28 UTC**（PR #189 merge `5f7f193`；review 闭环：PM final approve + 胡桃 dev review 4+2 + 刻晴 5 补充全合）
>
> ## r1 amend (2026-06-08 胡桃, S3-DOC-001) — 合同触发事件与实现对齐
>
> **背景**：S3-DEV-001-CONTRACT-EVENT-WIRING 拼拍阶段 (2026-06-08 08:11–08:44 UTC) 魈三次横跳后拍板最终 = **单 `accept_order` hook 触发合同生成** (不是 `payment.succeeded`)。拍板依据：
>
> 1. ADR-0046 §3.2 `hash_inputs` 强制含 `companion_id` (immutable)
> 2. `contract_hash.generate_contract_hash_at_commit_time()` 强制 `companion_id` required
> 3. accept_order = 双方合意时点 (商业合同建立语义)，payment 是履约对价支付
>
> 实现证据：PR #212 (`5d57e1f`/`48d616d` commit `backend/app/services/order/lifecycle.py:149-174` `accept_order` 里调 `ContractService.request_generation`)。
>
> **本次 amend 范围**：
>
> - §2.1 候选 A 描述修正：`payment.succeeded` → `accept_order` (限 contract 部分，insurance 仍 payment 触发)
> - §4.1 ContractStateMachine 流程图顶部触发事件修正
> - §5.1 触发链拆分 contract 分支 → `accept_order`；insurance 分支保留 `payment.succeeded`
> - §4.2 / §5.x InsuranceStateMachine 与保险触发链 **未动** (insurance 仍仅 payment.succeeded 触发)
>
> **本次 amend 不动**：
>
> - §3 数据模型 / §6 PIPL / §7 备择、AC 表、陈本阳后续事项与责任分配 — 与触发事件无关
> - ADR-0046 §3.2 hash_inputs schema 不动
> - contract_storage 接口 / state machine 6-state enum 不动
>
> **锁版 condition**：实现已 on main (PR #212 merge)；ADR 文字 r1 amend 合入后与代码合规。
>
> ## r2 amend (2026-06-08 魈, S3-OPS-ADR-0047-R2-AMEND-WORM-COMPENSATION) — WORM compensation 专章
>
> **背景**：S3-DEV-001-CONTRACT-WORM-COMPENSATION (PR #218 merge `de5d20e` 2026-06-08 13:42:35 UTC) 给 contract 加了 WORM 补偿状态机 + 修复 cron + 服务降级 + 3 档 alert。该功能与 §5.2 generation 补偿同型号镜像，但 ADR 文字仅写 generation 补偿，未显式写 WORM 补偿。本 amend 加 §5.3 WORM compensation 专章，使 ADR 文字 ↔ 代码字面一致。
>
> **本次 amend 范围**：
>
> - §3.1 `service_contracts` 表增字段说明（worm_status / worm_retry_count / worm_last_retry_at）— 在原表定义后追加 “(r2 amend)” 注脚（非 schema 改）
> - §5 新增 §5.3 WORM compensation 专章（独立小节，不动 §5.1 / §5.2）
> - §12 加 r2 变更记录
>
> **本次 amend 不动**：
>
> - §5.1 触发链 / §5.2 generation 补偿 cron 字面 — 与 WORM 补偿正交
> - §4.1 ContractStateMachine — WORM 状态机独立于 lifecycle 状态机 (worm_status 是补充字段，非主状态)
> - ADR-0046 §3.3 WORM 三层防御不动 (本 ADR 只补 §5 事件流层的补偿语义)
>
> **锁版 condition**：实现已 on main (PR #218 merge `de5d20e`)；ADR r2 amend 合入后字面对齐代码 (worm_status enum / cron 3-tier / alert metric)。

---

## 1. 背景

PRD-003 S3-REQ-001 引入两个新业务领域：电子服务合同 + 陪诊责任险。架构层 §8 Q2 已拍**必须独立领域模型，绝对不污染 OrderStateMachine**。本 ADR 给出独立状态机 + 事件流 + 数据模型设计。

**ADR-0041 已拍原则**：支付业务状态机解耦，订单/支付/履约/家属 4 个状态机独立。本 ADR 加第 5/6 状态机（合同 + 责任险），延续原则。

---

## 2. 选型对比

### 2.1 候选

| 候选 | 描述 | 评估 |
|---|---|---|
| **A. 独立领域模型 + 独立状态机 + 事件流** | 合同：`accept_order` 事件触发异步生成；保险：`payment.succeeded` 事件触发异步生成（r1 amend）。各自独立表 + 独立 state enum | ✅ 推荐 |
| B. 嵌入 OrderStateMachine（订单 state 加 contract_generated / insurance_active）| 单状态机扩展 | ❌ 违反 ADR-0041 单一职责，订单 state 爆炸 |
| C. 合同/保险共用一个 state 字段 | 简化模型 | ❌ 合同/保险业务流不同（合同立即生成，保险可能延迟出单）|
| D. 不做状态机，直接用 boolean 字段（is_contract_generated）| 简化到极致 | ❌ 失去状态转移审计 + 失败状态无表达 |

**A 推荐理由**：
1. ADR-0041 同款解耦原则延续，订单主表干净
2. 合同 + 保险业务流真不同（合同 5min 内生成，保险等 vendor PENDING 可能 1-3 天）
3. 状态机独立 = 失败重试边界清晰（合同失败不影响保险，反之亦然）
4. Order 主表零侵入：仅 nullable 外键 `contract_id` / `insurance_id`，订单成立完全不依赖二者

### 2.2 Owner 拍板：**A. 独立领域模型 + 独立状态机**（架构推荐，待 Owner Accept）

---

## 3. 数据模型

### 3.1 `service_contracts` 表

```sql
CREATE TABLE service_contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL UNIQUE REFERENCES orders(id),  -- 一单一合同
    template_version VARCHAR(32) NOT NULL,                 -- 如 "v1.0.0"
    contract_hash VARCHAR(64) NOT NULL UNIQUE,             -- SHA-256 hex
    hash_inputs JSONB NOT NULL,                            -- 刻晴补充 #1: 合同生成时一次性冻结的 hash 原材料
    storage_blob_path VARCHAR(512),                        -- contracts/{year}/{month}/{order_id}_{hash}.pdf
    status contract_status NOT NULL DEFAULT 'pending_generation',
    retry_count SMALLINT NOT NULL DEFAULT 0,
    last_error_trace TEXT,                                 -- 失败原因（最近一次）
    generated_at TIMESTAMPTZ,                              -- 成功生成时间
    is_immutable BOOLEAN NOT NULL DEFAULT TRUE,            -- WORM 标记，UPDATE trigger reject
    invalidation_reason TEXT,                              -- 凝光 PR #189 P1：manually_invalidated 状态必填
    invalidated_by_admin_id UUID REFERENCES admins(id),    -- 凝光 PR #189 P1：manually_invalidated 设置人
    invalidated_at TIMESTAMPTZ,                            -- 作废时间
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE contract_status AS ENUM (
    'pending_generation',           -- 初始：支付成功后未开始生成
    'generating',                    -- apscheduler cron job 持锁中
    'active',                        -- 成功生成 + WORM 已存
    'generation_failed',             -- 单次失败（可重试）
    'generation_permanently_failed', -- 3 次重试全失败（不可重试，需 admin 介入）
    'manually_invalidated'           -- 灰度回滚 / 客服手动作废（合同 blob 不删，仅状态变更）
);

CREATE INDEX idx_contracts_status ON service_contracts(status)
  WHERE status IN ('pending_generation', 'generation_failed');  -- 补偿 cron 用
```

**关键约束**：
- `order_id` UNIQUE = 一单一合同（不允许重复生成）
- `contract_hash` UNIQUE = 同 hash 拒重复入库（防双写）
- `hash_inputs` = 合同生成时一次性冻结的 hash 原材料（防 user 改名 / patient 资料修改破坏历史 hash 验证）
- `is_immutable` + UPDATE trigger = DB 层 WORM 防御（ADR-0046 §3.3 第 3 层）
- 索引仅 cover 待补偿状态（status=generation_failed），减小索引大小

**immutable_fields 白名单（刻晴 PR #189 r3 补充 #2）**：

| 字段 | 是否可变 | 理由 |
|---|---|---|
| `status` | ✅ 可变 | 状态机推进 / 灰度作废需要 |
| `retry_count` / `last_error_trace` | ✅ 可变 | 补偿 cron 需要 |
| `invalidation_reason` / `invalidated_by_admin_id` / `invalidated_at` | ✅ 可变 | `manually_invalidated` 留痕需要 |
| `contract_hash` | ❌ 不可变 | 合同防篡改核心 |
| `template_version` | ❌ 不可变 | 历史合同模板版本不可篡改 |
| `storage_blob_path` | ❌ 不可变 | WORM blob path 不可换 |
| `hash_inputs` | ❌ 不可变 | hash 验证原材料必须冻结 |
| `order_id` | ❌ 不可变 | 一单一合同绑定不可变 |

UPDATE trigger 规则：只允许更新 ✅ 字段；任何 ❌ 字段更新直接 raise `ContractImmutableFieldViolation`。

### 3.2 `service_insurance_records` 表

```sql
CREATE TABLE service_insurance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL UNIQUE REFERENCES orders(id),
    product_name VARCHAR(128) NOT NULL,           -- 如 "陪诊责任险标准版"
    coverage_amount_cny INTEGER NOT NULL,         -- 保额（分单位整数）
    vendor_name VARCHAR(64) DEFAULT 'PLACEHOLDER_VENDOR',
    vendor_policy_no VARCHAR(128),                 -- PRD-003 §3.3 AC-4 "policy_no（允许 PENDING）"
    status insurance_status NOT NULL DEFAULT 'pending_issue',
    issued_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE insurance_status AS ENUM (
    'pending_issue',     -- 初始：等 vendor 出单（S3 阶段 vendor 是 PLACEHOLDER，立即 active）
    'active',            -- vendor 确认出单
    'expired',           -- 服务完成 + 保障期过
    'cancelled',         -- 退款/取消订单导致保险也作废
    'issue_failed'       -- vendor API 失败（S3 阶段无真 vendor，永不触发）
);
```

**S3 阶段简化（PRD §2.2 不做真 vendor）**：
- `vendor_name = 'PLACEHOLDER_VENDOR'` 默认值
- `vendor_policy_no` 用占位（如 `PLACEHOLDER-{order_id_short}`）
- 状态直接 `active`（不调真 vendor API）
- 表结构留好 vendor 接入字段，下迭代切真 vendor 不改 schema

### 3.3 `orders` 表 minimal 修改

```sql
ALTER TABLE orders
  ADD COLUMN contract_id UUID REFERENCES service_contracts(id),   -- nullable
  ADD COLUMN insurance_id UUID REFERENCES service_insurance_records(id);  -- nullable
```

**关键约束**：
- 两字段都 nullable = 订单成立完全不依赖合同/保险（PRD AC-5 强约束）
- 不加索引（订单不通过 contract/insurance 查询）
- migration 不回填历史订单（S3 启动后新订单才有）

### 3.4 `contract_templates` 表

```sql
CREATE TABLE contract_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version VARCHAR(32) NOT NULL UNIQUE,           -- semver
    title VARCHAR(128) NOT NULL,                    -- 如 "医路安陪诊服务合同"
    body_markdown TEXT NOT NULL,                    -- 模板正文 markdown
    is_active BOOLEAN NOT NULL DEFAULT FALSE,       -- 同时仅 1 个 active
    activated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_active_template ON contract_templates(is_active) WHERE is_active = TRUE;
```

**唯一 active 模板**：UNIQUE partial index 保证同时仅 1 个 `is_active=TRUE`，admin 切换模板时旧模板自动 false。

---


### 3.5 `user_audit_logs` 表（电子合同取证专用）

胡桃 dev review #4 指出用户勾选合同事件不能放 `admin_audit_logs`。S3-REQ-001 新增用户侧审计表：

```sql
CREATE TABLE user_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    order_id UUID REFERENCES orders(id),
    action VARCHAR(64) NOT NULL,        -- contract_acceptance_clicked / contract_viewed / insurance_terms_viewed
    metadata JSONB NOT NULL DEFAULT '{}',
    user_agent TEXT,                    -- 刻晴补充 #3: PIPL/民法典电子合同取证
    client_ip INET,                     -- 刻晴补充 #3: PIPL/民法典电子合同取证
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_audit_logs_user_time ON user_audit_logs(user_id, created_at DESC);
CREATE INDEX idx_user_audit_logs_order_action ON user_audit_logs(order_id, action);
```

**关键约束**：
- 用户侧行为（勾选合同 / 查看合同 / 查看保障条款）一律入 `user_audit_logs`
- admin 操作仍入 `admin_audit_logs`
- `user_agent` + `client_ip` 必填（可通过反代提取真实 IP，缺失时写 `0.0.0.0` + `missing_ip=true` metadata）

## 4. 状态机定义

### 4.1 ContractStateMachine

```
                  accept_order  (r1 amend: 不是 payment.succeeded)
                          |
                          v
                pending_generation
                          |
                          v (apscheduler cron pickup)
                     generating
                    /         \
              success         failure
                /                 \
               v                   v
            active        generation_failed
                                    |
                                    v (cron retry 5min/30min/2h)
                          [retry_count++]
                                    |
                          [retry_count >= 3]
                                    |
                                    v
                    generation_permanently_failed
                                    |
                          [admin manual fix]
                                    |
                                    v
                                  active

[hot path 旁支]
        active OR generation_permanently_failed
                          |
                          v (admin 手动作废 / 灰度回滚)
                    manually_invalidated
```

### 4.2 InsuranceStateMachine（S3 阶段简化）

```
              payment.succeeded
                      |
                      v
                pending_issue
                      |
                      v (S3 立即 active，无真 vendor)
                   active
                      |
                      v (服务完成 + 保障期过)
                   expired

[hot path 旁支]
                   active
                      |
                      v (订单取消/退款)
                   cancelled
```

下迭代接入真 vendor 时 `pending_issue → active` 改为异步 + 失败 → `issue_failed`。

---

## 5. 事件流

### 5.1 触发链

```
[accept_order] (OrderService 发出, r1 amend)
       └──→ contract.generate.requested (同事务内 INSERT pending_generation 行
             + apscheduler cron pickup 异步渲染 PDF)
                 └──→ ContractStorageBackend.put_contract()
                      └──→ service_contracts.status: pending_generation → active / generation_failed

[payment.succeeded] (PaymentService 发出, 保险仍仅此触发)
       └──→ insurance.issue.requested (异步 apscheduler cron job)
                 └──→ S3 阶段直接 PLACEHOLDER_VENDOR 写入
                      └──→ service_insurance_records.status: pending_issue → active
```

> r1 amend (2026-06-08): 合同触发从 `payment.succeeded` 修正为 `accept_order`。
> 原因：`contract_hash` 公式强制 `companion_id` (ADR-0046 §3.2)，
> payment.succeeded 时广播订单 `companion_id IS NULL` 会导致 hash
> 计算报错。保险仍仅 payment.succeeded 触发 (保险 hash 不含
> `companion_id`)。实现参 PR #212 commit `48d616d` §`backend/app/services/order/lifecycle.py:149-174`。

### 5.2 补偿 cron（ADR-0046 §3.4 + 刻晴 review §1 强约束 #2）

```python
# backend/app/services/cron/contract_retry.py

EXPONENTIAL_BACKOFF_MINUTES = [5, 30, 120]  # 第 1/2/3 次重试间隔

def retry_failed_contracts():
    """每 5min 跑一次：拣 generation_failed 状态合同，按指数退避重试"""
    candidates = db.query(ServiceContract).filter(
        ServiceContract.status == 'generation_failed',
        ServiceContract.retry_count < 3,
    ).all()

    for contract in candidates:
        elapsed = now() - contract.updated_at
        expected_delay = EXPONENTIAL_BACKOFF_MINUTES[contract.retry_count]
        if elapsed.total_seconds() < expected_delay * 60:
            continue  # 未到重试时刻

        try:
            ContractStorageBackend().put_contract(...)
            contract.status = 'active'
            contract.generated_at = now()
        except Exception as e:
            contract.retry_count += 1
            contract.last_error_trace = traceback.format_exc()
            if contract.retry_count >= 3:
                contract.status = 'generation_permanently_failed'
                fire_alert(
                    alert_name='contract_generation_permanently_failed',
                    severity='warning',
                    order_id=contract.order_id,
                    failure_reason=str(e),
                )
        db.commit()
```

**alertmanager alert 定义**（ADR-0040 alert.yml 加）：

```yaml
- alert: ContractGenerationPermanentlyFailed
  expr: increase(contract_generation_permanently_failed_total[5m]) > 0
  for: 0s
  labels:
    severity: warning
  annotations:
    summary: "合同 3 次重试全失败 (order_id={{ $labels.order_id }})"
    description: "需要 admin 介入手动处理"
    runbook: "https://docs.yiluan.internal/runbook/contract-permanent-failure"
```

---

### 5.3 WORM compensation 专章 (r2 amend, S3-DEV-001-CONTRACT-WORM-COMPENSATION / PR #218)

**背景**：put_contract 写入路径含两个 Azure API 调用：

1. `put_if_absent(blob_path, pdf_bytes)` — blob 内容上传 (主要数据写入)
2. `set_immutability_policy(blob_path, period_days=2555)` — WORM 不可变性应用 (法律义务)

**race window**：第 1 步成功后，第 2 步可能 raise (Azure 权限/quota/网络瞬断/API 短期不可用)。此时 blob 内容已落 + 用户可读 PDF，但 WORM 保护尚未生效。ADR-0046 §3.3 已写 WORM 三层防御 (immutability policy + version log + admin alert)，但 §5 事件流层之前未明示补偿协议。本节补上。

**核心原则 (与 §5.2 generation 补偿同型号镜像)**：

| 维度 | §5.2 generation 补偿 | §5.3 WORM 补偿 (本节) |
|---|---|---|
| 触发 | `contracts.status='generation_failed'` | `contracts.worm_status='pending_retry'` |
| 修复 cron 周期 | 每 5min | 每 1h |
| 退避策略 | 指数 5/30/120 min | 固定 1h 间隔 (3 次) |
| 终态 fail enum | `generation_permanently_failed` | `worm_status='permanently_failed'` |
| 服务降级 | failed → 用户看不到合同 | `worm_status != applied` → 用户**仍可读** (blob 存在)，仅 admin invalidate 拒 |
| Alert metric | `contract_generation_permanently_failed_total` | `contract_worm_policy_failed{stage=initial|permanent_fail}` |

#### 5.3.1 数据模型增量 (r2 amend, §3.1 配套)

`service_contracts` 表加 3 字段 (alembic migration `579fc0fbccaa`)：

```sql
worm_status ENUM('applied', 'pending_retry', 'permanently_failed') NOT NULL DEFAULT 'applied'
worm_retry_count INT NOT NULL DEFAULT 0
worm_last_retry_at TIMESTAMPTZ NULL
```

**MUTABLE_FIELDS 白名单加 3 项** (此前 7 项 → 10 项)：`worm_status` / `worm_retry_count` / `worm_last_retry_at`。**IMMUTABLE_FIELDS 不动** (8 项守 hash_inputs / contract_hash / storage_blob_path / template_version / etc)。

#### 5.3.2 初始失败路径 (synchronous put_contract)

```python
# backend/app/services/contract/storage.py (简化伪码，字面以 PR #218 实现为准)

def put_contract(contract_id, pdf_bytes, blob_path):
    storage_backend.put_if_absent(blob_path, pdf_bytes)  # 成功后 blob 已存在
    try:
        storage_backend.set_immutability_policy(blob_path, period_days=2555)
        contract.worm_status = 'applied'
    except Exception as e:
        contract.worm_status = 'pending_retry'
        contract.worm_retry_count = 0
        contract.worm_last_retry_at = now()
        contract.last_error_trace = traceback.format_exc()
        metrics.contract_worm_policy_failed.labels(stage='initial').inc()
    db.commit()
```

**关键约束**：

- 初始失败**不 rollback blob** (put_if_absent 已成功，rollback 会损坏 idempotency)
- 服务降级语义：`worm_status='pending_retry'` 时 `get_contract_signed_url()` **仍返回 URL** (用户合同可见)
- 仅 `invalidate_contract()` (admin 路径) 在 `worm_status='permanently_failed'` 时拒 (HTTP 409, 因 admin 操作要求 WORM 已生效)

#### 5.3.3 修复 cron (apscheduler `contract_worm_repair`)

```python
# backend/app/cron/contract_worm_repair.py (路径以实现为准)

CONTRACT_WORM_REPAIR_LOCK_KEY = "yiluan:scheduler:contract-worm-repair:lock"
CONTRACT_WORM_REPAIR_LOCK_TTL_SECONDS = 55
WORM_RETRY_CAP = 3

async def contract_worm_repair_job(app) -> dict:
    """每 1h 跑一次: 拣 worm_status=pending_retry 合同, 重试 set_immutability_policy.

    默认 enabled (与 generate_pickup 不同, 因 _set_worm_policy_if_azure 是
    idempotent no-op-on-success, 不会产出“空合同副作用”).
    返 {"status": "ok|skipped|disabled|error", "applied": int, "retry_again": int,
    "permanently_failed": int, "errors": int}.
    """
    if not settings.contract_worm_repair_enabled:
        return {"status": "disabled", ...}

    async with async_session() as session:
        lock = acquire_scheduler_lock(  # ADR-0035 §3 P1-A red line
            session=session, redis_client=app.state.redis,
            key=CONTRACT_WORM_REPAIR_LOCK_KEY,
            ttl=CONTRACT_WORM_REPAIR_LOCK_TTL_SECONDS,
        )
        async with lock:
            if not lock.acquired:
                return {"status": "skipped", ...}  # 多副本其他实例持锁

            stmt = (select(ServiceContract)
                .where(ServiceContract.worm_status == ContractWormStatus.pending_retry)
                .order_by(ServiceContract.worm_last_retry_at.asc().nulls_first())
                .limit(settings.contract_worm_repair_batch_size))
            rows = (await session.execute(stmt)).scalars().all()

            backend = _resolve_backend()
            for contract in rows:
                try:
                    _set_worm_policy_if_azure(backend, contract.storage_blob_path)
                    contract.worm_status = ContractWormStatus.applied
                except ContractWormPolicyError:
                    contract.worm_retry_count += 1
                    contract.worm_last_retry_at = utcnow()
                    if contract.worm_retry_count >= WORM_RETRY_CAP:
                        contract.worm_status = ContractWormStatus.permanently_failed
                        contract_worm_policy_failed_total.labels(stage="permanent_fail").inc()
                    else:
                        contract_worm_policy_failed_total.labels(stage="repair_retry").inc()
                await session.commit()  # 每行独立 commit, 一行失败不阻批次
```

**实现细节** (PR #218 字面, `backend/app/cron/contract_worm_repair.py` 路径)：

- `acquire_scheduler_lock` (ADR-0035 §3 P1-A red line): 多副本只一个实例拿锁跑，其他 skip。锁 backend = Redis (生产) 或 PG advisory lock (fallback)，TTL 55s 小于 cron 间隔 1h。
- `_set_worm_policy_if_azure` 是**幂等 no-op-on-success** (Azure SDK 识别同 policy 不重复写)。重试安全, 因此 cron 默认 enabled。
- Local backend / Azure mock 路径返 False (不 raise), cron 直接 mark applied (业务上无 WORM 概念).
- 每行独立 commit (nested transaction / savepoint 隔离), 避免一行失败拖累批次。
- `select(...)` SQLAlchemy 2.0 async style + `ORDER BY worm_last_retry_at ASC NULLS FIRST` (从未 retry 优先重试).
- batch size 默认 50 (`settings.contract_worm_repair_batch_size`).
- fault inject prod 路径 0 影响: 单测路径 mock _set_worm_policy_if_azure raise, prod 路径不动.

#### 5.3.4 alertmanager alert 定义

```yaml
- alert: ContractWORMPolicyInitialFailed
  expr: increase(contract_worm_policy_failed_total{stage="initial"}[5m]) > 0
  for: 0s
  labels:
    severity: warning
  annotations:
    summary: "contract WORM policy 初次写入失败 (order_id={{ $labels.order_id }})，将由 cron 重试"
    description: "非阻塞 alert: cron 1h/3 次重试，3 次全失败升级 high"
    runbook: "https://docs.yiluan.internal/runbook/contract-worm-policy-failure"

- alert: ContractWORMPolicyPermanentlyFailed
  expr: increase(contract_worm_policy_failed_total{stage="permanent_fail"}[5m]) > 0
  for: 0s
  labels:
    severity: high
  annotations:
    summary: "contract WORM policy 3 次重试全失败 (order_id={{ $labels.order_id }})"
    description: "WORM 不可变性未生效，admin 必须介入: 检查 Azure quota/权限/手动调用 set_immutability_policy"
    runbook: "https://docs.yiluan.internal/runbook/contract-worm-permanent-failure"
```

**5min admin 可见性约束**: `for: 0s` (立即触发) + alertmanager group_wait 默认 30s → 5min 内 admin 必收到。

#### 5.3.5 staging 集成测 (S3-TEST-004 灰度回归)

- 1% blob 抽样调 `get_immutability_policy()` → 验证返回 `state=Locked` + `period_days=2555`
- 失败抽样写入 `contract_worm_audit_log` 供回归排查
- 灰度 checklist 加此项 (S3-TEST-004 测试员侧 own)

#### 5.3.6 Phase B forward-compat (multi-region)

Phase B 多 region 部署时，每个 region 独立运行修复 cron。**核心约束**：

- region-affinity: contract 必须在原 region 修复 (Azure immutability policy 是 region-local)
- cron 实例数 = region 数 × 1 (避免跨 region race，由 scheduler-lock 守)
- alert metric 加 `region` label 区分

#### 5.3.7 与 §5.2 generation 补偿语义区别

| 失败 | 用户影响 | admin 影响 | 紧迫度 |
|---|---|---|---|
| §5.2 generation 失败 | **用户看不到合同** (PDF 不存在) | 必须人工或 cron 重试生成 | high (订单流阻塞) |
| §5.3 WORM 失败 | **用户可看合同** (PDF 已存在，仅 WORM 未生效) | cron 1h/3 次重试 + admin alert 排查 Azure | warning → high (WORM 是法律义务，但不阻塞业务) |

关键: WORM 失败属**法律合规风险**而非**业务功能风险**，因此服务降级允许用户读 + 仅 admin invalidate 路径拒。

---

## 6. 状态查询 + 用户体验（PRD-003 §3.2/§3.3 + 刻晴 review）

### 6.1 三端状态展示一致性（PRD AC-6 强约束）

| 端 | 看 | 来源 |
|---|---|---|
| 用户 | order detail.contract_status + .insurance_status | `GET /api/v1/users/orders/{id}` |
| 陪诊师 | order detail.contract_status + .insurance_status（脱敏视图）| `GET /api/v1/companions/orders/{id}` |
| admin | 全字段 + 失败原因 + retry_count + 模板版本 | `GET /api/v1/admin/orders/{id}` |

**字段命名（ADR-0046 §3.5 双门契约）**：
- `contract_status` / `contract_generated_at` / `contract_hash`（用户/陪诊师可见）
- `contract_retry_count` / `contract_last_error`（仅 admin 可见）
- `insurance_status` / `insurance_policy_no` / `insurance_coverage_amount_cny`

### 6.2 客服入口类型（刻晴 review §3 AC-1 客服入口明示）

PRD-003 §3.3 AC-1 "理赔/纠纷处理入口"明示为：
- **主入口**：客服微信链接（小程序内 `wx.openCustomerServiceChat` / iOS `URLScheme `weixin://`）
- **备选入口**：客服电话（小程序 `tel:` / iOS `tel:` URI）
- **S3 不做**：在线表单系统（待 BACKLOG-CUSTOMER-SERVICE-PORTAL）

**凝光 PR #189 备注**：PRD §3.3 AC-1 原写三种入口（微信 / 在线表单 / 电话），ADR §6.2 简化为微信 + 电话 — 凝光 PM 同意简化。v1.0 灰度后评估是否补表单系统，视客服压力 + 用户实际采用入口分布决定。

### 6.3 支付前合同/保障摘要勾选（PRD-003 §5 AC-3 + 刻晴 review §3 AC-3 强约束）

**默认 unchecked + 支付按钮 disabled**：

```
[小程序/iOS 支付前确认页]

[ ] 我已阅读并同意 《医路安陪诊服务合同》 + 《陪诊责任险服务条款》
                    └ tap 弹 合同摘要 + 完整 modal
                       └ tap 弹 保障摘要 + 完整 modal

[ 立即支付 ]  <-- 默认 disabled，等上面 checkbox 被勾选
```

**实施约束**：
- checkbox 初始 `checked=false`
- 支付按钮 `disabled=true` 直到 `checkbox.checked === true`
- 不允许 "记住选择" 跳过下次确认（PIPL/民法典电子合同合规要求）
- 勾选事件入 **`user_audit_logs`**（胡桃 review #4：不能写 `admin_audit_logs`）: `action=contract_acceptance_clicked` + `order_id` + `user_id` + `timestamp` + `template_version` + `user_agent` + `client_ip`（刻晴补充 #3：PIPL/民法典电子合同取证）

---

## 7. 实施分阶段

| Phase | Task | Owner | 周期 |
|---|---|---|---|
| P0 | DB migration（4 表 + ENUM + UPDATE trigger）| 胡桃 | 0.25d |
| P1 | ContractStorageBackend impl（ADR-0046 §3.1）| 胡桃 | 0.5d |
| P2 | 合同 hash 公式 + canonical JSON（ADR-0046 §3.2）| 胡桃 | 0.25d |
| P3 | apscheduler cron: contract.generate + insurance.issue | 胡桃 | 0.5d |
| P4 | 补偿 cron + alertmanager alert | 胡桃 | 0.25d |
| P5 | API: order detail 加 contract/insurance 字段（三端）| 胡桃 | 0.5d |
| P6 | admin-v2: 合同/保险管理页 + 模板维护 | 胡桃 | 1d |
| P7 | 微信/iOS 支付前合同/保障摘要 + 勾选 | 胡桃 | 1d |
| P8 | 双门契约 CI gate（ADR-0046 §3.5）| 胡桃 + 刻晴 | 0.5d |

**总估** ~5d（不含 admin-v2 / 微信 / iOS UI 联调）

---

## 8. 实施 Acceptance（魈 review 阶段硬核）

| AC | 标准 | 验证方式 |
|---|---|---|
| AC-1 | 合同 + 保险独立状态机不污染 OrderStateMachine（订单 state enum 字段无变化）| schema diff |
| AC-2 | Order.contract_id / insurance_id nullable，订单成立不依赖二者 | 集成测：disable contract.generate → 订单仍成立 |
| AC-3 | DB UPDATE trigger reject `is_immutable=TRUE` 行的非状态字段修改 | trigger 单元测 |
| AC-4 | 补偿 cron 严格按 5min/30min/2h 退避 + 3 次失败触发 alert | cron 模拟测 + alertmanager fire 验 |
| AC-5 | 三端 contract_status / insurance_status 字段一致（脱敏视图不变） | 三端 fixture 对比 |
| AC-6 | 支付前 checkbox 默认 unchecked + 按钮 disabled | UI 集成测 |
| AC-7 | 勾选事件入 `user_audit_logs` + template_version + user_agent + client_ip 留痕 | audit_log 校验 |

---

## 9. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 合同/保险与订单状态不一致（订单 paid 但 contract pending）| 高 | 用户困惑 | PRD AC-5 明示 "合同生成中" 状态文案 + 补偿 cron 兜底 |
| apscheduler cron 阻塞导致大量 pending_generation 堆积 | 中 | 用户等不到合同 | 监控 contract status histogram + alertmanager 触发 backlog > 100 告警 |
| WORM trigger 误伤合法状态变更（status: active → manually_invalidated）| 低 | 灰度回滚失败 | trigger 仅 reject 修改 `storage_blob_path` / `contract_hash` 等不可变字段；状态字段允许变 |
| 模板更新影响新订单 / 历史订单 hash 验证 | 低 | 老合同 hash 验证失败 | DB `template_version` 与 ContractTemplate.version 严格绑定 + 历史合同保留原模板版本 |
| S3 PLACEHOLDER_VENDOR 上线时 vendor 仍未对接 | 高（S3 不接真 vendor 是 PM 明示）| 用户看到 placeholder 字样 | UI 文案使用 "服务保障已激活"，不暴露 placeholder 字样；下迭代接真 vendor 替换底层不改 UI |
| 灰度回滚后已生成合同 WORM 不可删 | 中 | container 累积无用合同 | 状态机加 `manually_invalidated`，合同 blob 留存仅状态变更；定期审计但不删除 |

---

## 10. 相关 ADR

- **ADR-0041 支付业务状态机解耦**（同款解耦原则）
- **ADR-0046 contract storage extension**（兄弟 ADR：本 ADR 用 ContractStorageBackend）
- **ADR-0048 AI assistant budget guard**（兄弟 ADR：AI 准备包独立成本控件）
- **ADR-0040 distributed circuit breaker + alertmanager**（本 ADR 复用 alertmanager fire）

---

## 11. 实施授权

待 v0.3 三签（PM/架构/测试）+ 帝君 Owner Accept → 凝光拆 S3-REQ-001 develop task → 本 ADR Accept → 胡桃 implement。

---

## 12. 变更记录

- **r1（2026-06-05）**：Draft 初版，吸收刻晴 tester review §1 AC#5 强约束（补偿 cron 5min/30min/2h）+ §3 AC-3 强约束（默认 unchecked + 按钮 disabled）+ AC-1 客服入口（微信 + 电话，不做表单）
- **r2（2026-06-05）**：吸收凝光 PR #189 business review **P1 建议**
  - §3.1 `service_contracts` 表加 `invalidation_reason TEXT` 必填（当状态 = manually_invalidated）+ `invalidated_by_admin_id` 外键 + `invalidated_at` 时间戳 — 作废动作留迹完整
  - §6.2 客服入口加凝光 PM 同意简化备注（PRD 三种入口 → ADR 简化为微信 + 电话，v1.0 灰度后评估是否补表单系统）
- **r3（2026-06-05）**：吸收刻晴补充 #2/#3 + 胡桃 dev review #4
- **r1 amend（2026-06-08，胡桃，S3-DOC-001-ADR-0047-CONTRACT-TRIGGER-CONSISTENCY，PR #216）**：合同触发事件 `payment.succeeded` → `accept_order` 修正，对齐 PR #212 实现
- **r2 amend（2026-06-08，魈，S3-OPS-ADR-0047-R2-AMEND-WORM-COMPENSATION）**：新增 §5.3 WORM compensation 专章，字面对齐 PR #218 (S3-DEV-001-CONTRACT-WORM-COMPENSATION `de5d20e`) — worm_status enum (applied/pending_retry/permanently_failed) + cron `contract_worm_repair` (1h × 3 retry) + 服务降级语义 (worm_status != applied 仍允许 get URL，仅 invalidate 拒) + 双 alert (initial/permanent_fail) + Phase B 多 region 约束。同步 §3.1 `service_contracts` 字段增量注脚。
  - §3.1 `service_contracts` 加 `hash_inputs JSONB NOT NULL`，并列明 immutable_fields 白名单：`status` 可变；`contract_hash` / `template_version` / `storage_blob_path` / `hash_inputs` 不可变
  - §3.5 新增 `user_audit_logs` 表；§6.3 勾选合同事件写 `user_audit_logs` 而非 `admin_audit_logs`，并强制记录 `user_agent` + `client_ip` 作为 PIPL/民法典电子合同取证材料
  - 全文 `Celery` 统一改为 `apscheduler cron job`，对齐 backend 实跑依赖
