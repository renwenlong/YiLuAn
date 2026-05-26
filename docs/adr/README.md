# ADR (Architecture Decision Record) 注册表

> **下一可用编号** = `0035`（参见下方「已知问题」，**不要再用 0028/0029/0030**）
> 新建 ADR 之前先在本表登记编号 + 标题（避免编号冲突），PR 合入时再补 Status/日期。

> ⚠️ **已知问题（2026-05-26 甘雨审计）**：编号 0028/0029/0030 在 `docs/adr/` 和 `docs/decisions/` 各占一份不同主题，**编号空间被污染**。
> - 不重编号（旧引用面太大，仅 ADR-0028 就有 12 文件 31 处引用）；保留两套 ADR 共存，按目录区分语义。
> - **新建 ADR 从 0035 起步**，避免再冲突。
> - 单一权威注册表 = 本文件；`docs/decisions/README.md` 指向此。
> - 详细审计见 `docs/audits/2026-05-26-decision-numbering.md`。

## 当前已占用编号

### `docs/adr/`（架构决策，权威目录）

| 编号 | 标题 | 状态 | 日期 | 关联决策 |
|------|------|------|------|---------|
| 0001 | 微信支付集成方案 | Accepted | 2025-Q4 | — |
| 0026 | 出站调用可靠性（重试 / 熔断 / 超时） | Accepted | 2026-05-26 | D-026 |
| 0029 | Emergency PII 留存与加密 | Accepted | 2026-04-27 | D-043 |
| 0030 | Staging Mock 环境 | Accepted | 2026-04-27 | D-039 |
| 0031 | WebSocket / ChatService 通道统一 | Accepted | 2026-04-27 | D-040 |
| 0032 | 资金三源对账（Money Reconciliation） | Accepted | 2026-04-28 | D-044 / D-046 / D-047 |
| 0033 | Money Reconciliation 扩展（Scaling） | Accepted | 2026-04 | D-044 派生 |
| 0034 | Admin v2 鉴权 | Accepted | 2026-04 | — |

### `docs/decisions/`（历史遗留，与本目录共享编号空间，**不再新增**）

| 编号 | 标题 | 状态 | 日期 | 备注 |
|------|------|------|------|------|
| 0028 | Canary Release & Rollback | Proposed | 2026-04-24 | 引用面广（12 文件 31 处），保留原编号 |
| 0029 | Expired Order Payment Handling | — | — | 与本目录 ADR-0029 编号冲突 |
| 0030 | Money Decimal Migration | Accepted | 2026-04-25 | 与本目录 ADR-0030 编号冲突 |

> **缺号说明**：0002–0025 / 0027 历史上未占用；**0028/0029/0030 视为已被 `docs/decisions/` 占用，不可复用**；0035 起为下一可用区间。
> **历史**：早期决策直接落入 `DECISION_LOG.md`（D-001~D-018）；2026-Q2 之后
> 将系统级决策升级为 ADR，DECISION_LOG 仅记录决议要点（D-044 Q1 拍板）。

## 写作规范

- 每个 ADR 一个文件，命名 `ADR-NNNN-kebab-case-title.md`。
- 章节固定：`Context` / `Decision` / `Consequences` / `Alternatives Considered`，
  可选 `Open Questions` / `Rollout Plan` / `Related`。
- 状态：`Proposed` → `Accepted`（或 `Superseded`）。
- ADR 编号一旦分配，**不复用**。被 supersede 的 ADR 标 `Superseded by ADR-NNNN`，
  原文件保留。
- 新 ADR 一律放 `docs/adr/`，**不要再往 `docs/decisions/` 加 ADR-* 文件**。

## PR Checklist 模板片段

```markdown
- [ ] 涉及架构/数据/合规决策？→ 已新增/更新 ADR-NNNN，并在本 README 表格登记
- [ ] DECISION_LOG.md 已记录 D-NNN 决议（短摘要 + 链接到 ADR）
- [ ] 编号无冲突（已查阅本 README 「下一可用编号」，从 0035 起）
- [ ] PR body 说明：本变更是 ADR 落地的哪个 milestone（M1/M2/M3...）
```

## 模板

```md
# ADR-NNNN 标题

- 日期：YYYY-MM-DD
- 状态：Proposed / Accepted / Superseded by ADR-NNNN

## 1. Context（背景）

## 2. Decision（决策）

## 3. Consequences（后果）

## 4. Alternatives Considered（备选方案）

## 5. Related

- DECISION_LOG: D-NNN
- 相关 ADR: ADR-NNNN
```
