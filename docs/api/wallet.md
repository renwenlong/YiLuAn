# 钱包（wallet）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

钱包余额、累计收入/支出、流水分页查询。提现走运营后台审核流，暂未对前端开放。

## 鉴权要求

全部接口要求登录。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/wallet` | 获取钱包概览 |
| `GET` | `/api/v1/wallet/transactions` | 获取钱包交易流水 |

## 端点详情

### `GET /api/v1/wallet` — 获取钱包概览

返回当前用户的钱包余额、累计收入、累计支出、可提现金额等概览信息。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 钱包概览 |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/wallet' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/wallet/transactions` — 获取钱包交易流水

分页查询当前用户的钱包流水（含支付、退款、提现等记录）。

**参数：**

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
curl -X GET 'https://api.yiluan.example.com/api/v1/wallet/transactions' \
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
