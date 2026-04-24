# 错误码与前端处理建议

## 一、统一错误响应格式

所有非 2xx 响应**统一**返回 JSON：

```json
{ "detail": "human-readable message" }
```

> 例外：FastAPI 校验失败（`422`）的 `detail` 是结构化数组，见下文。

---

## 二、标准错误码

| HTTP 状态 | 语义 | 典型 `detail` | 前端建议处理 |
| --- | --- | --- | --- |
| **400** Bad Request | 业务规则不满足，参数语义错误 | `Order cannot be cancelled in current status` | 直接 toast `detail`；不要重试。 |
| **401** Unauthorized | 未登录 / 令牌缺失 / 令牌过期 | `Not authenticated` / `Token expired` | 自动调用 `/auth/refresh`；失败则跳登录页。 |
| **403** Forbidden | 已登录，但无权访问该资源 | `Forbidden` / `Admin access required` | 显示无权访问提示；不要静默重试。 |
| **404** Not Found | 资源不存在或已被删除 | `Order not found` | 提示『资源不存在』并返回上一页。 |
| **409** Conflict | 资源状态冲突（并发抢单失败等） | `Order already accepted` | 刷新最新状态，提示用户冲突原因。 |
| **413** Payload Too Large | 上传文件超限 | `File too large` | 提示文件大小限制，建议压缩。 |
| **415** Unsupported Media Type | 文件格式不支持 | `Unsupported media type` | 提示允许的文件类型。 |
| **422** Unprocessable Entity | 字段校验失败（FastAPI / Pydantic） | 见下文结构 | 高亮对应字段错误。 |
| **429** Too Many Requests | 触发限流 | `Rate limit exceeded: 5 per 1 minute` | 倒计时禁用按钮；不要立即重试。 |
| **500** Internal Server Error | 服务端未捕获异常 | `Internal server error` | 提示『服务器繁忙，请稍后再试』；上报 Sentry。 |
| **502 / 503 / 504** | 网关 / 上游 / 超时 | — | 视为可重试错误，按指数退避重试 1~2 次。 |

---

## 三、422 校验错误结构

FastAPI 将每个校验失败的字段以数组形式返回：

```json
{
  "detail": [
    {
      "loc": ["body", "phone"],
      "msg": "Invalid phone number format",
      "type": "value_error"
    },
    {
      "loc": ["body", "code"],
      "msg": "OTP code must be 6 digits",
      "type": "value_error"
    }
  ]
}
```

前端建议：

- 遍历 `detail`，按 `loc[-1]` 字段名定位输入框。
- 直接展示 `msg`（已为人类可读英文）；面向 C 端可在前端做一层中文映射。

---

## 四、业务专属错误片段

下表罗列后端可能返回的业务级 `detail` 字符串及含义。前端可用作 i18n 映射的 key。

### 认证 & 用户
- `Invalid phone number format` — 手机号格式不合法
- `OTP code must be 6 digits` — 验证码格式不合法
- `Invalid OTP code` — 验证码错误
- `OTP expired` — 验证码超时
- `Phone already bound` — 手机号已被其他账号绑定
- `Invalid refresh token` — refresh_token 已失效或被使用
- `Role must be 'patient' or 'companion'` — 角色字段错误

### 订单 & 支付
- `Order not found` — 订单不存在
- `Order already paid` — 订单已支付，请勿重复支付
- `Order cannot be cancelled in current status` — 当前状态不允许取消
- `Refund failed — order may already be refunded or unpaid` — 退款被拒
- `Companion already assigned` — 抢单冲突
- `Not a participant` — 当前用户不是订单参与方

### 陪诊师
- `Companion application already exists` — 已有进行中的入驻申请
- `Companion not verified` — 未通过审核

### 后台
- `Admin access required` — 当前用户不具备 `admin` 角色
- `Invalid status: <value>` — 强制状态值不合法

---

## 五、429 限流处理建议

后端按 IP / 用户维度限流。响应头会带 `Retry-After`（秒）：

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json

{"detail":"Rate limit exceeded: 5 per 1 minute"}
```

前端建议：

- 读取 `Retry-After` 倒计时禁用相关按钮（如『发送验证码』）。
- 不要在 catch 里立即重试 → 会进一步触发限流。

---

## 六、网络层兜底

- 所有 5xx 响应面向用户统一显示『服务器繁忙，请稍后再试』，技术细节写日志或上报到 Sentry / 阿里云 ARMS。
- 请求超时（连接 10s / 读取 30s）按 5xx 处理。
- 必要时实现『指数退避 + 抖动』重试，重试**仅限**幂等方法（GET、PUT、DELETE）和明确标注幂等的 POST（如支付回调）。
