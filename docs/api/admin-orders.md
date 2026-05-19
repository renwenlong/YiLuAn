# admin-orders

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/orders` | 后台：订单列表 |
| `GET` | `/api/v1/admin/orders/{order_id}` | 后台：订单详情 |
| `POST` | `/api/v1/admin/orders/{order_id}/force-status` | 后台：强制修改订单状态 |
| `POST` | `/api/v1/admin/orders/{order_id}/refund` | 后台：管理员退款 |

## 端点详情

### `GET /api/v1/admin/orders` — 后台：订单列表

按状态 / 患者 / 陪诊师 / 预约日期范围分页查询订单。

**参数：**

- `status` (query, —, required=—) — OrderStatus 之一
- `patient_id` (query, —, required=—) — 
- `companion_id` (query, —, required=—) — 
- `date_from` (query, —, required=—) — 预约开始日期 YYYY-MM-DD
- `date_to` (query, —, required=—) — 预约结束日期 YYYY-MM-DD
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/orders' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/orders/{order_id}` — 后台：订单详情

返回单个订单的完整字段（含 patient_display_name / companion_display_name / patient_phone_masked / price），并写入 view_order_detail 审计行。

**参数：**

- `order_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/orders/{order_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/orders/{order_id}/force-status` — 后台：强制修改订单状态

管理员手动覆盖订单状态，**绕过业务状态机**，仅用于运营干预。 必须提供原因；进入禁止转换会 400 + 写 force_status_denied 审计。

**参数：**

- `order_id` (path, string, required=✅) — 
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
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/orders/{order_id}/force-status' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/orders/{order_id}/refund` — 后台：管理员退款

管理员发起退款。约束： (1) 订单状态需为 accepted / in_progress / completed / reviewed； (2) 退款金额 ≤ 已支付金额； (3) 同一订单已存在 success 退款时拒绝（依赖 PaymentService 唯一约束）。

**参数：**

- `order_id` (path, string, required=✅) — 
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
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/orders/{order_id}/refund' \
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
