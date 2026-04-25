# 健康检查（health）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

K8s / ACA 探针使用：

- `GET /health`：liveness，进程存活即返回 200。
- `GET /readiness` & `GET /api/v1/readiness`：检查 DB + Redis，全部 OK → 200，任一失败 → 503。
- `GET /api/v1/ping`：通用连通性测试。

## 鉴权要求

无鉴权。

## 限流

无限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 健康检查（liveness） |
| `GET` | `/api/v1/ping` | Ping测试 |
| `GET` | `/api/v1/readiness` | 就绪检查（readiness） |
| `GET` | `/health` | 健康检查（liveness, root） |
| `GET` | `/readiness` | 就绪检查（readiness, root） |

## 端点详情

### `GET /api/v1/health` — 健康检查（liveness）

liveness 探针：进程活着即返回 200，不检查外部依赖。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/health' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/ping` — Ping测试

简单的连通性测试接口，返回pong和API版本号。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/ping' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/readiness` — 就绪检查（readiness）

检查数据库（SELECT 1）和 Redis（PING）连接。全部 OK → 200；任一失败 → 503。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/readiness' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /health` — 健康检查（liveness, root）

根路径 liveness 探针，仅返回进程存活状态。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/health' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /readiness` — 就绪检查（readiness, root）

根路径就绪探针，等价于 /api/v1/readiness：检查 DB + Redis。任一失败 → 503。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/readiness' \
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
