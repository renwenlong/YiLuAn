# 陪诊师档案（companions）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

陪诊师入驻、资料维护、列表搜索、详情查看、个人统计。

陪诊师身份生命周期：用户调用 `POST /companions/apply` → `pending` → 后台审核 → `verified` 即可接单。

## 鉴权要求

全部接口要求登录。`PUT /companions/me` 与 `/companions/me/stats` 还要求当前账号已开通陪诊师角色。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/companions` | 搜索陪诊师列表 |
| `POST` | `/api/v1/companions/apply` | 申请成为陪诊师 |
| `GET` | `/api/v1/companions/me` | 获取我的陪诊师档案 |
| `PUT` | `/api/v1/companions/me` | 更新我的陪诊师档案 |
| `GET` | `/api/v1/companions/me/stats` | 获取陪诊师统计概览 |
| `GET` | `/api/v1/companions/{companion_id}` | 查看陪诊师详情 |

## 端点详情

### `GET /api/v1/companions` — 搜索陪诊师列表

按区域、城市、服务类型、医院筛选可接单的陪诊师，分页返回。

**参数：**

- `area` (query, —, required=—) — 服务区域关键字，如『朝阳区』
- `city` (query, —, required=—) — 城市，如『北京』
- `service_type` (query, —, required=—) — 服务类型：full_accompany / half_accompany / errand
- `hospital_id` (query, —, required=—) — 按签约医院 ID 过滤
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/companions' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/companions/apply` — 申请成为陪诊师

用户提交陪诊师入驻申请，填写真实姓名、服务区域、擅长项目等。提交后状态为 `pending`，需后台 `admin-companions` 模块审核。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/companions/apply' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/companions/me` — 获取我的陪诊师档案

返回当前登录用户的陪诊师档案；若用户未申请陪诊师角色将抛出 404。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/companions/me' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PUT /api/v1/companions/me` — 更新我的陪诊师档案

陪诊师本人更新服务区域、服务类型、签约医院、个人简介等可修改字段。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X PUT 'https://api.yiluan.example.com/api/v1/companions/me' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/companions/me/stats` — 获取陪诊师统计概览

返回当前陪诊师在接单量、完成量、平均评分、累计收入等维度的统计。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/companions/me/stats' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/companions/{companion_id}` — 查看陪诊师详情

根据陪诊师 ID 查看公开的资料、服务范围与评分概要。

**参数：**

- `companion_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/companions/{companion_id}' \
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
