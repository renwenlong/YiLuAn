# 医路安 — 测试覆盖盲点评估报告

> 作者：刻晴（测试员，YiLuAn-Team）
> 任务：S1-TEST-001（board `yiluan-study-iter`）
> 评估对象：`/home/wenlongren/repo/YiLuAn`（Sprint W18 之后的当前主干）
> 立场：默认"未通过"，每条结论对应可在仓内复现的事实。

---

## 0. TL;DR

四端测试规模 **1239+** 个 case（backend pytest 1104+、wechat jest 54 个 spec 文件 / 256 case、iOS XCTest 17 个文件 / 57 case、admin-h5 3 个 spec / ~预估几十 case），主干模块（资金对账、订单生命周期、支付回调幂等、PII、Outbound 可靠性）有**单元 + 服务级**测试垫底，**资金对账模块语句覆盖 92%**。

但识别出 **12 个测试盲点**，其中 **P1 = 7**、**P2 = 5**，主要集中在：

1. **跨端契约测试缺失** — 后端 OpenAPI 与小程序/iOS 客户端模型之间无 contract test，schema 漂移只能等 E2E 撞出来。
2. **真 WS 端到端浅** — `test_e2e_chat_websocket.py` 单文件，没有覆盖断线重连 / 消息顺序 / pubsub fan-out 在多 worker 下的丢消息场景。
3. **支付/退款 webhook 回调对抗性测试不足** — idempotency 有专项 case，但缺重放 + 乱序 + 跨幂等键 + 签名失败混合场景的 fuzz/property 测试。
4. **admin-h5 几乎裸奔** — 仅 3 个 util 级 spec，无组件测试、无 admin 关键操作 E2E（双签 close、对账 worklist 操作）。
5. **小程序无真机/模拟器集成测试层** — 仅 jest 单元，缺 miniprogram-automator 流程测试。
6. **iOS 仅 ViewModel + Decoding 单测** — 无 UI 测试（XCUITest 为零），SwiftUI 屏幕交互没人测。
7. **可观测性回归门缺失** — metrics / telemetry / log retention 有功能测试，但没有"告警触发→Alertmanager 路由→通知到达"链路测试。
8. **数据库迁移测试只覆盖 1 个 revision** — `test_alembic_a1d0c0de0030_smoke.py`，其他 revision 缺 up/down 双向 smoke。

---

## 1. 四端测试规模盘点

### 1.1 Backend (FastAPI / pytest)

| 维度 | 数据 |
|------|------|
| 测试文件数 | 118（含 unit/services/cron/e2e/smoke 子目录） |
| 主目录 test_*.py | 75 个顶层 spec 文件 |
| 子目录 | `unit/`（1）/ `services/`（含 order、reconciliation 子模块 9 个文件）/ `cron/`（2）/ `e2e/`（7）/ `smoke/`（4）/ `utils/`（1） |
| 全仓 pytest passed | **1104 passed** + 16 skipped + 1 xfailed（recon_coverage.md 记录） |
| 覆盖率 | 资金对账模块**语句 92% / 分支 82%**（其他模块未见正式覆盖率报告） |
| pytest 配置 | `addopts = "-m 'not smoke'"` — **smoke 测试默认不跑**，需手工触发 |
| 覆盖工具 | coverage.py 7.13.5，`core = "sysmon"`（Python 3.12 必须，否则 async 误判 miss 约 4%） |

**主干已覆盖的领域**（看 spec 文件名可推）：
- 认证（手机号 / 微信 / Apple）、注册必填守卫
- 订单全生命周期（创建/取消/退款/过期/拒绝/资金子态/idempotency D-058）
- 支付（callback 幂等 + boundary + concurrent + expire interlock + 真支付 E2E）
- 资金对账（autofix / diff / incremental / 双签 close 负向 / 并发）
- PII（envelope 加密、emergency 加密、退号清空）
- WS（chat service / connection cap / endpoints / pubsub / outbound pubsub）
- Outbound 可靠性（utils/test_outbound.py，对应 ADR-0026）
- Cron（reconcile_money / reconciliation_cleanup / cleanup_emergency_pii）
- 限流（读 + 写两套）、SMS（多 provider、并发、send_log）
- Admin V2、Admin 对账、Admin Dashboard 审计、Admin Wallet ledger、Admin orders W19 + 死信
- Followup reminders、family members、emergency、reviews、telemetry、log retention、health/readiness

### 1.2 微信小程序 (wx + jest)

| 维度 | 数据 |
|------|------|
| Spec 文件 | **54 个** `*.test.js`（之前消息里说 256 应为 case 数，文件数为 54） |
| 组件测试 | 2 个（rating-stars / skeleton-list） |
| 工具/store/config | ~20 个（utils、store、config、core/ws-base） |
| Services | ~19 个 service 层 spec（websocket、order-lifecycle、payment、notification、emergency 等） |
| Pages | ~13 个页面级 spec（emergency-contacts、chat-room-history-pagination、pay-result、order-detail-* 等） |
| app 层 | app.test.js |
| 集成/真机 | **无 miniprogram-automator 流程测试** |

### 1.3 iOS (SwiftUI / XCTest)

| 维度 | 数据 |
|------|------|
| 测试文件 | **17 个** `*.swift` |
| 类型 | ViewModel 测试（Auth/Order/Review/Settings/Wallet）、Decoding（CompanionProfile）、Endpoint（API/Emergency/Followup&Hospital/NewEndpoints）、Design System、CurrencyFormatter、AppleSignInService、ErrorCodeGuideCard、PaymentResult、Model、ScrollOffsetKey |
| UI 层 | **无 XCUITest** — SwiftUI 屏幕交互、导航、表单提交、深链跳转完全无自动化 |
| Snapshot 测试 | **无**（DesignSystemTests 只是组件单测，不是快照对比） |

### 1.4 admin-h5（管理后台 H5）

| 维度 | 数据 |
|------|------|
| Spec | **3 个**：`familyMember.test.js` / `usersMultiRole.test.js` / `formatCurrency.test.js` |
| 主体 | 仅工具/字段层。**核心 admin 操作（对账 worklist、双签 close、订单干预、用户管理）零测试** |
| E2E | **零** |

---

## 2. 测试盲点清单

每条按 **盲点 → 风险 → 建议补法** 三段式给出。优先级按业务影响 + 出错爆破半径定。

### P1（必补，影响核心业务可信度）

#### P1-GAP-01 · 跨端 API 契约测试缺失

**事实**：后端有 OpenAPI（`backend/app/api/v1/openapi_meta.py`），但仓内未见 schema 与小程序/iOS 客户端模型的 contract test（grep 无 `openapi-typescript`、`swagger-codegen` 校验脚本，iOS `APIEndpointTests` 只校验 URL/method，不校验 response schema 字段）。
**风险**：后端字段重命名 / 类型改动（如 `Decimal` ↔ `string` ↔ `int`）只能等 E2E 或线上 crash 才暴露，跨端不一致是当前最大隐性回归源。已上线 Sprint W18 + admin V2 + 对账双签，未来迭代字段必会变。
**建议**：
1. CI 加 step：导出 OpenAPI JSON → 用 `openapi-typescript` 生成 TS 类型，对小程序 `services/*.js` 入参/返回字段做 schema 校验（先在 services 层加 JSDoc + type check）。
2. iOS 侧：`APIEndpointTests` 扩展 — 用 mock 后端 OpenAPI 例子 JSON 反序列化到模型，断言无字段丢失/不匹配（Pact-style consumer contract）。
3. 后端 CI 加 schema diff 门：与 main 分支 OpenAPI 比对，breaking change 必须人工放行。

#### P1-GAP-02 · WS 真链路 E2E 太浅

**事实**：`backend/tests/e2e/test_e2e_chat_websocket.py` 单文件；`test_ws_pubsub_outbound.py` / `test_ws_pubsub.py` 是 pubsub 层单测，多 worker / 跨节点 fan-out / 客户端断线重连 / 消息 ack / 消息顺序保序 都没有专项 E2E。小程序 `services/websocket.test.js` + `services/notificationWs.test.js` 是 mock 层。
**风险**：聊天、通知、急救事件都依赖 WS；W18 做了 ChatService 统一（ADR-0031），但生产场景下断线/重连/Redis pubsub 在多 worker 下的丢消息问题没法被现有测试捕获。
**建议**：
1. 加 `tests/e2e/test_e2e_ws_reconnect.py`：客户端中断 → 重连 → 验证未送达消息按 ack 重发，序号无空洞。
2. 加 `tests/e2e/test_e2e_ws_fanout.py`：起 2 个 worker → 一个发，多端收，断言每条消息恰好送达一次（结合 idempotency key）。
3. 小程序加 miniprogram-automator 脚本（见 P1-GAP-05），覆盖"前台→后台→前台"WS 重连。

#### P1-GAP-03 · 支付/退款回调对抗测试不足

**事实**：已有 `test_payment_callback_idempotency.py` / `test_payment_callback_blocker.py` / `test_refund_callback.py` / `test_refund_e2e.py` / `test_payment_concurrent.py` / `test_payment_expire_interlock.py` — 覆盖很扎实，但**乱序回调 + 跨幂等键混合 + 签名失败 + 重放窗口**的组合性 fuzz 缺失，且 `test_wechat_verify_callback.py` 只测正向。
**风险**：微信支付/退款回调在线上必然出现乱序（success → close → success_again，refund_success 早于 refund_create）；签名失败的重试风暴若与 idempotency 交互不当会污染账。
**建议**：
1. 用 hypothesis 加 property-based test：随机生成回调序列（含重放、乱序、签名错、不同 out_trade_no），断言最终账态收敛到唯一正确状态。
2. 加 `test_payment_callback_signature_fuzz.py`：签名错回调的速率限制 + 不落账 + 不触发告警风暴。
3. 退款回调 + 对账 autofix 联测：退款回调丢失场景下，T+1 cron 是否能从对账差异自愈（覆盖 ADR-0032 的关键 SLA）。

#### P1-GAP-04 · admin-h5 几乎裸奔

**事实**：3 个 util 级 spec，**对账双签 close、worklist 操作、用户禁用、订单干预、Wallet ledger 操作**这些 admin V2 关键操作（ADR-0034）零自动化。
**风险**：admin 是高权限入口，回归一旦失误直接造成线上资金/隐私事故。手测频率低、易遗漏。
**建议**：
1. 引入 Playwright（admin-h5 是 H5，无小程序限制），先写 5-8 个最关键 E2E：登录 → 双签 close → worklist 处理 → 用户禁用 → 钱包 ledger 查询 → 退款审批。
2. 关键操作加 audit log 断言（呼应 `test_admin_dashboard_audit_notes.py`）。
3. 组件级：admin-modules.js 拆出后补单测，至少覆盖 form 校验、危险操作二次确认弹窗。

#### P1-GAP-05 · 小程序无流程级集成测试

**事实**：54 个 jest spec 都跑在 mock 环境，**miniprogram-automator 流程测试为零**。下单 → 支付 → 聊天 → 评价 → 投诉这条主链没有跨页面自动化。
**风险**：jest 测不到 page 跳转、组件树渲染、tab 切换、wx API 真实行为差异、网络异常下的 UI 状态。每次发版只能依赖手测 regress。
**建议**：
1. 引入 miniprogram-automator，先覆盖 **3 条最关键 flow**：① 患者完整下单→支付→收到陪诊确认；② 陪诊员接单→开始服务→完成→拿到结算；③ 急救按钮触发→倒计时→联系人收到通知。
2. 跟后端 e2e 拉同一份 fixture，避免 mock 漂移。

#### P1-GAP-06 · iOS 零 UI 测试

**事实**：17 个 XCTest 全是 ViewModel / Decoding / Endpoint 层，**XCUITest 文件 0 个**。SwiftUI 关键屏（登录、订单详情、聊天、急救、Apple Pay 流程）UI 完全无自动化。
**风险**：iOS 客户端 SwiftUI 容易因系统版本/字体/语言差异破坏布局；交互回归只能靠人测。
**建议**：
1. 加 `YiLuAnUITests` target（XCUITest），先覆盖：登录、订单列表+详情、聊天发消息、急救按钮触发。
2. 加 SnapshotTesting（pointfreeco）做关键视图的快照，跑 iPhone SE / 14 Pro / 大字体 三种 trait。
3. AppleSignInService 已有单测，但**Apple Pay 整链路**（如果用）需要 UITest 验通。

#### P1-GAP-07 · 数据库迁移只有 1 个 revision 测试

**事实**：`test_alembic_a1d0c0de0030_smoke.py` 是唯一 alembic smoke。`backend/alembic` 下其他 revision 没有 up/down 双向测试，`test_models_pg_smoke.py` 只是建库后跑 ORM smoke。
**风险**：W19+ 任何 schema 变更（含资金对账、admin V2 等近期大动作）的 downgrade 路径未被验证；线上回滚相当于赌博。
**建议**：
1. 写参数化 smoke：列举所有 revision，对每个做 upgrade → downgrade → upgrade 三步验证 schema/约束不漂移。
2. 关键 revision 加数据保留断言（downgrade 不应丢业务数据）。

---

### P2（建议补，影响质量纵深与可观测性）

#### P2-GAP-08 · 可观测性链路无端到端门

**事实**：`test_metrics.py` / `test_telemetry.py` / `test_log_retention.py` 覆盖埋点是否产生、保留是否清理，但 **Prometheus → Alertmanager 路由 → 通知到达** 这条链路无集成测试（`prometheus/` + `ops/alertmanager/` 目录存在）。
**风险**：告警静默是生产中最难发现的退化（你以为有告警，其实早就哑了）。
**建议**：
1. 起 docker-compose（已有 `docker-compose.alertmanager.yml`）做 staging smoke：人工触发 SLO 违反 → 断言 alertmanager 收到 → mock receiver 收到 webhook。
2. 加 cron 检查：每日触发"心跳告警"验证链路通。

#### P2-GAP-09 · Outbound 可靠性装饰器只有正向单测

**事实**：`tests/utils/test_outbound.py` 单文件，覆盖 ADR-0026 的可靠性装饰器，但 SMS/支付/微信几类 outbound 在真 provider 故障（5xx 风暴、超时、半响应）下的退避 + 死信 + metrics 联动行为缺集成测试。
**风险**：供应商抖动时熔断/降级行为没有自动化验证，线上才发现退避策略错。
**建议**：
1. 加 `tests/integration/test_outbound_provider_chaos.py`：用 toxiproxy / responses 模拟延迟、断流、5xx、半响应，断言重试/熔断/死信落库。
2. 死信队列消费器加专项测试（呼应 `test_admin_orders_w19_and_dead_letter.py`，扩展到非订单类型）。

#### P2-GAP-10 · 并发竞态测试单点

**事实**：有 `test_payment_concurrent.py` / `test_sms_concurrency.py` / `test_recon_autofix_concurrency.py` / `test_pg_prepay_race.py` / `test_pg_order_conflict.py`（smoke），覆盖到了核心资金路径，但 **WS 连接 cap、钱包 ledger 并发写、family_member 互斥操作**这些次级路径无并发用例。
**风险**：并发 bug 极难复现，业务量上来后才暴露。
**建议**：
1. 给 wallet_ledger_writer / WS connection cap 加 100x 并发压测（pytest-xdist + sqlalchemy session 隔离）。
2. 将 smoke 测试从 `not smoke` 默认排除中拆出，在 CI nightly 任务里跑。

#### P2-GAP-11 · 安全侧覆盖偏功能而非攻击面

**事实**：`test_config_security.py` / `test_rate_limit.py` / `test_rate_limit_writes.py` / `test_pii.py` / `test_pii_envelope.py` / `test_emergency_encryption.py` 都属于正向功能验证，**JWT 篡改/过期/签名错、SQL 注入、IDOR（跨用户访问对方订单/PII）、SSRF（如有富文本图床）、目录穿越（avatar 上传）** 等攻击面缺专项 negative test。
**风险**：业务上 OK 不代表安全 OK。陪诊业务含 PII + 资金，攻击面比一般 SaaS 严肃。
**建议**：
1. 加 `tests/security/test_idor.py`：用户 A 的 token 访问用户 B 的订单/聊天/急救联系人 → 必须 403/404。
2. 加 `tests/security/test_jwt_tampering.py`：篡改 / 过期 / alg=none / kid 切换。
3. avatar / 文件上传：路径穿越 / MIME 伪造 / 大小限制。
4. 引入 bandit + semgrep 到 CI。

#### P2-GAP-12 · 国际化 / 多语言 / 时区 / 货币 边界

**事实**：`CurrencyFormatterTests` (iOS) 和 `formatCurrency.test.js` (wechat/admin-h5) 覆盖基础格式化，但**夏令时、跨时区订单展示、闰年、闰秒边界**未见用例。后端 Decimal 迁移有 `test_decimal_money.py` + ADR-0030，但 BigInt 边界 / 极小金额 / 负数防御没有专测。
**风险**：陪诊订单跨时区（用户在外地就医）会出现时间错位；金额边界出 1 分钱差异即对账失败。
**建议**：
1. 加 `tests/unit/test_money_boundary.py`：0、0.01、999999999、负数、超精度。
2. 时区/DST：用 freezegun 在春秋切换点验证 followup_reminders 触发时机。

---

## 3. 后续 E2E / 契约测试建议

按补测顺序排队，配合 board 节奏：

| 序号 | 工作项 | 工具/位置 | 预估 | 关联 task type |
|------|--------|-----------|------|----------------|
| E2E-1 | OpenAPI → TS 类型 + 前端契约校验 CI 步 | `backend/scripts/export_openapi.py` + `wechat/scripts/contract-check.js` | 1d | develop |
| E2E-2 | WS 重连 + 多 worker fan-out E2E | `backend/tests/e2e/` 新增 2 文件 | 1d | test |
| E2E-3 | 支付/退款回调 hypothesis 测试 | `backend/tests/test_payment_callback_fuzz.py` | 1.5d | test |
| E2E-4 | admin-h5 Playwright 关键 5-8 个 E2E | `admin-h5/e2e/` 新建 | 2d | test + develop（搭脚手架） |
| E2E-5 | 小程序 miniprogram-automator 3 条主链 | `wechat/e2e/` 新建 | 2d | test + develop |
| E2E-6 | iOS XCUITest + SnapshotTesting | `ios/YiLuAnUITests/` 新建 target | 2d | develop（建 target）+ test |
| E2E-7 | Alembic 全 revision up/down smoke | `backend/tests/smoke/test_alembic_all.py` | 0.5d | test |
| E2E-8 | Alertmanager staging smoke | `ops/scripts/` 加心跳 | 1d | develop（cron）+ test |
| E2E-9 | Outbound provider chaos | `backend/tests/integration/` 新建 | 1.5d | test |
| E2E-10 | Security: IDOR / JWT / Upload | `backend/tests/security/` 新建 | 2d | test |

**契约测试方案选型建议**：优先 **OpenAPI → openapi-typescript** 单向校验（轻），不上 Pact（重，多服务才划算）。

---

## 4. 风险等级与处理建议（给凝光/魈/甘雨）

- **凝光排迭代时**：P1-GAP-01 / P1-GAP-04 / P1-GAP-05 / P1-GAP-06 直接挂"质量提升"主题 Epic，与新功能并行而非串行。
- **魈拆 develop task 时**：每个 develop task 必须有对应 test task 显式列出对应的 P1/P2 盲点编号（让我有依据写 E2E）。
- **甘雨排期时**：建议 E2E-1（契约）→ E2E-7（migration）→ E2E-4（admin）→ E2E-5/6（移动端 UI）这个顺序，先封堵跨端漂移和数据安全。

---

## 5. 我（测试员）会怎么用这份报告

- 拿到任一新 develop task 验收时，对照本盲点清单中相关条目检查是否被覆盖；若未覆盖，按报告里 E2E 序号补 test task 的范围。
- 后续 Sprint 我会优先把 P1 盲点对应的 E2E 脚本列入个人交付清单，按 E2E-1 → E2E-7 → E2E-4 → E2E-5/6 顺序落码。
- 复测时严格遵守 workflow 规则"先 get_task 重读最新 acceptance"原则——这份评估只标盲点，不替代 acceptance。

---

文档完。后续问题群里 @ 我。
