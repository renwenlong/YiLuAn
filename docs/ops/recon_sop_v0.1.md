# 资金对账运营 SOP v0.1

> **版本**：v0.1（Draft）
> **生效日期**：2026-04-29
> **维护人**：Ops + Backend
> **关联**：ADR-0032（资金对账机制）、D-048（数据 5 年留存）、D-050 / D-051（wallet_ledger）、TD-MONEY-01

---

## 1. 背景与适用范围

TD-MONEY-01 资金对账机制已经覆盖三条主要链路：

- **T+1 cron**：每日凌晨对前一自然日全量订单与 PSP 交易做匹配比对，产出 `reconciliation_run` + `reconciliation_diff`
- **增量队列**：基于支付 / 退款回调实时入队，分钟级粒度产出增量 diff
- **autofix**：对可自动闭环的轻量 diff（金额一致但状态滞后、ledger 缺写等）尝试自动修复，失败回退到人工

本 SOP 适用于上述三条链路在生产环境运行期间的运营值班、告警响应、双签关闭与月度审计流程。

---

## 2. 角色与职责

| 角色 | 职责 |
| --- | --- |
| 运营值班（Ops on-duty） | 7×24 接收告警；初判 diff；驱动闭环；填写运营初签 |
| Backend on-call | 处理代码 / 数据层异常；T+1 cron / autofix 故障排障；必要时手动重跑 |
| 财务对账人（Finance） | 复核 diff 金额与凭证；执行双签关闭流程的财务复签；月度对账月报出具与归档 |
| 架构组（Arch） | 升级路径触发后的复盘主持；SOP 修订评审 |

---

## 3. 告警响应时限

| 告警类型 | 触发条件 | 响应时限 | 首响应人 |
| --- | --- | --- | --- |
| diff 总额超阈 | 单日累计 diff 金额 > 阈值（默认 ¥1,000，可在 admin 配置） | **30 分钟内**确认 | 运营值班 |
| T+1 cron 失败 | cron 退出码 ≠ 0 / 超时 / run 状态 = `failed` | **15 分钟内**确认并触发 Backend on-call | 运营值班 → Backend on-call |
| autofix 撤销次数超阈 | 单日 autofix 撤销 ≥ 3 次 | **1 小时内**确认 | 运营值班 |
| 增量队列堆积 | 队列长度持续 > 100 超过 10 分钟 | 30 分钟内确认 | 运营值班 |

> 所有告警接收渠道：飞书 Ops 群（主）+ 短信兜底（值班人）。

---

## 4. 双签关闭流程

`reconciliation_diff` 一旦进入 `pending / mismatched / compensated` 状态，必须经双签关闭，不允许单点直接置 `closed`。

1. **运营初签**：运营值班人在 admin H5 → 对账详情页点击「关闭申请」，填写关闭原因（≥ 20 字）与凭证截图链接。系统写入 `reconciliation_action(kind=manual_close, outcome="pending_second_sign")`，diff 进入待复签态。
2. **财务复签**：财务对账人在 admin H5 看到 `pending_second_sign` 列表，核对金额与凭证后点击「确认关闭」。复签人必须与初签人不同（系统强校验 Operator）。
3. **系统标记 closed**：复签通过后 diff 置 `closed`，写入第二条 `reconciliation_action(kind=manual_close, outcome="closed", payload.first_operator=..., payload.first_action_id=...)`。
4. **同一 diff 同一时刻仅允许一个 pending 关闭申请**；如需变更原因，由初签人先撤销再重新发起。
5. **审计日志**：每一步同步写入 `admin_audit_log`（`recon_close_request` / `recon_close_confirm`）。

---

## 5. 月度审计 checklist

每月月末 + T+3 工作日内由财务对账人主导，运营值班人配合：

- [ ] 出具当月《对账月报》（覆盖 diff 数量、金额、关闭率、autofix 占比、人工占比）
- [ ] 抽样 10 单 ledger 核账（覆盖：5 单正常支付、3 单退款、2 单调整流水），核对 `wallet_ledger` 与 PSP 流水一致
- [ ] 复核当月所有 `unreconciled` 残留 diff，对超过 7 天未闭环的逐条标记原因
- [ ] 检查 autofix 撤销次数与失败次数，超阈条目附带 root cause
- [ ] 月报与抽样明细归档至 `docs/ops/recon_audit/YYYY-MM.md`（首次落盘前由财务对账人创建目录）

---

## 6. 升级路径

| 触发条件 | 升级动作 |
| --- | --- |
| autofix 同一规则失败 ≥ 3 次 | 暂停该规则的 autofix；转人工对账队列；运营值班创建 ticket |
| 单日 diff 总额超阈 ≥ 3 次 | 升级 Backend on-call + 财务对账人；当晚同步排查 |
| 人工对账队列单日新增 ≥ 20 单 | 触发架构组复盘；Arch 在 24 小时内召集对账复盘会 |
| T+1 cron 连续 2 日失败 | 升级 Arch；评估是否启动 ADR-0033 资金对账扩展性方案 |

复盘产物统一记入 `docs/REVIEW_YYYY-MM-DD.md` 并在 DECISION_LOG 追加对应条目。

---

_本 SOP 为 v0.1 草案，按需迭代。重大流程变更须 Ops + Backend + Finance 三方评审。_
