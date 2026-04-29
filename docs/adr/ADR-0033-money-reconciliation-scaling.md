# ADR-0033 — 资金对账扩展性预研草案

- **状态**：Draft
- **决策日期**：—（待评审，预计触发条件达成时落地）
- **关联**：ADR-0032（资金对账机制）、TD-MONEY-01、D-048（5 年留存）、D-050 / D-051（wallet_ledger）、`docs/ops/recon_sop_v0.1.md`
- **作者**：Arch + Backend
- **PR**：feat/w18-docs-bundle

> 本 ADR 仅做扩展性预研草案（≤ 1 页），不形成最终结论；当触发条件达成时再正式 Accepted。

---

## Context

当前 T+1 cron（`scripts/reconcile_t1.py` 等）以 **单进程顺序遍历 + 单 DB 连接** 方式跑全量对账。在压测环境下，单次执行时长大约随订单量线性增长：

- 日单量 ~5k：单次 cron 约 8 分钟，可在凌晨窗口内完成
- 日单量 ~1w：预估单次 cron > 25 分钟，开始挤压增量队列与 autofix 的处理窗口
- 日单量 > 2w：单进程模型不再可行，需要切分

参考 D-048 资金类数据须保留 5 年，对账扩展不能依赖"丢老数据"路径。

## 1. 触发条件

满足以下任一条件即启动 ADR-0033 落地：

- **日单量阈值**：连续 3 个自然日订单量 ≥ 8,000；或单日峰值 ≥ 12,000
- **cron 单次执行时长阈值**：T+1 cron 单次执行时长 ≥ 20 分钟（连续 2 日）或单次 ≥ 30 分钟
- **资源信号**：cron 运行期间 DB 连接 / CPU / 内存任一指标持续 ≥ 80%

## 2. 候选方案

### 方案 A：按 provider 拆 worker
- 拆分粒度：每个 PaymentProvider（wechat / alipay / mock）独占一个 worker 进程
- 优点：实现成本低；天然隔离 PSP 故障域；与 D-052 Provider 冻结期兼容
- 风险：当某一 provider 占主体（如微信支付 ≥ 90%）时收益有限

### 方案 B：按时间窗口分片
- 拆分粒度：将 T+1 时间窗口按小时（24 片）或按订单 ID 哈希分片，多 worker 并行
- 优点：横向扩展线性；与 provider 数量解耦
- 风险：跨片 ledger 一致性；diff 聚合需要额外汇总步骤

### 方案 C：引入 Celery 队列
- 拆分粒度：将每条订单的对账任务作为独立 Celery task；T+1 cron 只负责派发
- 优点：弹性最好；与增量队列同栈；天然支持重试 / 优先级
- 风险：基础设施依赖（Redis / RabbitMQ broker）；运维负担上升；需要重写 autofix 触发链路

## 3. 待决问题（Open Questions）

1. **数据一致性**：分片 / 队列方案下，单日 reconciliation_run 的"完成"如何原子聚合？
2. **autofix 触发位置**：autofix 是跟随各 worker 即时执行，还是在 run 聚合完成后统一执行？
3. **ledger 写入冲突**：并行 worker 同时 append wallet_ledger 时，`(provider_txn_id, direction)` 唯一索引下的冲突恢复策略？
4. **基础设施成本**：方案 C 引入的 broker（Redis Cluster / RabbitMQ）是否复用现有部署？SLA / 监控如何对齐 ADR-0026？
5. **回滚路径**：若新方案上线后需回滚到单进程，wallet_ledger / reconciliation_run 状态机是否兼容？

## 4. 后续动作

- 触发条件达成后，由 Arch 召集 Backend + Ops 评审本草案
- 选定方案后另起 ADR-0034 正式 Accepted；本草案保留为历史背景

---

_本草案不做结论，仅锁定问题域。任何实施前请将状态从 Draft 推进到 Proposed → Accepted。_
