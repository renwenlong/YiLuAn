"""OpenAPI 元数据：tags_metadata、全局 description、通用错误响应模板。"""

API_DESCRIPTION = """
# YiLuAn 一路安 后端 API

「一路安」是一款连接患者与陪诊师的服务平台。本 API 文档涵盖：

- **认证（auth）**：手机号 OTP 登录、微信登录、JWT 刷新
- **用户与角色（users / patients / companions）**：账户、患者档案、陪诊师档案
- **医院与订单（hospitals / orders）**：医院搜索、下单、状态流转
- **支付与钱包（payment-callbacks / wallet）**：微信支付回调、钱包流水
- **沟通（chats / notifications）**：订单内聊天、站内通知
- **后台管理（admin / admin-companions）**：审核、强制状态、退款
- **运维（health）**：liveness / readiness 探针

## 鉴权

绝大多数 `/api/v1/*` 接口需要在请求头携带：

```
Authorization: Bearer <access_token>
```

`access_token` 由 `/api/v1/auth/verify-otp`、`/api/v1/auth/wechat-login`、
`/api/v1/auth/refresh` 等端点签发。详见 [AUTHENTICATION.md](../../docs/api/AUTHENTICATION.md)。

## 错误响应

所有 4xx / 5xx 错误统一返回如下结构：

```json
{ "detail": "human-readable message" }
```

详见 [ERROR_HANDLING.md](../../docs/api/ERROR_HANDLING.md)。
"""

TAGS_METADATA = [
    {
        "name": "auth",
        "description": "**认证模块**。手机号验证码登录、微信小程序登录、刷新令牌、绑定手机号。"
                       "登录链路：`/auth/send-otp` → `/auth/verify-otp` → 携带 `Authorization: Bearer ...` 调用其他接口。",
    },
    {
        "name": "users",
        "description": "**用户基础资料**。当前用户信息、修改资料、上传头像、切换角色（患者/陪诊师）、注销账户。",
    },
    {
        "name": "patients",
        "description": "**患者档案**。紧急联系人、就医备注、常用医院等就诊辅助信息。",
    },
    {
        "name": "companions",
        "description": "**陪诊师档案**。陪诊师列表、详情、申请成为陪诊师、更新服务信息、个人统计。",
    },
    {
        "name": "hospitals",
        "description": "**医院数据**。按关键词/省市区/等级/标签搜索医院、查询筛选项、根据经纬度定位最近区域。"
                       "列表查询带 1 小时 Redis 缓存。",
    },
    {
        "name": "orders",
        "description": "**订单全生命周期**。下单、查询、状态流转（接单 / 开始 / 完成 / 拒绝 / 取消）、支付、退款、过期清理。",
    },
    {
        "name": "reviews",
        "description": "**订单评价**。患者对已完成订单的评分与评论，以及陪诊师收到的评价聚合。",
    },
    {
        "name": "chats",
        "description": "**订单内聊天**。HTTP 用于历史拉取与已读标记；实时收发请使用 `WS /api/v1/ws/chat/{order_id}`。",
    },
    {
        "name": "notifications",
        "description": "**站内通知**。通知列表、未读数、标记已读、设备推送 token 注册。",
    },
    {
        "name": "wallet",
        "description": "**钱包与流水**。当前用户钱包余额概览、交易流水分页查询。",
    },
    {
        "name": "payment-callbacks",
        "description": "**支付平台回调**（服务端到服务端）。微信支付的支付/退款异步通知接收端，"
                       "**不要求 JWT**，由签名验证保护，且通过 `payment_callback_log` 做幂等。",
    },
    {
        "name": "admin",
        "description": "**平台后台**。订单查询/强制状态/管理员退款、用户启用/停用。要求当前用户具备 `admin` 角色。",
    },
    {
        "name": "admin-companions",
        "description": "**陪诊师审核后台**。待审核列表、批准、驳回。鉴权方式：请求头 `X-Admin-Token: <token>`。",
    },
    {
        "name": "health",
        "description": "**健康检查**。`/health` 为 liveness（仅返回进程存活），`/readiness` 检查 DB+Redis 连接。",
    },
]


# 通用错误响应（供路由层 responses= 复用）。
COMMON_ERROR_RESPONSES = {
    400: {
        "description": "请求参数错误",
        "content": {
            "application/json": {
                "example": {"detail": "Invalid request payload"}
            }
        },
    },
    401: {
        "description": "未鉴权或令牌无效",
        "content": {
            "application/json": {
                "example": {"detail": "Not authenticated"}
            }
        },
    },
    403: {
        "description": "无权限",
        "content": {
            "application/json": {
                "example": {"detail": "Forbidden"}
            }
        },
    },
    404: {
        "description": "资源不存在",
        "content": {
            "application/json": {
                "example": {"detail": "Resource not found"}
            }
        },
    },
    422: {
        "description": "校验失败（FastAPI 标准）",
        "content": {
            "application/json": {
                "example": {
                    "detail": [
                        {"loc": ["body", "phone"], "msg": "Invalid phone number format", "type": "value_error"}
                    ]
                }
            }
        },
    },
    429: {
        "description": "触发限流",
        "content": {
            "application/json": {
                "example": {"detail": "Rate limit exceeded: 5 per 1 minute"}
            }
        },
    },
    500: {
        "description": "服务器内部错误",
        "content": {
            "application/json": {
                "example": {"detail": "Internal server error"}
            }
        },
    },
}


def err(*codes: int) -> dict:
    """挑选若干错误码组成 responses 字典。"""
    return {c: COMMON_ERROR_RESPONSES[c] for c in codes if c in COMMON_ERROR_RESPONSES}
