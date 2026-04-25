# 认证（auth）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

认证模块负责用户身份鉴别。提供两条登录链路：

1. **手机号 + 短信验证码**（主要链路）：`/auth/send-otp` → `/auth/verify-otp` → 拿到 `access_token`。
2. **微信小程序 code 登录**：`/auth/wechat-login`，必要时再补绑手机号。

登录成功后，调用其他接口需要在请求头携带：

```
Authorization: Bearer <access_token>
```
完整流程详见 [AUTHENTICATION.md](./AUTHENTICATION.md)。

## 鉴权要求

本模块各接口除 `/auth/bind-phone` 外**均不要求 Bearer Token**。

## 限流

`/auth/send-otp` 限流 **5 次 / 分钟 / IP**。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/auth/bind-phone` | 为当前账号绑定手机号 |
| `POST` | `/api/v1/auth/refresh` | 刷新访问令牌 |
| `POST` | `/api/v1/auth/send-otp` | 发送短信验证码 |
| `POST` | `/api/v1/auth/verify-otp` | 校验短信验证码并登录 |
| `POST` | `/api/v1/auth/wechat-login` | 微信小程序登录 |

## 端点详情

### `POST /api/v1/auth/bind-phone` — 为当前账号绑定手机号

已登录用户绑定手机号，需要提供手机号 + 验证码。用于「微信注册账号」补充绑定手机号场景。

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
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/bind-phone' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/auth/refresh` — 刷新访问令牌

使用 `refresh_token` 换取新的 `access_token` 和 `refresh_token`。旧的 refresh_token 会被撤销（一次性使用）。

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
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/refresh' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/auth/send-otp` — 发送短信验证码

向指定手机号发送 6 位短信验证码，用于登录或绑定手机号。

**限流**：同一 IP 每分钟最多 5 次。

**有效期**：验证码 5 分钟内有效。

**幂等**：同一手机号 60 秒内重复请求会复用未过期的验证码。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 已发送 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/send-otp' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/auth/verify-otp` — 校验短信验证码并登录

校验手机号 + 6 位验证码。校验通过后：

- 若手机号已注册 → 返回该用户的 JWT 令牌对；
- 若手机号未注册 → 自动注册一个新用户后返回令牌对。

返回的 `access_token` 默认 1 小时过期，`refresh_token` 默认 30 天过期。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/verify-otp' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/auth/wechat-login` — 微信小程序登录

通过微信小程序 `wx.login()` 拿到的临时 `code` 完成登录。后端会调用微信 `code2session` 接口获取 `openid` 并完成账号映射。首次登录会创建一个无手机号的账号，后续可通过 `/auth/bind-phone` 绑定手机号。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/wechat-login' \
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
