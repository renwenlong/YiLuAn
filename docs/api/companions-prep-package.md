# companions-prep-package

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/companions/orders/{order_id}/prep-package` | 陪诊师获取本订单的 AI 准备包 (脱敏视图, 不含病史原文) |

## 端点详情

### `GET /api/v1/companions/orders/{order_id}/prep-package` — 陪诊师获取本订单的 AI 准备包 (脱敏视图, 不含病史原文)

**红线**: 不含 pre_visit_notes / possible_questions / trace_*; carry_items 已压缩为 carry_items_summary 短摘要。仅陪诊师为本订单的指派服务者时返回; 否则返回 404。

**参数：**

- `order_id` (path, string, required=✅) — 

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
curl -X GET 'https://api.yiluan.example.com/api/v1/companions/orders/{order_id}/prep-package' \
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
