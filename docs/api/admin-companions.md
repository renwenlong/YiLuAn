# 运营后台 - 陪诊师审核（admin-companions）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

审核员审核陪诊师入驻申请：列表 / 批准 / 驳回（带原因）。

## 鉴权要求

**鉴权方式与其他接口不同**：请求头 `X-Admin-Token: <token>`，不使用 JWT。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/companions/` | 后台：待审核陪诊师列表 |
| `GET` | `/api/v1/admin/companions/search` | 后台：陪诊师轻量搜索（钱包账本筛选用） |
| `GET` | `/api/v1/admin/companions/{companion_id}` | 后台：陪诊师审核详情 |
| `POST` | `/api/v1/admin/companions/{companion_id}/approve` | 后台：批准陪诊师入驻 |
| `POST` | `/api/v1/admin/companions/{companion_id}/certify` | 管理员：设置陪诊师资质认证（F-01） |
| `POST` | `/api/v1/admin/companions/{companion_id}/reject` | 后台：驳回陪诊师申请 |

## 端点详情

### `GET /api/v1/admin/companions/` — 后台：待审核陪诊师列表

分页返回提交了入驻申请、状态为 `pending` 的陪诊师。请求头需携带 `X-Admin-Token`。

**参数：**

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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/companions/search` — 后台：陪诊师轻量搜索（钱包账本筛选用）

按姓名或手机号模糊搜索陪诊师，返回 user_id + 姓名 + 手机号尾 4 位。默认仅返回 `verified` 状态；传 `status=all` 取消该过滤。

**参数：**

- `q` (query, —, required=—) — 姓名或手机号关键字
- `status` (query, string, required=—) — verified | all
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/search' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/companions/{companion_id}` — 后台：陪诊师审核详情

返回单个陪诊师 14 字段审核视图。⚠️ `certification_image_signed_url` 在 PR-E1 为占位 `None`，实安全包装留 PR-E2（storage 后端调研 + ADR-0044 r1 amend）。reveal phone 走独立端点 `GET /admin/users/{user_id}?reveal=true`。 写入 view_companion_detail 审计。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/approve` — 后台：批准陪诊师入驻

批准指定陪诊师，状态转为 `verified`，该陪诊师随即可被搜索与接单。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/certify' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/reject` — 后台：驳回陪诊师申请

驳回指定陪诊师的入驻申请并写入原因（1~500 字）。

**参数：**

- `companion_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/reject' \
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
