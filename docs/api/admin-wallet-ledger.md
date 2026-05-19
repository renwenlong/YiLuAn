# admin-wallet-ledger

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/admin/wallet-ledger/adjustments` | Create Manual Adjustment |
| `GET` | `/api/v1/admin/wallet-ledger/{user_id}` | List User Ledger |

## 端点详情

### `POST /api/v1/admin/wallet-ledger/adjustments` — Create Manual Adjustment

人工记一笔调账。强制 ``X-Admin-Operator``；落 admin_audit_log + ledger。

**参数：**

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/wallet-ledger/adjustments' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/wallet-ledger/{user_id}` — List User Ledger

诊断用：查看某 user 的账本流水。

**参数：**

- `user_id` (path, string, required=✅) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `reason` (query, —, required=—) — 
- `companion_id` (query, —, required=—) — 可选，仅接受与路径 user_id 一致的陪诊师 user_id；用于后台 H5 从陪诊师选择器传入。不一致返回 422。
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/wallet-ledger/{user_id}' \
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
