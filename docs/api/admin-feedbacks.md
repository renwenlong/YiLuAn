# admin-feedbacks

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/feedbacks` | admin 反馈列表 + 过滤分页 |
| `POST` | `/api/v1/admin/feedbacks` | admin 代录反馈 (multipart, customer_service / phone / offline) |
| `GET` | `/api/v1/admin/feedbacks/{feedback_id}` | admin 反馈详情 (全字段) |
| `PATCH` | `/api/v1/admin/feedbacks/{feedback_id}/status` | admin 状态流转 (state-machine 验) |

## 端点详情

### `GET /api/v1/admin/feedbacks` — admin 反馈列表 + 过滤分页

支持过滤: status / severity / module / companion_id. 默认每页 50, 最多 100. 排序: created_at desc.

**参数：**

- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `status` (query, —, required=—) — 
- `severity` (query, —, required=—) — 
- `module` (query, —, required=—) — 
- `companion_id` (query, —, required=—) — 
- `Authorization` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/feedbacks' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/feedbacks` — admin 代录反馈 (multipart, customer_service / phone / offline)

**multipart/form-data**. 客服/电话/线下代用户录反馈 (可选附件). source 必须是 {customer_service, phone, offline}, 拒绝 'user' (admin 不能伪装用户提交). 写入 AdminAuditLog (target_type=user_feedback, action=create). 限频: 60/h per admin (ADR-0049 §3.2.1).

**参数：**

- `Authorization` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/feedbacks' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/feedbacks/{feedback_id}` — admin 反馈详情 (全字段)

全字段视图. 写入 AdminAuditLog (target_type=user_feedback, action=view); audit 在外层 transaction commit, fetch 走 SAVEPOINT — 404 仅回滚 fetch, audit 行仍保留 (probe 审计, ADR-0049 §6.2 魈 review #5 双 commit boundary).

**参数：**

- `feedback_id` (path, string, required=✅) — 
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/feedbacks/{feedback_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PATCH /api/v1/admin/feedbacks/{feedback_id}/status` — admin 状态流转 (state-machine 验)

UserFeedbackStateMachine 5 状态合法迁移. 非法迁移 → HTTP 409. 首次 pending → in_review 自动设 handled_by_admin_id + handled_at. 迁移到 closed 自动设 closed_at (供后续 user_append 30d 窗口判). 写入 AdminAuditLog (target_type=user_feedback, action=patch_status).

**参数：**

- `feedback_id` (path, string, required=✅) — 
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
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X PATCH 'https://api.yiluan.example.com/api/v1/admin/feedbacks/{feedback_id}/status' \
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
