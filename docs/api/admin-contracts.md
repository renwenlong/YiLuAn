# admin-contracts

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/admin/contracts/{contract_id}/invalidate` | admin 客服作废合同 (AC#3) |

## 端点详情

### `POST /api/v1/admin/contracts/{contract_id}/invalidate` — admin 客服作废合同 (AC#3)

客服在用户申请作废合同 / 灰度回滚 / 误生成时使用。

**必须** JWT admin 登录, 拒绝 legacy X-Admin-Token (需 admin_user.id).

副作用:
- service_contracts.status → manually_invalidated
- service_contracts.invalidation_reason / invalidated_by_admin_id / invalidated_at 填
- 写 admin_audit_logs (target_type=service_contract, action=invalidate)
- **不删 blob** (WORM 不可删, ADR-0046 §3.3 第 3 层)
- **不退款** (走 PaymentService 独立流程)

**参数：**

- `contract_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

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
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/contracts/{contract_id}/invalidate' \
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
