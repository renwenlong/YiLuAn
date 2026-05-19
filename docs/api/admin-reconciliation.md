# admin-reconciliation

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/reconciliation/diffs` | List Diffs |
| `GET` | `/api/v1/admin/reconciliation/diffs/{diff_id}` | 后台：差异详情 |
| `POST` | `/api/v1/admin/reconciliation/diffs/{diff_id}/close-confirms` | Confirm Close |
| `POST` | `/api/v1/admin/reconciliation/diffs/{diff_id}/close-requests` | Request Close |
| `GET` | `/api/v1/admin/reconciliation/runs` | 后台：对账 run 列表 |

## 端点详情

### `GET /api/v1/admin/reconciliation/diffs` — List Diffs

List reconciliation diffs with filters; newest first.

**参数：**

- `status` (query, —, required=—) — 
- `kind` (query, —, required=—) — 
- `provider` (query, —, required=—) — 
- `order_id` (query, —, required=—) — 
- `run_id` (query, —, required=—) — 
- `date_from` (query, —, required=—) — 
- `date_to` (query, —, required=—) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/reconciliation/diffs/{diff_id}` — 后台：差异详情

返回指定 reconciliation diff 详情 + 全部动作记录（按 created_at 升序）。

**参数：**

- `diff_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs/{diff_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/reconciliation/diffs/{diff_id}/close-confirms` — Confirm Close

Second signature. Must be performed by a *different* operator than
the one who filed the pending request. Flips the diff to ``closed``.

**参数：**

- `diff_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 
- `X-Admin-Operator` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs/{diff_id}/close-confirms' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/reconciliation/diffs/{diff_id}/close-requests` — Request Close

First signature. Records a ``manual_close`` action with outcome
``pending_second_sign``. Diff stays in its current status.

**参数：**

- `diff_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 
- `X-Admin-Operator` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs/{diff_id}/close-requests' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/reconciliation/runs` — 后台：对账 run 列表

按 started_at 倒序分页返回对账批次（run）列表，供审计查看历史对账状态。

**参数：**

- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/reconciliation/runs' \
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
