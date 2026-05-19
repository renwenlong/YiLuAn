# family-members

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/users/me/family-members` | 获取我的家人列表 (F-05) |
| `POST` | `/api/v1/users/me/family-members` | 新增一位家人 (F-05) |
| `DELETE` | `/api/v1/users/me/family-members/{member_id}` | 软删除一位家人 (F-05) |
| `PATCH` | `/api/v1/users/me/family-members/{member_id}` | 更新一位家人 (F-05) |

## 端点详情

### `GET /api/v1/users/me/family-members` — 获取我的家人列表 (F-05)

按创建时间升序返回当前用户所有未软删除的家人/被陪诊人档案。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/users/me/family-members' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/users/me/family-members` — 新增一位家人 (F-05)

为当前用户创建一个家人/被陪诊人档案，默认 relation=other / gender=unknown。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/users/me/family-members' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/users/me/family-members/{member_id}` — 软删除一位家人 (F-05)

软删除：标记 deleted_at，历史订单仍可解析快照。

**参数：**

- `member_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `204` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/users/me/family-members/{member_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PATCH /api/v1/users/me/family-members/{member_id}` — 更新一位家人 (F-05)

部分字段更新当前用户名下的家人档案；不影响历史订单上的快照。

**参数：**

- `member_id` (path, string, required=✅) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X PATCH 'https://api.yiluan.example.com/api/v1/users/me/family-members/{member_id}' \
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
