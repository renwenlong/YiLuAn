# ADR-0056 — Precheck ABAC Counter 双 scope 规范（v1 owner-gate / v2 4 张牌字段）

> 状态：**Draft** · 作者：魈 · 日期：2026-06-16
> 关联：S3-DOC-009-ADR-0056-PRECHECK-ABAC-COUNTER-SPEC / PR #319 merge `f302fdc` / design `docs/design/S3-trust-precheck-ui.md` §4.3、§6.3、§9、§13.3
> 触发：反案 #47 — PR #319 commit message 误引 ADR-0048；实际 ADR-0048 是 AI 就诊准备包预算控件 + Prompt 版本化，不是 precheck ABAC counter
> Reviewer：PM 凝光 ratify；Owner：帝君最终拍板（如需）

---

## 1. 背景

PR #319（`feat(precheck): ABAC counter for L2.5 owner gate`）已 merge：merge commit `f302fdc5650b6c7a45b4b69e794570b6cb441ce2`。

该 PR 在 `backend/app/observability/precheck_abac_metrics.py` 实施 Prometheus counter：

```text
precheck_abac_filtered_total{endpoint,user_role,filter_reason}
```

触发点在 `backend/app/api/v1/deps_precheck.py::assert_order_owner_or_404` deny 分支：

- `order_not_found`
- `abac_owner_mismatch`

问题：PR #319 的 commit message / 源码注释曾写“实施 ADR-0048 §4.3 + design §6.3 的 ABAC counter”。这是错引。

ADR-0048 标题与范围是 **AI 就诊准备包预算控件 + Prompt 版本化 + 双层关键词过滤**，不包含 precheck owner-gate ABAC counter。正确 ADR 应是本文 ADR-0056。

同时，design `S3-trust-precheck-ui.md` §4.3 原文写：

```text
precheck_abac_filtered_total{card,field}
```

这代表“4 张牌字段级 ABAC 过滤”业务观测；而 PR #319 实施的是“precheck endpoint owner gate L2.5 deny”安全观测。二者同名但 scope 不同，不能互相覆盖。

---

## 2. 目标

1. 给 PR #319 已实施的 counter 补正确 ADR 归属。
2. 明确 `precheck_abac_filtered_total` v1 / v2 双 scope 并存，避免把 v1 owner-gate 实施误解成 v2 业务 dashboard 已完成。
3. 修正 design §4.3 / §6.3 / §9 / §13.3，使其不再暗示 `{card,field}` 已由 PR #319 实施。
4. 为后续 “UI 4 张牌 trust/precheck dashboard 立项时” 的 v2.0 观测留明确触发条件。

---

## 3. 方案对比

### 3.1 候选方案

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A. 单 counter 名，双 scope label set 并存 | 保留 `precheck_abac_filtered_total`；v1 使用 `{endpoint,user_role,filter_reason}`，v2 未来扩展 `{card,field}` 或另加兼容 label | 不改已 merge PR #319 metric name；保留 design 原业务意图；历史 dashboard/alert 迁移成本低 | 同名不同 label set 需文档写清，否则 reviewer 容易误判 |
| B. v1 改名为 `precheck_owner_gate_filtered_total`，v2 独占 `precheck_abac_filtered_total{card,field}` | 名称语义最清晰 | 需要改已 merge 实施、测试、dashboard 预期；PR #319 已落地的证据链要迁移；收益不足 |

### 3.2 决策：选择 A

选择 **A：单 counter 名，双 scope 文档化并存**。

理由：

1. PR #319 已 merge，v1 counter name 已进入代码与测试；为命名洁癖重改不值。
2. v1 owner-gate counter 是安全 deny-path 观测，已满足当前 S3 PRECHECK-BACKEND owner 校验需要。
3. v2 `{card,field}` 是 4 张牌业务 dashboard 需求，尚未立项；不能倒逼当前 PR 扩范围。
4. 双 scope 的风险来自文档不清，而不是实现错误；用 ADR + design amend 收敛即可。

---

## 4. 决定

### 4.1 Counter scope 表

| 版本 | 状态 | metric | labels | trigger | 用途 |
|---|---|---|---|---|---|
| v1.0 owner-gate | 已实施（PR #319 / `f302fdc`） | `precheck_abac_filtered_total` | `{endpoint,user_role,filter_reason}` | `/api/v1/users/orders/{order_id}/precheck-status` REST / WS owner gate deny：`order_not_found` 或 `abac_owner_mismatch` | 监控越权枚举 / 非 owner 访问 precheck summary 的安全 deny-path |
| v2.0 card-field | Deferred | `precheck_abac_filtered_total`（同名扩 label 或另开 child metric，立项时再定） | `{card,field}`（可加 `filter_reason`，不得破坏 v1 dashboard） | **UI 4 张牌 trust/precheck dashboard 立项时**：aggregator / serializer 对 4 张牌字段做字段级过滤时 inc | 监控 4 张牌字段级敏感信息过滤与业务卡片字段漂移 |

### 4.2 v1.0 实施约束

v1.0 以 PR #319 当前实现为准：

- module：`backend/app/observability/precheck_abac_metrics.py`
- 常量：`PRECHECK_ABAC_FILTERED_TOTAL`
- Prometheus name：`precheck_abac_filtered_total`
- labels：`endpoint` / `user_role` / `filter_reason`
- trigger：`backend/app/api/v1/deps_precheck.py::assert_order_owner_or_404` deny branch `.labels(...).inc()`
- expose：`/metrics` Prometheus scrape

v1.0 不承担 `{card,field}` 业务 dashboard。

### 4.3 v2.0 触发条件

v2.0 只有在以下条件满足时启动，不做隐性扩展：

> **UI 4 张牌 trust/precheck dashboard 立项时**，由新 develop task 明确实现 `{card,field}` 字段级 ABAC counter，并同步 test task 锁定 dashboard / alert / metric label 契约。

v2.0 立项时必须重新评估：

1. 是否继续复用 `precheck_abac_filtered_total` 名称。
2. 是否允许 Prometheus 同名 metric 多 label set（不推荐），或拆 `precheck_card_field_filtered_total`。
3. v1 dashboard / alert 是否需要 migration。
4. `{card,field}` 是否包含 `filter_reason`，避免只知道字段被滤、不知道为什么被滤。

---

## 5. 设计文档修正

`docs/design/S3-trust-precheck-ui.md` 修正口径：

- §4.3：保留原业务意图，但标注 `{card,field}` 为 v2.0 deferred；补 v1.0 owner-gate 已实施。
- §6.3：ABAC counter 行改为 v1/v2 双 scope 表述。
- §9 AC#8：改为“v1 owner-gate counter 可观测；v2 card-field counter deferred”。
- §13.3：刻晴 D ABAC counter 处补 ADR-0056 cross-ref。

---

## 6. 后果

### 正向

- PR #319 的实施归属从错误 ADR-0048 迁到 ADR-0056。
- PM / architect / tester 对 v1 / v2 scope 有共同口径。
- 保留 design 原 `{card,field}` 业务观测，不因为 v1 已落地而被误删。

### 代价

- 同一 metric name 在文档上存在 v1/v2 双语义；后续 reviewer 必须先看 labels / trigger，不能只看 metric name。
- v2 立项时仍需重新决策是否拆新 metric 名，本文不提前锁死。

### Review 硬规

后续 review 中遇到 `precheck_abac_filtered_total` 必先判断：

1. labels 是 `{endpoint,user_role,filter_reason}` → ADR-0056 v1 owner-gate。
2. labels 是 `{card,field}` → ADR-0056 v2 card-field（当前 deferred，除非有新 task / PR 立项）。
3. PR description / commit message 不得再引用 ADR-0048 描述 ABAC counter。
