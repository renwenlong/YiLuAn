# 订单评价（reviews）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

已完成订单的患者评价。**单订单仅可评价一次**。陪诊师详情页通过『陪诊师评价列表』展示历史评价。

## 鉴权要求

全部接口要求登录。提交评价仅订单的患者本人可调用。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/companions/{companion_id}/reviews` | 陪诊师收到的评价列表 |
| `GET` | `/api/v1/orders/{order_id}/review` | 查看订单评价 |
| `POST` | `/api/v1/orders/{order_id}/review` | 提交订单评价 |

## 端点详情

### `GET /api/v1/companions/{companion_id}/reviews` — 陪诊师收到的评价列表

分页查询某位陪诊师收到的全部评价（公开数据，用于详情页展示）。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/companions/{companion_id}/reviews' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/orders/{order_id}/review` — 查看订单评价

查看指定订单的评价。若订单未被评价，返回 404。

**参数：**

- `order_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/orders/{order_id}/review' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/orders/{order_id}/review` — 提交订单评价

患者在订单 `completed` 后提交评价：1~5 星评分 + 5~500 字评论。**单订单仅可评价一次**，重复提交将返回 400。

**参数：**

- `order_id` (path, string, required=✅) — 

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
| `403` | 无权限 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/orders/{order_id}/review' \
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
