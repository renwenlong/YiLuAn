# emergency

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/emergency/contacts` | 紧急联系人列表 |
| `POST` | `/api/v1/emergency/contacts` | 新增紧急联系人（最多 3 个） |
| `DELETE` | `/api/v1/emergency/contacts/{contact_id}` | 删除紧急联系人 |
| `PUT` | `/api/v1/emergency/contacts/{contact_id}` | 更新紧急联系人 |
| `GET` | `/api/v1/emergency/events` | 我的紧急事件历史 |
| `POST` | `/api/v1/emergency/events` | 触发紧急事件 |
| `GET` | `/api/v1/emergency/hotline` | 平台客服热线 |

## 端点详情

### `GET /api/v1/emergency/contacts` — 紧急联系人列表

返回当前用户配置的紧急联系人（最多 3 个），按 created_at 升序。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/emergency/contacts' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/emergency/contacts` — 新增紧急联系人（最多 3 个）

为当前用户新增一位紧急联系人；超过 3 个或重复手机号会返回 409。

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
curl -X POST 'https://api.yiluan.example.com/api/v1/emergency/contacts' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/emergency/contacts/{contact_id}` — 删除紧急联系人

软删除指定的紧急联系人；非本人持有返回 403。

**参数：**

- `contact_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `204` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/emergency/contacts/{contact_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PUT /api/v1/emergency/contacts/{contact_id}` — 更新紧急联系人

更新指定 contact_id 的姓名 / 关系 / 手机号；非本人持有返回 403。

**参数：**

- `contact_id` (path, string, required=✅) — 

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
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X PUT 'https://api.yiluan.example.com/api/v1/emergency/contacts/{contact_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/emergency/events` — 我的紧急事件历史

返回当前用户触发过的紧急事件列表，按 created_at 降序，用于历史回溯审计。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/emergency/events' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/emergency/events` — 触发紧急事件

患者点击紧急呼叫后调用：传入 contact_id 或 hotline=true，服务端记录审计并返回前端要 wx.makePhoneCall 的号码。

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
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/emergency/events' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/emergency/hotline` — 平台客服热线

返回平台配置的客服热线，前端用于紧急呼叫弹层。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/emergency/hotline' \
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
