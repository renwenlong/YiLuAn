# share

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/orders/{order_id}/shares` | 下单人查看当前 active 分享 token |
| `POST` | `/api/v1/orders/{order_id}/shares` | 下单人创建家属分享 token |
| `DELETE` | `/api/v1/orders/{order_id}/shares/{token_id}` | 下单人吊销指定分享 token |
| `GET` | `/api/v1/shares/session/order` | 家属端用 share_session 拉脱敏订单视图 |
| `POST` | `/api/v1/shares/{token}/otp` | 家属端（iOS/H5）请求下发短信验证码 |
| `POST` | `/api/v1/shares/{token}/session` | 家属端用 token + openid/(phone+otp) 换 share_session JWT |

## 端点详情

### `GET /api/v1/orders/{order_id}/shares` — 下单人查看当前 active 分享 token

下单人（owner）查询指定订单下当前处于 active 状态的家属分享 token 列表，返回 token 概要及 ``share_active_count`` 计数。需 owner 身份鉴权。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/orders/{order_id}/shares' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/shares` — 下单人创建家属分享 token

创建一条 OrderShareToken 并返回短链。单订单 active token 数硬上限 = 3，已达上限时自动 revoke 最老一条。

**参数：**

- `order_id` (path, string, required=✅) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/shares' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/orders/{order_id}/shares/{token_id}` — 下单人吊销指定分享 token

幂等吊销。WS 服务端读 ``revoked_at``，已建立的家属连接将以 code 4013 主动断开（S2-DEV-003 实现）。

**参数：**

- `order_id` (path, string, required=✅) — 
- `token_id` (path, string, required=✅) — 

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
curl -X DELETE 'https://api.yiluan.example.com/api/v1/orders/{order_id}/shares/{token_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/shares/session/order` — 家属端用 share_session 拉脱敏订单视图

返回 §2.5 PII 表筛选后的字段集。``scope=progress_only`` 时影像 + AI 摘要的 can_* 标志为 false (AC#21)。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/shares/session/order' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/shares/{token}/otp` — 家属端（iOS/H5）请求下发短信验证码

iOS App / 外部浏览器无微信静默授权时的降级路径（ADR-0036 §2.2）。双轴频控：单 token 24h ≤ 5 次、单手机号 1h ≤ 3 个不同 token，超限 429 转人工。成功后验证码有效期 5min。

**参数：**

- `token` (path, string, required=✅) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/shares/{token}/otp' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/shares/{token}/session` — 家属端用 token + openid/(phone+otp) 换 share_session JWT

微信小程序静默路径传 ``wx_openid``；iOS / 外部浏览器路径先调 ``POST /shares/{token}/otp`` 收码，再传 ``phone`` + ``otp``（6 位）。过期 / 已 revoke 的 token、验证码错误/过期 一律 401。

**参数：**

- `token` (path, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/shares/{token}/session' \
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
