# YiLuAn 后端 API 文档

本文档由 `backend/scripts/dump_openapi.py` 与 `backend/scripts/build_api_md.py` 自动生成。
源文件位于 `docs/api/openapi.json`，请勿手动编辑 `<tag>.md` 内的端点列表。

## 通用文档

- [认证流程（OTP / JWT / 微信登录）](./AUTHENTICATION.md)
- [错误码与前端处理建议](./ERROR_HANDLING.md)
- [openapi.json](./openapi.json) — 机读 OpenAPI 3 规范

## 按业务模块索引

### [认证（auth）](./auth.md)

认证模块负责用户身份鉴别。提供两条登录链路：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/auth/apple/login` | Apple Sign-In 登录 |
| `POST` | `/api/v1/auth/bind-phone` | 为当前账号绑定手机号 |
| `POST` | `/api/v1/auth/refresh` | 刷新访问令牌 |
| `POST` | `/api/v1/auth/send-otp` | 发送短信验证码 |
| `POST` | `/api/v1/auth/verify-otp` | 校验短信验证码并登录 |
| `POST` | `/api/v1/auth/wechat-login` | 微信小程序登录 |

### [用户基础资料（users）](./users.md)

用户账号本身的资料：昵称、头像、可用角色、活跃角色切换、注销。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `DELETE` | `/api/v1/users/me` | 注销当前账户 |
| `GET` | `/api/v1/users/me` | 获取当前登录用户信息 |
| `PUT` | `/api/v1/users/me` | 更新当前用户基本资料 |
| `POST` | `/api/v1/users/me/avatar` | 上传头像 |
| `POST` | `/api/v1/users/me/switch-role` | 切换活跃角色 |

### [患者档案（patients）](./patients.md)

患者档案补充医疗背景信息（紧急联系人、过敏史、常用医院），用于下单时自动填充。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/users/me/patient-profile` | 获取我的患者档案 |
| `PUT` | `/api/v1/users/me/patient-profile` | 更新我的患者档案 |

### [陪诊师档案（companions）](./companions.md)

陪诊师入驻、资料维护、列表搜索、详情查看、个人统计。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/companions` | 搜索陪诊师列表 |
| `POST` | `/api/v1/companions/apply` | 申请成为陪诊师 |
| `GET` | `/api/v1/companions/me` | 获取我的陪诊师档案 |
| `PUT` | `/api/v1/companions/me` | 更新我的陪诊师档案 |
| `GET` | `/api/v1/companions/me/stats` | 获取陪诊师统计概览 |
| `GET` | `/api/v1/companions/{companion_id}` | 查看陪诊师详情 |

### [医院数据（hospitals）](./hospitals.md)

医院搜索、筛选项、按经纬度定位最近省市、详情查询。`POST /hospitals/seed` 仅用于初始化部署。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/hospitals` | 分页搜索医院 |
| `GET` | `/api/v1/hospitals/filters` | 获取医院筛选项 |
| `GET` | `/api/v1/hospitals/nearest-region` | 按经纬度定位最近的省市 |
| `POST` | `/api/v1/hospitals/seed` | 导入种子医院数据（运维） |
| `GET` | `/api/v1/hospitals/{hospital_id}` | 获取医院详情 |

### [订单（orders）](./orders.md)

订单贯穿『下单 → 支付 → 接单 → 服务 → 完成 / 退款』完整生命周期。常见状态：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/orders` | 获取我的订单列表 |
| `POST` | `/api/v1/orders` | 患者创建订单 |
| `POST` | `/api/v1/orders/check-expired` | 扫描并取消过期订单（运维/定时任务） |
| `GET` | `/api/v1/orders/{order_id}` | 获取订单详情 |
| `POST` | `/api/v1/orders/{order_id}/accept` | 陪诊师接单 |
| `POST` | `/api/v1/orders/{order_id}/cancel` | 取消订单 |
| `POST` | `/api/v1/orders/{order_id}/complete` | 完成订单 |
| `POST` | `/api/v1/orders/{order_id}/confirm-start` | 患者确认开始服务 |
| `POST` | `/api/v1/orders/{order_id}/pay` | 对订单发起支付 |
| `POST` | `/api/v1/orders/{order_id}/refund` | 患者申请退款 |
| `POST` | `/api/v1/orders/{order_id}/reject` | 陪诊师拒单 |
| `POST` | `/api/v1/orders/{order_id}/request-start` | 陪诊师发起开始服务请求 |
| `POST` | `/api/v1/orders/{order_id}/start` | 陪诊师直接开始服务 |

### [订单评价（reviews）](./reviews.md)

已完成订单的患者评价。**单订单仅可评价一次**。陪诊师详情页通过『陪诊师评价列表』展示历史评价。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/companions/{companion_id}/reviews` | 陪诊师收到的评价列表 |
| `GET` | `/api/v1/orders/{order_id}/review` | 查看订单评价 |
| `POST` | `/api/v1/orders/{order_id}/review` | 提交订单评价 |

### [订单聊天（chats）](./chats.md)

订单参与方在订单生命周期内进行实时沟通。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/chats/{order_id}/messages` | 获取订单聊天历史 |
| `POST` | `/api/v1/chats/{order_id}/messages` | 发送一条聊天消息（HTTP 兜底） |
| `POST` | `/api/v1/chats/{order_id}/read` | 批量标记订单消息为已读 |

### [站内通知（notifications）](./notifications.md)

站内通知列表、未读数、标记已读、设备推送 token 注册/注销。推送通过 APNs / FCM / 微信订阅消息分发。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/notifications` | 分页获取站内通知 |
| `DELETE` | `/api/v1/notifications/device-token` | 注销设备推送 token |
| `POST` | `/api/v1/notifications/device-token` | 注册设备推送 token |
| `POST` | `/api/v1/notifications/read-all` | 一键全部已读 |
| `GET` | `/api/v1/notifications/unread-count` | 未读通知数 |
| `POST` | `/api/v1/notifications/{notification_id}/read` | 标记单条通知已读 |

### [钱包（wallet）](./wallet.md)

钱包余额、累计收入/支出、流水分页查询。提现走运营后台审核流，暂未对前端开放。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/wallet` | 获取钱包概览 |
| `GET` | `/api/v1/wallet/transactions` | 获取钱包交易流水 |

### [支付回调（payment-callbacks）](./payment-callbacks.md)

微信支付（含模拟 provider）回调入口。**这两个端点由微信服务端调用，并非前端 / App 调用。**

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/payments/wechat/callback` | 微信支付 - 支付结果回调 |
| `POST` | `/api/v1/payments/wechat/refund-callback` | 微信支付 - 退款结果回调 |

### [运营后台 - 通用（admin）](./admin.md)

运营后台对订单、用户的管理操作（查询、强制状态、退款、停用/启用账号）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/companions/` | 后台：待审核陪诊师列表 |
| `POST` | `/api/v1/admin/companions/{companion_id}/approve` | 后台：批准陪诊师入驻 |
| `POST` | `/api/v1/admin/companions/{companion_id}/reject` | 后台：驳回陪诊师申请 |
| `GET` | `/api/v1/admin/orders` | 后台：查询全部订单 |
| `POST` | `/api/v1/admin/orders/{order_id}/admin-refund` | 后台：管理员退款 |
| `POST` | `/api/v1/admin/orders/{order_id}/force-status` | 后台：强制修改订单状态 |
| `GET` | `/api/v1/admin/users` | 后台：用户列表 |
| `POST` | `/api/v1/admin/users/{user_id}/disable` | 后台：停用用户 |
| `POST` | `/api/v1/admin/users/{user_id}/enable` | 后台：启用用户 |

### [运营后台 - 陪诊师审核（admin-companions）](./admin-companions.md)

审核员审核陪诊师入驻申请：列表 / 批准 / 驳回（带原因）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/companions/` | 后台：待审核陪诊师列表 |
| `POST` | `/api/v1/admin/companions/{companion_id}/approve` | 后台：批准陪诊师入驻 |
| `POST` | `/api/v1/admin/companions/{companion_id}/reject` | 后台：驳回陪诊师申请 |

### [健康检查（health）](./health.md)

K8s / ACA 探针使用：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 健康检查（liveness） |
| `GET` | `/api/v1/ping` | Ping测试 |
| `GET` | `/api/v1/readiness` | 就绪检查（readiness） |
| `GET` | `/health` | 健康检查（liveness, root） |
| `GET` | `/readiness` | 就绪检查（readiness, root） |
