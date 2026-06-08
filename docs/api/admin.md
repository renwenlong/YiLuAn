# 运营后台 - 通用（admin）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

运营后台对订单、用户的管理操作（查询、强制状态、退款、停用/启用账号）。

## 鉴权要求

要求 `Authorization: Bearer <access_token>`，**且当前用户具备 `admin` 角色**（401 / 403 拦截）。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/ai-blocklist/debug-version` | 返本副本当前读到的 blocklist version (验 reload 传播) |
| `GET` | `/api/v1/admin/ai-blocklist/preview` | 查看 AI 双层关键词过滤 blocklist (read-only) |
| `POST` | `/api/v1/admin/ai-blocklist/reload` | 触发 AI 关键词黑名单 hot reload (异步, 多副本 ≤5s) |
| `GET` | `/api/v1/admin/audit-logs` | 后台：审计日志列表 |
| `GET` | `/api/v1/admin/companions/` | 后台：待审核陪诊师列表 |
| `POST` | `/api/v1/admin/companions/certification-images` | 后台：上传陪诊师证件图（Phase A 本地私有存储） |
| `GET` | `/api/v1/admin/companions/certification-images/{filename}` | 后台：读取证件图 signed URL（双闸：admin token + HMAC） |
| `GET` | `/api/v1/admin/companions/search` | 后台：陪诊师轻量搜索（钱包账本筛选用） |
| `GET` | `/api/v1/admin/companions/{companion_id}` | 后台：陪诊师审核详情 |
| `POST` | `/api/v1/admin/companions/{companion_id}/approve` | 后台：批准陪诊师入驻 |
| `POST` | `/api/v1/admin/companions/{companion_id}/certify` | 管理员：设置陪诊师资质认证（F-01） |
| `POST` | `/api/v1/admin/companions/{companion_id}/reject` | 后台：驳回陪诊师申请 |
| `POST` | `/api/v1/admin/contracts/{contract_id}/invalidate` | admin 客服作废合同 (AC#3) |
| `GET` | `/api/v1/admin/dashboard/summary` | 后台首页：KPI + 7 日趋势 |
| `GET` | `/api/v1/admin/dead-letters` | 后台：死信队列表 |
| `GET` | `/api/v1/admin/dead-letters/{dl_id}` | 后台：死信详情 |
| `POST` | `/api/v1/admin/dead-letters/{dl_id}/resolve` | 后台：标记死信已解决 |
| `POST` | `/api/v1/admin/login` | Admin v2 登录（JWT） |
| `GET` | `/api/v1/admin/notes` | 后台：按 target 列出备注 |
| `POST` | `/api/v1/admin/notes` | 后台：新增备注 |
| `DELETE` | `/api/v1/admin/notes/{note_id}` | 后台：删除备注（仅作者） |
| `PATCH` | `/api/v1/admin/notes/{note_id}` | 后台：编辑备注（仅作者） |
| `GET` | `/api/v1/admin/orders` | 后台：订单列表 |
| `GET` | `/api/v1/admin/orders/{order_id}` | 后台：订单详情 |
| `POST` | `/api/v1/admin/orders/{order_id}/force-status` | 后台：强制修改订单状态 |
| `POST` | `/api/v1/admin/orders/{order_id}/refund` | 后台：管理员退款 |
| `GET` | `/api/v1/admin/orders/{order_id}/timeline` | 后台：订单状态变迁时间轴 |
| `GET` | `/api/v1/admin/reconciliation/diffs` | List Diffs |
| `GET` | `/api/v1/admin/reconciliation/diffs/{diff_id}` | 后台：差异详情 |
| `POST` | `/api/v1/admin/reconciliation/diffs/{diff_id}/close-confirms` | Confirm Close |
| `POST` | `/api/v1/admin/reconciliation/diffs/{diff_id}/close-requests` | Request Close |
| `GET` | `/api/v1/admin/reconciliation/runs` | 后台：对账 run 列表 |
| `GET` | `/api/v1/admin/service-packages/` | 后台：服务档位列表 |
| `POST` | `/api/v1/admin/service-packages/` | 后台：新建服务档位 |
| `DELETE` | `/api/v1/admin/service-packages/{pkg_id}` | 后台：软删服务档位 |
| `GET` | `/api/v1/admin/service-packages/{pkg_id}` | 后台：服务档位详情 |
| `PATCH` | `/api/v1/admin/service-packages/{pkg_id}` | 后台：更新服务档位 |
| `GET` | `/api/v1/admin/telemetry/events` | 埋点事件列表（admin） |
| `GET` | `/api/v1/admin/users` | 后台：用户列表 |
| `GET` | `/api/v1/admin/users/{user_id}` | 后台：用户详情 |
| `POST` | `/api/v1/admin/users/{user_id}/disable` | 后台：停用用户 |
| `POST` | `/api/v1/admin/users/{user_id}/enable` | 后台：启用用户 |
| `POST` | `/api/v1/admin/wallet-ledger/adjustments` | Create Manual Adjustment |
| `GET` | `/api/v1/admin/wallet-ledger/{user_id}` | List User Ledger |

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

### `GET /api/v1/admin/audit-logs` — 后台：审计日志列表

按操作员 / 目标类型 / 目标 id / 动作 / 时间窗口过滤后台审计日志，分页返回。

**参数：**

- `operator` (query, —, required=—) — 按操作员精确匹配
- `target_type` (query, —, required=—) — 按目标类型，如 order/user/companion
- `target_id` (query, —, required=—) — 按具体目标 id 精确匹配
- `action` (query, —, required=—) — 按动作类型精确匹配
- `since` (query, —, required=—) — created_at >= since
- `until` (query, —, required=—) — created_at < until
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/audit-logs' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/companions/` — 后台：待审核陪诊师列表

分页返回提交了入驻申请、状态为 `pending` 的陪诊师。请求头需携带 `X-Admin-Token`。

**参数：**

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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/certification-images` — 后台：上传陪诊师证件图（Phase A 本地私有存储）

仅 admin 可用。保存 jpg/jpeg/png/webp <= 5MB 到 backend 私有本地目录，返回可写入 certify.certification_image_url 的 cert-image:// 标识 + 15min signed URL。

**参数：**

- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/certification-images' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/companions/certification-images/{filename}` — 后台：读取证件图 signed URL（双闸：admin token + HMAC）

双闸鉴权（ADR-0044 r1 §4.2）：
1. 闸1 = require_admin（X-Admin-Token / JWT）
2. 闸2 = HMAC 签名 + expires (TTL ≤ 15min) + filename 路径白名单
admin-v2 drawer 走 fetch + blob URL 模式（不能直接 <img src=、否则浏览器不携 header）。写 view_cert_image 审计。

**参数：**

- `filename` (path, string, required=✅) — 
- `expires` (query, integer, required=✅) — 
- `sig` (query, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/certification-images/{filename}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/companions/search` — 后台：陪诊师轻量搜索（钱包账本筛选用）

按姓名或手机号模糊搜索陪诊师，返回 user_id + 姓名 + 手机号尾 4 位。默认仅返回 `verified` 状态；传 `status=all` 取消该过滤。

**参数：**

- `q` (query, —, required=—) — 姓名或手机号关键字
- `status` (query, string, required=—) — verified | all
- `limit` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/search' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/companions/{companion_id}` — 后台：陪诊师审核详情

返回单个陪诊师 14 字段审核视图。`certification_image_signed_url` 对 PR-E2 Phase A 本地 cert-image:// 对象返回 15min signed URL；历史外部 URL 返回 None，待 Phase B storage 迁移。reveal phone 走独立端点 `GET /admin/users/{user_id}?reveal=true`。 写入 view_companion_detail 审计。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/approve` — 后台：批准陪诊师入驻

批准指定陪诊师，状态转为 `verified`，该陪诊师随即可被搜索与接单。

**参数：**

- `companion_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/approve' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/certify` — 管理员：设置陪诊师资质认证（F-01）

设置认证类型/证书编号/证书图片并戳记 certified_at；写入 admin_audit_log。

**参数：**

- `companion_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/certify' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/companions/{companion_id}/reject` — 后台：驳回陪诊师申请

驳回指定陪诊师的入驻申请并写入原因（1~500 字）。

**参数：**

- `companion_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/companions/{companion_id}/reject' \
  -H 'Authorization: Bearer <access_token>'
```

---

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

### `GET /api/v1/admin/dashboard/summary` — 后台首页：KPI + 7 日趋势

返回今日订单数 / GMV / 待审陆的陪诊师 / 未关闭差异等 KPI 以及过去 7 日的趋势点位。

**参数：**

- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/dashboard/summary' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/dead-letters` — 后台：死信队列表

查询需人工补偿的遗留任务，默认按时间倒序。

**参数：**

- `status` (query, —, required=—) — pending / resolved
- `channel` (query, —, required=—) — 例：order_refund
- `target_id` (query, —, required=—) — 
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/dead-letters' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/dead-letters/{dl_id}` — 后台：死信详情

返回指定 dead_letter 行的全部字段（含 payload 与解决态）。

**参数：**

- `dl_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/dead-letters/{dl_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/dead-letters/{dl_id}/resolve` — 后台：标记死信已解决

记录解决人、说明、时间；同时写入 admin_audit_logs。

**参数：**

- `dl_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/dead-letters/{dl_id}/resolve' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/login` — Admin v2 登录（JWT）

校验 `admin_users.username` + bcrypt 密码，签发 8h JWT。Token 用 `Authorization: Bearer <token>` 传递。见 ADR-0034。

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/login' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/notes` — 后台：按 target 列出备注

按 (target_type, target_id) 列出后台备注，限 100到500 条，创建时间倒序。

**参数：**

- `target_type` (query, string, required=✅) — 
- `target_id` (query, string, required=✅) — 
- `limit` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/notes' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/notes` — 后台：新增备注

为指定 target (order/user/companion) 创建一条后台备注，同时写入审计日志。

**参数：**

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/notes' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/admin/notes/{note_id}` — 后台：删除备注（仅作者）

仅原作者可删除备注；delete 动作同步记录审计日志。

**参数：**

- `note_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/admin/notes/{note_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PATCH /api/v1/admin/notes/{note_id}` — 后台：编辑备注（仅作者）

仅原作者可修改备注内容；edit 记录会进入审计日志。

**参数：**

- `note_id` (path, string, required=✅) — 
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
curl -X PATCH 'https://api.yiluan.example.com/api/v1/admin/notes/{note_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

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

### `GET /api/v1/admin/orders/{order_id}/timeline` — 后台：订单状态变迁时间轴

按创建时间升序返回指定订单的状态变迁记录（order_status_history），供客服复盘使用。

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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/orders/{order_id}/timeline' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/reconciliation/diffs` — List Diffs

List reconciliation diffs with filters; newest first.

**参数：**

- `status` (query, —, required=—) — 
- `kind` (query, —, required=—) — 
- `provider` (query, —, required=—) — 
- `order_id` (query, —, required=—) — 
- `run_id` (query, —, required=—) — 
- `date_from` (query, —, required=—) — 
- `date_to` (query, —, required=—) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/reconciliation/diffs/{diff_id}` — 后台：差异详情

返回指定 reconciliation diff 详情 + 全部动作记录（按 created_at 升序）。

**参数：**

- `diff_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs/{diff_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/reconciliation/diffs/{diff_id}/close-confirms` — Confirm Close

Second signature. Must be performed by a *different* operator than
the one who filed the pending request. Flips the diff to ``closed``.

**参数：**

- `diff_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 
- `X-Admin-Operator` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs/{diff_id}/close-confirms' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/reconciliation/diffs/{diff_id}/close-requests` — Request Close

First signature. Records a ``manual_close`` action with outcome
``pending_second_sign``. Diff stays in its current status.

**参数：**

- `diff_id` (path, string, required=✅) — 
- `X-Admin-Token` (header, string, required=✅) — 
- `X-Admin-Operator` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/reconciliation/diffs/{diff_id}/close-requests' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/reconciliation/runs` — 后台：对账 run 列表

按 started_at 倒序分页返回对账批次（run）列表，供审计查看历史对账状态。

**参数：**

- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/reconciliation/runs' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/service-packages/` — 后台：服务档位列表

默认仅返回 is_active=true。?include_inactive=true 拉全部（含软删）。按 sort_order 升序。

**参数：**

- `include_inactive` (query, boolean, required=—) — 为 true 时返回 is_active=false 的软删项
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/service-packages/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/service-packages/` — 后台：新建服务档位

code 全局唯一；price 必须 > 0；写 admin_audit_log create + before/after diff。

**参数：**

- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `201` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/service-packages/' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `DELETE /api/v1/admin/service-packages/{pkg_id}` — 后台：软删服务档位

软删（is_active=false）。**不真删**，避免历史 Order.service_type 引用断裂（ADR-0043 §2.2 弱外键策略）。写 admin_audit_log soft_delete。

**参数：**

- `pkg_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X DELETE 'https://api.yiluan.example.com/api/v1/admin/service-packages/{pkg_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/service-packages/{pkg_id}` — 后台：服务档位详情

返回单个服务档位全部字段 (code/name/price/is_active/sort_order/description/created_at/updated_at)。未找到 404。该端点不过滤 is_active，admin 可查软删项用于恢复场景。

**参数：**

- `pkg_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/service-packages/{pkg_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PATCH /api/v1/admin/service-packages/{pkg_id}` — 后台：更新服务档位

部分更新 name/price/is_active/sort_order/description；code 不可改（避免历史 Order.service_type 引用断裂）。写 admin_audit_log update + before/after diff。

**参数：**

- `pkg_id` (path, string, required=✅) — 
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
curl -X PATCH 'https://api.yiluan.example.com/api/v1/admin/service-packages/{pkg_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/telemetry/events` — 埋点事件列表（admin）

分页查询 `telemetry_events`。支持按 event_type 精确匹配、时间区间、user_id 过滤。默认按 created_at 倒序。

**参数：**

- `event_type` (query, —, required=—) — 精确匹配 event_type
- `user_id` (query, —, required=—) — 按上报用户过滤
- `since` (query, —, required=—) — created_at >= since
- `until` (query, —, required=—) — created_at < until
- `limit` (query, integer, required=—) — 
- `offset` (query, integer, required=—) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/telemetry/events' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/users` — 后台：用户列表

分页查询用户，支持按 role / is_active / phone 模糊过滤。

**参数：**

- `role` (query, —, required=—) — 角色 tag，如 patient / companion / admin
- `is_active` (query, —, required=—) — 
- `phone` (query, —, required=—) — 手机号模糊匹配
- `reveal` (query, boolean, required=—) — 是否返回明文手机号；置 true 会写入 reveal_pii 审计日志。
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
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/users' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/users/{user_id}` — 后台：用户详情

返回单个用户详情；phone 默认脱敏，?reveal=true 返回明文并写 reveal_pii 审计；同时写入 view_user_detail 审计行。

**参数：**

- `user_id` (path, string, required=✅) — 
- `reveal` (query, boolean, required=—) — 是否返回明文手机号；置 true 会写入 reveal_pii 审计日志。
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/disable` — 后台：停用用户

将指定用户置为 is_active=False。操作必须给出原因，写入 admin_audit_log。

**参数：**

- `user_id` (path, string, required=✅) — 
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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/disable' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/users/{user_id}/enable` — 后台：启用用户

重新启用被停用账号；操作写入 admin_audit_log。

**参数：**

- `user_id` (path, string, required=✅) — 
- `Authorization` (header, —, required=—) — 
- `X-Admin-Token` (header, —, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/users/{user_id}/enable' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/admin/wallet-ledger/adjustments` — Create Manual Adjustment

人工记一笔调账。强制 ``X-Admin-Operator``；落 admin_audit_log + ledger。

**参数：**

- `X-Admin-Token` (header, string, required=✅) — 
- `X-Admin-Operator` (header, string, required=✅) — 

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
curl -X POST 'https://api.yiluan.example.com/api/v1/admin/wallet-ledger/adjustments' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/admin/wallet-ledger/{user_id}` — List User Ledger

诊断用：查看某 user 的账本流水。

**参数：**

- `user_id` (path, string, required=✅) — 
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 
- `reason` (query, —, required=—) — 
- `companion_id` (query, —, required=—) — 可选，仅接受与路径 user_id 一致的陪诊师 user_id；用于后台 H5 从陪诊师选择器传入。不一致返回 422。
- `X-Admin-Token` (header, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/admin/wallet-ledger/{user_id}' \
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
