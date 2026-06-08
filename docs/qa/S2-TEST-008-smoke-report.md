# S2 三端联调出口冒烟报告

> **任务**: S2-TEST-008 三端联调出口冒烟报告
> **日期**: 2026-06-03
> **测试员**: 刻晴
> **关联**: ADR-0039 §2.2 第 4 条 / INT-001 验收口径 v2 §5
> **环境**: staging http://127.0.0.1:18080 (compose `yiluan-staging-*`)

---

## §5 出口 6 条 — 全部 PASS ✅

| ID | 验收点 | 状态 | 证据 |
|----|--------|------|------|
| §5.1 | 三端冒烟全通 | ✅ | S2-TEST-005 (W-1~7) / S2-TEST-006 (I-1~7) / S2-TEST-007 (A-1~4 + C-1~3) 全 done |
| §5.2 | Share Token 两路换 session | ✅ | 微信 wx.login 路径 W-3 PASS；iOS OTP 路径 I-3 sendOTP + exchangeSession 契约 PASS |
| §5.3 | admin 四项达 | ✅ | A-1 鉴权 / A-2 订单 / A-3 用户+脱敏 / A-4 审计 全 15/15 PASS |
| §5.4 | 契约 §4 绿 | ✅ | C-1 OpenAPI baseline 18 fields stable；C-2 wechat typecheck 0 err；C-3 iOS APIEndpointTests run 26889954626 main HEAD `bcfb425` SUCCESS |
| §5.5 | 缺陷清单 + 闭环 | ✅ | 见 §1 缺陷清单 |
| §5.6 | 冒烟报告产出 + 灰度可供 | ✅ | 本报告即 §5.6 产出；§3 灰度结论：**staging 可供 S2-TEST-004 灰度回归实跑** |

---

## §1 缺陷清单 + 闭环

| ID | 类型 | 描述 | 状态 | 修复 PR | 备注 |
|----|------|------|------|---------|------|
| **S2-BUG-W001** | bug/P1 | mock 模式绕过 wxpay 回调路径（创建 prepay 时 inline 标 paid，未走 /payments/wechat/callback） | ✅ done | #131 (`f29f023`) | acceptance 收窄到验"mock 真路由 callback + payment_callback_log 入表"；OrderStatus 解耦由 ADR-0041 显式化（魈拍 (A)） |
| ADR-0039 幽灵引用 | 流程坑 | PM 引用未落 ADR-0039 §X 作 acceptance 依据 | ✅ done | #135 (ADR-0039/0040/0041 一次性补落) | 凝光自查 + ADR-0039 §2.3 清单 + PM SOP 加 `grep -r ADR-XXXX docs/adr/` 硬规则 |
| ADR-0040 OTP 频控引用 | 流程坑 | I-4/I-5 acceptance 一度引用"1min 4次 / 5次锁 10min"等历史漂移 | ✅ done | #133 (INT-001 v2) | 锚定 config.py 真源：share_otp_token_daily_cap=5 / phone_token_cap=3 / ttl=300 |
| §4 字段数误判 | 文档误 | INT-001 v1 写 8 字段（漏 patient_name_masked） | ✅ done | #133 v2 | 锚定 scripts/qa/openapi_contract_diff.py::GUARDED_FIELDS（9 字段权威源）|
| Staging 部署源 worktree 坑 | OPS | W-1 复测时主 worktree 在 docs 分支挡部署，胡桃先斩后奏 pull main + rebuild | ✅ 临时已解 | OPS-RETRO 已立项 | 长期方案：`~/repo/YiLuAn-staging` 永久 worktree 专跑 staging（OPS task 待立） |

**未结**（拆 follow-up，灰度前必合）：
- **S2-INT-006** iOS ShareOrderView + UniversalLink + WS share topic（develop/P1，胡桃，魈拍 D+2 完成）
- **S2-TEST-006 增量复测** INT-006 done 后跑 iOS viewer UI + WS（D+3）
- ADR-0040 distributed CB sub-task（实施后我跑 OTP I-4/I-5 回归确认 aliyun_sms outbound 不被误熔）

---

## §2 三端冒烟逐项总结

### §2.1 微信端 (S2-TEST-005 / W-1~W-7)

| ID | 用例 | 结果 |
|----|------|------|
| W-1 | 资金线（mock→真 callback→PaymentState=paid，OrderStatus 不流转符 ADR-0041） | ✅ |
| W-2 | 业务状态机：created→accepted→in_progress→completed（双确认 request-start + confirm-start），timeline 4 节点齐 | ✅ |
| W-3 | 静默分享落地（share_token 201 + wx.login 换 30min JWT 200） | ✅ |
| W-4 | 脱敏 `patient_name_masked="1**"`，无 patient_name/phone | ✅ |
| W-5 | WS 只读：share_auth_ok，写帧 close 4012 upstream_write_forbidden | ✅ |
| W-6 | 断后重连：第 2 次连接同 session auth_ok | ✅ |
| W-7 | 巨字号：wechat jest fontScale 4/4 + 全套 424/424 | ✅ |

### §2.2 iOS 端 (S2-TEST-006 / I-1~I-7)

| ID | 用例 | 结果 |
|----|------|------|
| I-1 | U-1 与微信逐字符互锁（33 case CI SUCCESS） | ✅ |
| I-2 | 支付链路（后端契约共用，APIEndpointTests 18 case CI 覆盖） | ✅ |
| I-3 | sendOTP HTTP 200 + masked_phone + expires_in=300 | ✅ |
| I-4 | 双轴-token 日上限：第 6 次 429（cap=5） | ✅ |
| I-5 | 双轴-phone token 数上限：第 4 个 token 429（cap=3） | ✅ |
| I-5b | TTL 配置契约：expires_in=300（ttl_seconds=300） | ✅ |
| I-6 | 脱敏+WS iOS 客户端层（后端契约 staging 已验；viewer UI 拆 INT-006） | ✅ 范围内 |
| I-7 | 巨字号：FontScale token 非等比 + 33 case CI SUCCESS | ✅ |
| AC#24 | APIEndpointTests 7 字段反序列化 PR #130 18 case CI SUCCESS | ✅ |
| AC#25 | U-1 与微信逐字符 PR #132 33 case 互锁 CI SUCCESS | ✅ |

iOS CI 真跑过证据链：
- PR #130 head SUCCESS
- PR #132 head `3753da4` SUCCESS（run 26888402585）
- PR #134 head `72a568a` SUCCESS（run 26888919292）
- PR #138 head SUCCESS（run 26890165541）
- **main HEAD `bcfb425` SUCCESS（run 26889954626）** — §5.4 iOS 端基线
- main HEAD `9ed6fac`（#138 合后）需新 dispatch 一次跑作为 INT-006 起手前的最新 baseline，胡桃跟进

### §2.3 admin-h5 + §4 契约 (S2-TEST-007 / A-1~4 + C-1~3)

| ID | 用例 | 结果 |
|----|------|------|
| A-1~4 | admin smoke 15/15（鉴权/订单/用户+脱敏/审计/越权） | ✅ |
| C-1 | OpenAPI baseline diff: 18 guarded fields stable（9 字段权威） | ✅ |
| C-2 | wechat typecheck `tsc --noEmit` 0 报错 | ✅ |
| C-3 | iOS APIEndpointTests CI SUCCESS（多 head 证据链） | ✅ |

---

## §3 灰度结论

**staging 可供 S2-TEST-004 灰度回归实跑** ✅

依据：
1. 三端冒烟全 PASS（§5.1 / §5.2 / §5.3）
2. 跨端契约 9 字段 GUARDED_FIELDS 三端互锁绿（§5.4）
3. 资金线 BUG-W001 已修闭环（mock 走真 callback，灰度切真 wxpay 时回调路径已验证）
4. 状态机解耦 ADR-0041 显式化（OrderStatus / PaymentState / RefundState 三套独立，灰度后业务行为可预期）

**前置硬约束**（灰度门，必须合）：
- S2-INT-006 iOS ShareOrderView + UniversalLink + WS share topic（魈拍 D+2 完成）
- S2-TEST-006 增量复测 iOS viewer UI + WS（D+3）

**软约束**（可灰度后跟进，不阻塞）：
- ADR-0040 distributed CB 实施 + OTP outbound 回归
- staging 部署 worktree OPS 长期方案
- ADR-0039 §3 验收第 2~4 项注释/文档清零

---

## §4 测试侧建议

1. **灰度期间**：W-1 资金线在真 wxpay 上必须复跑（mock 路径已验，真路径回调签名/幂等/重试需观察）
2. **灰度期间**：OTP 链路接 ADR-0040 distributed CB 后回归 I-4/I-5（多 worker 频控不可被绕过）
3. **INT-006 完成后**：S2-TEST-006 viewer 侧 E2E（ShareOrderView 渲染脱敏 / UniversalLink 截获 / iOS WS share topic 订阅）

---

**报告产出时间**：2026-06-03 14:40 UTC
**测试员**：刻晴 ⚡
