# Code Review Checklist

> 架构师 / 程序员 review PR 时使用。每项 ✅/⚠️/❌ 三态，⚠️ 给出修改建议，❌ 阻塞 merge。
> 与 docs/conventions/git-push-policy.md 配套：CI gate 把不掉的语义/契约层用本 checklist 兜底。

---

## §0 元信息（机制类）

- [ ] PR title 与实际改动一致（不要 "fix X" 但 diff 含 unrelated feature）
- [ ] commit 历史是否原子（一个 PR 一个目的，复杂改动允许多 commit 但单 PR 单主题）
- [ ] CI 全绿（含本仓库 4 个 required check：Backend Tests / Docker Build / WeChat Mini Program Tests / Build & Test iOS Simulator）
- [ ] 分支 up-to-date with main（strict required_status_checks=true）
- [ ] 引用的 ADR / 设计文档真存在（`grep -r "ADR-XXXX" docs/adr/`，幽灵引用直接打回）

## §1 状态机解耦（ADR-0041）

凡涉及 `Order` / `OrderStatus` / `PaymentState` / `RefundState` / wallet 的改动：

- [ ] **OrderStatus 状态集禁止扩展"支付意味"字段**（`paid` / `pending_accept` / `paying` 等）
- [ ] **`ORDER_TRANSITIONS` 不以"支付成功"为转换条件**——业务推进由用户/陪诊师/系统事件驱动，不由支付域驱动
- [ ] payment callback handler 只动 `payment.status` + `PaymentState`，**不动 `OrderStatus`**
- [ ] 退款流程：RefundState 转换不回写 OrderStatus；业务 cancel → RefundState 是单向依赖
- [ ] timeline UI 拼接是唯一允许的"统一时间线"出口，三套状态机各管各的
- [ ] 测试用例 acceptance 不写"支付成功后 OrderStatus → paid"（ADR-0041 §2.2 硬规则）

任一违反直接打回 develop，引用 ADR-0041。

## §2 资金安全（pytest -m money_safety）

- [ ] 改动涉及 payment / wallet / ledger / refund / reconciliation → 本地跑 `pytest -m money_safety` 全绿
- [ ] 新增金额字段用 `Decimal` 不用 float
- [ ] callback / refund / wallet update 幂等（同 tx_id / 同 trade_no 重复请求只入一行）
- [ ] 空 transaction_id / 空 trade_no 显式拒绝（ADR-0037）
- [ ] 跨域调用走 `@outbound_call` 装饰器（ADR-0026r1 / ADR-0040）

## §3 分享安全（pytest -m share_security）

- [ ] 改动涉及 share / OTP / share_session / WS share topic → 本地跑 `pytest -m share_security` 全绿
- [ ] share_token 9 字段契约不漂移（`scripts/qa/openapi_contract_diff.py::GUARDED_FIELDS` 真源，三端互锁）
- [ ] PII 脱敏覆盖完整（patient_name → "X**"；phone → mask_phone；medical_notes 不下发）
- [ ] OTP 双轴频控参数与 `backend/app/config.py` 一致（`share_otp_token_daily_cap=5` / `share_otp_phone_token_cap=3` / `share_otp_ttl_seconds=300`）

## §4 契约（跨端 + 状态机）

- [ ] OpenAPI schema diff vs `docs/api/openapi-baseline.json` 无未声明漂移
- [ ] iOS APIEndpointTests 反序列化断言覆盖新字段
- [ ] 微信端 d.ts (`scripts/qa/wechat_openapi_check.sh`) 覆盖新字段
- [ ] 任一端字段类型 string ↔ number 切换、必填 ↔ 可空切换、命名变更 → 显式 ADR 修订 + 双签

## §5 安全 / PII / 鉴权

- [ ] 新接口走 auth dependency（`require_admin` / `Depends(get_current_user)` / share_session 验证）
- [ ] 没有硬编码的 default token / API key（`dev-admin-token` / `staging-admin-token` 等已知字符串 grep 0 命中）
- [ ] PII 日志脱敏（phone / id / name / medical_notes 不裸打 log）
- [ ] sessionStorage / Keychain 命名空间与已有 token 隔离

## §6 性能 / 可维护

- [ ] N+1 查询：list endpoint 用单 SELECT users + dict lookup，不在循环里 query
- [ ] 大循环里没有同步 httpx / requests 调用（用 async + outbound 装饰器）
- [ ] 新增 dependency 评估体积（前端 dist gzip < 2MB，后端不引大 framework）
- [ ] 类拆分 / mixin 模式参照已有 OrderService / PaymentService

## §7 测试覆盖

- [ ] 新增公共方法 / 关键路径有单测（≥ 80% 行覆盖）
- [ ] 边界 case：空 / null / 极值 / 并发 / 异常重试
- [ ] 资金 / 安全相关改动单测 case 数量 ≥ 5（含 fuzz / property-based 优先）
- [ ] iOS PR 必跑 iOS CI 真绿（S2-OPS-008 已落 required gate）
- [ ] 测试 acceptance 与 config 真源一致（不写死硬编码数字而 config 已变化）
- [ ] 双路径字段（写 DB + 读 API）必须 unit 同时断言 DB row + API response（S2-BUG-S010-01 教训：只验 DB 不验 API schema = 漏暴露字段仍返 None）

## §8 文档 / 协作

- [ ] 新增 ADR 文件落盘（不要 PM 引用 ADR 编号但文件不存在）
- [ ] task notes 同步 board（PR # / merge commit / done 后 handoff）
- [ ] 重大决策 commit message 引用 ADR
- [ ] 涉及部署改动 → README.md / docs/conventions/git-push-policy.md 同步

---

## 分级与处理

| 级别 | 含义 | 处理 |
|------|------|------|
| 🔴 阻塞 | 安全 / 数据 / 资金 / 状态机解耦 / 契约漂移 | 必须修，PR 不合 |
| 🟡 建议 | 可维护 / 性能 / 命名 / 测试覆盖 | 应该修，可下一刀 |
| 💭 备注 | 风格偏好 / 改进想法 | 供参考 |

review 评论必须分级。

---

## 反向引用

- ADR-0026r1 outbound 可靠性
- ADR-0036 family-share authorization
- ADR-0037 payment callback empty tx_id rejection
- ADR-0038 admin-h5 default token hardening
- ADR-0040 分布式 Circuit Breaker
- **ADR-0041 支付域/业务域状态机解耦显式化**（§1 主依据）
- ADR-0042 admin-v2 框架选型
- S2-OPS-008 iOS CI required gate
- docs/conventions/git-push-policy.md
- docs/conventions/git-push-sop.md
