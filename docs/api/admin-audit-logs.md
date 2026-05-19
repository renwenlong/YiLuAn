# admin-audit-logs

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/audit-logs` | 后台：审计日志列表 |

## 端点详情

### `GET /api/v1/admin/audit-logs` — 后台：审计日志列表

按操作员 / 目标类型 / 目标 id / 动作 / 时间窗口过滤后台审计日志，分页返回。

**参数：**

- `operator` (query, —, required=—) — 按操作员精确匹配
- `target_type` (query, —, required=—) — 按目标类型，如 order/user/companion
- `target_id` (query, —, required=—) — 按具体目标 id 精确匹配
- `action` (query, —, required=—) — 按动作类型精确匹配
- `since` (query, —, required=—) — created_at >= since
- `until` (query, —, required=—) — created_at < until
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/audit-logs' \
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
