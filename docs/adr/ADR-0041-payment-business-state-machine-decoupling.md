# ADR-0041 — 支付域与业务域状态机解耦显式化

> 状态：**Draft（D+1）** · 作者：魈 · 日期：2026-06-03
> 关联：S2-BUG-W001 拍板口径 / S2-INT-001 验收口径 v2 §1.1 / `backend/app/models/order.py`
> Supersedes: 隐式契约（model 注释 "ORDER_TRANSITIONS is intentionally NOT extended"）→ 显式 ADR

---

## 1. 背景

2026-06-03 S2-BUG-W001 排查中，刻晴引用"ADR-0039 §1.2 状态机要求 order.status created → paid"作为验收依据，胡桃发现：

1. **ADR-0039 文件不存在**（grep 全仓 0 命中，凝光自查后认账）
2. **OrderStatus 当前**没有 `paid` 态，状态机为 `created → accepted`（陪诊师 accept 推进）
3. `PaymentState` 子状态注释明确写 "`ORDER_TRANSITIONS` is intentionally NOT extended"——支付域与业务域状态机有意解耦
4. callback handler 只动 `payment.status` + `PaymentState`，不动 `OrderStatus`

帝君 + 魈 + 刻晴 + 胡桃四方对齐拍板 **(A)**：OrderStatus 不动是 deliberate，BUG-W001 范围仅修"mock 绕过 callback"。

**问题**：这是一条**隐式契约**，仅在 model 注释 + 资深团队成员脑里。新人 / PM / 测试一旦不读 model 注释，就会再次产生"order.status 应该→paid"的合理误解。已经造成一次 BUG-W001 范围扩张争议。

**本 ADR 把隐式契约显式化**，闭环 S2-INT-001 验收口径 v2 §1.1 的"待 ADR-0041 显式化"挂账。

---

## 2. 决策

### 2.1 三套状态机相互隔离

YiLuAn 后端订单生命周期由 **三套独立状态机** 描述，**禁止跨域驱动**：

| 状态机 | 模型字段 | 推进者 | 状态集合 |
|--------|---------|--------|---------|
| **业务域 OrderStatus** | `Order.status` | 业务事件（用户取消 / 陪诊师 accept/reject/start/complete / 系统过期） | `created / accepted / in_progress / completed / reviewed / cancelled_by_patient / cancelled_by_companion / rejected_by_companion / expired` |
| **支付域 PaymentState** | `Order.payment_state` | 支付事件（PSP callback / refund / 对账） | `none / paying / paid / refunded / refund_pending / failed / abnormal` |
| **退款域 RefundState** | `Order.refund_state` | 退款事件（admin refund / 自动退款 / PSP refund callback） | `none / requested / processing / succeeded / failed` |

### 2.2 解耦原则（硬规则）

1. **支付成功（PaymentState=paid）不驱动 OrderStatus 切换**
   - 用户支付完成后，`OrderStatus` 仍是 `created`，必须由陪诊师 accept 才能 → `accepted`
   - 反之 OrderStatus accept 也不假设 PaymentState（accept 前必须显式校验 `payment_state in {paid}`）
2. **退款（RefundState）不驱动 OrderStatus 切换**
   - 退款流程独立，UI 通过 timeline 拼接显示
   - 业务 cancel 是 OrderStatus 域内事件（cancelled_by_*），可触发 RefundState 转换（依赖关系单向：业务→退款）
3. **OrderStatus 状态集禁止扩展"支付意味"字段**
   - ❌ 禁止新增 `OrderStatus.paid` / `OrderStatus.pending_accept` / `OrderStatus.paying`
   - ❌ 禁止在 `ORDER_TRANSITIONS` 中以"支付成功"为转换条件
   - 任何让 OrderStatus 反映支付状态的 PR 直接打回
4. **timeline UI 拼接是唯一允许的"统一时间线"** 出口
   - 各域独立写时间线节点（"订单创建 / 已支付 / 已接单 / 服务中 / 已完成 / 已退款"）
   - timeline 是渲染层，**不是状态机**

### 2.3 例外口径

- **退款驱动业务状态**：退款 succeeded 不回写 OrderStatus（保持 cancelled_by_X）。已退款的事实由 RefundState=succeeded 承载。
- **状态机崩溃修复**：极端情况下若 PaymentState 与业务侧严重不一致（如对账发现 paid 但 OrderStatus 不可能成立），走 `admin force-status` + 审计留痕路径，不修改本 ADR 的解耦原则。

---

## 3. 验收

- [x] BUG-W001 实施按本口径完成（已 done，PR #131 merge `f29f023`）
- [x] S2-INT-001 验收口径 v2 §1.1 钉死本口径（已合 PR #133）
- [ ] `backend/app/models/order.py` 顶部注释扩写：从"ORDER_TRANSITIONS is intentionally NOT extended" 升级为 "see ADR-0041"，反向引用本 ADR
- [ ] PRD-001 / S2-INT-001 / S2-TEST-005~008 描述中"order.status → paid"等表述全部清零（凝光自查 + 改）
- [ ] 后续 develop PR Review checklist 增加 "状态机解耦检查" 一项

---

## 4. 反向引用 / 历史关联

- ADR-0032 资金对账：`reconciliation_cutoff` 处理历史不一致，与本 ADR 解耦原则一致
- ADR-0033 资金对账扩展：同上
- ADR-0036 family-share：share 流程不涉及 OrderStatus 推进，仅读视图
- ADR-0037 payment callback empty tx_id：callback 域内事件，与 OrderStatus 隔离
- ADR-0039 三端联调任务拆分（待追认补落）：本 ADR 与之独立

---

## 5. 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| 三套状态机让 UI 渲染复杂度上升 | 高 | timeline 拼接已是现成方案；admin-h5 已落 `OrderStatus + PaymentState` 两栏分离展示 |
| 新员工/PM 仍按"统一状态机"思维拆需求 | 中 | 本 ADR 落地 + PR Review checklist + PRD 模板加 "状态机三域" 章节 |
| 对账系统跨域协调成本 | 中 | ADR-0032/0033 已覆盖；新对账 task 必读本 ADR |
| 业务方要求"已支付即可视为接单"等捷径 | 低 | 业务原则不让步：陪诊师 accept 是劳务契约确认动作，不可绕过 |

---

## 6. 决定

**Accept**。本 ADR 是对已实施隐式契约的事后追认显式化，无新代码改动需求（除 §3 验收第 3 项注释扩写 + 第 4 项文档清零 + 第 5 项 Review checklist）。

Reviewer：程序员（胡桃）+ 测试员（刻晴）按 design type workflow review，凝光同步知会。Owner（帝君）批准后状态 Draft → Accepted。
