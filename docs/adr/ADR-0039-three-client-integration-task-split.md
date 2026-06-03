# ADR-0039 — 三端联调任务拆分（追认补落）

> 状态：**Draft（追认补落 D+1）** · 作者：魈 · 日期：2026-06-03
> 关联：S2-INT-001（主 task）/ S2-INT-002~005 / S2-TEST-005~008
> 历史背景：2026-05-28 ~ 2026-06-01 阶段，魈口述拆分方案，PM 在 S2-INT-001 task description 中引用 "ADR-0039 §X" 多处，但 ADR 文件本身从未落盘。2026-06-03 BUG-W001 + INT-001 验收口径 v2 起草期间被刻晴/胡桃发现，凝光自查认账，由本 ADR 追认补落。

---

## 1. 背景

S2-INT-001 主 task（D4-D10 三端联调 → staging）由 PM 在 2026-06-01 创建后，魈于会议 / 群聊中口述了拆分方案：

- D-1 契约基线先行
- 三端并行：iOS / 微信 / admin
- 三端冒烟随后
- 出口报告汇总

PM 在 task description / acceptance / 后续 task notes 中引用 "ADR-0039 §1.2 / §2.X / §3.X / §4.X / §5"。但 **ADR-0039 文件本身从未落盘**（grep 全仓 0 命中）。

由此衍生：
- 部分引用指向"应有但不存在"的文档段（如 §1.2 状态机），造成 BUG-W001 中"order.status → paid"误解（已由 ADR-0041 处理）
- `scripts/qa/wechat_openapi_check.sh` 注释引用 "ADR-0039 权威表" 实际是魈口述
- iOS `ShareEndpointContractTests.swift` §4.4 引用同上

**修复路径**：补落 ADR-0039 文件，把已实施的拆分追认为正式架构决策。

---

## 2. 决策（追认）

### 2.1 拆分骨架

| Task | 类型 | 内容 | 状态（2026-06-03） |
|------|------|------|-------------------|
| S2-INT-002 | develop | 跨端契约基线（9 字段 OpenAPI + 三端互锁 + CI diff gate） | done |
| S2-INT-003 | develop | 微信端联调（U-1 折叠下单 + F2 静默分享 + WS + 巨字号） | done |
| S2-INT-004 | develop | iOS 端联调（U-1 + F2 OTP + WS + 巨字号 + APIEndpointTests） | in-progress（第 3 刀 PR #134） |
| S2-INT-005 | develop | admin-h5 端联调（订单/用户/审计 + 越权） | done（PR #129 merge `ed8c1f8`） |
| S2-TEST-005 | test | 微信端冒烟 | in-progress |
| S2-TEST-006 | test | iOS 端冒烟 | not-started（等 INT-004） |
| S2-TEST-007 | test | admin-h5 冒烟 + §4 契约 | in-progress（魈 INT-005 done 后解锁） |
| S2-TEST-008 | test | 出口报告 | not-started（等 005/006/007） |

### 2.2 设计原则（追认）

1. **契约基线先行**：S2-INT-002 必须 done 才能启动 003/004/005，避免三端各自发明字段
2. **三端互锁**：9 字段 GUARDED_FIELDS（含 `patient_name_masked`，权威源 `scripts/qa/openapi_contract_diff.py::GUARDED_FIELDS`），任一端漂移直接打回 develop
3. **AC#25 逐字符互锁**：iOS / 微信端 U-1 摘要模板（OrderSummary）逐字符一致，任一漂移打回（参考 `wechat/utils/orderSummary.js` 与 `ios/YiLuAn/Core/Utilities/OrderSummary.swift`）
4. **冒烟后出口**：S2-TEST-008 汇总三端冒烟通过 + 缺陷闭环 + staging 可供 S2-TEST-004 灰度回归 → 解锁灰度
5. **支付域解耦**：U-1 下单 + 支付链路不驱动 OrderStatus（详见 ADR-0041）

### 2.3 已发现并修复的"幽灵引用"

| 位置 | 原引用 | 修复 |
|------|--------|------|
| `scripts/qa/wechat_openapi_check.sh:7` | "ADR-0039 权威表（魈拍板）" | ✅ 本 ADR Accept 后引用真实，无需改动 |
| `scripts/qa/openapi_contract_diff.py:7` | 同上 | 同上 |
| `ios/.../ShareEndpointContractTests.swift §4.4` | "ADR-0039 §4.4" | ✅ 本 ADR §2.2 第 2 项即对应内容 |
| PRD-001 / S2-INT-001 / S2-TEST-005~008 description 引用 "ADR-0039 §1.2 状态机" | "order.status → paid" | ❌ 实际是 ADR-0041 范畴，由凝光自查清零，本 ADR 不承载 |

---

## 3. 验收

- [x] 本 ADR 文件落盘
- [ ] `scripts/qa/wechat_openapi_check.sh` + `openapi_contract_diff.py` 注释从 "魈拍板" 升级为 "ADR-0039"
- [ ] `ShareEndpointContractTests.swift` §4.4 引用本 ADR
- [ ] PM 自查 task description / PRD 中所有 "ADR-0039 §X" 引用，对照本 ADR 章节核对（前面 ADR-0041 已处理状态机相关误引用）

---

## 4. 教训

1. 架构师口述方案必须 24h 内落 ADR 文件，否则 PM 引用"待 ADR"反而成幽灵
2. PM 引用 ADR 编号前必须 `grep -r "ADR-XXXX" docs/adr/`，找不到当场标"待 ADR"或转架构师立项（已写入 PM MEMORY 硬规则）
3. ADR 编号申请与文件创建是同一动作，不可分离

---

## 5. 决定

**Accept**。追认补落，无代码改动需求（仅文档引用对齐）。reviewer 程序员（胡桃）+ 测试员（刻晴）按 design type workflow review，凝光知会。
