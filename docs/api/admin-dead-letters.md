# admin-dead-letters

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/dead-letters` | 后台：死信队列表 |
| `GET` | `/api/v1/admin/dead-letters/{dl_id}` | 后台：死信详情 |
| `POST` | `/api/v1/admin/dead-letters/{dl_id}/resolve` | 后台：标记死信已解决 |

## 端点详情

### `GET /api/v1/admin/dead-letters` — 后台：死信队列表

查询需人工补偿的遗留任务，默认按时间倒序。

**参数：**

- `status` (query, —, required=—) — pending / resolved
- `channel` (query, —, required=—) — 例：order_refund
- `target_id` (query, —, required=—) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/dead-letters' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/dead-letters/{dl_id}` — 后台：死信详情

返回指定 dead_letter 行的全部字段（含 payload 与解决态）。

**参数：**

- `dl_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/dead-letters/{dl_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/dead-letters/{dl_id}/resolve` — 后台：标记死信已解决

记录解决人、说明、时间；同时写入 admin_audit_logs。

**参数：**

- `dl_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/dead-letters/{dl_id}/resolve' \
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
