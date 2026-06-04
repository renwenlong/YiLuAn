# public

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/public/service-packages` | 获取服务档位列表 (公开) |

## 端点详情

### `GET /api/v1/public/service-packages` — 获取服务档位列表 (公开)

返回当前 active 服务档位，按 sort_order 升序。以此价格为下单准，后台可动态调整。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/public/service-packages' \
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
