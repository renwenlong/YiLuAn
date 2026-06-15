# readonly-gate

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/admin/readonly/complaint-rate` | PM weekly manual 注入 customer complaint rate (ADR-0053 §AC#4) |

## 端点详情

### `POST /api/v1/admin/readonly/complaint-rate` — PM weekly manual 注入 customer complaint rate (ADR-0053 §AC#4)

PM 每周手动 POST 注入客诉率 sample, redis ZSET 7 天滑动窗口. Cron gate `check_readonly_flag_real_gate` 每日 02:00 UTC 读 rolling average 比 0.1% 阈值. AdminAuditLog 同事务写 (PR #250 反 pattern 已 escape).

**参数：**

- `Authorization` (header, —, required=—) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/readonly/complaint-rate' \
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
