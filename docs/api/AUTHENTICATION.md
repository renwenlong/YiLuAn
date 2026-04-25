# 认证流程（OTP / JWT / 微信登录）

YiLuAn 后端使用 **JWT Bearer Token** 鉴权。下面分别说明三种登录链路与令牌生命周期。

---

## 一、概念

| 名称 | 用途 | 默认有效期 | 存放位置 |
| --- | --- | --- | --- |
| `access_token` | 普通业务接口鉴权 | **1 小时** | 客户端内存 / 安全存储 |
| `refresh_token` | 续签 access_token | **30 天** | 客户端安全存储（KeyChain / Keystore） |

> 实际有效期以后端 `settings.access_token_expire_minutes` 与 `settings.refresh_token_expire_days` 为准。

JWT Claim 约定：

```json
{
  "sub": "<user_uuid>",
  "role": "patient",
  "roles": ["patient", "companion"],
  "type": "access",          // 或 "refresh"
  "exp": 1700000000
}
```

---

## 二、链路 A：手机号 + 短信验证码登录（主流）

### 1. 发送验证码

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/send-otp' \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000"}'
```

- 限流：**5 次 / 分钟 / IP**。超出返回 `429`。
- 60 秒内对同一手机号重发会复用未过期的验证码（不会反复扣短信费）。
- 验证码 5 分钟有效。

### 2. 校验验证码并拿到令牌

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/verify-otp' \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000","code":"123456"}'
```

返回：

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "user": {
    "id": "uuid",
    "phone": "13800138000",
    "role": "patient",
    "roles": ["patient"],
    "display_name": "小明",
    "avatar_url": null,
    "created_at": "2026-04-24T10:00:00+08:00"
  }
}
```

- 手机号未注册时，**自动注册一个新账号**并签发令牌。

### 3. 业务调用

```
GET /api/v1/users/me
Authorization: Bearer <access_token>
```

### 4. 续签

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/refresh' \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

> ⚠️ refresh_token 是**一次性**的：调用后旧 refresh_token 立即作废，必须用响应中的新 refresh_token 替换本地存储。

---

## 三、链路 B：微信小程序登录

### 1. 小程序拿 code

```js
wx.login({ success: ({ code }) => post('/api/v1/auth/wechat-login', { code }) })
```

### 2. 后端登录

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/wechat-login' \
  -H 'Content-Type: application/json' \
  -d '{"code":"0a1B2cD..."}'
```

- 后端调用微信 `code2session` 拿 `openid`，按 `openid` 完成账号映射或自动注册。
- 返回结构与 `/auth/verify-otp` 一致。

### 3. 补绑手机号（可选）

微信注册账号没有手机号，调用：

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/auth/bind-phone' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000","code":"123456"}'
```

---

## 四、角色（patient / companion / admin）

- 一个账号可同时拥有 `patient` 与 `companion` 两个角色（陪诊师审核通过后）。
- `role` claim 表示**当前活跃角色**，`roles` claim 表示**全部已开通角色**。
- 切换活跃角色：`POST /api/v1/users/me/switch-role`，**会返回新令牌对**，前端必须用新令牌覆盖。
- `admin` 角色由后台手工授予，仅用于 `/api/v1/admin/*` 路由。

---

## 五、错误处理速查

| 场景 | 状态码 | detail |
| --- | --- | --- |
| 验证码错误 / 过期 | 400 | `Invalid OTP code` / `OTP expired` |
| access_token 缺失 | 401 | `Not authenticated` |
| access_token 过期 | 401 | `Token expired` → 走 refresh 流程 |
| refresh_token 失效 | 401 | `Invalid refresh token` → 重新登录 |
| 手机号格式错 | 422 | FastAPI 校验错误结构 |
| 触发短信限流 | 429 | `Rate limit exceeded: 5 per 1 minute` |

完整错误码语义见 [ERROR_HANDLING.md](./ERROR_HANDLING.md)。

---

## 六、客户端集成建议

- **存储**：使用平台安全存储（iOS KeyChain / Android EncryptedSharedPreferences / 微信小程序 `wx.setStorageSync` 加密）。
- **请求拦截器**：在请求拦截层附加 `Authorization`；在响应拦截层捕获 401 自动调用 `/auth/refresh`，失败再跳登录。
- **并发刷新**：多请求同时遇到 401 时，使用一个 mutex / Promise 复用同一次 refresh，避免重复消耗 refresh_token。
- **登出**：本地清除 token 并调用 `DELETE /api/v1/users/me/avatar`（如需）/ 撤销设备 token：`DELETE /api/v1/notifications/device-token`。
