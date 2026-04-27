# ADR-0031 — WebSocket 双模块统一：ChatService + WSBase + idle timeout + nonce 幂等

- **状态**：✅ Accepted（2026-04-27）
- **关联**：C-12 / TD-MSG-04 / TD-MSG-01
- **作者**：YiLuAn 后端 + 前端联合
- **PR**：feat/c12-ws-dedup → main

## Context

历史上 WebSocket 链路有三处独立演化产生的债务：

1. **后端 ws.py 绕过 service 层**：`backend/app/api/v1/ws.py`（8.5KB）的
   `/ws/chat/{order_id}` handler 直接 `ChatMessage(...)`、`db.commit`、再
   推 broker。`backend/app/services/chat.py` 里已存在 `ChatService` 且被
   HTTP `/chats/...` 用到，但 WS 路径没用，权限校验、内容裁剪、消息构造
   等逻辑双轨。
2. **微信端 95% 代码重复**：`wechat/services/websocket.js` 与
   `wechat/services/notificationWs.js` 各自实现 `connect / reconnect /
   _startHeartbeat / _stopHeartbeat`，差异只在 URL / 回调名。
3. **僵尸连接**：后端 WS 没有 idle timeout，TCP keepalive 失败的连接会
   留在 `_local` dict 直到下次 send 才出错（TD-MSG-04）。
4. **聊天消息幂等**：客户端网络抖动 / 双击 / 重连重发可能让同一条消息被
   多次落库（TD-MSG-01）。

## Decision

**统一走 ChatService + 抽 WSBase + 90s server-side idle timeout +
端到端 nonce 幂等**。

### 后端

- `ChatService` 新增 `send_message_via_ws(order_id, sender_id, content,
  msg_type, *, nonce, redis)`：参与方校验 + 内容 trim + nonce dedup +
  落库 + 返回 `(message, broadcast_payload, is_duplicate)`。
- `app/api/v1/ws.py` 完全去 Model 化：handler 只做 JWT/参与方预检 +
  asyncio idle timeout + 调 ChatService + 把 payload 交给 broker。
- 新增 metric `ws_idle_timeout_total{channel}`，已挂 `/metrics`。
- nonce 用 Redis `SET key val NX EX 300`，key
  `chat:nonce:{user_id}:{nonce}`，5 分钟窗口内重复 → 不落库不广播。
- 不破坏 frame 契约：上行 `{type, content, nonce?}`、下行
  `{id, order_id, sender_id, type, content, is_read, created_at, nonce?}`。

### 前端（小程序）

- 新增 `wechat/core/ws-base.js`：`WSBase` 类封装 connect / reconnect
  （指数退避 1/2/5/10/30s）/ heartbeat（30s PING）/ send（默认自动
  注入 16 字符 nonce + 5 分钟 LRU dedup）/ on(event,
  handler) 钩子。可注入 `socketFactory / setTimeout / setInterval`
  以便单测。
- `services/websocket.js` 与 `services/notificationWs.js` 改造为薄壳：
  内部委托给同一个 WSBase 实例，对外 export 形态完全保持向后兼容
  （`connect / send / onMessage / disconnect` 与 `connect / disconnect`
  签名不变）。

### Idempotency 双侧布防

- **客户端**：WSBase send 时本地 `Map<nonce, expiresAt>`，TTL = 5min；
  GC 在每次 send 时按插入序提前退出。
- **服务端**：ChatService Redis SETNX，TTL = 5min，命中即丢；命中时
  返回 `(None, {}, True)`，handler 跳过 broadcast。
- 客户端短路最先生效，避免无谓的网络往返；服务端兜底防恶意客户端 / 跨设备
  重发。

## Alternatives considered

1. **保留双轨（仅修 timeout + nonce）** —
   被否决：双套连接/心跳逻辑长期维护成本高，TD-MSG-* 一直在堆。
2. **引入 socket.io 客户端** —
   被否决：微信小程序 `wx.connectSocket` 与 socket.io 协议不兼容，
   引入会强行带入 polling fallback 与较大体积；当前规模不需要 namespace /
   room 的高阶抽象。
3. **后端用 uvicorn `ws_ping_interval`** —
   被否决：uvicorn ping 失败的可见性较差（不会触发我们 service 层的
   `unregister`）；显式 `asyncio.wait_for` 加 metric 更可观测。

## Consequences

**正向**

- ws.py 单文件减重 ~10%，所有写路径只剩 `send_message` / `send_message_via_ws`
  两个入口。
- 微信端 WS 相关代码重复从 ~95% 降到 0；新增 WS 通道（如未来运营广播）
  只需 `new WSBase()`。
- `ws_idle_timeout_total` 直接接入现有 Prometheus 看板。
- TD-MSG-01 / TD-MSG-04 / C-12 一次性收口。

**风险 / 注意事项**

- 迁移期内两侧 frame 格式必须严格匹配；上行只新增 `nonce` 字段（向后兼容），
  下行 broadcast 也只新增 `nonce` 透传字段，老前端仍可解析。
- 每条消息会多 1 次 Redis SETNX；按当前 QPS（< 50/s 聊天峰值）可忽略，
  但 Prometheus `redis_command_total` 会有可见涨幅。
- `WS_IDLE_TIMEOUT_SECONDS=90` 是常量；如未来需要按租户调，应迁到
  settings 而非环境变量直读。

## Rollout

- 单 PR 合并；6 个原子 commit 便于二分定位。
- CI 必须绿（pytest 921 / jest 247）才允许 auto-merge。
- 灰度可通过把 `chat:nonce:*` 的 TTL 临时调短验证 nonce 行为。

## Verification

- 后端：`pytest -q` 921 passed / 15 skipped（基线 914 / 15）。新增
  `tests/test_ws_chat_service.py` 7 用例覆盖 service-level / nonce dedup /
  unauthorised / 双通道 idle timeout。
- 前端：`npx jest` 247 passed（基线 235）。新增
  `__tests__/core/ws-base.test.js` 8 用例 + `__tests__/services/
  websocket-thinwrapper.test.js` 4 用例覆盖 backoff ladder、heartbeat、
  nonce auto-inject、pong swallow、向后兼容 export。
