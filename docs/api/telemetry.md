# telemetry

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/telemetry/events` | 上报埋点 / 异常事件 |

## 端点详情

### `POST /api/v1/telemetry/events` — 上报埋点 / 异常事件

前端 `utils/logger.report` 通道 + `utils/analytics` 漏斗事件统一入口。

**鉴权**：可选。带 `Authorization: Bearer <token>` 时会关联 `user_id`，否则匿名落库。

**限流**：同一 IP 每分钟最多 120 次。

**PII 拒收**：payload / client_meta 含手机号 / 身份证 / 卡号样式字符串时返回 422。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `202` | Successful Response |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/telemetry/events' \
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
