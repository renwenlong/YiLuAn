# S2-OPS-A Read-Only Flag Metric Dashboard Design

> **task**: `S2-OPS-A-METRIC-DASHBOARD-READONLY` (P1, design, architect own)  
> **关联 ADR**: [ADR-0053 §7 + §8 哨兵 #1](../adr/ADR-0053-token-readonly-flag.md)  
> **前置于**: `S2-DEV-016-READ-ONLY-FLAG-DB` (依赖本 design 完成 + metric 实装上线 + 7 天数据全绿)  
> **author**: 魈 (architect)  
> **created**: 2026-06-10  
> **status**: draft r0

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

### 3.2 3 个 Metric 定义

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
    "User-level access token revocation events (bumps users.token_version).",
    ["reason", "source"],
)
"""
labels:
  reason:
    - "credential_leak"   - 真凭据泄露 (紧急吊销, 不计入客诉率)
    - "compliance_report" - 合规举报 (紧急吊销, 不计入客诉率)
    - "user_request"      - 用户主动登出
    - "admin_kick"        - 管理员手动 kick
    - "auto_scanner"      - 自动扫描器 (与 share_token_auto_revoked_total 区分用户范围)
  source:
    - "mock"   - mock 灰度 (S2-OPS-A 套件 wrapper)
    - "real"   - real 灰度 / 生产
"""


# AC#2: 用户重登成功 (revoke 后 baseline 99% 验证)
USER_RELOGIN_SUCCESS_TOTAL: Counter = _get_or_create_counter(
    "user_relogin_success",
    "User successful re-login after token revocation (used to validate 99% relogin SLA).",
    ["source", "trigger"],
)
"""
labels:
  source:
    - "mock"   - mock 灰度
    - "real"   - real 灰度 / 生产
  trigger:
    - "post_revoke"     - revoke 后 30min 内重登 (核心 SLA 指标, 反映用户体验)
    - "passive"         - 自然重登 (token 自然过期, 非 revoke 触发, 不计入 SLA)
"""


# AC#3: session 中断 (drop rate < 0.5% baseline 验证)
USER_SESSION_DROPPED_TOTAL: Counter = _get_or_create_counter(
    "user_session_dropped",
    "User session terminated unexpectedly (revoke / keepalive timeout / server kick).",
    ["cause", "source"],
)
"""
labels:
  cause:
    - "revoke"            - token revoke 导致 (refresh_token 失效 / token_version mismatch)
    - "keepalive_timeout" - session keepalive 超时 (refresh token TTL 到)
    - "server_kick"       - 服务端主动 disconnect (维护 / 异常)
    - "client_close"      - 客户端主动关闭 (不计入 drop, label 用于排除)
  source:
    - "mock"   - mock 灰度
    - "real"   - real 灰度 / 生产
"""
```

### 3.3 Cardinality 估算

| Metric | label combination | 最大基数 |
|---|---|---|
| `user_token_revoke_total` | 5 reason × 2 source | 10 |
| `user_relogin_success_total` | 2 source × 2 trigger | 4 |
| `user_session_dropped_total` | 4 cause × 2 source | 8 |
| **共** | | **22 time series** |

✅ 22 series 远低于 prometheus 推荐上限 (通常 < 1000), 零基数风险.

### 3.4 Endpoint Hook 实装点 (参考, 不在本 design 范围)

`S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` (hutao) 接手时 hook 这些点:

| Metric | Hook 位置 | 触发条件 |
|---|---|---|
| `user_token_revoke_total{reason, source}` | `backend/app/api/v1/users.py:112` revoke_all (推荐 wrapper) | `bumps token_version` 后 `+1`, reason 从 request body / context 拿, source 从 env (mock vs real) 拿 |
| `user_relogin_success_total{source, trigger}` | `backend/app/services/auth.py` `login_user` 成功 path | 用户 login 成功后, query 30min 内是否有 `user_token_revoke_total` 事件 → 是 = `post_revoke`, 否 = `passive` |
| `user_session_dropped_total{cause, source}` | `backend/app/services/auth.py` `get_current_user` reject path + `RefreshTokenStore` 失效 path | token_version mismatch → `revoke`, refresh expire → `keepalive_timeout`, manual disconnect → `server_kick` |

⚠️ **本 design 不指定具体实施代码** (那是 develop task 范围), 仅 hint 实装位置.

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

### 5.1 Mock 灰度 baseline (S2-OPS-A 套件, 7 天滑动窗口)

mock 灰度上线后用 `audit_logs` 查 baseline (不靠 prometheus, 因 mock 期可能 metric 未部署):

```sql
-- Mock 灰度 baseline (7 天滑动)
-- Source: audit_logs (S2-OPS-A 套件已埋点)
WITH revoke_events AS (
    SELECT 
        user_id,
        created_at AS revoked_at,
        detail->>'reason' AS reason
    FROM audit_logs
    WHERE action = 'user_token_revoke'
      AND detail->>'source' = 'mock'
      AND created_at >= NOW() - INTERVAL '7 days'
      AND detail->>'reason' NOT IN ('credential_leak', 'compliance_report')
),
relogin_events AS (
    SELECT 
        user_id,
        created_at AS reloggin_at
    FROM audit_logs
    WHERE action = 'user_login_success'
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

-- Expected: relogin_sla_percent ≥ 99 (mock 期可接 90%+ 作为 lower bound, real 期严格 99)
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

### 5.3 客诉率 (需配合客服系统)

客诉率 < 0.1% 不在 prometheus 范围, 配合客服系统 query (本 design 不覆盖, 由 PM/客服团队 own).

---

## 6. Real T-7 Cron Gate (AC#6 实施 hint)

`S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` 实施时加 cron gate:

```python
# backend/app/cron/readonly_flag_real_gate.py (新建)

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
        "reason": str (NOGO 时填)
    }
    """
    # 1. verify 3 metric 都查得到数据 (≥ 7 天数据)
    # 2. relogin SLA ≥ 99
    # 3. session drop < 0.5
    # 4. 任一 fail → NOGO + alert 哨兵 1 红
    ...
```

⚠️ **本 design 不指定具体 cron 实施** (那是 develop task 范围, 由 `S2-OPS-A-READ-ONLY-FLAG-ADMIN-API` 或独立 follow-up task `S2-OPS-A-READONLY-REAL-GATE-CRON` 接).

---

## 7. AC verify map

| 本 task AC | 本 design 覆盖 |
|---|---|
| AC#1 部署 `user_token_revoke_total{reason, source}` | §3.2 metric 定义 + §3.4 hook 位置 hint |
| AC#2 部署 `user_relogin_success_total{source, trigger}` | §3.2 metric 定义 + §3.4 hook 位置 hint |
| AC#3 部署 `user_session_dropped_total{cause, source}` | §3.2 metric 定义 + §3.4 hook 位置 hint |
| AC#4 grafana panel 3 个 + commit `ops/grafana/yiluan-canary.json` | §4 dashboard 设计 (新文件 `yiluan-readonly-flag.json`, 不污染 yiluan-canary, **此点跟 task description 偏离, 走 §11 trade-off**) |
| AC#5 baseline query SQL 模板 (mock 7 天滑动 + real T+7 对比) | §5 SQL + PromQL 模板 |
| AC#6 real T-7 cron gate (3 metric + 7 天全绿) | §6 cron hint (实施由后续 task) |
| AC#7 PR description 强制 cite ADR-0053 §7 + §8 | 本 design PR description 强制 cite |

---

## 8. 哨兵集成

ADR-0053 §8 哨兵 #1 (`S2-OPS-A-METRIC-DASHBOARD-READONLY` P1) 本 design 完成 = 哨兵转黄. 完整解锁需:

1. ✅ design done (本 PR merge)
2. ⏳ implement done (S2-OPS-A-READ-ONLY-FLAG-ADMIN-API 完成 metric 埋点)
3. ⏳ deploy done (grafana + prometheus alert 上线)
4. ⏳ 7 天数据收集 (real go-live 前)
5. ⏳ baseline query 全绿

任一未完成, `S2-DEV-016-READ-ONLY-FLAG-DB` blocked (depends_on 链).

---

## 9. Trade-off

### 9.1 Grafana 文件位置

task description AC#4 写 "部署到 `ops/grafana/yiluan-canary.json` 并 commit", 我设计**独立新文件** `ops/grafana/yiluan-readonly-flag.json`. 理由:
- `yiluan-canary.json` 是 canary launch dashboard, 跟 share token 滥用 metric 强绑定, 加 read-only flag panel 视觉混乱
- 独立 dashboard 便于 read-only flag 团队 (S2-OPS-A) 聚焦, OPS 入口分离
- 不影响 prometheus rule (`yiluan-canary.yml`) 追加 alert 兼容

→ AC#4 措辞偏离, 由 review 决定接受 trade-off 还是回到合并写法.

### 9.2 不直接定义 cron 实施

§6 只 hint cron gate 结构, 不写完整代码. 这是 design 而非 develop, 实施由 OPS/develop task 接.

### 9.3 客诉率不在本 design

客诉率 < 0.1% (AC#5 第三条数字) 走客服系统而非 prometheus, 不在本 design 范围.

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
| Architect | 魈 | (draft r0) | 2026-06-10 |
| Reviewer (test) | 刻晴 | pending | — |
| Implementer (OPS hint) | hutao | pending notify | — |
