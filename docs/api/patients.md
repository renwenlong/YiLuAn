# 患者档案（patients）

> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。

## 业务背景

患者档案补充医疗背景信息（紧急联系人、过敏史、常用医院），用于下单时自动填充。

## 鉴权要求

全部接口要求登录。

## 限流

无特殊限流。

## 端点速查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/users/me/patient-profile` | 获取我的患者档案 |
| `PUT` | `/api/v1/users/me/patient-profile` | 更新我的患者档案 |

## 端点详情

### `GET /api/v1/users/me/patient-profile` — 获取我的患者档案

获取当前登录用户的患者档案；不存在则自动创建一条空档案后返回。

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X GET 'https://api.yiluan.example.com/api/v1/users/me/patient-profile' \
  -H 'Authorization: Bearer <access_token>'
```

---

### `PUT /api/v1/users/me/patient-profile` — 更新我的患者档案

更新当前用户的患者档案：紧急联系人、紧急联系人手机号、就医备注、常用医院。

**请求体（JSON）：**

```json
""
```

**响应：**

| 状态码 | 说明 |
| --- | --- |
| `200` | Successful Response |
| `401` | 未鉴权或令牌无效 |
| `422` | 校验失败（FastAPI 标准） |
| `500` | 服务器内部错误 |

**curl 示例：**

```bash
curl -X PUT 'https://api.yiluan.example.com/api/v1/users/me/patient-profile' \
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
