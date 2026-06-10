# admin-cache

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/admin/cache/invalidate` | admin 手动失效订单 precheck 缓存并触发重算 (super_admin only) |

## 端点详情

### `POST /api/v1/admin/cache/invalidate` — admin 手动失效订单 precheck 缓存并触发重算 (super_admin only)

admin (仅 super) 手动触发某订单 precheck:order:{order_id} 缓存失效 + OrderPrecheckAggregator 重算 + WS broadcast。

**stub 阶段返 501** (本 PR S3-DEV-005-CACHE-INVALIDATE 范围)。
aggregator.evaluate 在 S3-DEV-003-PRECHECK-BACKEND 实装后, 本 endpoint 不动, 自动返 200 (invalidated_keys + broadcast=true)。

保证 (即使 501 回应)：
* defensive Redis DEL precheck:order:{order_id} 已执行;
* AdminAuditLog 已写 (admin_id / order_id / cards / timestamp)。

rate limit: 5/min per admin (按 Authorization token 分桶)。

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
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |
| `501` | OrderPrecheckAggregator stub 未实装 evaluate / SET / broadcast (S3-DEV-005-CACHE-INVALIDATE 范围)。PRECHECK-BACKEND 接管后翻 200。 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/cache/invalidate' \
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
