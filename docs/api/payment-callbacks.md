# 支付回调（payment-callbacks）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

微信支付（含模拟 provider）回调入口。**这两个端点由微信服务端调用，并非前端 / App 调用。**

幂等机制：`payment_callback_log` 唯一约束 `(provider, transaction_id)`。

## 鉴权要求

**不要求 JWT**。鉴权由微信回调签名验证完成。

## 限流

无限流。微信侧 24 小时内最多 8 次重试，已通过幂等表去重。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/payments/wechat/callback` | 微信支付 - 支付结果回调 |
| `POST` | `/api/v1/payments/wechat/refund-callback` | 微信支付 - 退款结果回调 |

## 端点详情

### `POST /api/v1/payments/wechat/callback` — 微信支付 - 支付结果回调

微信支付服务端调用的支付通知接收端。**不要求 JWT**，由签名验证保护。

幂等：基于 `payment_callback_log` 的 `(provider, transaction_id)` 唯一约束去重，重复回调直接返回 SUCCESS 不会再次更新订单。

返回体始终为 `{"code": "SUCCESS"|"FAIL", "message": ...}`，HTTP 状态码恒为 200，以便微信侧停止重试。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 已确认（成功或显式失败均返回 200） |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/payments/wechat/callback' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/payments/wechat/refund-callback` — 微信支付 - 退款结果回调

微信支付的退款通知接收端。鉴权与幂等策略与支付回调一致。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 已确认 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/payments/wechat/refund-callback' \
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
