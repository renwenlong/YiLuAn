# 站内通知（notifications）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

站内通知列表、未读数、标记已读、设备推送 token 注册/注销。推送通过 APNs / FCM / 微信订阅消息分发。

## 鉴权要求

全部接口要求登录。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/notifications` | 分页获取站内通知 |
| `DELETE` | `/api/v1/notifications/device-token` | 注销设备推送 token |
| `POST` | `/api/v1/notifications/device-token` | 注册设备推送 token |
| `POST` | `/api/v1/notifications/read-all` | 一键全部已读 |
| `GET` | `/api/v1/notifications/unread-count` | 未读通知数 |
| `POST` | `/api/v1/notifications/{notification_id}/read` | 标记单条通知已读（含深链 target） |

## 端点详情

### `GET /api/v1/notifications` — 分页获取站内通知

返回当前用户的站内通知，按时间倒序分页。

**参数：**

- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/notifications' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/notifications/device-token` — 注销设备推送 token

登出或换设备时调用，移除推送 token。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/notifications/device-token' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/notifications/device-token` — 注册设备推送 token

上报设备推送 token，用于服务端通过 APNs / FCM / 微信订阅消息推送。同一个 (user, token) 重复注册将复用现有记录。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/notifications/device-token' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/notifications/read-all` — 一键全部已读

将当前用户的所有未读通知一次性标记为已读，返回标记数量。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/notifications/read-all' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/notifications/unread-count` — 未读通知数

返回当前用户未读通知的总数，用于 App 角标显示。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/notifications/unread-count' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/notifications/{notification_id}/read` — 标记单条通知已读（含深链 target）

将指定通知标记为已读，并返回最新的通知（含 `target_type` / `target_id`），前端可据此立刻跳转到对应详情页。

**参数：**

- `notification_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 操作结果 |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/notifications/{notification_id}/read' \
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
