# 技术债登记 (TECH_DEBT.md)

> 消息链路审计（2026-04-17，D-019 Update 后）发现的轻微问题集合。严重 / 重要的问题
> 已在本次修复，本文件只记录"暂缓处理、但需要在后续迭代中跟踪"的技术债。

## TD-MONEY-01 schemas 主动 `float()` 序列化金额

- **状态**：进行中（2026-04-27 W18 复盘后登记）。
- **问题描述**：`backend/app/schemas/order.py::_ser_price`、`_ser_amount` 及 `companion.py::_ser_total_earnings` 为兼容老客户端契约，主动将 `Decimal` 转 `float`。侍服上线 Decimal-aware parser 后应迁回原始 Decimal 字符串序列化。
- **代码位置**：`backend/app/schemas/order.py` `_ser_price` / `_ser_amount`；`backend/app/schemas/companion.py` `_ser_total_earnings`。
- **修复计划**：WeChat / iOS / admin-h5 都升级为 Decimal-aware parser 后（跟踪于 ADR-0030）删除 `float()` 转换，返回 Pydantic 默认 Decimal 序列化。
- **优先级**：P2（deadline 2026-06-30 / W26）。

## TD-ORDER-LOGGER-01 OrderService 子模块 logger 间接

- **状态**：✅ 已解决（2026-04-27 chore/post-w18-cleanup）。
- **原问题**：`cancel.py` / `expiry.py` 原本用 `sys.modules["app.services.order"].logger` 间接取 logger，子模块独立 import 时会 KeyError。
- **解决方式**：`_OrderServiceBase` 加 `logger` property，走 `from app.services import order as _pkg; return _pkg.logger`，依然兏容 `patch("app.services.order.logger")`。
- **PR**：chore/post-w18-cleanup

## TD-ADMIN-H5-CSP · admin-h5 token 存储 + CSP

- **状态**：✅ 已解决（2026-04-27）。Token 从 localStorage 迁到 sessionStorage（关闭标签页后失效）；index.html 加 CSP + nosniff。

## TD-MSG-01 聊天消息幂等性

- **状态**：✅ 已解决（2026-04-27，见 ADR-0031）。
- **解决方式**：WSBase send 时自动注入 16 字符 client nonce + 5 分钟本地 LRU
  短路；后端 `ChatService.send_message_via_ws` 用 `SET key val NX EX 300`
  在 Redis（key `chat:nonce:{user_id}:{nonce}`）兜底，命中则不落库不广播。
- **PR**：feat/c12-ws-dedup → main

## TD-ADMIN-01 force-status 走 refunded 不触发退款

- **描述**：`POST /api/v1/admin/orders/{id}/force-status` 仅以 deny-list 拦住不可逆转换，
  漏掉了「如果运营手工将状态改为 `refunded`」这条金钱路径。现在只写审计 +
  变更 `Order.status`，不创建 Refund Payment、不出账、不冻结。
- **代码错**：`backend/app/api/v1/admin/orders.py::force_order_status`。
  现存 TODO(W19) 标记在接口体内。
- **缓解方案**：检测 `new_status == "refunded"` 时调用 `PaymentService.create_refund(原订单全额)`，
  并联动 wallet 冻结释放；dry-run 模式供财务预览。
- **优先级**：P1（有财务风险，上线 wechat provider 后严重）。

## TD-ADMIN-02 force-cancel 不通知两方

- **描述**：运营进行 `force-status` 为 `cancelled_by_*` 时，不推送给患者与陪诊师任何
  WS / 订阅消息。双方只能通过下拉刷新发现订单变更。
- **代码错**：`backend/app/api/v1/admin/orders.py::force_order_status` 仅写审计未发通知。
- **缓解方案**：复用 `notification_service.send_to_user(...)`，为 `force-cancel` 动作调用一次；
  模板 「订单已被运营取消: <reason>」。
- **优先级**：P1（体验严重损伤）。

## TD-ADMIN-03 force-status 到 completed 不更 companion_profile 计数器

- **描述**：正常完成路径会递增 `CompanionProfile.total_orders`；`force-status` 跳过状态机后
  此计数器不动，导致后台「陪诊师接单量」与实际订单表不一致。
- **代码错**：同上 force_order_status。
- **缓解方案**：在 force 完成路径以及其他应动计数器的转换里走同一个 `OrderStatsService.recompute(order)`
  （不变量：profile.total_orders == count(orders WHERE companion_id=? AND status∈{completed,reviewed})）。
- **优先级**：P1（与 W19 一同交付）。

## TD-MSG-02 重连期间消息回补

- **描述**：WS 断线 → 重连成功之间，如果对方发来新消息，前端不会主动拉取
  未读（当前仅在页面首次打开时 `loadHistory`）。
- **缓解方案建议**：重连成功回调里调用一次 `getChatMessages({ after: lastKnownId })`；
  后端增加 `after` / `since_id` 查询参数。
- **优先级**：P2

## TD-MSG-03 已读状态跨设备同步

- **描述**：用户 A 在手机 A 上标记已读，手机 B 本地内存中的未读计数不会立即更新；
  需要重新进入页面或刷新。
- **缓解方案建议**：已读动作也通过通知 Pub/Sub 下发 `{type: "read_receipt"}`，
  所有该用户的 WS 端都更新本地未读。
- **优先级**：P3

## TD-MSG-04 WS 服务端心跳空闲超时

- **状态**：✅ 已解决（2026-04-27，见 ADR-0031）。
- **解决方式**：`/ws/notifications` 与 `/ws/chat/{order_id}` 的 receive 循环
  统一用 `asyncio.wait_for(receive_text, timeout=90)`；超时即 4002 关闭并
  累加 Prometheus 计数器 `ws_idle_timeout_total{channel}`。客户端心跳 30s，
  容差 3 次。
- **PR**：feat/c12-ws-dedup → main

## TD-MSG-05 消息历史分页使用 offset

- **描述**：`GET /chats/{order_id}/messages` 使用 `skip / limit` offset 分页；
  订单长时间聊天（数万消息）时 offset 翻页会变慢。
- **缓解方案建议**：改为 cursor 分页，参数 `before=<message_id>` 已部分支持，
  但后端 repository 仍是 offset；接入已有 index (`created_at`) 做真·cursor。
- **优先级**：P3

## TD-MSG-06 iOS WebSocket 重连未自动回连到 order

- **描述**：`WebSocketClient.reconnect()` 仅 sleep 后退出，注释说"caller should
  observe isConnected and call connect() again"，但当前调用方未做该监听。
- **缓解方案建议**：iOS 团队在 `ChatViewModel` 订阅 `isConnected`，断开后自动
  `connect(orderId:)`。本次仅只读审计，登记在此供 iOS 迭代处理。
- **优先级**：P2（iOS 侧）

## TD-MSG-07 大消息体压缩

- **描述**：单条聊天消息 content 上限 4000 字符（服务端新增），未对大文本做压缩；
  走 JSON over WS 时流量不高，但未来支持图片 base64 / 富文本需要进一步审视。
- **优先级**：P3（当前仅 text 类型，未启用 image/system 详细字段）

## TD-ADMIN-01 force_status → refunded 时联动触发退款

- **描述**：`POST /api/v1/admin/orders/{id}/force-status` 仅修改
  `Order.status` 字段，不会主动调用 `PaymentService.create_refund`。
  若运营人员手动把订单强制改成 `refunded` 状态，钱不会退还给患者。
- **缓解方案**：force_status 进入 `refunded` 分支时，自动以原支付金额触发退款；
  或在 H5 上禁用该选项、仅允许走 `/refund` 端点。
- **优先级**：P1（admin 上线前必须解决）

## TD-ADMIN-02 force-cancel 时通知双方

- **描述**：force_status 把订单改成 `cancelled_by_*` 时，未发送 WS / 推送给
  患者或陪诊师；用户体验上像被静默取消。
- **缓解方案**：force_status 在 cancellation 路径上调用现有
  `NotificationService.broadcast_order_cancelled` 与对应模板消息。
- **优先级**：P1

## TD-ADMIN-03 completion 时更新 companion total_orders

- **描述**：`force_status → completed` 不会更新 `Companion.total_orders` /
  `Companion.last_order_at` 等聚合字段；正常 completion path（陪诊师端
  `complete_service`）会更新这些。
- **缓解方案**：force_status 进入 completed 分支时复用现有
  `CompanionService.bump_completed_counter` 逻辑。
- **优先级**：P1

## TD-MSG-08 微信订阅消息（Subscribe Message）未接入

- **描述**：当前通知仅通过 WebSocket 实时推送；小程序后台 / 切出时收不到系统弹窗。
- **阻塞**：需要向微信开放平台申请订阅消息模板（模板 ID 需要人工审核通过）。
- **缓解方案建议**：走后端 `订单状态变更` 节点触发 `subscribeMessage.send`；
  前端在下单 / 接单前调 `wx.requestSubscribeMessage`。
- **优先级**：P2（产品可感知；但依赖外部审批）

---

每条技术债被解决后，请更新 DECISION_LOG.md 对应 D-xxx 小节并从本文件删除。

## Lessons learned

### 2026-04-27 · admin-h5 状态枚举漂移

**现象**：MVP 合入后发现 admin H5 select / status badge / refund 弹窗全部使用了
`pending/paid/serving/cancelled/refunded` 这套「常识性」字符串，但后端 `OrderStatus`
枚举是 `created/accepted/in_progress/completed/reviewed/cancelled_by_*/rejected_by_companion/expired`。
后果：除 `completed` 以外列表过滤、改状态全部 400；表格取 `o.patient_name/o.amount/u.nickname/u.mobile`
全是 undefined，UI 只能显示 UUID。

**根本原因**：

1. **单一事实源丢了**：MVP 带上纯手写 vanilla JS 后台，没有 TypeScript / OpenAPI codegen，纯靠人粘引用后端字段名。 
2. **无集成测试报警**：admin-h5 历史上无 jest 套件，PR #36/#37 review 也没要求实测。 
3. **交付验收唯 mock**：下游连联调试被运营门口到才发现，堆后累计成「实战不可用」。

**改进措施**：

- 后端 list / detail response 在代码注释里明确标记为「后台 H5 contract」，变更需同步改 H5。
- `admin-h5/app.js` 顶部 `STATUS_LABELS` 表与 backend `OrderStatus` 一一对应；代码 review checklist
  加一项「枚举变更是否同步后台字典」。
- 后续如果后台启动不再是临时 vanilla JS，优先考虑 OpenAPI 生成 TS DTO。
- 此事件后 · admin-h5 状态枚举漂移【✅ 已修复（2026-04-27）】。

## Lessons Learned

### H5 ↔ backend 状态枚举漂移（2026-04-27）

admin-h5 早期沿用了 `pending / paid / serving / cancelled / refunded` 等
**虚构** 的 OrderStatus 字符串，与 backend 真实枚举
（`created / accepted / in_progress / completed / cancelled_by_* / expired`）
完全错位；上线前最后一刻才在 contract review 中发现，否则会出现
「下拉框选不到任何订单」+「force-status 全部 422」的事故。

**结论**：
- 任何 admin / 内部前端在引用后端 enum 时都不允许硬编码字符串；
  必须把后端 OpenAPI schema 的 enum 自动导出为 H5 / 小程序常量
  （建议 CI 步骤：`scripts/gen_status_constants.py` 读取
  `backend/app/models/order.py::OrderStatus` 生成 `admin-h5/constants.gen.js` 与
  `wechat/constants/order-status.gen.js`，diff 即 fail）。
- 同样问题在 `User.is_active` ↔ H5 `status=active|disabled` 也出现过：
  长期目标是 contract test 自动锁死字段名 + 类型。

## 已解决的技术债
- **W18 admin-h5 contract alignment** — 2026-04-27 解决。
  PR `fix/admin-h5-contract` 一次性解决：(1) admin-h5 的 OrderStatus 枚举
  对齐后端真实枚举；(2) 字段名对齐（`patient_display_name` / `price` /
  `phone_masked` / `display_name`）；(3) 后端 admin/orders、admin/users 列表
  响应补 join User；(4) PII 脱敏默认开 + `?reveal=true` 写 `reveal_pii` 审计；
  (5) 全部 admin 读端补 `view_*` 审计行；(6) `force_status` 加 deny-list +
  写 `force_status_denied` 审计。pytest 41/41（test_admin.py）+ 全量
  ~924 passed。
- **C-12 / TD-MSG-04 / TD-MSG-01 WebSocket 双模块统一** — 2026-04-27 解决，
  见 ADR-0031。后端 `app/api/v1/ws.py` 全部走 `ChatService.send_message_via_ws`；
  新增 90s asyncio idle timeout + `ws_idle_timeout_total{channel}` 计数器；
  抽出 `wechat/core/ws-base.js`，`services/websocket.js` 与
  `services/notificationWs.js` 改造为薄壳，去掉 95% 重复代码；端到端 nonce
  幂等（客户端 5min LRU + 服务端 Redis SETNX 5min TTL）。pytest 921 passed
  / 15 skipped；jest 247 passed / 235 baseline。PR：feat/c12-ws-dedup → main。
- **TD-ARCH-03 金额字段使用 Float（IEEE 754 风险）** — 2026-04-25 解决，见 ADR-0030。
  `Order.price` / `Payment.amount` Float → `Numeric(10, 2)`；`SERVICE_PRICES`、
  Provider DTO（`OrderDTO.amount_yuan` / `RefundDTO.total_yuan` / `refund_yuan`）、
  `PaymentService` / `WalletService` / 退款比例计算全链路切 `Decimal`。
  Alembic 迁移 `a1d0c0de0030_money_to_decimal_adr_0030.py`（Postgres 用
  `USING ::numeric(10,2)` 强转，SQLite 走 `batch_alter_table`）。
  对外契约不变：Pydantic `field_serializer` 把 Decimal 输出为 number，
  前端（小程序 `formatPrice`）零改动。新增 `tests/unit/test_decimal_money.py`
  13 用例锁死契约（精度、舍入、yuan→fen、API 序列化形态）。
  全量 880 passed / 15 skipped / 108s。
  iOS 端 `Order.price`、`Payment.amount` 已是 `Decimal`（早期完成）；
  遗留小坑：Swift `Decimal` 默认 Codable 经 Double 中转，需后续提供自定义
  decoder（暂未触发，金额仅 2 位小数）。
- **TD-PAY-01 订单过期时支付状态未联动收尾** — 2026-04-25 解决，见 ADR-0029。

- **ADR-0029 紧急呼叫 PII 加密 + 180d 保留** — 2026-04-27 部分解决（PR #N）。
  - ✅ **F-1**: AES-256-GCM envelope encryption + phone_hash 落库（`app/core/pii.py`）
  - ✅ **F-3**: `delete_account` 联动硬删 `emergency_contacts` / `emergency_events`（`app/services/user.py`）
  - ✅ **F-4**: cron `cleanup_emergency_pii` 每日 03:00 清理过期 contact (90d grace) + event (180d)
  - ⏳ **F-2 KMS 密钥轮换**：envelope key 当前从 `settings.pii_envelope_key` 加载（进程内常驻）；真正的 KMS data-key 流程留 W19+，优先级 P1（上生产前必须）。`pii.EnvelopeKey.rotate` 已预留接口。


- **TD-OPS-01 `/readiness` 端点缺失** — 2026-04-17 解决，见 D-021。
  根路径 `/readiness` + `/api/v1/readiness` 双挂载；DB(SELECT 1) + Redis(PING)
  健康检查，失败 503 含错误摘要；`/health` 保持纯 liveness 不查依赖。
- **TD-CI-01 测试轨道与生产迁移脱钩** — 2026-04-17 解决，见 D-022。
  新增 `backend/tests/smoke/test_pg_alembic_smoke.py`（真 PG，5 tests）+
  `.github/workflows/ci-smoke.yml`（services: postgres15/redis7）+
  `.pre-commit-config.yaml`（`alembic check` hook via scripts/alembic_check_hook.py）+
  `alembic/env.py` 支持 `ALEMBIC_DATABASE_URL` / `DATABASE_URL` env override。
- **TD-OPS-02 `/readiness` 缺少迁移漂移检测 (Migration drift)** — 2026-04-25 解决。
  `backend/app/api/v1/health.py::_check_alembic` 比对 `alembic_version` 表当前
  `version_num` 与 `ScriptDirectory.from_config().get_current_head()`，不一致
  即返回 `error: migration drift: db=<x> head=<y>`，整体 503；head 在应用启动
  时通过 `prime_alembic_head_cache()` 缓存一次，避免每次探针都 import alembic；
  `READINESS_SKIP_MIGRATION_CHECK=1` 提供灰度逃生开关；
  回归用例 `tests/smoke/test_readiness_blocker.py::test_readiness_detects_migration_drift`
  已移除 `xfail` 标记，新增 4 个单测覆盖缓存与开关，文件内 16/16 全绿。

## TD-PAY-01 订单过期时支付状态未联动收尾

- **描述**：调度器 `check_expired_orders` 把 `Order.status` 标为 `expired`
  时，对应 `Payment` 行不会被自动转 `failed` / 触发自动退款。如果 Mock provider
  已经把 pay 行设为 `success`，订单过期后这笔款会处于"订单过期但已付款"的悬空状态。
- **风险**：中。Mock provider 仅 dev/test 影响；wechat provider 上线后，
  Pay 回调若在订单已 expired 后才到达，`handle_pay_callback` 的"terminal state guard"
  只在 pay 行已经是 success/failed 时才生效——如果 pay 行还是 pending 而订单已 expired，
  回调会把 pay 翻成 success 且**不会**触发退款。
- **来源**：P1-7 阻断级测试 `test_callback_after_expired_does_not_reactivate`
  在编写过程中发现，已通过手工把 pay 行写成 `failed` 来绕过；生产路径里这个清理动作目前没人做。
- **缓解方案**：
  1. `OrderService.check_expired_orders` 在标过期时同步把 pay 行降级为 `failed`（如尚未 success）。
  2. `PaymentService.handle_pay_callback` 增加"order 已是 expired/cancelled 时强制走退款分支"的防御逻辑。
- **优先级**：P1（与 wechat provider 上线同窗口）

- **已解决（2026-04-25）**：见 ADR-0029。check_expired_orders 对 paid 订单 raise NotExpirableOrderError（HTTP 409），对 pending pay 走 close + fail + 留痕；late SUCCESS 回调由 handle_pay_callback 防御退款分支兜底。



## TD-ORDER-01 check_expired_orders 中 pending-close 块重复 ✅ 已完成

- **状态**：✅ 已修复（PR `fix/order-expiry-dedup`）。删除 `expiry.py` 中重复的 pending-close 块；新增 `tests/test_order_expiry.py` 用 mock 计数固化「每个 expired order 一次 expiry 周期内 `close_pending_payment` 仅被调用 1 次」的契约（含批量场景）。
- **描述（历史）**：`backend/app/services/order/expiry.py::check_expired_orders` 第 65-110 行存在两段几乎完全相同的 try/`close_pending_payment`/`flush` 代码。SP-01 拆分时为了保持"零行为变更"原样保留。第二次执行时 `existing_pay.status` 已被第一次 try 块改成 `failed` 或 `closed`，所以 PSP `close_pending_payment` 实际还是会被调用第二次（除非 PSP 端幂等返回失败）。
- **风险（修复前）**：Mock provider 幂等无副作用；上线 wechat 真实 provider 后第二次 close 会把第一次 `[order_expired]` 痕迹覆盖成 `close_failed`，事后审计指错根因。
- **来源**：SP-01 (D-042) 拆分时发现，commit `0af598d` 之前就存在的 legacy bug。
- **优先级**：P3 → 完成
- **Lessons learned**：mock provider 幂等掩盖 bug 的反模式 — 真实 PSP 切换前必须用真实非幂等 mock 跑回归，否则二次调用 / 重复调用类 bug 会被吞掉直到生产才暴露。
