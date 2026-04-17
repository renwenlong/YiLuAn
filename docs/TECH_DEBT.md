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
