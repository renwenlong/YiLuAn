# admin-ai-blocklist

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/ai-blocklist/debug-version` | 返本副本当前读到的 blocklist version (验 reload 传播) |
| `GET` | `/api/v1/admin/ai-blocklist/preview` | 查看 AI 双层关键词过滤 blocklist (read-only) |
| `POST` | `/api/v1/admin/ai-blocklist/reload` | 触发 AI 关键词黑名单 hot reload (异步, 多副本 ≤5s) |

## 端点详情

### `GET /api/v1/admin/ai-blocklist/debug-version` — 返本副本当前读到的 blocklist version (验 reload 传播)

S3-DEV-002-HOT-RELOAD 验证端点. PRD-003 v0.3 §7 灰度监控: 两副本 admin trigger reload 后 5s 内, 各调此接口均返新 version.
不会写 audit_log (仅技术 debug 入口, 低成本调 OK).

**参数：**

- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/ai-blocklist/debug-version' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/ai-blocklist/preview` — 查看 AI 双层关键词过滤 blocklist (read-only)

ADR-0048 §4.1 admin-v2 关键词查看页:
- read-only — 不允许 admin 后台直改, 修改走 PR + 医疗顾问 review
- 任何 admin 调用写 admin_audit_logs action=ai_blocklist_viewed
- 同时 incr metric ai_blocklist_viewed_total{admin_id=...}
- query category 可过滤单个分类, 不带返全部 6 大分类

**参数：**

- `category` (query, —, required=—) — 可选: 指定分类只返该分类 (e.g. diagnosis); 不指定返全部
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/ai-blocklist/preview' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/ai-blocklist/reload` — 触发 AI 关键词黑名单 hot reload (异步, 多副本 ≤5s)

S3-DEV-002-HOT-RELOAD (ADR-0048 §4.1 + 刻晴 review #5).
admin 修改 docs/medical-content/prohibited-keywords.yml (走 PR + 医疗顾问 review approve + merge main) 后, 调此接口 publish reload 事件 → 所有 backend 副本 subscriber 收事件 → load_blocklist() 重 init cache.
“不会” 等待传播: 返 202 Accepted, 各副本 ≤5s 内生效 (PRD-003 v0.3 §7).
审计: admin_audit_logs action=ai_blocklist_reload + admin_id; metric ai_blocklist_reload_triggered_total{admin_id} incr.

**参数：**

- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `202` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `403` | 无权限 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/ai-blocklist/reload' \
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
