# 用户基础资料（users）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

用户账号本身的资料：昵称、头像、可用角色、活跃角色切换、注销。

## 鉴权要求

全部接口要求 `Authorization: Bearer <access_token>`。

## 限流

无特殊限流，遵循全局默认。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `DELETE` | `/api/v1/users/me` | 注销当前账户 |
| `GET` | `/api/v1/users/me` | 获取当前登录用户信息 |
| `PUT` | `/api/v1/users/me` | 更新当前用户基本资料 |
| `POST` | `/api/v1/users/me/avatar` | 上传头像 |
| `POST` | `/api/v1/users/me/switch-role` | 切换活跃角色 |

## 端点详情

### `DELETE /api/v1/users/me` — 注销当前账户

**永久**删除当前用户账户及关联数据。操作不可恢复，请前端二次确认。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/users/me' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/users/me` — 获取当前登录用户信息

返回当前 JWT 对应用户的基本资料（id、手机号、昵称、头像、角色、可用角色集合）。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/users/me' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PUT /api/v1/users/me` — 更新当前用户基本资料

支持修改昵称、头像 URL、当前活跃角色。手机号不能通过本接口修改。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X PUT 'https://api.yiluan.example.com/api/v1/users/me' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/users/me/avatar` — 上传头像

上传一张头像图片（multipart/form-data，字段名 `file`）。服务端保存到对象存储后，将 URL 写回用户资料并返回最终 URL。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/users/me/avatar' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/users/me/switch-role` — 切换活跃角色

在 `patient` 与 `companion` 两个已开通的角色间切换，**返回新的 JWT 令牌对**（新令牌的 `role` claim 已更新）。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/users/me/switch-role' \
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
