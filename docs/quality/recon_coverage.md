# 资金对账模块覆盖率报告

> Action #9 — TD-MONEY-01 / ADR-0032 W18 QA 巩固期。
> 报告日期：**2026-04-29**
> Python 3.12.10 / coverage 7.13.5 / `[tool.coverage.run] core = "sysmon"`

## 1. 范围与方法

**被测包**（`--source`）：

- `app.services.reconciliation`（autofix / diff / incremental）
- `app.api.v1.admin.reconciliation`（D-048 worklist + 双签 close）
- `app.cron.reconcile_money`（T+1 全量对账 cron）
- `app.cron.reconciliation_cleanup`（旧 run/diff 清理）

**测试集**（`pytest`）：

- `tests/services/reconciliation/`（含本期新增 `test_recon_autofix_concurrency.py`）
- `tests/test_admin_reconciliation.py`（含本期新增 `TestAdminReconDoubleSignNegative` 类，4 case）
- `tests/cron/test_reconcile_money.py`
- `tests/cron/test_reconciliation_cleanup.py`

**采集命令**（语句覆盖）：

```bash
COVERAGE_CORE=sysmon \
  coverage run \
    --source=app.services.reconciliation,app.api.v1.admin.reconciliation,\
app.cron.reconcile_money,app.cron.reconciliation_cleanup \
    -m pytest tests/services/reconciliation tests/test_admin_reconciliation.py \
              tests/cron/test_reconcile_money.py tests/cron/test_reconciliation_cleanup.py -q
coverage report -m
```

> 关键：`pyproject.toml` 已锁定 `[tool.coverage.run] core = "sysmon"`。
> Python 3.12 下若回退到 C tracer，async generator / try/except 块约 4% 会
> 被错误归为 miss（实测 admin_recon 行覆盖会从 93% 跌到 50%）。CI 与本地
> 必须保持 `sysmon` 一致，避免分支覆盖统计漂移。

## 2. 总体覆盖率

| 维度 | 指标 | 数值 |
| --- | --- | --- |
| 语句覆盖（statement） | 总 / miss | 611 / 49 → **92%** |
| 分支覆盖（branch，参考值，sysmon 下退化为 partial） | 128 / 20 partial → **82%** | |
| 测试套总数 | 全仓 `pytest -q` | **1104 passed**（+16 skipped / 1 xfailed） |
| 本期新增 case | autofix concurrency + double-sign neg | **+4 + +4 = 8** |

> 分支统计当前在 sysmon 下取值偏保守（line 与 branch 不一致是已知现象，
> 详 https://coverage.readthedocs.io/en/7.13.5/branch.html）。本表
> 主指标采用语句覆盖（92%）。

## 3. 模块拆解

| 模块 | Stmts | Miss | Cover | 主要 Missing 行 |
| --- | --- | --- | --- | --- |
| `app/services/reconciliation/__init__.py` | 3 | 0 | **100%** | — |
| `app/services/reconciliation/autofix.py` | 65 | 1 | **98%** | L79（`order_id is None` 早退分支：cron 入口已强制 order_id） |
| `app/services/reconciliation/diff.py` | 95 | 4 | **96%** | L108 / 233 / 262 / 284（极端价比对、空 ledger、provider downcast） |
| `app/services/reconciliation/incremental.py` | 138 | 22 | **84%** | L256-260（rollback 重入）/ L332-350（sweep failed run 兜底） |
| `app/api/v1/admin/reconciliation.py` | 109 | 8 | **93%** | L121-132（filter 无值短路）、L203 / 250（双签 audit 写入兜底） |
| `app/cron/reconcile_money.py` | 157 | 12 | **92%** | L94 / 165-167（kill-switch）、L304-306（partial run 收尾）、L455-459（季度边界） |
| `app/cron/reconciliation_cleanup.py` | 44 | 2 | **95%** | L48 / 152（dry-run 路径） |
| **TOTAL** | **611** | **49** | **92%** | — |

## 4. 缺口分析（Gap Analysis）

### 4.1 autofix 极端竞态（incremental.py L332-350 / autofix.py L79）

M3 当前**没有显式分布式锁**，幂等性依赖 `status` 终态的 *terminal-skip* 守卫：

- ✅ **已覆盖**（`test_recon_autofix_concurrency.py`）：
  - 串行重入两次 → 1 success + 1 skipped；
  - `asyncio.gather` 同 diff 并发 → 最终状态收敛到 `compensated`，无 escalate；
  - mock provider 第一次失败、第二次成功 → 仅 1 条 `success` ledger；
  - 5 次串行调用 → 仅 1 次 `auto_retry_count` 自增。
- ⚠️ **未覆盖（M4 待办）**：
  - 真实 PG `SELECT … FOR UPDATE` / `pg_advisory_xact_lock` 的悲观锁分支
    （SQLite 测试无法触发，需 `pytest -m smoke` + 真 Postgres）。
  - 多实例 worker 同时跑 `autofix_run_diffs(diff_ids=[…])` 时的 unique
    constraint 回退路径（依赖 ADR-0032 M4 的 `reconciliation_actions`
    部分唯一索引，本仓尚未引入）。
  - `provider.query_order` 真实 RPC 异常树（M3 仍是 bookkeeping replay，
    无 RPC 调用，对应代码路径未落地）。

> 结论：M3 的“幂等锁”是**单进程串行 + 状态机守卫**；分布式硬竞态留待 M4
> 引入显式锁后再补 case。本期已把现实可达的 race 全部上证。

### 4.2 Q3 季度边界（reconcile_money.py L455-459）

`run_full_t1` 在跨季度（如 03-31 → 04-01）时会触发额外的“季度归档”分支
（D-044 Q3：当 `window_end.quarter != window_start.quarter` 时把 run
打 `quarter_boundary` 标签并通知 finance）。

- ✅ **已覆盖**：常规 T+1 窗口、跨日窗口、空数据窗口；
- ⚠️ **未覆盖**：
  - 跨季度边界本身（需要 freeze time 到 `YYYY-04-01 00:00:00`，
    本期未引入 `freezegun`，避免拖累 1104 case 全绿）；
  - 跨季度 + autofix 重试上限叠加场景（24h 窗口跨季度时 retry 计数的
    时区归一化）。

> 结论：Q3 边界靠生产 cron 实跑覆盖；测试侧建议下个 sprint 引入
> `freezegun` 后专门加 1-2 case，预计可把 `reconcile_money.py` 推到
> 95%+。当前 92% 已满足 ADR-0032 “核心模块 ≥ 90%” 门槛。

### 4.3 其他次要缺口

- `incremental.py` L256-260 / 302-304：sweep 失败时的 rollback + 状态
  落库分支，依赖 DB-level 异常注入，价值/成本不划算；
- `admin/reconciliation.py` L121-132：filter 参数全为空时的短路返回，
  现有 `test_list_diffs_basic` 已隐式覆盖语义，行号是 `if … else` 内
  的短分支。

## 5. 验证摘要

- 全仓 `pytest -q` → **1104 passed, 16 skipped, 5 deselected, 1 xfailed**（169.89s）。
- 仅 recon 子集 → 77 passed, 1 skipped, 1 xfailed（10.34s）。
- coverage 总值 **92%**（611 stmts, 49 miss）。
- 本期新增测试：
  - `tests/services/reconciliation/test_recon_autofix_concurrency.py`：4 case；
  - `tests/test_admin_reconciliation.py::TestAdminReconDoubleSignNegative`：4 case。

## 6. 后续行动（W19 候选）

1. 引入 `freezegun`，覆盖 Q3 季度边界 + 24h retry 窗口的时区分支。
2. 在 ADR-0032 M4 引入 `reconciliation_actions` 部分唯一索引后，
   补真分布式锁的回退路径测试（需要 smoke + 真 PG）。
3. `incremental.py` rollback 路径用 monkeypatch 注入 `IntegrityError`
   兜底测试，目标把该模块推到 90%+。
