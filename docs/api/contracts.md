# contracts

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景



## 鉴权要求

—

## 限流

—

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/contracts/{contract_id}` | 用户查看合同详情 + 签名 URL (AC#2) |
| `POST` | `/api/v1/contracts/{contract_id}/accept` | 用户勾选合同同意 (AC#1) |

## 端点详情

### `GET /api/v1/contracts/{contract_id}` — 用户查看合同详情 + 签名 URL (AC#2)

返合同元信息 + ContractStorage 签名 URL (TTL=15min, ViewerRole.USER, ADR-0046 §3.1).

`status != 'active'` (生成中 / 失败 / 作废) 时 signed_url 为 null, 前端按 status 显示对应文案.

写 `user_audit_logs.contract_viewed` 留痕 (PIPL 取证).

**参数：**

- `contract_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/contracts/{contract_id}' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/contracts/{contract_id}/accept` — 用户勾选合同同意 (AC#1)

用户在支付前勾选 '我已阅读并同意' checkbox 时调用。

写 `user_audit_logs.contract_acceptance_clicked` 留痕 (含 user_agent + client_ip, PIPL/民法典电子合同取证). **幂等**: 同一用户重复 accept 同一 contract 会写多条 audit log (取证需要看到所有勾选时点), 但 contract 状态不变.

**参数：**

- `contract_id` (path, string, required=✅) — 

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `404` | 资源不存在 |
| `422` | 校验失败（FastAPI 标准） |
| `429` | 触发限流 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/contracts/{contract_id}/accept' \
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
