# S2-OPS-A Read-Only Flag Metric Dashboard Design

> **task**: `S2-OPS-A-METRIC-DASHBOARD-READONLY` (P1, design, architect own)  
> **关联 ADR**: [ADR-0053 §7 + §8 哨兵 #1](../adr/ADR-0053-token-readonly-flag.md)  
> **前置于**: `S2-DEV-016-READ-ONLY-FLAG-DB` (依赖本 design 完成 + metric 实装上线 + 7 天数据全绿)  
> **author**: 魈 (architect)  
> **created**: 2026-06-10  
> **status**: draft r1 (r0 → r1: 刻晴 PR #248 review red-line amend, 见 §12 changelog)

---

## 1. 背景

`ADR-0053` §AC#5 拍 read-only flag real 上线 quantitative metric guard 3 条数字:
- **重登成功率 ≥ 99%** (revoke 用户)
- **session 中断率 < 0.5%** (灰度异常)
- **客诉率 < 0.1%** (灰度异常, 紧急吊销/合规事件不计入)

刻晴 PR #246 review 红线拍穿: 现状 (2026-06-10 实测) 监控埋点**完全缺位**:
- `deploy/prometheus/yiluan-canary.yml` + `ops/grafana/yiluan-canary.json`: **只有** `share_token_auto_revoked_total` (share token 范围, 不是 user-level revoke)
- `backend/app/`: `user_token_revoke_total` / `user_relogin_success_total` / `user_session_dropped_total` **全不存在**
- mock 灰度日志只能 grep application log → baseline 取数不能自动化

→ 不上 metric dashboard = AC#5 quantitative phase 跑不起来 = real T-7 自动 NoGo (ADR-0053 §8 哨兵 #1 红).

**本 design** 输出 3 个 metric 命名 + label schema + grafana panel 结构 + baseline query SQL 模板, 实施由 `S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` (hutao) + OPS (grafana commit) 接.

---

## 2. 方案对比

### 方案 A: 单一 counter, 用 label 区分 (推荐)

- 3 个 `prometheus_client.Counter`, 每个带 label 维度
- 优点: 单一 metric source, query 简单, panel 配置直接
- 缺点: high-cardinality label 风险 (但本 case label 数量可控, 见 §3.2)

### 方案 B: 多个 Gauge + cron 推送

- backend cron 每 1min query DB + push Gauge
- 优点: 业务逻辑集中, 不污染 endpoint code
- 缺点: cron 延迟 1min, 高基数风险更大, 数据真实性比 Counter 弱 (cron 漏跑数据丢)

### 方案 C: structured log + log aggregator (Loki / ELK)

- 不上 prometheus, 用 log query
- 优点: 0 code change
- 缺点: 查询慢, alert 不易, prometheus baseline 标准对不上

### 决定: **方案 A**

- prometheus 是现有团队标准 (`share_metrics`, `http_metrics`, `reconciliation_metrics`)
- label cardinality 在控制范围内 (§3.2 估算)
- alert + dashboard 直接走 prometheus 现成 stack
- 实施成本低 (3 个 Counter + endpoint hook, 估 1-1.5 day)

---

## 3. Metric 设计

### 3.1 文件位置 (新建)

`backend/app/observability/read_only_flag_metrics.py`

参考现有 `share_metrics.py` / `reconciliation_metrics.py` 命名 convention.

### 3.2 3 个 Metric 定义 (r1 amend: 删 source label, 见 §12.1)

```python
"""
backend/app/observability/read_only_flag_metrics.py

ADR-0053 §AC#5 quantitative metric guard 埋点.

3 个 Counter:
  - user_token_revoke_total{reason, source}        - user 级 token revoke 次数
  - user_relogin_success_total{source, trigger}    - 用户重登成功次数
  - user_session_dropped_total{cause, source}      - 用户 session 中断次数

设计原则:
  - Counter 自动加 _total 后缀 (prometheus_client behaviour)
  - label cardinality 控制: 每个 label 取值 ≤ 5 (见 §3.2 估算)
  - 不带 user_id label (high cardinality, 用 trace 而非 metric 关联)
"""

from collections.abc import Iterable
from prometheus_client import REGISTRY, Counter


def _get_or_create_counter(name: str, doc: str, labelnames: Iterable[str]) -> Counter:
    """复用 reconciliation_metrics pattern, 防 duplicate registration."""
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing
    return Counter(name, doc, list(labelnames))


# AC#1: user-level token revoke (区别于 share_token_auto_revoked_total)
USER_TOKEN_REVOKE_TOTAL: Counter = _get_or_create_counter(
    "user_token_revoke",  # 自动 + _total 后缀
    "User-level access token revocation events (bumps users.token_version, real only).",
    ["reason"],
)
"""
labels:
  reason:
    - "credential_leak"   - 真凭据泄露 (紧急吊销, 不计入客诉率)
    - "compliance_report" - 合规举报 (紧急吊销, 不计入客诉率)
    - "user_request"      - 用户主动登出
    - "admin_kick"        - 管理员手动 kick
    - "auto_scanner"      - 自动扫描器 (与 share_token_auto_revoked_total 区分用户范围)

Note: r1 amend (§12.1) 删 source label, mock 走 admin_audit_logs SQL (§5.1), real 走 prometheus (§5.2), 职责物理分离.
"""


# AC#2: 用户重登成功 (revoke 后 baseline 99% 验证)
USER_RELOGIN_SUCCESS_TOTAL: Counter = _get_or_create_counter(
    "user_relogin_success",
    "User successful re-login after token revocation (used to validate 99% relogin SLA, real only).",
    ["trigger"],
)
"""
labels:
  trigger:
    - "post_revoke"     - revoke 后 30min 内重登 (核心 SLA 指标, 反映用户体验)
    - "passive"         - 自然重登 (token 自然过期, 非 revoke 触发, 不计入 SLA)

Note: r1 amend (§12.1) 删 source label, 同 USER_TOKEN_REVOKE_TOTAL.
"""


# AC#3: session 中断 (drop rate < 0.5% baseline 验证)
USER_SESSION_DROPPED_TOTAL: Counter = _get_or_create_counter(
    "user_session_dropped",
    "User session terminated unexpectedly (revoke / keepalive timeout / server kick, real only).",
    ["cause"],
)
"""
labels:
  cause:
    - "revoke"            - token revoke 导致 (refresh_token 失效 / token_version mismatch)
    - "keepalive_timeout" - session keepalive 超时 (refresh token TTL 到)
    - "server_kick"       - 服务端主动 disconnect (维护 / 异常)
    - "client_close"      - 客户端主动关闭 (不计入 drop, label 用于排除)

Note: r1 amend (§12.1) 删 source label, 同 USER_TOKEN_REVOKE_TOTAL.
"""
```

### 3.3 Cardinality 估算 (r1 amend: 22→11 series)

| Metric | label combination | 最大基数 |
|---|---|---|
| `user_token_revoke_total` | 5 reason | 5 |
| `user_relogin_success_total` | 2 trigger | 2 |
| `user_session_dropped_total` | 4 cause | 4 |
| **共** | | **11 time series** (r0: 22, r1: 11) |

✅ 11 series 远低于 prometheus 推荐上限 (通常 < 1000), 零基数风险.

**r1 设计原则 (§12.1 amend)**: prometheus 只看 real, mock 走 audit SQL — 职责物理分离. 这样 source label 删, cardinality 减半, real 数据更清晰 (无 mock noise 污染 alert).

### 3.4 Endpoint Hook 实装点 (r1 amend: source label 删, audit hook 必加)

`S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` (hutao) 接手时 hook 这些点 (双埋点: prometheus counter + audit_log 写入, **同 transaction 强约束**, ADR-0053 §7 收尾要求):

| Metric | Prometheus Hook | **Audit Log Hook (新增, 必须同 transaction)** |
|---|---|---|
| `user_token_revoke_total{reason}` | `backend/app/services/auth.py:227` `revoke_all_sessions` 末尾 `+1`, 仅在 `ENVIRONMENT=production` 计 (mock 不上 prometheus, mock 走 audit SQL) | 同 method 同 transaction 插 `admin_audit_logs`: `action='user_token_revoke'`, `target_type='user'`, `target_id=user.id`, `operator=current_admin`, `reason=text(reason_enum)`, **`metadata={"source":"mock"\|"real","trigger":"manual\|auto_scanner"}`** (需 metadata JSONB 字段 alembic migration, 见 §3.5) |
| `user_relogin_success_total{trigger}` | `backend/app/services/auth.py` `login_user` 成功 path, 仅 real 计 | 同 method 同 transaction 插 `user_audit_logs`: `action='user_login_success'`, `user_id=user.id`, `metadata={"source":"mock"\|"real","trigger":"post_revoke"\|"passive"}` (需 user_audit_logs action enum 扩 + metadata JSONB migration, 见 §3.5) |
| `user_session_dropped_total{cause}` | `backend/app/services/auth.py` `get_current_user` reject path + `RefreshTokenStore` 失效 path, 仅 real 计 | 同 method 同 transaction 插 `user_audit_logs`: `action='user_session_dropped'`, `metadata={"source":...,"cause":...}` |

⚠️ **本 design 不指定具体实施代码** (那是 develop task 范围), 仅 hint 实装位置 + 强约束 (同 transaction).

### 3.5 Schema Migration 前置 (r1 新增, 红线 #1 方案 A 收尾)

**当前实测 (2026-06-10) 现状**:
- `admin_audit_logs.reason: Text` 单字段 (no JSON)
- `user_audit_logs` action enum: 只 3 contract action (无 login_success/session_dropped/token_revoke)
- 2 表都**无 metadata JSONB 字段**
- `revoke_all_sessions` 当前**无 audit hook**

**新增 alembic migration** (`S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` 实施时同 PR 出):

```python
# alembic/versions/XXXX_audit_logs_metadata_for_readonly_flag.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'XXXX'
down_revision = 'YYYY'  # 当前 head

def upgrade() -> None:
    # AC#1 admin_audit_logs metadata JSONB (read-only flag source/trigger 扩展)
    op.add_column(
        'admin_audit_logs',
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        'ix_admin_audit_logs_metadata_source',
        'admin_audit_logs',
        [sa.text("(metadata->>'source')")],
        postgresql_where=sa.text("action = 'user_token_revoke'"),
    )

    # AC#2 user_audit_logs metadata JSONB + 扩 action enum (login_success/session_dropped)
    op.add_column(
        'user_audit_logs',
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        'ix_user_audit_logs_metadata_source',
        'user_audit_logs',
        [sa.text("(metadata->>'source')")],
        postgresql_where=sa.text("action IN ('user_login_success', 'user_session_dropped')"),
    )

def downgrade() -> None:
    op.drop_index('ix_user_audit_logs_metadata_source', table_name='user_audit_logs')
    op.drop_column('user_audit_logs', 'metadata')
    op.drop_index('ix_admin_audit_logs_metadata_source', table_name='admin_audit_logs')
    op.drop_column('admin_audit_logs', 'metadata')
```

**ORM model 同步更新**:

```python
# backend/app/models/admin_audit_log.py 追加
metadata: Mapped[dict | None] = mapped_column(
    JSONB, nullable=True,
    comment="扩展字段 (read-only flag source/trigger 等, ADR-0053 §7)"
)

# backend/app/models/user_audit_log.py 追加 (同 + 扩 action enum)
```

⚠️ 这是 `S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` task **同 PR 必出** (单 PR 包含 metric + audit_log + migration + revoke_all hook), 不可拆 — 因为 baseline 取数依赖 audit_log, mock 灰度第 1 天就得能查.

---

## 4. Grafana Dashboard 设计

### 4.1 文件: `ops/grafana/yiluan-readonly-flag.json` (新建)

不动现有 `yiluan-canary.json` / `yiluan-overview.json`, 独立 dashboard 便于 read-only flag 团队聚焦.

### 4.2 3 Panel 结构

```json
{
  "title": "Read-Only Flag (S2-OPS-A) Real T-7 Guard",
  "uid": "yiluan-readonly-flag-real-guard",
  "tags": ["yiluan", "readonly", "s2-ops-a", "adr-0053"],
  "panels": [
    {
      "id": 1,
      "title": "Token Revoke Rate by Reason (1h)",
      "type": "timeseries",
      "targets": [
        {
          "expr": "sum by (reason) (rate(user_token_revoke_total{source=\"real\"}[1h]))",
          "legendFormat": "{{reason}}"
        }
      ],
      "description": "Real 灰度 user revoke 速率, 按 reason 拆分. AC#5 计算分母不计 credential_leak/compliance_report."
    },
    {
      "id": 2,
      "title": "Relogin Success Rate (post-revoke, 24h SLA)",
      "type": "stat",
      "targets": [
        {
          "expr": "sum(rate(user_relogin_success_total{source=\"real\", trigger=\"post_revoke\"}[24h])) / clamp_min(sum(rate(user_token_revoke_total{source=\"real\", reason!~\"credential_leak|compliance_report\"}[24h])), 1e-9)",
          "legendFormat": "Relogin SLA"
        }
      ],
      "thresholds": {
        "steps": [
          {"value": 0, "color": "red"},
          {"value": 0.99, "color": "green"}
        ]
      },
      "description": "AC#5 重登成功率 SLA ≥ 99% (post-revoke 30min 内重登 / 灰度异常 revoke 数). 红绿阈值 99%."
    },
    {
      "id": 3,
      "title": "Session Drop Rate by Cause (24h)",
      "type": "stat",
      "targets": [
        {
          "expr": "sum(rate(user_session_dropped_total{source=\"real\", cause!=\"client_close\"}[24h])) / clamp_min(sum(rate(user_token_revoke_total{source=\"real\"}[24h]) + rate(user_relogin_success_total{source=\"real\", trigger=\"passive\"}[24h])), 1e-9)",
          "legendFormat": "Session Drop Rate"
        }
      ],
      "thresholds": {
        "steps": [
          {"value": 0, "color": "green"},
          {"value": 0.005, "color": "red"}
        ]
      },
      "description": "AC#5 session 中断率 SLA < 0.5% (异常 drop / 总 active session estimate). 红绿阈值 0.5%."
    }
  ]
}
```

### 4.3 Alert Rules (`deploy/prometheus/yiluan-canary.yml` 追加)

```yaml
- alert: ReadOnlyFlagReloginSLAViolation
  expr: |
    sum(rate(user_relogin_success_total{source="real", trigger="post_revoke"}[24h]))
    /
    clamp_min(sum(rate(user_token_revoke_total{source="real", reason!~"credential_leak|compliance_report"}[24h])), 1e-9)
    < 0.99
  for: 30m
  labels:
    severity: critical
    team: ops-a
  annotations:
    summary: "Read-only flag relogin SLA breach (< 99%)"
    description: "Quantitative metric guard AC#5 violation. real 灰度 revoke 后用户重登成功率连续 30min 低于 99%, 阻 read-only flag real 全量推广. 见 ADR-0053 §AC#5."

- alert: ReadOnlyFlagSessionDropSLAViolation
  expr: |
    sum(rate(user_session_dropped_total{source="real", cause!="client_close"}[24h]))
    /
    clamp_min(sum(rate(user_token_revoke_total{source="real"}[24h]) + rate(user_relogin_success_total{source="real", trigger="passive"}[24h])), 1e-9)
    > 0.005
  for: 30m
  labels:
    severity: critical
    team: ops-a
  annotations:
    summary: "Read-only flag session drop SLA breach (> 0.5%)"
    description: "Quantitative metric guard AC#5 violation. real 灰度 session 异常中断率连续 30min 高于 0.5%, 阻 read-only flag real 全量推广. 见 ADR-0053 §AC#5."
```

---

## 5. Baseline Query SQL 模板

### 5.1 Mock 灰度 baseline (S2-OPS-A 套件, 7 天滑动窗口) — r1 amend

mock 灰度上线后用 **`admin_audit_logs` + `user_audit_logs`** 查 baseline (实测 schema, 红线 #1 修正):

**前提**: §3.5 alembic migration 已上 (metadata JSONB + 扩 action enum) + revoke_all/login 同 transaction 写 audit. 否则 SQL 取不到数据 (mock baseline 直接 fail = §8 哨兵 #1 红).

```sql
-- Mock 灰度 baseline (7 天滑动)
-- Source: admin_audit_logs.action='user_token_revoke' + user_audit_logs.action='user_login_success'
-- 字段实测 (2026-06-10):
--   admin_audit_logs.reason: Text 单字段 (枚举 credential_leak/compliance_report/...)
--   admin_audit_logs.metadata: JSONB (r1 §3.5 新增, 含 source=mock/real, trigger=...)
--   user_audit_logs.metadata: JSONB (同上)
WITH revoke_events AS (
    SELECT 
        target_id AS user_id,  -- admin_audit_logs.target_id = users.id
        created_at AS revoked_at,
        reason  -- 直接字段, 非 JSON
    FROM admin_audit_logs
    WHERE action = 'user_token_revoke'
      AND target_type = 'user'
      AND metadata->>'source' = 'mock'  -- r1 §3.5 新增 JSONB 字段
      AND created_at >= NOW() - INTERVAL '7 days'
      AND reason NOT IN ('credential_leak', 'compliance_report')
),
relogin_events AS (
    SELECT 
        user_id,
        created_at AS reloggin_at
    FROM user_audit_logs
    WHERE action = 'user_login_success'  -- r1 §3.5 扩 action enum
      AND metadata->>'source' = 'mock'
      AND metadata->>'trigger' = 'post_revoke'
      AND created_at >= NOW() - INTERVAL '7 days'
)
SELECT
    COUNT(DISTINCT r.user_id) AS revoked_users,
    COUNT(DISTINCT CASE 
        WHEN l.reloggin_at BETWEEN r.revoked_at AND r.revoked_at + INTERVAL '30 minutes' 
        THEN r.user_id 
    END) AS relogged_within_30min,
    ROUND(
        100.0 * COUNT(DISTINCT CASE 
            WHEN l.reloggin_at BETWEEN r.revoked_at AND r.revoked_at + INTERVAL '30 minutes' 
            THEN r.user_id 
        END) / NULLIF(COUNT(DISTINCT r.user_id), 0),
        2
    ) AS relogin_sla_percent
FROM revoke_events r
LEFT JOIN relogin_events l ON l.user_id = r.user_id;

-- Expected (r1 amend, 凝光 PM review):
--   mock 期 lower bound 95% (r0=90%, PM 推 → 95%, 风险偏小)
--   real 期严格 99%
```

```sql
-- Mock 灰度 session drop rate (7 天滑动)
WITH drop_events AS (
    SELECT user_id, created_at, metadata->>'cause' AS cause
    FROM user_audit_logs
    WHERE action = 'user_session_dropped'  -- r1 §3.5 扩 action enum
      AND metadata->>'source' = 'mock'
      AND metadata->>'cause' != 'client_close'  -- 排除主动 close
      AND created_at >= NOW() - INTERVAL '7 days'
),
active_estimate AS (
    -- 总活跃 session = revoke 数 + 自然重登数 (近似)
    SELECT (
        (SELECT COUNT(*) FROM admin_audit_logs WHERE action = 'user_token_revoke' AND metadata->>'source' = 'mock' AND created_at >= NOW() - INTERVAL '7 days')
        +
        (SELECT COUNT(*) FROM user_audit_logs WHERE action = 'user_login_success' AND metadata->>'source' = 'mock' AND metadata->>'trigger' = 'passive' AND created_at >= NOW() - INTERVAL '7 days')
    ) AS total
)
SELECT
    (SELECT COUNT(*) FROM drop_events) AS drops,
    (SELECT total FROM active_estimate) AS active_sessions,
    ROUND(100.0 * (SELECT COUNT(*) FROM drop_events) / NULLIF((SELECT total FROM active_estimate), 0), 4) AS drop_rate_percent;

-- Expected (r1 amend):
--   mock 期 < 1% (lower bound, real 严格 < 0.5%)
```

### 5.2 Real 灰度 T+7 真灰度回测对比

real 灰度上线后第 7 天用 prometheus query 拿 baseline:

```promql
# Relogin SLA (real, 7 天滑动)
sum(rate(user_relogin_success_total{source="real", trigger="post_revoke"}[7d]))
/
clamp_min(sum(rate(user_token_revoke_total{source="real", reason!~"credential_leak|compliance_report"}[7d])), 1e-9)
* 100

# Expected ≥ 99 → AC#5 quantitative phase PASS
```

```promql
# Session Drop Rate (real, 7 天滑动)
sum(rate(user_session_dropped_total{source="real", cause!="client_close"}[7d]))
/
clamp_min(sum(rate(user_token_revoke_total{source="real"}[7d]) + rate(user_relogin_success_total{source="real", trigger="passive"}[7d])), 1e-9)
* 100

# Expected < 0.5 → AC#5 quantitative phase PASS
```

### 5.3 客诉率 (需配合客服系统) — r1 amend (黄线 #3)

客诉率 < 0.1% 不在 prometheus 范围 (无标准 customer support metric SDK).

**r1 amend (黄线 #3)**:
- **Owner**: 凝光 (PM, PM review 中已 ack own)
- **流程**: weekly manual review — 每周一 PM 从客服系统 (拉单/工单系统) 拉**与 read-only flag 相关的客诉 ticket count** (按 trigger word 'token revoke' / 'session drop' / 'cannot login' 等过滤)
- **公式**: `客诉率 = 周客诉数 / 周 revoke 总数` (revoke 总数从 §5.1 SQL 拿)
- **录入 cron gate**: §6 cron `check_readonly_flag_real_gate()` 通过**手动注入接口** (`POST /admin/readonly/complaint-rate`, PM weekly 触发) 把客诉率喂给 cron gate, gate 取最近 7 天 rolling 值
- **Follow-up task** (凝光 PM 提): `S3-OPS-CUSTOMER-SUPPORT-METRIC-INTEGRATION` (P3, 待客服系统 API 接入后自动化, 不阻 §7 read-only flag 上线)

⚠️ **关键 trade-off**: 客诉率手动 vs 自动 — real 上线第一阶段接受 manual weekly, 后续 S3-OPS 把客服系统 API 化.

---

## 6. Real T-7 Cron Gate (AC#6 实施 hint) — r1 amend

**r1 amend (黄线 #2 + Q4)**: 拆独立 follow-up task `S2-OPS-A-READONLY-REAL-GATE-CRON` (P1, develop, hutao own, deps=[ADMIN-API, METRIC-DASHBOARD]), 凝光 PM + 刻晴 review 双推. 本 design 给 cron signature hint, 实施由该 follow-up task 接.

**cron 调度时区**: **02:00 UTC** (与现有 `share_metrics` reconciliation cron 时区惯例不一致, 黄线 #2 提及). 选 UTC 理由:
- prometheus 数据天然 UTC, retention window 计算 UTC 一致
- `reconcile_money` cron 02:00 GMT+8 (=18:00 UTC) 是历史业务时区惯例, real T-7 cron 是技术 gate, 不必绑业务时区
- 不阻 design, **黄线 #2 接受** (本 design 锁定 02:00 UTC, follow-up 实施按此)

```python
# backend/app/cron/readonly_flag_real_gate.py (新建, S2-OPS-A-READONLY-REAL-GATE-CRON 实施)

"""
ADR-0053 §AC#6 real T-7 cron gate.

real 上线 T-7 天自动 cron, query prometheus 3 metric + 7 天数据 → 全绿放行, 任一缺失/breach → NoGo 哨兵 1 红.

调度: 每日 02:00 UTC (real go-live 前 7 天起跑)
"""

async def check_readonly_flag_real_gate() -> dict:
    """
    Returns: {
        "go_no_go": "GO" | "NOGO",
        "relogin_sla": float (% 99+ = GO),
        "session_drop_rate": float (% <0.5 = GO),
        "metric_deployed": dict (3 metric 是否都查得到数据),
        "customer_complaint_rate": float | None (None = manual review 待入, 见 §5.3),
        "reason": str (NOGO 时填)
    }
    """
    # 1. verify 3 metric 都查得到数据 (≥ 7 天数据)
    # 2. relogin SLA ≥ 99
    # 3. session drop < 0.5
    # 4. customer_complaint_rate < 0.1 (manual 注入, 客服系统 weekly review)
    # 5. 任一 fail → NOGO + alert 哨兵 1 红
    ...
```

---

## 7. AC verify map (r1 amend)

| 本 task AC | 本 design 覆盖 |
|---|---|
| AC#1 部署 `user_token_revoke_total{reason}` (r1: source label 删) | §3.2 metric 定义 + §3.4 hook + §3.5 audit schema migration |
| AC#2 部署 `user_relogin_success_total{trigger}` (r1: source label 删) | §3.2 metric 定义 + §3.4 hook + §3.5 audit schema migration |
| AC#3 部署 `user_session_dropped_total{cause}` (r1: source label 删) | §3.2 metric 定义 + §3.4 hook + §3.5 audit schema migration |
| AC#4 grafana panel 3 个 + commit `ops/grafana/yiluan-canary.json` | §4 dashboard 设计 (新文件 `yiluan-readonly-flag.json`, 不污染 yiluan-canary, **trade-off §11.1, keqing PR #248 review ✅ APPROVE 此点**) |
| AC#5 baseline query SQL 模板 (mock 7 天滑动 + real T+7 对比) | §5 SQL + PromQL 模板 (r1 §5.1 字段实测修正, §5.3 客诉率 owner 明示) |
| AC#6 real T-7 cron gate (3 metric + 7 天全绿) | §6 cron hint + §6 拆 follow-up task `S2-OPS-A-READONLY-REAL-GATE-CRON` (r1 Q4) |
| AC#7 PR description 强制 cite ADR-0053 §7 + §8 | 本 design PR description 强制 cite |

---

## 8. 哨兵集成 (r1 amend)

ADR-0053 §8 哨兵 #1 (`S2-OPS-A-METRIC-DASHBOARD-READONLY` P1) 本 design 完成 = 哨兵转黄. 完整解锁需:

1. ✅ design done (本 PR merge)
2. ⏳ implement done (`S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` 完成: metric 埋点 + audit_log hook + §3.5 migration **同 PR 出**)
3. ⏳ cron gate done (`S2-OPS-A-READONLY-REAL-GATE-CRON` r1 Q4 follow-up)
4. ⏳ deploy done (grafana + prometheus alert + cron 上线)
5. ⏳ 7 天数据收集 (mock 灰度起跑, real go-live 前)
6. ⏳ baseline query 全绿 (§5.1 mock SQL + §5.2 real PromQL)
7. ⏳ 客诉率 weekly manual review (§5.3, PM 凝光 own)

任一未完成, `S2-DEV-016-READ-ONLY-FLAG-DB` blocked (depends_on 链).

---

## 9. Trade-off (r1 amend)

### 9.1 Grafana 文件位置 — keqing review ✅ APPROVE

task description AC#4 写 "部署到 `ops/grafana/yiluan-canary.json` 并 commit", 我设计**独立新文件** `ops/grafana/yiluan-readonly-flag.json`. keqing PR #248 review (id 4467903580) 明确 ✅ APPROVE 此 trade-off.

### 9.2 不直接定义 cron 实施

§6 只 hint cron gate 结构, 不写完整代码. r1 amend 拆 follow-up task `S2-OPS-A-READONLY-REAL-GATE-CRON` (P1, develop, hutao).

### 9.3 客诉率 weekly manual + S3 自动化 (r1 amend)

r0 "客诉率不在本 design" → r1 §5.3 补完 owner + 流程:
- 第一阶段: PM 凝光 own, weekly manual 客服系统拉数 + POST 接口注入 cron gate
- 第二阶段: S3 follow-up task `S3-OPS-CUSTOMER-SUPPORT-METRIC-INTEGRATION` (P3, 客服系统 API 化, 不阻本 design)

### 9.4 mock vs real prometheus source label 删 (r1 新增, 黄线 #1)

r0 设计 prometheus counter 带 `source=mock|real` label 区分. r1 amend 删 source label:
- prometheus 只看 real, mock 走 audit SQL (§5.1)
- 职责物理分离, real 数据无 mock noise, alert 阈值不被 mock 拉偏
- cardinality 22→11 series

### 9.5 audit_log hook 同 transaction 强约束 (r1 新增, 红线 #1)

r0 仅 hint metric hook 位置. r1 amend 加 audit_log hook **强约束**:
- 同 transaction 写 `admin_audit_logs` / `user_audit_logs` (与 metric counter 同 method)
- 需 §3.5 alembic migration (metadata JSONB + 扩 action enum) 前置
- 这是 baseline 取数 (§5.1) 的物理依赖, 不可省

---

## 10. Refs

- [ADR-0053 §AC#5, §7, §8](../adr/ADR-0053-token-readonly-flag.md)
- [PR #246 keqing review](https://github.com/renwenlong/YiLuAn/pull/246) (红线: baseline 来源不存在)
- `backend/app/observability/share_metrics.py` (现有 metric pattern 参考)
- `backend/app/observability/reconciliation_metrics.py` (Counter / Gauge helper 参考)
- `backend/app/services/auth.py:227` (revoke_all 实装位置 hint)
- `backend/app/core/security.py:16` (token_version cursor 设计)
- `ops/grafana/yiluan-canary.json` (现有 dashboard 参考)
- `deploy/prometheus/yiluan-canary.yml` (现有 alert rule 参考)

---

## 11. Sign-off

| 角色 | Owner | Approve | Date |
|---|---|---|---|
| Architect | 魈 | r1 amend | 2026-06-10 |
| Reviewer (test) | 刻晴 | r0 🔴 → r1 amend, 待 re-review | 2026-06-10 |
| Reviewer (PM) | 凝光 | r0 🟢 APPROVE (业务侧) | 2026-06-10 |
| Implementer (OPS hint) | hutao | r0 review pending | — |

---

## 12. Changelog

### 12.1 r0 → r1 (2026-06-10 13:25 UTC, keqing PR #248 review 4467903580 amend)

**🔴 红线 #1 (方案 A)**: §5.1 baseline SQL 字段全错 (实测 `audit_logs` 表不存在, 应为 `admin_audit_logs` + `user_audit_logs` 分离表, 字段非 JSON detail 而是 reason: Text 单字段, 无 source label, revoke_all 无 audit hook). r1 修正:
- §3.4 加 audit_log hook (双埋点 prometheus + audit, 同 transaction)
- §3.5 新增 alembic migration spec (metadata JSONB + 扩 action enum)
- §5.1 SQL 全改, `FROM admin_audit_logs` + `metadata->>'source'`, mock baseline lower bound 90%→95% (凝光 PM review)
- §8 哨兵集成步骤 (2) 补 audit_log hook + migration 同 PR 必出

**🟡 黄线 #1**: source label 删, prometheus 只看 real, mock 走 audit SQL. r1 修正:
- §3.2 3 metric 删 source label
- §3.3 cardinality 22→11 series
- §9.4 trade-off 新增解释

**🟡 黄线 #2**: §6 cron 调度时区 02:00 UTC vs 现有 `reconcile_money` 02:00 GMT+8. r1 修正: 锁 02:00 UTC, §6 注明理由 (prometheus 数据 UTC 一致), 接受 keqing nit, 不阻.

**🟡 黄线 #3**: §5.3 客诉率 owner + 流程空白. r1 修正:
- §5.3 补 owner=凝光 PM, weekly manual review + POST 注入接口, follow-up `S3-OPS-CUSTOMER-SUPPORT-METRIC-INTEGRATION` (P3)
- §6 cron return dict 加 `customer_complaint_rate` 字段
- §9.3 trade-off 重写

**Q4 拆 follow-up**: `S2-OPS-A-READONLY-REAL-GATE-CRON` (P1, develop, hutao, deps=[ADMIN-API, METRIC-DASHBOARD]). r1 §6 + §7 + §8 + §9.2 + §11 全部明示. (凝光 PM + 刻晴 双推, 不阻本 design)

**S2-TEST-016 受影响**: red-line #1 方案 A → `admin_audit_logs.metadata` JSONB → keqing E#6 audit log 全字段测试范围扩 (verify metadata 字段). 只是扩, 不阻测试.
