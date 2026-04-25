# 技术债登记 (TECH_DEBT.md)

> 消息链路审计（2026-04-17，D-019 Update 后）发现的轻微问题集合。严重 / 重要的问题
> 已在本次修复，本文件只记录"暂缓处理、但需要在后续迭代中跟踪"的技术债。

## TD-MSG-01 聊天消息幂等性

- **描述**：WebSocket 收到重复消息（例如客户端网络抖动触发重传、或同一 payload
  被多次写入）时，后端无幂等校验，会生成多条 DB 记录。
- **风险**：轻微。微信 `wx.connectSocket` 本身不会重放上行帧；仅在极端对抗场景下
  才会出现重复。
- **缓解方案建议**：让客户端在每条 WS 消息带 `client_nonce`（UUID），服务端在
  写库前先查 redis `SETNX nonce:{client_nonce} 1 EX 60`，命中则丢弃。
- **优先级**：P3

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

- **描述**：后端 WS endpoint 无 idle timeout，如果 TCP 层 keepalive 失败，连接
  会残留在 `_local` dict 里直到下次 `send` 失败。
- **缓解方案建议**：给 WS endpoint 套 `asyncio.wait_for(receive_text, timeout=90s)`，
  超时即视为僵尸连接并关闭；或使用 uvicorn 的 `ws_ping_interval` 强制 ping。
- **优先级**：P2

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

## TD-MSG-08 微信订阅消息（Subscribe Message）未接入

- **描述**：当前通知仅通过 WebSocket 实时推送；小程序后台 / 切出时收不到系统弹窗。
- **阻塞**：需要向微信开放平台申请订阅消息模板（模板 ID 需要人工审核通过）。
- **缓解方案建议**：走后端 `订单状态变更` 节点触发 `subscribeMessage.send`；
  前端在下单 / 接单前调 `wx.requestSubscribeMessage`。
- **优先级**：P2（产品可感知；但依赖外部审批）

---

每条技术债被解决后，请更新 DECISION_LOG.md 对应 D-xxx 小节并从本文件删除。

## 已解决的技术债
- **TD-PAY-01 订单过期时支付状态未联动收尾** — 2026-04-25 解决，见 ADR-0029。

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

