# admin-prep-package

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/prep-packages/{order_id}` | admin 查看订单的 AI 准备包 (含 ops metadata) |

## 端点详情

### `GET /api/v1/admin/prep-packages/{order_id}` — admin 查看订单的 AI 准备包 (含 ops metadata)

返回完整内容 + ops metadata (trace_id / prompt_version_id / model / estimated/actual cost / generation_time_ms / fallback_reason)。仅 admin JWT principal 可访问 (legacy X-Admin-Token sentinel 拒绝)。**所有 admin 访问 (成功 200 / 404 不存在 / 500 异常) 均落 AdminAuditLog** (target_type=prep_package, action=view), 由 isolated AuditSession 保证 (S3-OPS-VIEW-PREP-AUDIT-ISOLATED-SESSION + PR #250 模式), 捕获 admin 侦察行为 (probe 不存在的 order_id)。

**参数：**

- `order_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 

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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/prep-packages/{order_id}' \
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
