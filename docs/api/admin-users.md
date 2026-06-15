# admin-users

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/users` | 后台：用户列表 |
| `POST` | `/api/v1/admin/users/batch-read-only` | 后台：批量设置/解除只读 (≤100) |
| `GET` | `/api/v1/admin/users/{user_id}` | 后台：用户详情 |
| `POST` | `/api/v1/admin/users/{user_id}/disable` | 后台：停用用户 |
| `POST` | `/api/v1/admin/users/{user_id}/enable` | 后台：启用用户 |
| `DELETE` | `/api/v1/admin/users/{user_id}/read-only` | 后台：解除用户只读 (unset read-only) |
| `POST` | `/api/v1/admin/users/{user_id}/read-only` | 后台：将用户置为只读 (read-only) |

## 端点详情

### `GET /api/v1/admin/users` — 后台：用户列表

分页查询用户，支持按 role / is_active / phone 模糊过滤。

**参数：**

- `role` (query, —, required=—) — 角色 tag，如 patient / companion / admin
- `is_active` (query, —, required=—) — 
- `phone` (query, —, required=—) — 手机号模糊匹配
- `reveal` (query, boolean, required=—) — 是否返回明文手机号；置 true 会写入 reveal_pii 审计日志。
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/users' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/batch-read-only` — 后台：批量设置/解除只读 (≤100)

ADR-0053 §7 批量上限 100。每个 user_id 独立成功/失败, 单 user 404 不阻整批; 全批同一事务 commit (要么 100 个 audit + 100 个 user 行 update 同时落, 要么全回滚)。批 >100 → 422 BATCH_TOO_LARGE。

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/batch-read-only' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/users/{user_id}` — 后台：用户详情

返回单个用户详情；phone 默认脱敏，?reveal=true 返回明文并写 reveal_pii 审计；同时写入 view_user_detail 审计行。

**参数：**

- `user_id` (path, string, required=✅) — 
- `reveal` (query, boolean, required=—) — 是否返回明文手机号；置 true 会写入 reveal_pii 审计日志。
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/disable` — 后台：停用用户

将指定用户置为 is_active=False。操作必须给出原因，写入 admin_audit_log。

**参数：**

- `user_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/disable' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/enable` — 后台：启用用户

重新启用被停用账号；操作写入 admin_audit_log。

**参数：**

- `user_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

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

### `DELETE /api/v1/admin/users/{user_id}/read-only` — 后台：解除用户只读 (unset read-only)

ADR-0053 §7. 清除 is_read_only + 4 列元数据，复用 PR #238 同事务 AdminAuditLog 路径。

**参数：**

- `user_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/read-only' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/read-only` — 后台：将用户置为只读 (read-only)

ADR-0053 §7. 复用 PR #238 同事务 AdminAuditLog 路径 — 成功 200 时写 audit; 失败 404/422 因事务回滚不留 audit。reason_detail 仅 audit 留存, response 永远不返 (PRD-001 §F8 D1)。

**参数：**

- `user_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/read-only' \
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
