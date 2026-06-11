# users-feedbacks

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/users/feedbacks` | 用户/家属提交首条反馈 (multipart, ADR-0049 §7) |
| `POST` | `/api/v1/users/feedbacks/{parent_id}/append` | 用户补充已有反馈 (multipart, ADR-0049 §7.1) |

## 端点详情

### `POST /api/v1/users/feedbacks` — 用户/家属提交首条反馈 (multipart, ADR-0049 §7)

**multipart/form-data**. 文本字段 + 可选 attachments[] 文件流, 一次性 POST. user_id 取自 JWT, 不接受请求体覆盖. 状态机初始: pending; admin 触达后流转 in_review → resolved/rejected → closed. 唯一约束: 同 user 对同 order 同 category 不可重复首条 (partial unique index uq_user_feedback_once_per_order_category, parent IS NULL). 重复 → HTTP 409. 限频: 10/h + 50/d per user (ADR-0049 §3.2.1).

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/users/feedbacks' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/users/feedbacks/{parent_id}/append` — 用户补充已有反馈 (multipart, ADR-0049 §7.1)

**multipart/form-data**. 对已有反馈追加内容 (可选附件). 鉴权: parent.user_id == current_user.id. 状态机要求: parent 处于 resolved/rejected/closed 才允许 append (pending/in_review 拒绝, HTTP 409). closed → in_review 受 30d 窗口限, 超期返 HTTP 410 Gone. append 成功后 parent 重新激活到 in_review. 限频: 30/h + 100/d per user (ADR-0049 §3.2.1).

**参数：**

- `parent_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/users/feedbacks/{parent_id}/append' \
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
