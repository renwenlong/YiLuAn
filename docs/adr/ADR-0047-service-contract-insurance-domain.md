# ADR-0047 — 电子合同 + 责任险独立领域模型与状态机

> 状态：**Draft（待 review + Owner Accept）** · 作者：魈 · 日期：2026-06-05
> 关联：PRD-003 §3 S3-REQ-001 / ADR-0041 支付业务状态机解耦 / ADR-0046 contract storage / PRD-003 v0.3 §8 Q2 架构评估 + 刻晴 tester review §1 AC#5 强约束（补偿 cron）+ §3 AC-3 强约束（默认未勾选）+ AC-1 客服入口
> 触发：S3-REQ-001 陪诊责任险 + 电子服务合同 / 帝君 2026-06-05 09:52 UTC v0.3 Owner Accept
> Owner Approval：**Pending（待 v0.3 三签 + 凝光拆 task ready 后 Accept）**

---

## 1. 背景

PRD-003 S3-REQ-001 引入两个新业务领域：电子服务合同 + 陪诊责任险。架构层 §8 Q2 已拍**必须独立领域模型，绝对不污染 OrderStateMachine**。本 ADR 给出独立状态机 + 事件流 + 数据模型设计。

**ADR-0041 已拍原则**：支付业务状态机解耦，订单/支付/履约/家属 4 个状态机独立。本 ADR 加第 5/6 状态机（合同 + 责任险），延续原则。

---

## 2. 选型对比

### 2.1 候选

| 候选 | 描述 | 评估 |
|---|---|---|
| **A. 独立领域模型 + 独立状态机 + 事件流** | 合同/保险各自独立表 + 独立 state enum + payment.succeeded 事件触发异步生成 | ✅ 推荐 |
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
    storage_blob_path VARCHAR(512),                        -- contracts/{year}/{month}/{order_id}_{hash}.pdf
    status contract_status NOT NULL DEFAULT 'pending_generation',
    retry_count SMALLINT NOT NULL DEFAULT 0,
    last_error_trace TEXT,                                 -- 失败原因（最近一次）
    generated_at TIMESTAMPTZ,                              -- 成功生成时间
    is_immutable BOOLEAN NOT NULL DEFAULT TRUE,            -- WORM 标记，UPDATE trigger reject
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE contract_status AS ENUM (
    'pending_generation',           -- 初始：支付成功后未开始生成
    'generating',                    -- Celery task 持锁中
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
- `is_immutable` + UPDATE trigger = DB 层 WORM 防御（ADR-0046 §3.3 第 3 层）
- 索引仅 cover 待补偿状态（status=generation_failed），减小索引大小

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

## 4. 状态机定义

### 4.1 ContractStateMachine

```
                  payment.succeeded
                          |
                          v
                pending_generation
                          |
                          v (Celery task pickup)
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
[payment.succeeded] (PaymentService 发出)
       ├──→ contract.generate.requested (异步 Celery)
       │         └──→ ContractStorageBackend.put_contract()
       │              └──→ service_contracts.status: pending_generation → active / generation_failed
       │
       └──→ insurance.issue.requested (异步 Celery)
                 └──→ S3 阶段直接 PLACEHOLDER_VENDOR 写入
                      └──→ service_insurance_records.status: pending_issue → active
```

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
- 勾选事件入 audit_log: `action=contract_acceptance_clicked` + `order_id` + `user_id` + `timestamp` + `template_version`

---

## 7. 实施分阶段

| Phase | Task | Owner | 周期 |
|---|---|---|---|
| P0 | DB migration（4 表 + ENUM + UPDATE trigger）| 胡桃 | 0.25d |
| P1 | ContractStorageBackend impl（ADR-0046 §3.1）| 胡桃 | 0.5d |
| P2 | 合同 hash 公式 + canonical JSON（ADR-0046 §3.2）| 胡桃 | 0.25d |
| P3 | Celery task: contract.generate + insurance.issue | 胡桃 | 0.5d |
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
| AC-7 | 勾选事件入 audit_log + template_version 留痕 | audit_log 校验 |

---

## 9. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 合同/保险与订单状态不一致（订单 paid 但 contract pending）| 高 | 用户困惑 | PRD AC-5 明示 "合同生成中" 状态文案 + 补偿 cron 兜底 |
| Celery task 阻塞导致大量 pending_generation 堆积 | 中 | 用户等不到合同 | 监控 contract status histogram + alertmanager 触发 backlog > 100 告警 |
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
