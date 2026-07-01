# ADR-0060: PaymentService Mixin 拆分设计

- **状态**: 设计冻结（Accepted）；**实施 gate 于 2026-07-01 00:51:28Z 由帝君本人明示 override → DEV 启动中（一次性开窗，重构完再 gate）**
- **日期**: 2026-06-30（初版）/ 2026-07-01（r1 amend: gate override）
- **决策者**: 魈（架构师）
- **关联**: BACKLOG-PAY-REFACTOR（P2 requirement, 凝光发起）/ OrderService SP-01 mixin 先例 / 反案#52(review前核git tracked) / 反案#47(引用前核实况)
- **上游 review**: 凝光 PM 业务 review（board comment ba7fe39b, AC 4→7）+ 刻晴测试视角 review（扫码实证 15 处 patch target + L388 跨 mixin self 调）

> ⚠️ **实施 gate（初版硬约束，已被 override，保留作决策历史）**: 本 ADR 仅锁**设计契约**。实施（DEV/TEST task）的启动前置 = **Top1 上线 + AI 扣费稳定 30 天（资金线无回归确认）**，当前远未满足（F2 REAL-LAUNCH 2026-06-30 刚 gate-ON, 24h 观察窗未满）。design 冻结 ≠ 启动重构。`S3-DES/DEV/TEST-PAY-MIXIN-SPLIT` 三 task 立项后保持 `not-started`，等触发条件 + 帝君拍板再启。**趁 review 热度锁防御条款（evidence 新鲜、行号未漂移），不是现在改支付代码。**

> 🔓 **r1 amend — gate override（2026-07-01 00:51:28Z）**: 帝君本人在璃月群 @全体明示 **「解 gate 启动 DEV，重构完再 gate」**（甘雨 session seq=565, role=user, sender=wenlongren, 非转述；魈 evidence-first 亲核 role=user 确认，反案#48：改 gate 硬规必帝君本人背书）。**语义**：(1)「解 gate 启动 DEV」= 立即启动 `S3-DEV-PAY-MIXIN-SPLIT`，帝君作为最终决策者 override 上方「启动前置（AC#1）= Top1+扣费稳30d」；(2)「重构完再 gate」= **一次性开窗**做重构，DEV/TEST 完成后重新上 gate（非永久解除）。**边界不变**：override 的只是「何时启动」，§4 契约 + §5 三雷区防御（patch target 逐字节 / L388 跨 mixin MRO / money_safety 单 PR 一把验）+ 纯结构搬移铁律（git diff 须识别 rename，任何夹带逻辑改动 = 🔴 阻塞）**一条不松**。当前状态：DEV in-progress（胡桃），TEST 等 DEV done。

---

## 1. 背景

`backend/app/services/payment_service.py` 单文件 **760 行 / 13 方法**（evidence-first 实测 2026-06-30），随支付域演进将复刻 OrderService 早期"单文件膨胀"困境。OrderService 已用 SP-01 mixin 模式拆分（`backend/app/services/order/` 6 文件），验证有效。本 ADR 设计 PaymentService 对齐方案。

**触发来源**: 魈 S1-DEV-001 review §1.1 提出，原定"Top1 上线 + AI 扣费稳定 1 月后再动支付重构"。本次趁 BACKLOG-PAY-REFACTOR review 热度锁设计，**不提前实施**。

---

## 2. 现状盘点（evidence-first 实测，非转述）

### 2.1 方法清单（13 方法，含归域）

| 行号 | 方法 | 归属 mixin |
|---|---|---|
| L102 | `__init__` (repo/session/provider/ledger_writer) | `_base` |
| L111 | `create_prepay` | `lifecycle` |
| L433 | `close_pending_payment` | `lifecycle` |
| L212 | `record_callback_or_skip` | `callback` |
| L284 | `is_callback_processed` | `callback` |
| L299 | `handle_pay_callback` | `callback` |
| L554 | `handle_refund_callback` | `callback` |
| L470 | `create_refund` | `refund` |
| L625 | `_set_payment_state` | `_base`（跨 pay/refund 共用） |
| L654 | `_set_refund_state` | `_base`（跨 pay/refund 共用） |
| L679 | `_resolve_companion_user_id` | `ledger` |
| L697 | `_append_pay_ledger_safe` | `ledger` |
| L727 | `_append_refund_ledger_safe` | `ledger` |

### 2.2 跨 mixin self 调依赖图（🔴 雷区2 实测，决定 MRO 约束）

```
handle_pay_callback (callback)
  ├─ L356 self._set_payment_state    → _base
  ├─ L368 self._append_pay_ledger_safe → ledger
  └─ L388 self.create_refund          → refund   ★跨 mixin self 调铁证（callback→refund）★

create_refund (refund)
  ├─ L538 self._set_refund_state       → _base
  └─ L545 self._append_refund_ledger_safe → ledger

handle_refund_callback (callback)
  ├─ L609 self._set_refund_state       → _base
  └─ L617 self._append_refund_ledger_safe → ledger

_append_*_ledger_safe (ledger)
  └─ L703/L733 self._resolve_companion_user_id → ledger(自域)
```

**MRO 必保跨 mixin 路径**: callback→refund / callback→ledger / callback→_base / refund→ledger / refund→_base。

### 2.3 调用方影响面（6 处，决定 shim 约束）

| 调用方 | import |
|---|---|
| `order/payment.py` | `from app.services.payment_service import PrepayResult` |
| `order/_base.py` | `from app.services.payment_service import PaymentService` |
| `order/__init__.py` | `PaymentService  # noqa: F401 (test patch target)` ★ |
| `user.py` | `from app.services.payment_service import PaymentService` |
| `api/v1/payment_callback.py` | `from ... import (多名)` ★ |
| `api/v1/admin/orders.py` | `from app.services.payment_service import PaymentService` |

### 2.4 测试守门面（🔴 雷区1+3 实测）

- **patch target = 15 处**（凝光报 14，**实测 15**：`test_wechat_verify_callback.py` L107-114 共 8 处 + L278-284 共 7 处），全是 `monkeypatch.setattr("app.services.payment_service.settings.XXX")` 模块级 patch。
- **money_safety 守门**: `test_money_safety_contract.py`（10 test）+ `test_payment_callback_blocker.py`（10）+ `test_wechat_verify_callback.py`（9）+ `test_refund_callback.py`（5）+ `test_d058_idempotency.py`（4）。

---

## 3. 方案对比

### 方案 A: shim 兼容（采纳 ✅）

`payment_service.py` 保留为 re-export shim（`from app.services.payment import *` + `__all__` 全保留 + 模块级 `settings` re-export），新建 `payment/` 包承载 mixin。call-site 零改动，15 处 patch target 路径逐字节可达。

- **优**: 6 调用方零改 / 15 patch 不破 / 18 测试 import 不动 / 行为零变（纯结构搬移）
- **劣**: 留一个 shim 文件（但有先例：原文件头注释已是此模式"To avoid touching call-sites... re-exported"）

### 方案 B: 全切新路径（否决）

删 `payment_service.py`，同步改 6 调用方 + 15 patch 路径 + 18 测试 import 到 `app.services.payment`。

- **优**: 无 shim 残留
- **劣**: 🔴 改动面大（6 调用方 + 15 patch + 18 测试）/ patch 路径搬错→**测试假绿（最危险假阳性）** / diff 混入大量非结构改动，review 困难

**决定: 方案 A**。理由：支付是资金线，"纯结构重组 + 行为零变"是最高优先级，shim 兼容把 blast radius 压到最小。全切的收益（消除一个 shim 文件）远不抵其风险（15 patch 路径搬错导致假绿）。

---

## 4. 设计契约（mixin 划分）

```
backend/app/services/payment/
├── _base.py        class _PaymentServiceBase:
│                     __init__(repo/session/provider/ledger_writer)
│                     _set_payment_state / _set_refund_state  (订单状态镜像, 跨 pay/refund 共用)
├── lifecycle.py    class _PaymentLifecycleMixin(_PaymentServiceBase):
│                     create_prepay / close_pending_payment
├── callback.py     class _PaymentCallbackMixin(_PaymentServiceBase):
│                     record_callback_or_skip / is_callback_processed
│                     handle_pay_callback (含 reconcile enqueue 尾步) / handle_refund_callback
├── refund.py       class _PaymentRefundMixin(_PaymentServiceBase):
│                     create_refund
├── ledger.py       class _PaymentLedgerMixin(_PaymentServiceBase):
│                     _resolve_companion_user_id / _append_pay_ledger_safe / _append_refund_ledger_safe
└── __init__.py     class PaymentService(
                        _PaymentCallbackMixin,
                        _PaymentLifecycleMixin,
                        _PaymentRefundMixin,
                        _PaymentLedgerMixin,
                        _PaymentServiceBase,
                      ): pass
                     + PrepayResult / RefundResult (DTO)
                     + legacy re-exports: PaymentProvider/MockPaymentProvider/
                       WechatPaymentProvider/settings/_platform_cert_cache (__all__ 全保留)
```

**各 mixin 继承 `_PaymentServiceBase`**（对齐 OrderService：每个 `_OrderXxxMixin(_OrderServiceBase)`），保 `self.session/repo/provider/ledger_writer` + 共享 state-mirror 方法全 mixin 可达。

### 4.1 vs 胡桃原 4 块方案的差异

胡桃原案 4 块（lifecycle/refund/callback/_base）。本 ADR **多切 `ledger.py`**：账本 3 方法（`_resolve_companion_user_id` + `_append_pay/refund_ledger_safe`）自成一域。**厘清易混点**：
- `reconcile enqueue`（L399 区 `enqueue_incremental_event`）= **callback 的回调落盘尾步**（同事务 fire-and-forget）→ 归 `callback`，**不**独立 mixin（决策点②）
- `ledger append`（钱包账本写入）= **资金账本主体**（companion 收入归属）→ 归 `ledger`
- 二者是两回事，勿混。`_set_payment_state`/`_set_refund_state`（order 状态镜像）跨 pay+refund 共用 → 进 `_base` 避免重复。

---

## 5. 🔴 防御条款（凝光 AC#6 锁定，刻晴 3 雷区，实施时强制）

### 5.1 雷区1（最高危）— patch target 失效防御

**风险**: 15 处 `monkeypatch.setattr("app.services.payment_service.settings.XXX")` 若拆分后 `settings` 搬到子模块，patch 打空路径 → 测试**假绿**（最危险假阳性，资金测试假阳 = 灾难）。

**防御（强制）**:
1. `payment/__init__.py` **必须** re-export 模块级 `settings`（`from app.config import settings`），保 `app.services.payment_service.settings` 逐字节可达。
2. `payment_service.py` shim **必须** `from app.services.payment import settings`（透传），保旧路径 patch 命中真对象。
3. **验收哨兵**: 拆分后 `test_wechat_verify_callback.py` 15 处 patch **全部命中真 settings 对象**（patch 后 provider 行为真变），不是 patch 空路径静默通过。先例: OrderService `order/__init__.py` L21 `# (test patch target)` re-export 模式。

### 5.2 雷区2 — 跨 mixin self 调 + MRO 防御

**风险**: L388 `handle_pay_callback`(callback) 内 `self.create_refund`(refund) 跨 mixin self 调；分到不同 mixin 后 MRO 断 → `AttributeError`。

**防御（强制）**:
1. 所有 mixin 继承同一 `_PaymentServiceBase`，`PaymentService` 多继承全部 mixin → MRO 链含所有 mixin，跨 mixin `self.X` 可达。
2. 共享私有方法（`_set_payment_state`/`_set_refund_state`）进 `_base`，所有 mixin 直接继承可调。
3. **验收哨兵**: §2.2 依赖图所有跨 mixin 路径（callback→refund/ledger/_base, refund→ledger/_base）拆后单测验通，特别是 L388 late-callback auto-refund 路径（callback 内调 refund）端到端绿。

### 5.3 雷区3 — 覆盖率守门

**防御（强制）**: 核心测试拆后全绿 + 断言数不减 + coverage 不降。重点 `test_money_safety_contract.py`(10) + callback/refund/wechat/d058 全量。**单 PR 一次拆**（决策点③）保 money_safety 测试一把验全量，不出"半拆中间态 CI 红"。

---

## 6. 决策点结论（4 项）

| # | 决策 | 结论 | 依据 |
|---|---|---|---|
| ① | shim vs 全切 | **shim（方案 A）** | 6 调用方 + 15 patch + 18 测试零改；全切风险 patch 假绿 |
| ② | reconcile hook | **放 callback 内** | reconcile enqueue 是回调落盘尾步（同事务 fire-and-forget），非独立职责 |
| ③ | 单 PR vs 分批 | **单 PR 一次拆** | mixin 间方法依赖（L388 跨调）；分批出半拆中间态 CI money_safety 红 |
| ④ | `__future__` annotations | **补，仅新文件** | 4 新文件统一加（对齐 order/ mixin）；不借机改已有文件其他风格（守纯结构重组边界） |

---

## 7. 实施任务拆分（gate override 后，DEV 启动中）

> 状态列反映 **2026-07-01 00:51:28Z 帝君 override 后**实际；初版为「not-started（gated）」，见上方 r1 amend。

| task | 角色 | 内容 | 状态 |
|---|---|---|---|
| `S3-DES-PAY-MIXIN-SPLIT` | 魈 | 本 ADR（设计冻结） | **done（本 ADR = 交付，PR #371 入 main）** |
| `S3-DEV-PAY-MIXIN-SPLIT` | 胡桃 | 按 §4 契约 + §5 防御实施（纯结构搬移 + shim） | **in-progress（gate 已 override，2026-07-01 起工）** |
| `S3-TEST-PAY-MIXIN-SPLIT` | 刻晴 | §5 三哨兵回归（15 patch 命中 + 跨 mixin self 调 + money_safety 全绿） | not-started（depends_on DEV，等 DEV done 启动） |

**启动前置（AC#1，初版）**: Top1 上线 + AI 扣费稳定 30 天。**→ 2026-07-01 00:51:28Z 帝君本人明示 override，改为立即启动（一次性开窗，重构完再 gate）**。

---

## 8. 后果

**正面**: 支付域可维护性对齐 OrderService；未来扩展（新 provider/新回调类型）落对应 mixin，不再单文件膨胀。

**负面/风险**: shim 文件长期保留（可接受，有先例）；拆分是资金线动土，必须严守"纯结构搬移 + 行为零变 + 三哨兵全绿"，任何夹带逻辑改动 = 🔴 阻塞。

**回滚**: 单 PR 拆分，回滚 = revert 单 commit，shim 模式下 call-site 无残留依赖，回滚干净。
