# admin-service-packages

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/service-packages/` | 后台：服务档位列表 |
| `POST` | `/api/v1/admin/service-packages/` | 后台：新建服务档位 |
| `DELETE` | `/api/v1/admin/service-packages/{pkg_id}` | 后台：软删服务档位 |
| `GET` | `/api/v1/admin/service-packages/{pkg_id}` | 后台：服务档位详情 |
| `PATCH` | `/api/v1/admin/service-packages/{pkg_id}` | 后台：更新服务档位 |

## 端点详情

### `GET /api/v1/admin/service-packages/` — 后台：服务档位列表

默认仅返回 is_active=true。?include_inactive=true 拉全部（含软删）。按 sort_order 升序。

**参数：**

- `include_inactive` (query, boolean, required=—) — 为 true 时返回 is_active=false 的软删项
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/service-packages/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/service-packages/` — 后台：新建服务档位

code 全局唯一；price 必须 > 0；写 admin_audit_log create + before/after diff。

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
| `201` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/service-packages/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/admin/service-packages/{pkg_id}` — 后台：软删服务档位

软删（is_active=false）。**不真删**，避免历史 Order.service_type 引用断裂（ADR-0043 §2.2 弱外键策略）。写 admin_audit_log soft_delete。

**参数：**

- `pkg_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/admin/service-packages/{pkg_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/service-packages/{pkg_id}` — 后台：服务档位详情

返回单个服务档位全部字段 (code/name/price/is_active/sort_order/description/created_at/updated_at)。未找到 404。该端点不过滤 is_active，admin 可查软删项用于恢复场景。

**参数：**

- `pkg_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/service-packages/{pkg_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PATCH /api/v1/admin/service-packages/{pkg_id}` — 后台：更新服务档位

部分更新 name/price/is_active/sort_order/description；code 不可改（避免历史 Order.service_type 引用断裂）。写 admin_audit_log update + before/after diff。

**参数：**

- `pkg_id` (path, string, required=✅) — 
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
curl -X PATCH 'https://api.yiluan.example.com/api/v1/admin/service-packages/{pkg_id}' \
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
