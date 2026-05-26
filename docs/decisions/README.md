# `docs/decisions/` — 决议记录目录

> **权威 ADR 注册表在 [`../adr/README.md`](../adr/README.md)。本目录不再接受新 ADR。**

## 这是什么

本目录历史上承担过 ADR（Architecture Decision Record）角色，部分文件以 `ADR-NNNN-*.md` 命名，与 `docs/adr/` **共享同一个编号空间**，导致编号 0028 / 0029 / 0030 在两个目录各占一份不同主题：

| 编号 | `docs/adr/` 主题 | `docs/decisions/` 主题 |
|------|------------------|------------------------|
| 0028 | （未占用） | Canary Release & Rollback |
| 0029 | Emergency PII 留存与加密 | Expired Order Payment Handling |
| 0030 | Staging Mock 环境 | Money Decimal Migration |

## 现状策略（2026-05-26 甘雨审计后确认）

1. **保留现状不动** — ADR-0028（canary）已被 12 个文件 31 处引用，重编号风险大于收益。
2. **新 ADR 一律去 [`docs/adr/`](../adr/)**，从编号 `0035` 起步。本目录不再新增 `ADR-*` 文件。
3. **本目录文件按"决议记录"语义解读** —— 记录某个具体决议的来龙去脉，**不视作正式架构决策记录**；如需升级为 ADR，请在 `docs/adr/` 新建文件并在 `docs/adr/README.md` 登记。
4. **引用规则**：引用本目录文件时显式写 `docs/decisions/ADR-00NN-*.md` 全路径，避免与 `docs/adr/` 同号文件混淆。

## 本目录现存文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `ADR-0028-canary-release-and-rollback.md` | 决议（ADR 风格） | Canary 与回滚策略，引用面广 |
| `ADR-0029-expired-order-payment-handling.md` | 决议（ADR 风格） | 过期订单支付处理 |
| `ADR-0030-money-decimal-migration.md` | 决议（ADR 风格） | 金额 Decimal 迁移 |
| `D-030_feature_backlog_decisions.md` | 决议清单 | Feature backlog 拍板记录 |
| `D-058-order-idempotency.md` | 决议（D-编号） | 订单幂等 |

## 相关

- 权威 ADR 注册表：[`../adr/README.md`](../adr/README.md)
- 编号污染审计：[`../audits/2026-05-26-decision-numbering.md`](../audits/2026-05-26-decision-numbering.md)
- 决议日志：[`../DECISION_LOG.md`](../DECISION_LOG.md)
