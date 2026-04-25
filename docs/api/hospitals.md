# 医院数据（hospitals）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

医院搜索、筛选项、按经纬度定位最近省市、详情查询。`POST /hospitals/seed` 仅用于初始化部署。

## 鉴权要求

搜索 / 详情接口**不强制登录**；`/hospitals/seed` 应通过运维通道执行。

## 限流

列表查询带 1 小时 Redis 缓存，命中缓存不打 DB。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/hospitals` | 分页搜索医院 |
| `GET` | `/api/v1/hospitals/filters` | 获取医院筛选项 |
| `GET` | `/api/v1/hospitals/nearest-region` | 按经纬度定位最近的省市 |
| `POST` | `/api/v1/hospitals/seed` | 导入种子医院数据（运维） |
| `GET` | `/api/v1/hospitals/{hospital_id}` | 获取医院详情 |

## 端点详情

### `GET /api/v1/hospitals` — 分页搜索医院

按关键词 / 省市区 / 等级 / 标签搜索医院。结果带 1 小时 Redis 缓存，同一组查询参数命中缓存时直接返回。

**参数：**

- `keyword` (query, —, required=—) — 医院名称模糊匹配
- `province` (query, —, required=—) — 省份名称
- `city` (query, —, required=—) — 城市名称
- `district` (query, —, required=—) — 区/县名称
- `level` (query, —, required=—) — 医院等级，如『三甲』
- `tag` (query, —, required=—) — 标签，如『综合』『儿科』
- `page` (query, integer, required=—) — 
- `page_size` (query, integer, required=—) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/hospitals' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/hospitals/filters` — 获取医院筛选项

根据当前选择的省/市级联返回可用的下级筛选条件（省、市、区、等级、标签）。

**参数：**

- `province` (query, —, required=—) — 已选省份
- `city` (query, —, required=—) — 已选城市

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/hospitals/filters' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/hospitals/nearest-region` — 按经纬度定位最近的省市

根据用户当前坐标，返回距离最近的医院所在的省、市，用于首屏自动选择城市。

**参数：**

- `latitude` (query, number, required=✅) — 纬度
- `longitude` (query, number, required=✅) — 经度

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/hospitals/nearest-region' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `POST /api/v1/hospitals/seed` — 导入种子医院数据（运维）

从内置数据文件批量导入医院信息到数据库。**仅在初始化部署或测试环境使用**，线上请通过运维流程而非公开调用。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | 导入完成 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X POST 'https://api.yiluan.example.com/api/v1/hospitals/seed' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `GET /api/v1/hospitals/{hospital_id}` — 获取医院详情

根据医院 ID 返回完整字段（含坐标、等级、标签）。

**参数：**

- `hospital_id` (path, string, required=✅) — 

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `404` | 资源不存在 |
| `422` | Validation Error |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/hospitals/{hospital_id}' \
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
