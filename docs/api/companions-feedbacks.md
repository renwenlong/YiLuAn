# companions-feedbacks

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/companions/feedbacks/{feedback_id}/appeal` | 陪诊师对反馈申诉 (写 companion_appeal 字段) |
| `GET` | `/api/v1/companions/feedbacks/{feedback_id}/summary` | 陪诊师反馈摘要视图 (RED LINE, 不含病史/附件原图) |

## 端点详情

### `POST /api/v1/companions/feedbacks/{feedback_id}/appeal` — 陪诊师对反馈申诉 (写 companion_appeal 字段)

陪诊师对反馈写申诉理由. 这个 endpoint 不创建新资源, 仅更新已有 UserFeedback 行 的 companion_appeal 字段, 所以 200 不是 201 (REST 语义 alignment). ABAC: 仅 feedback.companion_id == current_companion.id 才能写 (否则 HTTP 404, 不泄露存在). 返回脱敏摘要视图 (RED LINE 5 字段, 不含 raw_content).

**参数：**

- `feedback_id` (path, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/companions/feedbacks/{feedback_id}/appeal' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/companions/feedbacks/{feedback_id}/summary` — 陪诊师反馈摘要视图 (RED LINE, 不含病史/附件原图)

**红线**: 不含 raw_content / metadata / user_phone / patient_name / attachments / signed_url / handled_by_admin_id. 仅返 (id, severity, status, sanitized_summary, companion_appeal) 5 字段. sanitized_summary NULL 表示 admin 未脱敏 — 端展示「等待客服处理」. 仅 feedback.companion_id == current_companion.id 才返; 否则 HTTP 404.

**参数：**

- `feedback_id` (path, string, required=✅) — 

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
curl -X GET 'https://api.yiluan.example.com/api/v1/companions/feedbacks/{feedback_id}/summary' \
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
