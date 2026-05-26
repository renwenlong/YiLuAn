# 决议编号审计 — 2026-05-26

- 审计人：甘雨（协调者 / 文档专家）
- 范围：`docs/adr/`、`docs/decisions/`、`docs/DECISION_LOG.md`
- 触发：W1 sprint 文档清扫
- 关联 PR：`chore/w1-adr-and-docs-cleanup`

## 1. 摘要

W1 sprint 文档审计发现两类编号问题：

1. **ADR 编号空间污染**：`docs/adr/` 与 `docs/decisions/` 共享 `ADR-NNNN` 命名，编号 0028/0029/0030 在两目录各占一份不同主题的文件。
2. **`DECISION_LOG.md` 中的 D-编号缺号**：D-025 / D-026 / D-029 / D-030 / D-031 在 `DECISION_LOG.md` 中通过 `^## D-0XX` grep **全部缺失**；仅 D-032 实际存在（line 810，「iOS 工程文件声明式化（XcodeGen）」）。

## 2. 事实数据

### 2.1 ADR 编号冲突

| 编号 | `docs/adr/` | `docs/decisions/` |
|------|-------------|-------------------|
| 0028 | — | `ADR-0028-canary-release-and-rollback.md`（Proposed, 2026-04-24） |
| 0029 | `ADR-0029-emergency-pii-retention.md`（Accepted, 2026-04-27） | `ADR-0029-expired-order-payment-handling.md` |
| 0030 | `ADR-0030-staging-mock-environment.md`（Accepted, 2026-04-27） | `ADR-0030-money-decimal-migration.md`（Accepted, 2026-04-25） |

**ADR-0028 引用面**（12 文件 31 处，重编号成本高）：

- `backend/scripts/check_migration_reversibility.py`
- `docs/CLEANUP_REPORT_2026-04-29.md`
- `docs/DECISION_LOG.md`
- `docs/FULL_CLEANUP_REPORT_2026-04-29.md`
- `docs/MIGRATION_REVERSIBILITY_REPORT.md`
- `docs/PROVIDER_FREEZE.md`
- `docs/RUNBOOK_ROLLBACK.md`
- `docs/ops/GOLIVE_DRYRUN_REPORT_2026-04-25.md`
- `docs/ops/INCIDENT_PLAYBOOK.md`
- `docs/runbook-go-live.md`
- `ops/grafana/README.md`

### 2.2 DECISION_LOG.md 缺号

`DECISION_LOG.md` 实测（`grep ^## D-0XX`）：

| 编号 | 是否存在 | 备注 |
|------|----------|------|
| D-025 | ❌ 缺失 | 多处文档引用「D-025 Readiness 四件套」（如 ADR-0026 背景段），但 DECISION_LOG 无对应条目 |
| D-026 | ❌ 缺失 | ADR-0026 关联决策写明 D-026，但 DECISION_LOG 无条目 |
| D-029 | ❌ 缺失 | — |
| D-030 | ❌ 缺失 | 注意 `docs/decisions/D-030_feature_backlog_decisions.md` 存在，但 DECISION_LOG 主表无 D-030 条目 |
| D-031 | ❌ 缺失 | — |
| D-032 | ✅ 存在 | line 810 — iOS 工程文件声明式化（XcodeGen） |

来源：W1 sprint 侦察 SUMMARY（主代理代为执行的 grep）。

## 3. 处置建议

### 3.1 ADR 编号冲突 — 已采纳（不重编号）

- 保留两目录现状，按目录区分语义。
- `docs/adr/README.md` 标注两套占用并将「下一可用编号」推至 `0035`。
- 新建 `docs/decisions/README.md` 明确「本目录不再接受新 ADR」。
- 新 ADR 一律去 `docs/adr/`。

### 3.2 DECISION_LOG 缺号 — 待帝君拍板

候选方案（二选一，建议**方案 A**）：

**方案 A · 补登简短决议条目**（推荐）

- 为 D-025/026/029/030/031 各补一条占位条目，至少包含：标题、日期（尽力考据）、一句话决议、链接到对应 ADR / commit / 文档。
- 优点：编号连续，外部引用不再悬空；与 ADR-0026 等已存在的关联决策对得上。
- 工作量：约 1-2 小时（含考据）；可由产品经理 / 架构师协助回忆。

**方案 B · 明确弃用编号**

- 在 DECISION_LOG.md 顶部增加「废弃编号清单」段：D-025/026/029/030/031 标注「编号弃用，无对应决议条目」。
- 优点：零考据成本。
- 缺点：ADR-0026 等文档中的 `D-026` 引用变成悬空指针；不利于审计追溯。

### 3.3 D-030 的特殊情况

`docs/decisions/D-030_feature_backlog_decisions.md` 文件存在但 DECISION_LOG.md 中 D-030 条目缺失。

- 建议：将该文件视作 D-030 的"长文"，在 DECISION_LOG.md 中补登一条 D-030 摘要并链接到该文件。

## 4. 行动项

| # | 行动 | 负责 | 状态 |
|---|------|------|------|
| 1 | `docs/adr/README.md` 更新编号表与缺号说明 | 甘雨 | ✅ 本 PR 完成 |
| 2 | 新建 `docs/decisions/README.md` | 甘雨 | ✅ 本 PR 完成 |
| 3 | ADR-0026 状态 Proposed → Accepted + Implementation Notes | 甘雨 | ✅ 本 PR 完成 |
| 4 | DECISION_LOG.md 缺号处置方案拍板 | 帝君 | ⏳ 待决策 |
| 5 | 按拍板方案补登 / 弃用 D-025/026/029/030/031 | 待分配 | ⏳ Follow-up |
| 6 | CLAUDE.md / TASK_BREAKDOWN.md 同步过期内容 | 待分配 | ⏳ Follow-up（本 PR 仅加横幅） |

## 5. 参考

- `docs/adr/README.md`（本 PR 更新）
- `docs/decisions/README.md`（本 PR 新建）
- `docs/adr/ADR-0026-outbound-reliability.md`（本 PR 更新）
- W1 sprint 侦察 SUMMARY（主代理代执行 grep / find 的结果）
