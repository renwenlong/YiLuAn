# admin-notes

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/notes` | 后台：按 target 列出备注 |
| `POST` | `/api/v1/admin/notes` | 后台：新增备注 |
| `DELETE` | `/api/v1/admin/notes/{note_id}` | 后台：删除备注（仅作者） |
| `PATCH` | `/api/v1/admin/notes/{note_id}` | 后台：编辑备注（仅作者） |

## 端点详情

### `GET /api/v1/admin/notes` — 后台：按 target 列出备注

按 (target_type, target_id) 列出后台备注，限 100到500 条，创建时间倒序。

**参数：**

- `target_type` (query, string, required=✅) — 
- `target_id` (query, string, required=✅) — 
- `limit` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/notes' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/notes` — 后台：新增备注

为指定 target (order/user/companion) 创建一条后台备注，同时写入审计日志。

**参数：**

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/notes' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/admin/notes/{note_id}` — 后台：删除备注（仅作者）

仅原作者可删除备注；delete 动作同步记录审计日志。

**参数：**

- `note_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/admin/notes/{note_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PATCH /api/v1/admin/notes/{note_id}` — 后台：编辑备注（仅作者）

仅原作者可修改备注内容；edit 记录会进入审计日志。

**参数：**

- `note_id` (path, string, required=✅) — 
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
curl -X PATCH 'https://api.yiluan.example.com/api/v1/admin/notes/{note_id}' \
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
