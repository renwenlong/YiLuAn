# 运营后台 - 通用（admin）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

运营后台对订单、用户的管理操作（查询、强制状态、退款、停用/启用账号）。

## 鉴权要求

要求 `Authorization: Bearer <access_token>`，**且当前用户具备 `admin` 角色**（401 / 403 拦截）。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/companions/` | 后台：待审核陪诊师列表 |
| `POST` | `/api/v1/admin/companions/{companion_id}/approve` | 后台：批准陪诊师入驻 |
| `POST` | `/api/v1/admin/companions/{companion_id}/certify` | 管理员：设置陪诊师资质认证（F-01） |
| `POST` | `/api/v1/admin/companions/{companion_id}/reject` | 后台：驳回陪诊师申请 |
| `GET` | `/api/v1/admin/orders` | 后台：查询全部订单 |
| `POST` | `/api/v1/admin/orders/{order_id}/admin-refund` | 后台：管理员退款 |
| `POST` | `/api/v1/admin/orders/{order_id}/force-status` | 后台：强制修改订单状态 |
| `GET` | `/api/v1/admin/users` | 后台：用户列表 |
| `POST` | `/api/v1/admin/users/{user_id}/disable` | 后台：停用用户 |
| `POST` | `/api/v1/admin/users/{user_id}/enable` | 后台：启用用户 |

## 端点详情

### `GET /api/v1/admin/companions/` — 后台：待审核陪诊师列表

分页返回提交了入驻申请、状态为 `pending` 的陪诊师。请求头需携带 `X-Admin-Token`。

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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/approve` — 后台：批准陪诊师入驻

批准指定陪诊师，状态转为 `verified`，该陪诊师随即可被搜索与接单。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/approve' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/certify` — 管理员：设置陪诊师资质认证（F-01）

设置认证类型/证书编号/证书图片并戳记 certified_at；写入 admin_audit_log。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/certify' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/reject` — 后台：驳回陪诊师申请

驳回指定陪诊师的入驻申请并写入原因（1~500 字）。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/reject' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/orders` — 后台：查询全部订单

管理员查看所有订单列表，可按 `status` 过滤。仅 `admin` 角色可调用。

**参数：**

- `status` (query, —, required=—) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/orders' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/orders/{order_id}/admin-refund` — 后台：管理员退款

以 `refund_ratio`（0~1）按订单金额按比例退款，1.0 表示全额退。

**参数：**

- `order_id` (path, string, required=✅) — 
- `refund_ratio` (query, number, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/orders/{order_id}/admin-refund' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/orders/{order_id}/force-status` — 后台：强制修改订单状态

管理员手动将订单跳转到指定状态，**仅用于运营干预**，不走业务状态机。

**参数：**

- `order_id` (path, string, required=✅) — 
- `target_status` (query, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/orders/{order_id}/force-status' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/users` — 后台：用户列表

分页查看所有用户（含已停用）。

**参数：**

- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/users' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/disable` — 后台：停用用户

将指定用户账号设为 `is_active=False`，用于风控处置。

**参数：**

- `user_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/disable' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/enable` — 后台：启用用户

重新启用被停用的账号。

**参数：**

- `user_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/enable' \
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
