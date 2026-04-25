# 订单（orders）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

订单贯穿『下单 → 支付 → 接单 → 服务 → 完成 / 退款』完整生命周期。常见状态：

- `pending_payment` 待支付（30 分钟自动取消）
- `paid` 已支付，等待陪诊师接单
- `accepted` 已接单
- `in_service` 服务中
- `completed` 已完成
- `cancelled_by_patient` / `cancelled_by_companion` / `rejected_by_companion` / `expired` 终态


## 鉴权要求

除 `/orders/check-expired`（`X-Admin-Token`）外，全部接口要求 `Authorization: Bearer <access_token>`，并强校验当前用户是否为订单参与方。

## 限流

无特殊限流，遵循全局默认。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/orders` | 获取我的订单列表 |
| `POST` | `/api/v1/orders` | 患者创建订单 |
| `POST` | `/api/v1/orders/check-expired` | 扫描并取消过期订单（运维/定时任务） |
| `GET` | `/api/v1/orders/{order_id}` | 获取订单详情 |
| `POST` | `/api/v1/orders/{order_id}/accept` | 陪诊师接单 |
| `POST` | `/api/v1/orders/{order_id}/cancel` | 取消订单 |
| `POST` | `/api/v1/orders/{order_id}/complete` | 完成订单 |
| `POST` | `/api/v1/orders/{order_id}/confirm-start` | 患者确认开始服务 |
| `POST` | `/api/v1/orders/{order_id}/pay` | 对订单发起支付 |
| `POST` | `/api/v1/orders/{order_id}/refund` | 患者申请退款 |
| `POST` | `/api/v1/orders/{order_id}/reject` | 陪诊师拒单 |
| `POST` | `/api/v1/orders/{order_id}/request-start` | 陪诊师发起开始服务请求 |
| `POST` | `/api/v1/orders/{order_id}/start` | 陪诊师直接开始服务 |

## 端点详情

### `GET /api/v1/orders` — 获取我的订单列表

分页查询当前用户参与的订单（患者视角看自己创建的，陪诊师视角看自己接的）。

**参数：**

- `status` (query, —, required=—) — 订单状态过滤
- `date` (query, —, required=—) — 预约日期 YYYY-MM-DD
- `city` (query, —, required=—) — 按城市过滤
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
curl -X GET 'https://api.yiluan.example.com/api/v1/orders' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders` — 患者创建订单

患者发起一笔陪诊服务订单。需指定服务类型、医院、就诊日期与时间。可选 `companion_id` 直接指派，否则进入大厅由陪诊师抢单。

新订单状态为 `pending_payment`，**必须在 30 分钟内完成支付**，否则会被定时任务自动取消。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/check-expired` — 扫描并取消过期订单（运维/定时任务）

扫描所有 `pending_payment` 超过 30 分钟未支付的订单并自动取消。由内部定时任务调度，**需 `X-Admin-Token` 鉴权**。

**参数：**

- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 执行结果 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/check-expired' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/orders/{order_id}` — 获取订单详情

按订单 ID 获取详情。仅订单参与方与管理员可见。

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
curl -X GET 'https://api.yiluan.example.com/api/v1/orders/{order_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/accept` — 陪诊师接单

陪诊师接受指定订单。需订单处于 `paid` 且未被其他陪诊师接走。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/accept' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/cancel` — 取消订单

取消指定订单。患者和陪诊师均可在不同状态下调用，已支付订单将按规则触发退款（详见钱包/退款规则文档）。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/cancel' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/complete` — 完成订单

陪诊师标记订单服务已完成，订单进入 `completed`，触发评价流程。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/complete' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/confirm-start` — 患者确认开始服务

患者确认陪诊师的开始服务请求，订单正式进入 `in_service` 状态。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/confirm-start' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/pay` — 对订单发起支付

对指定订单发起支付，返回前端调起微信支付所需的参数。MVP 环境下使用 mock provider，会直接返回 `mock_success=true`。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 支付参数 |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/pay' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/refund` — 患者申请退款

对已支付订单申请退款，金额原路返回到支付账户。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/refund' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/reject` — 陪诊师拒单

陪诊师拒绝指定订单。若已支付，则自动触发全额退款。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/reject' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/request-start` — 陪诊师发起开始服务请求

陪诊师发起「开始服务」请求，等待患者在 App 内确认（双确认流程）。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/request-start' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/start` — 陪诊师直接开始服务

陪诊师标记开始服务（已与患者线下见面），订单进入 `in_service`。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `400` | 请求参数错误 |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/start' \
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
