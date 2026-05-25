# admin-telemetry

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/telemetry/events` | 埋点事件列表（admin） |

## 端点详情

### `GET /api/v1/admin/telemetry/events` — 埋点事件列表（admin）

分页查询 `telemetry_events`。支持按 event_type 精确匹配、时间区间、user_id 过滤。默认按 created_at 倒序。

**参数：**

- `event_type` (query, —, required=—) — 精确匹配 event_type
- `user_id` (query, —, required=—) — 按上报用户过滤
- `since` (query, —, required=—) — created_at >= since
- `until` (query, —, required=—) — created_at < until
- `limit` (query, integer, required=—) — 
- `offset` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/telemetry/events' \
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
