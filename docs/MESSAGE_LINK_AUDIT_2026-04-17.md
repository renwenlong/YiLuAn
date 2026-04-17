# 消息链路审计报告（2026-04-17）

> 范围：D-017（实时通知 WebSocket）+ D-019（聊天通道迁移到 Redis Pub/Sub）+ 后续修复。
> 目标：在 Pub/Sub 多副本架构下，系统性核对 20 项风险点，给出「无问题 / 已修 / 技术债 / 本次补」的结论与证据。
>
> 图例：✅ 无问题 · ⚠️ 已修复（含 commit）· 📝 已在 TECH_DEBT 登记 · 🔴 本次新增修复

## 0. 摘要表

| # | 项目 | 结论 | 关键证据 / commit |
|---|---|---|---|
| 1 | WS 认证（notifications + chat） | ✅ | `backend/app/api/v1/ws.py` 均 `decode_token` + `type==access` 校验 |
| 2 | WS 连接清理（无泄漏） | ✅ | `ws.py` try/finally + `broker.unregister` 全覆盖 |
| 3 | 多设备登录行为 | ✅ | `_local[key]` list 结构天然支持多连接 |
| 4 | Pub/Sub 重复推送抑制 | ✅ | `pubsub.py` `origin == instance_id` 自回环过滤 + `test_broker_suppresses_self_echo` |
| 5 | 消息幂等性 | 📝 | TD-MSG-01（P3） |
| 6 | 消息时序 | 📝 | TD-MSG-02（P2），REST fallback by `after/since_id` |
| 7 | 心跳超时阈值 | ⚠️+📝 | 前端 30s ping（见 notificationWs），后端无显式 idle timeout → TD-MSG-04 |
| 8 | 大消息体限制（前后端一致） | ⚠️ f76406f | REST/WS/微信输入框全 4000 |
| 9 | DB 索引覆盖度 | ⚠️ 19d4199 | `chat_messages` / `notifications` 复合索引已补 |
| 10 | 未读数一致性 | ✅ | `ChatMessageRepository.count_unread` + 聊天自动已读 8ac82ab |
| 11 | 软删消息排除 | ✅ | 无软删字段；`ChatMessage` 为硬存储（当前 MVP 决策） |
| 12 | 订单状态通知覆盖度 | ⚠️ 8ac82ab | 标签映射覆盖全部 OrderStatus |
| 13 | 通知模板字段 | ✅ | `NotificationService` + 前端 `utils/notification-label.js` 对齐 |
| 14 | 断线兜底 REST 拉未读 | ✅ | `services/notification.js` + 页面 onShow 触发 |
| 15 | 已读跨设备同步 | 📝 | TD-MSG-03（P3） |
| 16 | 推送与业务解耦 | ✅ | `push_notification_to_user` 独立入口，业务写库后调用 |
| 17 | 日志 PII 脱敏 | ⚠️ 1028e9d | `mask_phone` / `mask_id_card` 已加 |
| 18 | 前端消息 UI 完整度 | ✅ | 消息列表/详情/chat room/全局角标联动 |
| 19 | iOS 消息实现 | 📝 | TD-MSG-06（P2，iOS 侧；本周不改 iOS） |
| 20 | 微信订阅消息/模板消息 | 📝 | TD-MSG-08（P2，未接入；纯 WS MVP） |

本次审计未触发 🔴 新增代码修复（P2/P3 结构化收尾见本日 commit 清单）；文档化为主，功能修复已在本日前序 commit 完成。

---

## 1. WS 认证（notifications + chat）— ✅ 无问题

- 证据：
  - `backend/app/api/v1/ws.py:76-94`（notifications）：读取 `?token=` → `decode_token` → 校验 `type==access` → 校验 `sub` 为合法 UUID → 任一失败即 `close(4001)`。
  - `backend/app/api/v1/ws.py:118-140`（chat）：相同流程 + 额外校验订单参与者（`patient_id` / `companion_id`），不是参与者 `close(4003)`；订单不存在 `close(4004)`。
- 结论：认证链完整、分层（token → 用户 → 资源权限），错误码语义清晰。

## 2. WS 连接清理（无泄漏）— ✅ 无问题

- 证据：两个 endpoint 均使用 `try … finally: await broker.unregister(key, websocket)`（`ws.py:103-115` / `ws.py:179-183`）。
- `WsPubSubBroker.unregister`（`backend/app/ws/pubsub.py:171-177`）：从 `_local[key]` list 中按 `is` 精确剔除，空 list 清理。
- `WebSocketDisconnect` 与通用 `Exception` 均走 finally，极端异常下也不泄漏。

## 3. 多设备登录行为 — ✅ 无问题

- `_local: dict[str, list[WebSocket]]` 结构天然支持同一 user_id 多连接。
- `push_to_key` 遍历 list 全量投递 → 多设备都收到。
- 风险（本次任务 5 治理）：无上限会被恶意/异常客户端堆积。本次加入 `WS_MAX_CONNECTIONS_PER_USER=3`，超限踢最旧。

## 4. Pub/Sub 重复推送抑制 — ✅ 无问题

- 证据：`backend/app/ws/pubsub.py` 发布时挂 `origin=self.instance_id`；`_listen_loop` 收到消息若 `origin == instance_id` 直接 skip。
- 测试：`backend/tests/test_ws_pubsub.py::test_broker_suppresses_self_echo`、`test_broker_cross_instance_fanout`。

## 5. 消息幂等性 — 📝 技术债（TD-MSG-01，P3）

- 结论：当前 WS 发送无 `client_nonce`；网络抖动下客户端重发会落两条。
- 评估：MVP 聊天体量小，重复率低；方案 `SETNX nonce:{id} EX 60` 已在 TECH_DEBT 落档。

## 6. 消息时序 — 📝 技术债（TD-MSG-02，P2）

- 结论：WS 中断期间，客户端靠 `loadHistory` 全量刷新，存在 diff 复杂度。
- 建议方案：REST `getChatMessages({ after: lastKnownId })` 增量拉取。已登记 TD-MSG-02。

## 7. 心跳超时阀值 — ⚠️部分 + 📝 TD-MSG-04

- 现状：
  - 前端 `wechat/services/notificationWs.js` 每 30s 发 `ping`，无连续丢失计数。
  - 后端 `ws.py` 无显式 `asyncio.wait_for` idle timeout；依赖 `WebSocketDisconnect` + 上层反代 / uvicorn `ws_ping_interval`。
- 评估：MVP 可接受（用户量小 + 前端主动心跳）；用户量增长后建议添加 `receive_text(timeout=90s)` 服务端超时，已 TD-MSG-04。

## 8. 大消息体限制（前后端一致）— ⚠️ 已修复（commit f76406f）

- REST `schemas/chat.py` ChatMessageCreate: `content` ≤ 4000。
- WS `backend/app/api/v1/ws.py:163-167`：服务端 hard cap 4000，超长截断。
- 微信输入框 `wechat/pages/chat/room/index.wxml` `maxlength="4000"`；与后端对齐。
- 验证：`backend/tests/test_ws_chat.py` / REST chat 测试已覆盖边界。

## 9. DB 索引覆盖度 — ⚠️ 已修复（commit 19d4199）

- `chat_messages (order_id, created_at)` 、 `notifications (user_id, is_read, created_at)` 等覆盖高频查询。
- Alembic 迁移：`backend/alembic/versions/xxx_add_msg_indexes.py`。
- 评估：常见热点（未读统计、订单消息分页）都走索引。

## 10. 未读数一致性 — ✅ 无问题

- `ChatMessageRepository.count_unread(order_id, user_id)` 与 WS push 后端一致源。
- 聊天页自动已读（commit 8ac82ab）：用户打开聊天 → `mark_read`，不会出现开完仍计未读的脑裂。

## 11. 软删消息排除 — ✅ 无问题（MVP 决策）

- 当前 `chat_messages` 无 `deleted_at`，为硬存储。产品层未提收回 / 管员删除消息需求。
- 若后续添加，需在 repo `list_by_order`、`count_unread` 加 `deleted_at IS NULL`，本次不在范围。

## 12. 订单状态通知覆盖度 — ⚠️ 已修复（commit 8ac82ab）

- `wechat/utils/notification-label.js` 添加全部 `OrderStatus` 映射（created / accepted / in_progress / completed / reviewed / expired / rejected_by_companion / cancelled_* / paid / refunded）。
- 后端 `NotificationService` 在关键状态转变均有 `create_notification` 调用（看 `backend/app/services/notification.py`）。

## 13. 通知模板字段 — ✅ 无问题

- `schemas/notification.py::NotificationOut`：`id / type / title / body / order_id / created_at / is_read`。
- 前端 `services/notification.js` 与 `pages/notification/*` 均按此字段渲染，无缺失。

## 14. 断线兜底 REST 拉未读 — ✅ 无问题

- `GET /notifications?unread_only=true` + `GET /chats/{order_id}/messages` 均可用于重连后 fallback。
- 客户端：页面 `onShow` 触发 → 统计未读重建。

## 15. 已读跨设备同步 — 📝 技术债（TD-MSG-03，P3）

- 现状：设备 A 已读，设备 B 不会实时收到 read　receipt；下次刷新归一（基于 DB is_read）。
- 改进方案：Pub/Sub 广播 `{type:"read_receipt"}` 到同用户其他 WS。已登记。

## 16. 推送与业务解耦 — ✅ 无问题

- 模块边界：
  - `NotificationService.create_notification(...)` → 写 DB
  - `push_notification_to_user(app, user_id, payload)` → WS broker（低延迟）
  - `broker.publish_to_room(...)` → 聊天广播
- 业务层（OrderService 等）只关心“谁该收到什么”，不感知传输。

## 17. 日志 PII 脱敏 — ⚠️ 已修复（commit 1028e9d）

- `backend/app/utils/log_sanitizer.py::mask_phone / mask_id_card`
- 接入点：手机验证码下发 / 操作审计日志 / 点对点通知 body。
- 测试：`tests/test_log_sanitizer.py`。
- 注：业务 `chat_message.content` 不脱敏（用户自申文字，脱敏破坏语义）；若后续需要，应在 log 级别过滤而非第一类脱敏。

## 18. 前端消息 UI 完整度 — ✅ 无问题

- 消息列表：`wechat/pages/notification/list/index.*`
- 消息详情：`wechat/pages/notification/detail/index.*`
- 聊天房：`wechat/pages/chat/room/index.*` — 含自动已读、倒序预载、断线重连。
- 全局角标：`wechat/app.js::_dispatchNotification`（本次任务 3 扩展到 TabBar）。

## 19. iOS 消息实现 — 📝 技术债（TD-MSG-06，P2）

- 本次不改 iOS；`WebSocketClient.reconnect()` 目前为 sleep 占位，`ChatViewModel` 需观察 `isConnected` 手动重连。在 iOS sprint 补。

## 20. 微信订阅消息 / 模板消息 — 📝 技术债（TD-MSG-08，P2）

- 当前MVP 纯 WebSocket + 开启的 app 内通知；关窗后不能唤醒。
- 方案：关键节点接入 `wx.requestSubscribeMessage` 申请，服务端 `subscribeMessage.send` 推送；需产品立项准备模板 ID / 现场申请 UX。

---

## 附录：本次（D-017~D-019 收尾）单日 commit 序列

| commit | 主题 |
|---|---|
| 19d4199 | 消息链路数据库索引补齐（B-审计修复） |
| 1028e9d | 日志 PII 脱敏（手机号 / 身份证） |
| 8ac82ab | 聊天页自动已读 + 订单状态标签覆盖全部 OrderStatus |
| 177cef4 | TECH_DEBT.md 登记消息链路审计遗留轻微项 |
| f76406f | REST/WS 消息上限对齐 4000 + 微信输入框 maxlength |
| （本次文档/任务 1-6 commit） | 见 《本日任务 P2/P3 收尾》 commit 列表 |

## 遗留（已登记，非阻塞）

TD-MSG-01 幂等 / TD-MSG-02 时序 / TD-MSG-03 已读跨设备 / TD-MSG-04 idle timeout / TD-MSG-05 cursor 分页 / TD-MSG-06 iOS 重连 / TD-MSG-07 大文本分块 / TD-MSG-08 订阅消息。
