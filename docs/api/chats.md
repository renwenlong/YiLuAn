# 订单聊天（chats）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

订单参与方在订单生命周期内进行实时沟通。

- 实时收发使用 `WS /api/v1/ws/chat/{order_id}?token=<jwt>`
- HTTP 接口用于历史拉取、HTTP 兜底发送、批量已读

## 鉴权要求

全部接口要求登录，且当前用户必须是订单参与方（患者或接单陪诊师）。

## 限流

WS 单条消息正文上限 4000 字符，HTTP 与之保持一致。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/chats/{order_id}/messages` | 获取订单聊天历史 |
| `POST` | `/api/v1/chats/{order_id}/messages` | 发送一条聊天消息（HTTP 兜底） |
| `GET` | `/api/v1/chats/{order_id}/messages/backfill` | WS 重连后增量回灌聊天消息 |
| `POST` | `/api/v1/chats/{order_id}/read` | 批量标记订单消息为已读 |

## 端点详情

### `GET /api/v1/chats/{order_id}/messages` — 获取订单聊天历史

分页查询指定订单的聊天消息记录。仅订单参与方（患者 / 陪诊师）可访问。

两种分页模式：
- 默认 ``page``/``page_size`` 按页起始全量拉取（升序）。
- 传 ``before_id`` + ``limit`` 则进入上拉历史游标模式，返回严格早于该游标的最近 ``limit`` 条（依然升序返回，客户端可直接预添加到列表顶部）。

实时双向通信请使用 `WS /api/v1/ws/chat/{order_id}?token=<jwt>`。

**参数：**

- `order_id` (path, string, required=✅) — 
- `page` (query, integer, required=—) — 页码（从 1 开始）
- `page_size` (query, integer, required=—) — 每页条数 1~100
- `before_id` (query, —, required=—) — 上拉历史游标：当前本地最早一条消息 ID。传入后 ``page``/``page_size`` 被忽略。
- `limit` (query, integer, required=—) — 游标模式下单页条数（仅在 ``before_id`` 传入时生效）

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/chats/{order_id}/messages' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/chats/{order_id}/messages` — 发送一条聊天消息（HTTP 兜底）

在指定订单的聊天会话中发送一条消息。推荐通过 WebSocket 发送以获得实时性，HTTP 接口主要作为离线 / 弱网兜底。

**参数：**

- `order_id` (path, string, required=✅) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/chats/{order_id}/messages' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/chats/{order_id}/messages/backfill` — WS 重连后增量回灌聊天消息

基于游标的增量回灌接口，配合 WebSocket 重连场景使用。

- ``after_id`` 为客户端本地最后一条消息 ID；缺省时返回最早 ``limit`` 条。
- 返回顺序严格 ``(created_at ASC, id ASC)``，与 WS 推送顺序一致。
- ``after_id`` 不属于该订单或已被清理时，等价于全量回灌（不报 404）。
- ``limit`` 由服务端硬上限 200。

**参数：**

- `order_id` (path, string, required=✅) — 
- `after_id` (query, —, required=—) — 上次最后一条消息 ID；为空则从头开始
- `limit` (query, integer, required=—) — 单次最多返回条数 1~200

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/chats/{order_id}/messages/backfill' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/chats/{order_id}/read` — 批量标记订单消息为已读

将当前用户在该订单聊天中的全部未读消息标记为已读，返回标记数量。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 标记成功 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/chats/{order_id}/read' \
  -H 'Authorization: Bearer <access_token>'
```

---

## 错误码对照

通用错误码请见 [ERROR_HANDLING.md](./ERROR_HANDLING.md)。本模块在通用错误码之上的特殊语义：

- `400 Bad Request`：业务规则不满足（如订单状态不允许该操作）。
- `401 Unauthorized`：未登录或令牌过期。
- `403 Forbidden`：已登录但无权访问该资源。
- `404 Not Found`：资源不存在。
- `422 Unprocessable Entity`：请求体字段校验失败（FastAPI 标准格式）。
- `429 Too Many Requests`：触发限流。
