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
| `POST` | `/api/v1/chats/{order_id}/read` | 批量标记订单消息为已读 |

## 端点详情

### `GET /api/v1/chats/{order_id}/messages` — 获取订单聊天历史

分页查询指定订单的聊天消息记录。仅订单参与方（患者 / 陪诊师）可访问。

实时双向通信请使用 `WS /api/v1/ws/chat/{order_id}?token=<jwt>`。

**参数：**

- `order_id` (path, string, required=✅) — 
- `page` (query, integer, required=—) — 页码（从 1 开始）
- `page_size` (query, integer, required=—) — 每页条数 1~100

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
