# 医路安 — 医疗陪诊服务平台

连接需要就医陪伴的患者与专业陪诊师，提供全程陪诊、半程陪诊、代办跑腿等服务。

> **最后更新：** 2026-04-21（Sprint W17 / Release Wrap-Up Day 4）
> **后端测试：** 573 passed / 1 xfailed　**前端测试：** 165 passed / 30 suites　**iOS 测试：** 57 passed (XCTest 离线快照)
> **新增子项目：** `admin-h5/`（管理后台 MVP，陪诊师审核）
> **关键能力新增：** 微信真实支付/退款回调（幂等）、Aliyun SMS、OTP 暴破防护、订单过期自动退款、统一 outbound 可靠性装饰器（timeout + retry + circuit breaker）、`/readiness` 健康探针、APScheduler 部署、WS 同用户连接数限制
> **关键决策索引：** ADR-0026（outbound 可靠性）/ D-018~D-020（调度+连接限制）/ D-027（callback log TTL + OSS 归档）/ D-028（零提交日告警）/ D-029-D-030（Sprint W17 backlog）/ D-031（fix 与 test 优先级）/ D-032（XcodeGen）

---

## 技术选型

| 层级 | 技术 | 说明 |
|------|------|------|
| **iOS** | SwiftUI + MVVM | 原生 iOS 客户端, iOS 17+, @MainActor + ObservableObject |
| **微信小程序** | 原生框架 (WXML + WXSS + JS) | 30 页面, 9 组件, Observer 状态管理 |
| **后端** | Python 3.11 + FastAPI 0.115 (async) | 异步全链路, Pydantic v2 校验 |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic | asyncpg 驱动, Repository 泛型模式 |
| **数据库** | PostgreSQL 15 | Azure Flexible Server (生产) / SQLite aiosqlite (测试) |
| **缓存** | Redis 7 | OTP 存储 (TTL 300s), 发送频率限制 (TTL 60s) |
| **认证** | JWT HS256 (python-jose) | Access Token 30min + Refresh Token 7天 |
| **HTTP 客户端** | httpx (async) | 微信 jscode2session API 调用 |
| **文件存储** | Azure Blob Storage | avatars + chat-images 两个容器 |
| **容器** | Docker + Azure Container Apps | python:3.11-slim, 1-5 replicas |
| **实时通信** | WebSocket (原生) | 基于订单的聊天室, JWT query 参数认证 |
| **支付** | 微信支付 v3 + 模拟支付双 provider | provider 抽象 + 回调幂等 + 自动退款 + partial refund，回退到 mock 用于本地/测试 |
| **短信** | Aliyun SMS + Mock 双 provider | provider 抽象 + 发送限频 + OTP 5 次锁 15min 暴破防护 |
| **可靠性** | 统一 outbound 装饰器 | timeout + retry(指数退避) + circuit breaker（half-open 探活），覆盖支付 / SMS / Redis Pub/Sub |
| **调度** | APScheduler (AsyncIOScheduler) | 订单过期检查、迟到回调自动退款、callback log TTL 清理 |
| **健康检查** | `/readiness` + `/api/v1/readiness` | DB + Redis 双探活，Kubernetes/ACA 就绪探针使用 |
| **管理后台** | admin-h5（纯静态 HTML/JS） | 陪诊师审核 MVP，复用后端 admin token auth |
| **速率限制** | slowapi | 全局 60/min, OTP 发送 5/min |
| **日志** | 请求中间件 | method, path, status_code, duration_ms |

### 后端依赖

```
# Web 框架
fastapi==0.115.6         uvicorn[standard]==0.34.0     python-multipart==0.0.18

# 数据库
sqlalchemy[asyncio]==2.0.36    asyncpg==0.30.0         alembic==1.14.1

# 校验与配置
pydantic==2.10.4         pydantic-settings==2.7.1

# 认证
python-jose[cryptography]==3.3.0    passlib[bcrypt]==1.7.4

# 缓存
redis[hiredis]==5.2.1

# 云存储
azure-storage-blob==12.24.0

# HTTP & 速率限制
httpx==0.28.1            slowapi==0.1.9             pyyaml==6.0.2

# 测试
pytest==8.3.4            pytest-asyncio==0.25.0     aiosqlite==0.20.0

# 代码质量
black==24.10.0           ruff==0.8.6
```

---

## 项目结构

### 后端 `backend/`

```
backend/
├── app/
│   ├── main.py                # FastAPI 入口, lifespan, CORS, 日志中间件, 速率限制
│   ├── config.py              # pydantic-settings: DB/Redis/JWT/微信/Azure/APNs/SMS
│   ├── database.py            # create_async_engine (pool_size=20, max_overflow=10)
│   ├── dependencies.py        # get_db, get_current_user (HTTPBearer → JWT 解析)
│   ├── exceptions.py          # AppException 体系 (400/401/403/404/409)
│   ├── api/v1/
│   │   ├── router.py          # v1 路由聚合 + /ping
│   │   ├── auth.py            # OTP登录 + 微信登录 + JWT刷新 + 手机绑定 (限频5/min)
│   │   ├── users.py           # 用户资料 CRUD + 头像上传
│   │   ├── patients.py        # 患者档案 CRUD
│   │   ├── companions.py      # 陪诊师列表/详情/申请/更新/统计
│   │   ├── hospitals.py       # 医院搜索/详情/种子数据
│   │   ├── orders.py          # 订单 CRUD + 状态操作 + 支付/退款
│   │   ├── chats.py           # 聊天消息 + 已读回执
│   │   ├── reviews.py         # 评价提交/查看
│   │   ├── notifications.py   # 通知列表/已读/设备令牌
│   │   └── ws.py              # WebSocket 聊天 (/ws/chat/{order_id})
│   ├── models/                # 13 个 SQLAlchemy 2.0 模型
│   │   ├── base.py            # DeclarativeBase
│   │   ├── user.py            # users + UserRole enum
│   │   ├── patient_profile.py # patient_profiles
│   │   ├── companion_profile.py # companion_profiles + VerificationStatus enum
│   │   ├── hospital.py        # hospitals
│   │   ├── order.py           # orders + ServiceType/OrderStatus enum + 状态机
│   │   ├── order_status_history.py # order_status_history
│   │   ├── payment.py         # payments
│   │   ├── chat_message.py    # chat_messages + MessageType enum
│   │   ├── review.py          # reviews
│   │   ├── notification.py    # notifications + NotificationType enum
│   │   ├── device_token.py    # device_tokens
│   │   ├── payment_callback_log.py # 支付回调审计 + TTL (D-027)
│   │   └── admin_audit_log.py # 管理后台操作审计
│   ├── schemas/               # Pydantic v2 请求/响应模型
│   │   ├── auth.py            # SendOTP, VerifyOTP, WeChatLogin, TokenResponse...
│   │   ├── user.py            # UpdateUserRequest, UserResponse, AvatarUploadResponse
│   │   ├── patient.py         # PatientProfileResponse, UpdatePatientProfileRequest
│   │   ├── companion.py       # CompanionList/Detail/Stats Response, Apply/Update Request
│   │   ├── hospital.py        # HospitalResponse, HospitalListResponse
│   │   ├── order.py           # CreateOrderRequest, OrderResponse, PaymentResponse
│   │   ├── chat.py            # SendMessageRequest, ChatMessageResponse
│   │   ├── review.py          # CreateReviewRequest, ReviewResponse
│   │   └── notification.py    # NotificationResponse, RegisterDeviceRequest
│   ├── services/              # 24 个业务服务（含 7 个 provider 实现）
│   │   ├── auth.py            # AuthService (OTP, JWT, 微信登录, 手机绑定)
│   │   ├── user.py            # UserService
│   │   ├── patient_profile.py # PatientProfileService
│   │   ├── companion_profile.py # CompanionProfileService (含 get_stats)
│   │   ├── hospital.py        # HospitalService (含种子数据)
│   │   ├── order.py           # OrderService (状态机, 支付, 反规范化)
│   │   ├── chat.py            # ChatService
│   │   ├── review.py          # ReviewService (含 avg_rating 反规范化)
│   │   ├── notification.py    # NotificationService (含触发器)
│   │   ├── upload.py          # UploadService (Azure Blob)
│   │   ├── wechat.py          # WeChatAPIClient (jscode2session)
│   │   ├── payment_service.py # 统一支付编排（+ 显式抛错 + 结构化错误日志, C6）
│   │   ├── sms.py             # SMS 服务编排（+ OTP 暴破防护, C1）
│   │   ├── wallet.py          # 钱包余额 + 退款入账
│   │   ├── admin_audit.py     # 后台操作审计写入
│   │   └── providers/         # provider 抽象（基类 + 工厂 + 具体实现）
│   │       ├── payment/       # base / factory / mock / wechat（v3 真实回调 + 幂等）
│   │       └── sms/           # base / factory / mock / aliyun + rate_limit
│   ├── repositories/          # 11 个数据仓储 (泛型 BaseRepository[T])
│   │   ├── base.py            # BaseRepository[T] — get_by_id, create, update, delete
│   │   ├── user.py            # by_phone, by_wechat_openid
│   │   ├── patient_profile.py # by_user_id, upsert
│   │   ├── companion_profile.py # by_user_id, search (area/skip/limit)
│   │   ├── hospital.py        # search (keyword), seed
│   │   ├── order.py           # by_patient, by_companion, count_today, sum_earnings
│   │   ├── payment.py         # by_order_id
│   │   ├── chat_message.py    # by_order_id, mark_read
│   │   ├── review.py          # by_order_id, by_companion
│   │   ├── notification.py    # by_user_id, unread_count, mark_all_read
│   │   └── device_token.py    # by_user_id, by_token
│   └── core/
│       ├── security.py        # JWT 签发/验证 (create_access_token, decode_token)
│       ├── redis.py           # init_redis, get_redis (app.state 注入)
│       ├── rate_limit.py      # slowapi limiter 配置
│       └── logging.py         # 日志初始化
├── alembic/                   # 数据库迁移
│   ├── env.py                 # 异步迁移环境
│   └── versions/              # 迁移版本文件
├── tests/                     # 573 passed / 1 xfailed（pytest-asyncio + 全 provider mock）
│   ├── conftest.py            # SQLite 内存 DB + FakeRedis + 全套 seed fixtures
│   ├── test_auth.py           # OTP 登录全流程 (32 tests)
│   ├── test_wechat_auth.py    # 微信登录 + 手机绑定 (12 tests)
│   ├── test_users.py          # 用户资料 CRUD
│   ├── test_avatar.py         # 头像上传
│   ├── test_patient_profile.py # 患者档案
│   ├── test_companion_profile.py # 陪诊师档案
│   ├── test_companion_stats.py # 陪诊师统计
│   ├── test_hospitals.py      # 医院搜索
│   ├── test_orders.py         # 订单全流程 + 状态机
│   ├── test_chats.py          # 聊天消息
│   ├── test_reviews.py        # 评价 + 反规范化
│   ├── test_notifications.py  # 通知 CRUD
│   ├── test_notifications_triggers.py # 通知触发器
│   ├── test_device_token.py   # 设备令牌
│   ├── test_rate_limit.py     # 速率限制
│   ├── test_health.py         # 健康检查 + /readiness
│   ├── test_payment_callback_idempotency.py # 微信支付回调幂等 + 退款失败语义（C2/C6）
│   ├── test_payment_provider*.py        # 支付 provider 抽象与切换
│   ├── test_sms_*.py                    # Aliyun SMS provider + OTP 暴破 + 并发限频（C1/C5/A21-12）
│   ├── test_outbound_decorator.py       # timeout/retry/circuit breaker 单元（A5/ADR-0026）
│   ├── test_admin_*.py                  # admin token + companions 审核 + audit log（B1/A6）
│   ├── test_alembic_smoke.py            # PG+alembic schema 漂移 smoke（TD-CI-01）
│   └── test_ws_*.py                     # WS 限连接数 + Pub/Sub outbound 可靠性（D-020/A21-03）
├── Dockerfile                 # python:3.11-slim
├── docker-compose.yaml        # api + postgres:15-alpine + redis:7-alpine
├── requirements.txt
├── pyproject.toml             # black (100 chars) + ruff (E/F/I/W) + pytest
└── alembic.ini
```

### 微信小程序 `wechat/`

```
wechat/
├── app.js / app.json / app.wxss    # 入口: onLaunch 检查 token → 路由
├── config/index.js                  # API_BASE_URL, WS_BASE_URL
├── services/                        # 10 个网络服务模块
│   ├── api.js                      # wx.request Promise 封装 + Bearer 注入 + 401 队列刷新
│   ├── auth.js                     # wechatLogin, refreshToken, sendOTP, bindPhone, logout
│   ├── user.js                     # getMe, updateMe, getPatientProfile, uploadAvatar
│   ├── order.js                    # getOrders, createOrder, orderAction, payOrder
│   ├── companion.js                # getCompanions, getCompanionDetail, getCompanionStats
│   ├── hospital.js                 # getHospitals, getHospitalDetail
│   ├── chat.js                     # getChatMessages, sendChatMessage
│   ├── review.js                   # submitReview, getCompanionReviews
│   ├── notification.js             # getNotifications, markRead, getUnreadCount
│   └── websocket.js                # connectSocket + 心跳 + 指数退避重连
├── store/index.js                   # Observer 模式全局状态 (subscribe/setState)
├── utils/
│   ├── token.js                    # JWT 存取 + base64 解码过期检测
│   ├── validate.js                 # ^1[3-9]\d{9}$ / ^\d{6}$
│   ├── format.js                   # 日期/价格/手机号(138****8000)/订单状态
│   └── constants.js                # SERVICE_TYPES + ORDER_STATUS 枚举
├── components/                      # 7 个可复用组件 (各含 js/json/wxml/wxss)
│   ├── service-card/               # 服务类型卡片 (图标+名称+价格)
│   ├── order-card/                 # 订单摘要卡片
│   ├── companion-card/             # 陪诊师列表项
│   ├── rating-stars/               # 评分星星 (展示/交互双模式)
│   ├── empty-state/                # 空状态占位
│   ├── loading-overlay/            # 全局加载遮罩
│   └── chat-bubble/                # 聊天气泡 (文字/图片/时间)
├── pages/                           # 21 个页面
│   ├── login/                      # 微信一键登录
│   ├── role-select/                # 角色选择 (患者/陪诊师)
│   ├── patient/home/               # 患者首页 (3服务卡片 + 推荐陪诊师)
│   ├── patient/create-order/       # 多步表单 (服务→医院→日期→确认)
│   ├── patient/order-detail/       # 患者订单详情 + 操作
│   ├── companion/home/             # 陪诊师工作台 (统计 API + 待接单)
│   ├── companion/available-orders/ # 待接订单列表
│   ├── companion/order-detail/     # 陪诊师订单详情 + 操作
│   ├── orders/                     # 我的订单 (状态Tab筛选 + 下拉/上拉)
│   ├── chat/list/                  # 会话列表
│   ├── chat/room/                  # 聊天室 (WebSocket 实时)
│   ├── companion-detail/           # 陪诊师资料页
│   ├── notification/               # 通知列表
│   ├── review/write/               # 写评价
│   ├── profile/                    # 个人中心
│   ├── profile/edit/               # 编辑资料
│   ├── profile/bind-phone/         # 绑定手机号 (OTP 验证)
│   ├── profile/settings/           # 设置 (清除缓存)
│   └── profile/about/              # 关于 (版本信息)
└── __tests__/                       # 165 passed / 30 suites（Jest 单元测试）
    ├── setup.js                    # wx 全局对象 mock
    ├── pages/
    │   ├── bind-phone.test.js     # 绑定手机页面 (3 tests)
    │   └── notification.test.js   # 通知页面
    ├── services/                   # api(6), auth(7), user(4), order(3),
    │                               # companion(6), hospital(3), chat, review,
    │                               # notification, websocket
    ├── store/                      # store(4)
    └── utils/                      # token(4), format(3), validate(2)
```

### iOS `ios/YiLuAn/`

```
YiLuAn/
├── YiLuAnApp.swift                    # @main, 根据登录态路由
├── Configuration/
│   └── AppConfig.swift               # API Base URL, WebSocket URL
├── Core/
│   ├── Networking/
│   │   ├── APIClient.swift           # URLSession 封装 + JSONDecoder (snakeCase)
│   │   ├── APIEndpoint.swift         # 32 个静态端点定义
│   │   └── WebSocketClient.swift     # URLSessionWebSocketTask + 指数退避重连
│   ├── Storage/
│   │   └── KeychainManager.swift     # Token Keychain 安全存储
│   ├── Models/                        # 7 个 Codable 模型
│   │   ├── User.swift                # User + CompanionProfile
│   │   ├── AuthModels.swift          # TokenResponse, OTPRequest...
│   │   ├── Order.swift               # Order + ServiceType enum
│   │   ├── Hospital.swift            # Hospital
│   │   ├── ChatMessage.swift         # ChatMessage + MessageType
│   │   ├── Review.swift              # Review
│   │   ├── Payment.swift             # Payment
│   │   └── Notification.swift        # AppNotification + NotificationType
│   └── Extensions/
│       └── View+Extensions.swift
├── Features/
│   ├── Auth/                          # 登录模块
│   │   ├── ViewModels/AuthViewModel.swift
│   │   └── Views/ LoginView, OTPInputView, RoleSelectionView
│   ├── Patient/                       # 患者模块
│   │   ├── ViewModels/PatientProfileViewModel.swift
│   │   └── Views/ PatientHomeView (服务导航+推荐), PatientProfileEditView
│   ├── Companion/                     # 陪诊师模块
│   │   ├── ViewModels/CompanionProfileViewModel.swift (含 loadStats)
│   │   └── Views/ CompanionHomeView (实时统计), CompanionDetailView,
│   │             CompanionListView, CompanionProfileEditView
│   ├── Order/                         # 订单模块
│   │   ├── ViewModels/OrderViewModel.swift (含 searchHospitals)
│   │   └── Views/ CreateOrderView (4步表单+医院搜索),
│   │             OrderListView, OrderDetailView, AvailableOrdersView
│   ├── Chat/                          # 聊天模块
│   │   ├── ViewModels/ChatViewModel.swift
│   │   └── Views/ ChatListView (会话列表), ChatRoomView (实时聊天)
│   ├── Review/                        # 评价模块
│   │   ├── ViewModels/ReviewViewModel.swift
│   │   └── Views/ ReviewViews.swift
│   ├── Notifications/                 # 通知模块
│   │   ├── ViewModels/NotificationViewModel.swift
│   │   └── Views/ NotificationListView
│   └── Profile/                       # 个人资料模块
│       ├── ViewModels/ProfileViewModel.swift
│       └── Views/ ProfileView, ProfileEditView
└── SharedViews/
    └── MainTabView.swift              # 双角色 TabView (患者4tab / 陪诊师4tab)
```

---

## 数据库设计

共 **13 张表**（含 `payment_callback_log`、`admin_audit_log`），全部使用 UUID 主键 + UTC 时区时间戳。Alembic 已累计 **18 个迁移版本**（最近变更：`payments` 新增 `trade_no` / `prepay_id` / `refund_id` / `callback_raw` 4 列 + `trade_no` 唯一索引；`OrderStatus` enum 新增 `rejected_by_companion` / `expired`；`payment_callback_log` 新增 `expires_at` 用于 TTL）。

### users

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | 用户唯一标识 |
| `phone` | VARCHAR(20) | UNIQUE, INDEX, nullable | 手机号 (微信用户初始为 NULL) |
| `wechat_openid` | VARCHAR(128) | UNIQUE, INDEX, nullable | 微信 OpenID |
| `wechat_unionid` | VARCHAR(128) | UNIQUE, INDEX, nullable | 微信 UnionID (多平台) |
| `role` | ENUM(patient, companion) | nullable | 用户角色 (注册后选择) |
| `display_name` | VARCHAR(100) | nullable | 显示名称 |
| `avatar_url` | VARCHAR(500) | nullable | 头像 URL |
| `is_active` | BOOLEAN | default True | 账号启用状态 |
| `created_at` | TIMESTAMP WITH TZ | not null | 创建时间 |
| `updated_at` | TIMESTAMP WITH TZ | not null, auto-update | 更新时间 |

> **UNIQUE + nullable 设计**: PostgreSQL UNIQUE 约束允许多个 NULL 值，因此微信用户初始无手机号不会冲突。

### patient_profiles

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK(users), UNIQUE, INDEX | 一对一关联用户 |
| `emergency_contact` | VARCHAR(100) | nullable | 紧急联系人姓名 |
| `emergency_phone` | VARCHAR(20) | nullable | 紧急联系人电话 |
| `medical_notes` | TEXT | nullable | 病历备注 |
| `preferred_hospital_id` | UUID | nullable | 偏好医院 |
| `created_at` / `updated_at` | TIMESTAMP WITH TZ | | |

### companion_profiles

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK(users), UNIQUE, INDEX | 一对一关联用户 |
| `real_name` | VARCHAR(50) | not null | 真实姓名 |
| `id_number` | VARCHAR(30) | nullable | 身份证号 |
| `certifications` | TEXT | nullable | 资质证书 |
| `service_area` | VARCHAR(200) | nullable | 服务区域 |
| `bio` | TEXT | nullable | 个人简介 |
| `avg_rating` | FLOAT | default 0.0 | 平均评分 (反规范化) |
| `total_orders` | INTEGER | default 0 | 总完成订单数 (反规范化) |
| `verification_status` | ENUM(pending, verified, rejected) | default pending | 认证状态 |
| `created_at` / `updated_at` | TIMESTAMP WITH TZ | | |

### hospitals

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `name` | VARCHAR(200) | INDEX, not null | 医院名称 |
| `address` | VARCHAR(500) | nullable | 详细地址 |
| `level` | VARCHAR(50) | nullable | 医院等级 (三甲/三乙/二甲...) |
| `latitude` | FLOAT | nullable | 纬度 |
| `longitude` | FLOAT | nullable | 经度 |
| `created_at` | TIMESTAMP WITH TZ | | |

### orders

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `order_number` | VARCHAR(32) | UNIQUE, INDEX | 人类可读编号 PZ20260330xxxx |
| `patient_id` | UUID | FK(users), INDEX | 患者 |
| `companion_id` | UUID | FK(users), INDEX, nullable | 陪诊师 (接单后填入) |
| `hospital_id` | UUID | FK(hospitals) | 就诊医院 |
| `service_type` | ENUM(full_accompany, half_accompany, errand) | not null | 服务类型 |
| `status` | ENUM(7种状态) | INDEX, default created | 订单状态 |
| `appointment_date` | VARCHAR(10) | not null | 预约日期 YYYY-MM-DD |
| `appointment_time` | VARCHAR(5) | not null | 预约时间 HH:MM |
| `description` | TEXT | nullable | 备注 |
| `price` | FLOAT | not null | 服务价格 |
| `hospital_name` | VARCHAR(200) | nullable | 反规范化 |
| `companion_name` | VARCHAR(100) | nullable | 反规范化 |
| `patient_name` | VARCHAR(100) | nullable | 反规范化 |
| `created_at` / `updated_at` | TIMESTAMP WITH TZ | | |

### order_status_history

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `order_id` | UUID | FK(orders), INDEX | |
| `from_status` | VARCHAR(50) | nullable | 变更前状态 |
| `to_status` | VARCHAR(50) | not null | 变更后状态 |
| `changed_by` | UUID | FK(users) | 操作人 |
| `note` | TEXT | nullable | 变更原因 |
| `created_at` | TIMESTAMP WITH TZ | | 变更时间 |

### payments

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `order_id` | UUID | FK(orders), INDEX | |
| `user_id` | UUID | FK(users) | 操作人 |
| `amount` | FLOAT | not null | 金额 |
| `payment_type` | VARCHAR(20) | not null | `pay` 或 `refund` |
| `status` | VARCHAR(20) | default success | MVP 模拟支付始终成功 |
| `created_at` | TIMESTAMP WITH TZ | | |

### chat_messages

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `order_id` | UUID | FK(orders), INDEX | 所属订单 (一个订单一个聊天室) |
| `sender_id` | UUID | FK(users) | 发送者 |
| `type` | ENUM(text, image, system) | default text | 消息类型 |
| `content` | TEXT | not null | 消息内容 |
| `is_read` | BOOLEAN | default false | 已读状态 |
| `created_at` | TIMESTAMP WITH TZ | | |

### reviews

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `order_id` | UUID | FK(orders), UNIQUE | 一个订单一条评价 |
| `patient_id` | UUID | FK(users) | 评价者 |
| `companion_id` | UUID | FK(users) | 被评者 |
| `rating` | INTEGER | not null | 1-5 星 |
| `content` | TEXT | nullable | 评价文字 (5-500字) |
| `patient_name` | VARCHAR(100) | nullable | 反规范化 |
| `created_at` | TIMESTAMP WITH TZ | | |

### notifications

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK(users), INDEX | 接收者 |
| `type` | ENUM(order_status_changed, new_message, new_order, review_received, system) | | 通知类型 |
| `title` | VARCHAR(200) | not null | 标题 |
| `body` | TEXT | not null | 内容 |
| `reference_id` | VARCHAR(100) | nullable | 关联实体 ID |
| `is_read` | BOOLEAN | default false | |
| `created_at` | TIMESTAMP WITH TZ | | |

### device_tokens

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK(users), INDEX | |
| `token` | VARCHAR(500) | UNIQUE | 推送令牌 (APNs/FCM) |
| `device_type` | VARCHAR(20) | not null | ios / android / wechat |
| `created_at` | TIMESTAMP WITH TZ | | |

### 缓存设计 (Redis)

| Key 模式 | TTL | 说明 |
|----------|-----|------|
| `otp:{phone}` | 300s (5分钟) | OTP 验证码存储 |
| `otp:rate:{phone}` | 60s | OTP 发送频率限制 |

### ER 关系图

```
users ─────────┬──── 1:1 ──── patient_profiles
               ├──── 1:1 ──── companion_profiles
               ├──── 1:N ──── orders (as patient)
               ├──── 1:N ──── orders (as companion)
               ├──── 1:N ──── notifications
               └──── 1:N ──── device_tokens

orders ────────┬──── 1:N ──── order_status_history
               ├──── 1:N ──── payments
               ├──── 1:N ──── chat_messages
               └──── 1:1 ──── reviews

hospitals ─────┴──── 1:N ──── orders
```

---

## 订单状态机

### 状态定义

| 状态 | 中文 | 颜色标识 | 说明 |
|------|------|----------|------|
| `created` | 待接单 | `#FAAD14` (黄) | 患者创建订单, 等待陪诊师接单 |
| `accepted` | 已接单 | `#1890FF` (蓝) | 陪诊师已接单, 等待服务开始 |
| `in_progress` | 进行中 | `#1890FF` (蓝) | 陪诊服务进行中 |
| `completed` | 已完成 | `#52C41A` (绿) | 服务完成, 等待评价 |
| `reviewed` | 已评价 | `#52C41A` (绿) | 患者已评价, 订单关闭 |
| `cancelled_by_patient` | 患者取消 | `#FF4D4F` (红) | 患者主动取消 |
| `cancelled_by_companion` | 陪诊师取消 | `#FF4D4F` (红) | 陪诊师取消接单 |

### 状态流转

```
                    ┌──────────────────────────────────────┐
                    │          cancelled_by_patient         │
                    └──────────────────────────────────────┘
                              ▲                ▲
                              │                │
created ──→ accepted ──→ in_progress ──→ completed ──→ reviewed
                │
                ├──→ cancelled_by_patient (accepted 后取消可能扣费)
                └──→ cancelled_by_companion
```

**取消规则:**
- `created` → `cancelled_by_patient`: 免费取消
- `accepted` → `cancelled_by_patient`: 可能产生取消费用
- `accepted` → `cancelled_by_companion`: 陪诊师主动取消

### 定价规则 (MVP)

| 服务类型 | 英文标识 | 价格 |
|---------|----------|------|
| 全程陪诊 | `full_accompany` | ¥299 |
| 半程陪诊 | `half_accompany` | ¥199 |
| 代办跑腿 | `errand` | ¥149 |

---

## API 设计

共 32 个端点 (含 1 个 WebSocket)。所有 REST 端点前缀 `/api/v1`。

### 基础

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 健康检查 → `{"status": "healthy", "version": "0.1.0"}` |
| GET | `/api/v1/ping` | 无 | API 连通性 → `{"message": "pong", "version": "v1"}` |

### 认证 Auth — `/api/v1/auth/*`

| 方法 | 路径 | 认证 | 限频 | 请求体 | 响应 |
|------|------|------|------|--------|------|
| POST | `/auth/send-otp` | 无 | 5/min | `{phone}` | `{message}` |
| POST | `/auth/verify-otp` | 无 | — | `{phone, code}` | `TokenResponse` |
| POST | `/auth/refresh` | 无 | — | `{refresh_token}` | `RefreshTokenResponse` |
| POST | `/auth/wechat-login` | 无 | — | `{code}` | `TokenResponse` |
| POST | `/auth/bind-phone` | Bearer | — | `{phone, code}` | `UserResponse` |

> **开发便利**: OTP `000000` 始终有效; 微信 code `dev_test_code` 绕过微信服务器。

### 用户 Users — `/api/v1/users/*`

| 方法 | 路径 | 认证 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/users/me` | Bearer | — | `UserResponse` |
| PUT | `/users/me` | Bearer | `{role?, display_name?}` | `UserResponse` |
| POST | `/users/me/avatar` | Bearer | `multipart/form-data (file)` | `{avatar_url}` |

### 患者档案 — `/api/v1/users/me/patient-profile`

| 方法 | 路径 | 认证 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/users/me/patient-profile` | Bearer | — | `PatientProfileResponse` |
| PUT | `/users/me/patient-profile` | Bearer | `{emergency_contact?, emergency_phone?, medical_notes?, preferred_hospital_id?}` | `PatientProfileResponse` |

### 陪诊师 Companions — `/api/v1/companions/*`

| 方法 | 路径 | 认证 | 参数 | 响应 |
|------|------|------|------|------|
| GET | `/companions` | Bearer | `?area=&page=1&page_size=20` | `CompanionListResponse[]` |
| GET | `/companions/me/stats` | Bearer | — | `{today_orders, total_orders, avg_rating, total_earnings}` |
| GET | `/companions/{id}` | Bearer | — | `CompanionDetailResponse` |
| POST | `/companions/apply` | Bearer | `{real_name, id_number?, certifications?, service_area?, bio?}` | `CompanionDetailResponse` (201) |
| PUT | `/companions/me` | Bearer | `{service_area?, bio?, certifications?}` | `CompanionDetailResponse` |

### 医院 Hospitals — `/api/v1/hospitals/*`

| 方法 | 路径 | 认证 | 参数 | 响应 |
|------|------|------|------|------|
| GET | `/hospitals` | 无 | `?keyword=&page=1&page_size=20` | `{items, total}` |
| GET | `/hospitals/{id}` | 无 | — | `HospitalResponse` |
| POST | `/hospitals/seed` | 无 | — | `{seeded: count}` |

### 订单 Orders — `/api/v1/orders/*`

| 方法 | 路径 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------------|------|
| POST | `/orders` | Bearer | `{service_type, hospital_id, appointment_date, appointment_time, description?}` | `OrderResponse` (201) |
| GET | `/orders` | Bearer | `?status=&page=1&page_size=20` | `{items, total}` |
| GET | `/orders/{id}` | Bearer | — | `OrderResponse` |
| POST | `/orders/{id}/accept` | Bearer | — | `OrderResponse` |
| POST | `/orders/{id}/start` | Bearer | — | `OrderResponse` |
| POST | `/orders/{id}/complete` | Bearer | — | `OrderResponse` |
| POST | `/orders/{id}/cancel` | Bearer | — | `OrderResponse` |
| POST | `/orders/{id}/pay` | Bearer | — | `PaymentResponse` |
| POST | `/orders/{id}/refund` | Bearer | — | `PaymentResponse` |

### 聊天 Chats — `/api/v1/chats/*`

| 方法 | 路径 | 认证 | 请求体/参数 | 响应 |
|------|------|------|------------|------|
| GET | `/chats/{order_id}/messages` | Bearer | `?page=1&page_size=50` | `{items, total}` |
| POST | `/chats/{order_id}/messages` | Bearer | `{content, type?}` | `ChatMessageResponse` (201) |
| POST | `/chats/{order_id}/read` | Bearer | — | `{marked_read: count}` |

### 评价 Reviews

| 方法 | 路径 | 认证 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/orders/{id}/review` | Bearer | `{rating: 1-5, content: 5-500字}` | `ReviewResponse` (201) |
| GET | `/orders/{id}/review` | Bearer | — | `ReviewResponse` |
| GET | `/companions/{id}/reviews` | Bearer | `?page=1&page_size=20` | `{items, total}` |

### 通知 Notifications — `/api/v1/notifications/*`

| 方法 | 路径 | 认证 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/notifications` | Bearer | `?page=1&page_size=20` | `{items, total}` |
| GET | `/notifications/unread-count` | Bearer | — | `{count}` |
| POST | `/notifications/{id}/read` | Bearer | — | `{success}` |
| POST | `/notifications/read-all` | Bearer | — | `{marked_read: count}` |
| POST | `/notifications/device-token` | Bearer | `{token, device_type}` | `DeviceTokenResponse` |
| DELETE | `/notifications/device-token` | Bearer | `{token}` | `{success}` |

### WebSocket — `/ws/chat/{order_id}`

| 连接 | 认证 | 说明 |
|------|------|------|
| `ws://host/ws/chat/{order_id}?token={jwt}` | query 参数 | 实时聊天 |

**消息格式：**
- 发送: `{"type": "text|image|system", "content": "..."}`
- 接收: `{"id", "order_id", "sender_id", "type", "content", "is_read", "created_at"}`
- 心跳: 发 `{"type": "ping"}` → 收 `{"type": "pong"}`
- 错误码: 4001 (认证失败), 4003 (非订单参与者), 4004 (订单不存在)

### 数据模型

```
TokenResponse:
  access_token: str
  refresh_token: str
  token_type: "bearer"
  user: UserResponse

UserResponse:
  id: uuid
  phone: str | null
  role: "patient" | "companion" | null
  display_name: str | null
  avatar_url: str | null
  is_active: bool
  created_at: datetime

OrderResponse:
  id: uuid
  order_number: str           # PZ20260330xxxx
  patient_id / companion_id / hospital_id: uuid
  service_type / status: str
  appointment_date / appointment_time: str
  description: str | null
  price: float
  hospital_name / companion_name / patient_name: str | null
  created_at / updated_at: datetime
```

---

## 认证流程

### 手机号 OTP 登录

```
客户端                          后端                           Redis
  │                              │                              │
  ├─ POST /auth/send-otp ──────►│                              │
  │   {phone: "138xxxx"}        ├─ 检查频率限制 ──────────────►│ GET otp:rate:{phone}
  │                              │◄────────────────────────────┤
  │                              ├─ 生成6位OTP ────────────────►│ SET otp:{phone} TTL=300s
  │                              ├─ 设置频率限制 ──────────────►│ SET otp:rate:{phone} TTL=60s
  │◄──── {message: "sent"} ─────┤                              │
  │                              │                              │
  ├─ POST /auth/verify-otp ────►│                              │
  │   {phone, code}             ├─ 校验 OTP ──────────────────►│ GET otp:{phone}
  │                              │◄────────────────────────────┤
  │                              ├─ 查/创建用户 → 签发 JWT      │
  │◄──── TokenResponse ─────────┤                              │
```

### 微信小程序登录

```
小程序                          后端                       微信服务器
  │                              │                            │
  ├─ wx.login() → code           │                            │
  ├─ POST /auth/wechat-login ──►│                            │
  │   {code: "0a1b2c..."}       ├─ jscode2session(code) ────►│
  │                              │◄── {openid, session_key} ──┤
  │                              ├─ 按 openid 查/创建用户      │
  │                              ├─ 签发 JWT                   │
  │◄──── TokenResponse ─────────┤                            │
  │                              │                            │
  ├─ (可选) POST /auth/bind-phone ──► OTP 验证 → 绑定手机号   │
```

### JWT 策略

| 参数 | 值 |
|------|-----|
| 算法 | HS256 |
| Access Token 有效期 | 30 分钟 |
| Refresh Token 有效期 | 7 天 |
| Payload | `{sub: user_id, type: "access"/"refresh", exp, iat}` |
| 401 处理 | 客户端自动用 refresh token 静默刷新, 失败则跳转登录 |

---

## 架构设计

```
┌─────────────┐     ┌──────────────────┐
│   iOS App   │     │  微信小程序       │
│  (SwiftUI)  │     │  (WXML/WXSS/JS)  │
└──────┬──────┘     └────────┬─────────┘
       │ HTTPS/WSS           │ HTTPS/WSS
       └──────────┬──────────┘
                  ▼
    ┌─────────────────────────────┐
    │   Azure Container Apps      │
    │   FastAPI (1-5 replicas)    │
    │   ┌─────────────────────┐   │
    │   │ API Layer (路由)     │   │
    │   │ Service Layer (逻辑) │   │
    │   │ Repository (数据访问) │   │
    │   └─────────────────────┘   │
    └─────┬──────────────┬────────┘
          │              │
          ▼              ▼
┌─────────────────┐ ┌────────────┐
│ PostgreSQL 15   │ │  Redis 7   │
│ (Azure Flex)    │ │ (Azure)    │
│ B1ms, VNet      │ │ Basic C0   │
└─────────────────┘ └────────────┘

          ┌──────────────────────┐
          │  Azure Blob Storage  │
          │  (avatars, images)   │
          └──────────────────────┘
```

### 后端分层架构

```
Request → API Route → Service → Repository → Database
                        ↓
                    Exceptions → 全局异常处理器 → HTTP Response
```

| 层级 | 职责 | 文件 |
|------|------|------|
| **API Route** | 请求校验, 依赖注入, HTTP 响应 | `api/v1/*.py` (含 admin 子路由) |
| **Service** | 业务逻辑, 事务编排, 触发器 | `services/*.py` + `services/providers/**/*` (24 个) |
| **Repository** | 数据访问, SQL 查询封装 | `repositories/*.py` (泛型基类 `BaseRepository[T]`) |
| **Schema** | Pydantic v2 请求/响应模型 | `schemas/*.py` (9 个模块) |
| **Model** | SQLAlchemy 2.0 ORM 映射 | `models/*.py` (13 个表) |

### 异常处理体系

| 异常 | HTTP 状态码 | 使用场景 |
|------|------------|----------|
| `BadRequestException` | 400 | OTP 过期/错误, 无效请求 |
| `UnauthorizedException` | 401 | JWT 无效/过期, 账号禁用 |
| `ForbiddenException` | 403 | 权限不足 (角色校验) |
| `NotFoundException` | 404 | 资源不存在 |
| `ConflictException` | 409 | 手机号已被占用, 重复申请 |

---

## 本地开发

### 前置要求

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端运行时 |
| Docker + Docker Compose | latest | PostgreSQL + Redis |
| Node.js | 16+ | 微信小程序测试 (Jest) |
| npm | 8+ | 依赖管理 |
| Xcode | 15+ | iOS 开发 (macOS only) |
| 微信开发者工具 | latest | 小程序调试/预览 |

### 方式一：Docker Compose 全栈启动 (推荐)

```bash
cd backend

# 1. 启动所有服务 (API + PostgreSQL + Redis)
docker compose up -d

# 2. 查看日志
docker compose logs -f api

# 3. 访问
#    API:         http://localhost:8000
#    Swagger UI:  http://localhost:8000/docs
#    ReDoc:       http://localhost:8000/redoc

# 4. 初始化医院种子数据
curl -X POST http://localhost:8000/api/v1/hospitals/seed

# 5. 停止
docker compose down

# 6. 停止并清除数据
docker compose down -v
```

Docker Compose 包含的服务：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `api` | 本地 Dockerfile 构建 | 8000 | FastAPI + Uvicorn |
| `db` | postgres:15-alpine | 5432 | 用户 postgres, 密码 postgres, 库 yiluan |
| `redis` | redis:7-alpine | 6379 | 内存缓存 |

### 方式二：本地直接运行 (开发调试)

```bash
cd backend

# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动外部服务 (只启动 DB + Redis, 不启动 API 容器)
docker compose up -d db redis

# 4. 创建 .env 文件 (可选, 也可用默认值)
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=my-dev-secret-key
DEBUG=true
ENVIRONMENT=development
EOF

# 5. 数据库迁移 (如果 alembic/versions/ 下有迁移文件)
alembic upgrade head

# 6. 启动开发服务器 (热重载)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. 初始化医院种子数据
curl -X POST http://localhost:8000/api/v1/hospitals/seed
```

### 运行测试

```bash
# 后端 (无需启动 Docker, 使用 SQLite 内存 + FakeRedis)
cd backend
python -m pytest tests/ -v              # 573 passed / 1 xfailed
python -m pytest tests/ -v -k "auth"    # 只运行认证测试
python -m pytest tests/ -v --tb=short   # 简短错误信息

# 微信小程序
cd wechat
npm install
npm test                                # 165 passed / 30 suites
npm test -- --verbose                   # 详细输出
npm test -- --watch                     # 监听模式

# 代码检查
cd backend
black --check app/ tests/              # 格式检查
ruff check app/ tests/                 # lint 检查
```

### 微信小程序开发

```bash
# 1. 安装测试依赖
cd wechat
npm install

# 2. 修改 API 地址 (连接本地后端)
#    编辑 config/index.js:
#    API_BASE_URL: 'http://localhost:8000/api/v1'
#    WS_BASE_URL:  'ws://localhost:8000'

# 3. 用微信开发者工具打开 wechat/ 目录
#    - AppID: 使用测试号或真实 AppID
#    - 不校验合法域名 (本地开发需勾选)

# 4. 测试登录
#    - 微信登录: 使用 code "dev_test_code" 绕过微信服务器
#    - OTP 登录: 使用验证码 "000000"
```

### iOS 开发

```bash
# 1. 用 Xcode 打开项目
open ios/YiLuAn.xcodeproj

# 2. 修改 API 地址
#    编辑 Configuration/AppConfig.swift:
#    apiBaseURL = URL(string: "http://localhost:8000/api/v1")!
#    wsBaseURL  = URL(string: "ws://localhost:8000")!

# 3. 选择模拟器 (iPhone 15 Pro) → Cmd+R 运行
# 4. 支持 iOS 17.0+
```

### 数据库迁移

```bash
cd backend

# 生成新迁移 (自动检测模型变化)
alembic revision --autogenerate -m "描述变更"

# 执行迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1

# 查看当前版本
alembic current

# 查看历史
alembic history
```

---

## 环境变量

所有配置通过 `pydantic-settings` 管理，支持 `.env` 文件和环境变量（环境变量优先）。

### 应用基础

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `APP_NAME` | str | `"YiLuAn API"` | 应用名称 |
| `APP_VERSION` | str | `"0.1.0"` | API 版本 |
| `DEBUG` | bool | `true` | 调试模式 (启用 Swagger UI/ReDoc) |
| `ENVIRONMENT` | str | `"development"` | 运行环境标识 |

### 数据库

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | str | `postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan` | 异步数据库连接 URL |

> 连接池: `pool_size=20`, `max_overflow=10`。`DEBUG=true` 时输出 SQL 日志到控制台。

### Redis

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `REDIS_URL` | str | `redis://localhost:6379/0` | Redis 连接 URL |

### JWT 认证

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `JWT_SECRET_KEY` | str | `"dev-secret-key-change-in-production"` | **生产环境必须修改** |
| `JWT_ALGORITHM` | str | `"HS256"` | 签名算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | int | `30` | Access Token 过期时间 (分钟) |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | int | `7` | Refresh Token 过期时间 (天) |

### 微信小程序

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `WECHAT_APP_ID` | str | `""` | 小程序 AppID |
| `WECHAT_APP_SECRET` | str | `""` | 小程序 AppSecret |

> 开发模式下 code 为 `dev_test_code` 时跳过微信服务器调用。

### Azure 存储

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `AZURE_STORAGE_CONNECTION_STRING` | str | `""` | Azure Blob 连接字符串 |
| `AZURE_STORAGE_CONTAINER_AVATARS` | str | `"avatars"` | 头像容器名 |
| `AZURE_STORAGE_CONTAINER_CHAT` | str | `"chat-images"` | 聊天图片容器名 |

### Apple 推送通知 (APNs)

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `APNS_KEY_ID` | str | `""` | APNs Key ID |
| `APNS_TEAM_ID` | str | `""` | Apple Team ID |
| `APNS_BUNDLE_ID` | str | `"com.yiluan.app"` | iOS Bundle ID |

### 其他

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `SMS_PROVIDER` | str | `"mock"` | 短信服务商 (mock: 不发真实短信) |
| `CORS_ORIGINS` | list | `["*"]` | 允许的跨域来源 (**生产环境应限制**) |

### 最小 `.env` 示例 (本地开发)

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=my-local-dev-secret
```

### 生产环境 `.env` 示例

```env
DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/yiluan
REDIS_URL=redis://:password@redis-host:6380/0
JWT_SECRET_KEY=<随机生成的256位密钥>
DEBUG=false
ENVIRONMENT=production
CORS_ORIGINS=["https://your-domain.com"]
WECHAT_APP_ID=wx1234567890
WECHAT_APP_SECRET=<secret>
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
APNS_KEY_ID=ABC123
APNS_TEAM_ID=DEF456
SMS_PROVIDER=aliyun
```

> **安全提醒**: `.env` 文件已在 `.gitignore` 中，不会被提交到版本控制。

---

## 实施阶段

| Phase | 名称 | 状态 | 后端 | 前端 |
|-------|------|------|------|------|
| **0** | 项目脚手架 | ✅ 完成 | FastAPI + SQLAlchemy async + Docker + BaseRepository + pytest | Xcode 项目 + APIClient + 小程序骨架 |
| **1** | 认证系统 | ✅ 完成 | users 表, OTP, JWT, 微信登录, 手机绑定 | iOS: Login/OTP/RoleSelect; 小程序: 页面框架 + 组件 |
| **2** | 用户资料 + 医院 | ✅ 完成 | patient/companion profiles, 头像上传, 医院种子数据 | ProfileView, HospitalPicker |
| **3** | 订单系统 | ✅ 完成 | 订单 CRUD, 状态机, 定价, 模拟支付 | CreateOrder 多步表单, OrderDetail, 双角色首页 |
| **4** | 实时聊天 + 评价 + 通知 UI | ✅ 完成 | WebSocket 聊天, 评价/通知 CRUD | ChatRoom, WriteReview, Notifications |
| **5** | 反规范化 + 触发器 + 基础设施 | ✅ 完成 | avg_rating 反规范化, 通知触发器, 设备令牌, 日志, 速率限制 | 通知列表页, 聊天列表 |
| **6** | 推送通知 | ⏭️ 跳过 | APNs 集成 | 推送权限, 深度链接 |
| **7** | 功能完整性收尾 | ✅ 完成 | 陪诊师统计 API | 全部 placeholder 替换为真实实现; 小程序: 绑定手机/设置/关于 |

### 测试统计

| 平台 | 框架 | 测试数 | 状态 |
|------|------|--------|------|
| 后端 | pytest + pytest-asyncio | **573 passed / 1 xfailed** | ✅ 全部通过（含支付幂等、SMS 限频、outbound 装饰器、admin 审核、PG+alembic smoke）|
| 微信小程序 | Jest | **165 / 30 suites** | ✅ 全部通过 |
| iOS | XCTest（离线快照） | **57 passed** | ✅ macOS runner workflow 已 stub（A21-10），4/22 起跑 GitHub Actions |

---

## 关键设计决策

| 决策 | 原因 |
|------|------|
| 反规范化 avg_rating / total_orders | 陪诊师列表页是高频读路径, 避免 JOIN 聚合 |
| 反规范化 hospital_name / patient_name / companion_name 到 orders | 订单列表页不需要额外 JOIN |
| 人类可读 order_number (PZ20260329xxxx) | 客服沟通方便, UUID 不适合口头传达 |
| WebSocket JWT 通过 query 参数 | WebSocket API 不支持自定义 header |
| 模拟支付 (MVP) | 真实支付需企业资质审核, 与开发并行无依赖 |
| Repository 泛型模式 `BaseRepository[T]` | 隔离数据访问, 便于单元测试 mock |
| Phone nullable + UNIQUE | 微信用户可后续绑定手机, PG UNIQUE 允许多 NULL |
| OTP 开发 bypass `000000` | 开发/测试环境无需真实短信 |
| 微信登录 dev bypass `dev_test_code` | 测试环境无需微信授权服务器 |
| SQLite aiosqlite 用于测试 | 测试无需外部 PG 实例, CI 友好 |
| 小程序 Observer 状态管理 | 轻量级, 无框架依赖, 适合小程序体量 |
| 401 队列刷新 (小程序 api.js) | 并发请求遇 401 时只刷新一次, 其余排队等待 |
| order_status_history 审计表 | 完整追踪订单状态变更, 支持争议回溯 |
| 连接池 pool_size=20 + max_overflow=10 | 生产环境多副本下平衡连接数与性能 |
| Outbound 统一可靠性装饰器 (ADR-0026) | 所有跨进程出站调用（支付/SMS/Redis Pub/Sub）走 timeout + retry + circuit breaker，故障收敛行为一致、可观测 |
| 支付/SMS Provider 抽象 + 工厂 | 真实 provider（微信支付 v3 / Aliyun SMS）与 mock 一键切换，本地与 CI 不依赖外部凭证 |
| 支付回调幂等 (C2) | `payment_callback_log` 唯一约束 + TTL，重复回调安全；7 天后由 APScheduler 归档到 OSS（D-027） |
| 退款失败显式抛错 + 结构化日志 (C6 / D-031) | 拒绝静默吞错；测试以「原子失败」语义校验，避免半成功状态 |
| 订单过期 + 迟到回调自动退款 (C3) | 用户体验侧不留「钱付了但订单已死」的孤儿状态 |
| OTP 暴破防护 (C1) | 同手机号 5 次错码即锁 15min，结合 SMS 发送 5/min 限频 |
| `/readiness` 双探针 (TD-OPS-01) | DB + Redis 真实连通性检查，区分 liveness 与 readiness，给容器编排正确信号 |
| WS 同用户连接数限制 (D-020) | 默认上限 3，超出踢最老连接，避免移动端断网+重连堆积 |
| APScheduler AsyncIOScheduler (D-018/D-019) | 单进程内调度订单过期/迟到回调/日志清理，多副本部署用 leader election 文档化 |
| 零提交日告警 (D-028) | 每日 23:30 检查仓库当日提交数为 0 时报警，反映「项目是否在动」 |
| XcodeGen 管理 iOS 项目 (D-032) | `project.yml` 声明式生成 `.xcodeproj`，避免合并冲突 + 让 macOS runner 一键 generate-and-build |

---

## 可靠性与容错（新）

### 统一 Outbound 装饰器（ADR-0026）

所有「进程出站调用」（HTTP / Redis pub-sub / 第三方 SDK）必须经过 `app/core/outbound.py` 的统一装饰器：

```python
from app.core.outbound import outbound

@outbound(
    name="wechat.pay.unifiedorder",
    timeout=5.0,            # 单次调用上限
    retries=2,              # 失败后再试 2 次
    backoff="exponential",  # 0.5s → 1s → 2s（带 ±20% jitter）
    circuit_breaker={        # half-open 探活
        "failure_threshold": 5,
        "recovery_timeout": 30,
    },
)
async def call_wechat_pay(...): ...
```

**当前接入点：**

| 出站 | 文件 | 说明 |
|------|------|------|
| 微信支付 v3 / 退款 | `services/providers/payment/wechat.py` | 单订单 5s 超时 + 2 retry + 5/30s 熔断 |
| Aliyun SMS | `services/providers/sms/aliyun.py` | 单条 3s 超时 + 1 retry（短信不宜重发太多） |
| Redis Pub/Sub 推送 | `app/ws/pubsub.py`（A21-03） | WS fanout 走 outbound 包装；熔断打开时降级到 best-effort 写库 |

熔断器状态可通过 `/api/v1/internal/circuit-breakers`（admin-only）查看，已接入测试 `test_outbound_decorator.py`（含 Windows 时钟分辨率 flake 修复 / `f3d7ddb`）。

### 速率限制矩阵

| 维度 | 上限 | 实现 |
|------|------|------|
| 全局每客户端 | 60/min | slowapi（`app/core/rate_limit.py`） |
| OTP 发送（同手机号） | 5/min | Redis INCR + EXPIRE 60s（`services/providers/sms/rate_limit.py`） |
| OTP 校验（同手机号） | 5 次错则锁 15min | Redis 计数 + 锁 key（C1 / `ce4259e`） |
| WS 同用户并发连接 | 3（默认） | `app/ws/manager.py`（D-020 / `237039f`） |
| 支付回调入库 | 唯一约束 `(provider, transaction_id)` | DB 层幂等，重复回调读走早期记录 |

---

## 支付与退款（新）

### Provider 抽象

```
backend/app/services/providers/payment/
├── base.py       # PaymentProvider 协议（unifiedorder / query / refund / parse_callback）
├── factory.py    # 根据 settings.payment_provider 选择 wechat | mock
├── mock.py       # 即时确认，本地 / CI / 测试默认
└── wechat.py     # 微信支付 v3：JSAPI 下单 + 真实回调验签 + 退款
```

**切换：** `PAYMENT_PROVIDER=wechat`（生产）/ `PAYMENT_PROVIDER=mock`（默认）。

### 业务保障

| 场景 | 行为 |
|------|------|
| 用户重复点击支付 | DB 层 `payments.trade_no` 唯一索引拦截 |
| 微信回调重复推送 | `payment_callback_log (provider, transaction_id)` 唯一约束 + 第二次直接返回 `success` |
| 用户已超时但回调迟到 | APScheduler 检测到 `order.expired` + 收到 paid 回调时，自动触发退款（C3 / `b127e3c`） |
| 退款 API 失败 | 显式抛 `RefundFailed`，记录结构化错误日志（订单号/金额/provider 错误码），不静默吞（C6 / `d06867a`） |
| 部分退款 | `wallet.refund_to_wallet(amount, reason)` 支持 partial，全链路有 e2e 测试 |
| 本地开发 | `PAYMENT_PROVIDER=mock` + 任意金额即时成功，方便压全流程 |

### 关键迁移

`alembic/versions/` 中支付相关：

- `b7c8d9e0f1a2_*`：`payments` 加 `trade_no` / `prepay_id` / `refund_id` / `callback_raw` 4 列 + `trade_no` 唯一索引；`OrderStatus` enum `ADD VALUE rejected_by_companion / expired`（autocommit block）
- `<later>_*`：新建 `payment_callback_log` 表 + `(provider, transaction_id)` 唯一约束 + `expires_at` TTL（D-027）

---

## 短信（新）

```
backend/app/services/providers/sms/
├── base.py        # SMSProvider 协议（send_otp / send_template）
├── factory.py     # 根据 settings.sms_provider 选择 aliyun | mock
├── mock.py        # 开发环境固定返回 OK，OTP 始终 000000
├── aliyun.py      # Aliyun SMS API 封装（outbound 装饰器：3s timeout + 1 retry）
└── rate_limit.py  # 同手机号 5/min 限频 + 5 次错码 15min 锁（C1）
```

**切换：** `SMS_PROVIDER=aliyun` + `ALIYUN_SMS_ACCESS_KEY_ID/SECRET/SIGN_NAME/TEMPLATE_OTP`（生产）/ `SMS_PROVIDER=mock`（默认）。

**OTP 暴破防护流程：**

```
verify_otp(phone, code) →
  if redis.incr("otp:fail:{phone}") > 5:
      redis.set("otp:lock:{phone}", 1, ex=900)
      raise OTPLocked(retry_after=900)
  if code != stored:
      raise OTPInvalid(remaining=5 - count)
  redis.delete("otp:fail:{phone}")  # 成功即清零
```

---

## 可观测性（新）

### 健康探针

| 端点 | 检查项 | 用途 |
|------|--------|------|
| `GET /` | FastAPI 启动 | liveness（容器还活着） |
| `GET /readiness` | DB 连通 + Redis ping | readiness（容器能接流量） |
| `GET /api/v1/readiness` | 同上，带版本号回显 | 业务链路健康（K8s/ACA 探针） |

### 日志规范

- 中间件 `app/main.py` 输出每请求：`method`, `path`, `status_code`, `duration_ms`, `request_id`
- 业务关键点（支付回调、退款、OTP 暴破触发）走 `logger.info(extra={...})` 结构化字段，便于 Azure Log Analytics / OSS 检索
- 详细规范见 `docs/observability-spec.md`（A7）

### 告警与运维节奏

- **零提交日告警（D-028）**：每日 23:30 cron 扫 git 当日提交数 = 0 则发企业群提醒「项目今日是否在动」
- **零 504 / 异常率**：留给 Azure Monitor + Application Insights，部署清单在 `docs/credentials/checklist.md`
- **PG schema 漂移防护**：`tests/test_alembic_smoke.py`（TD-CI-01）在 PG 容器跑 `alembic upgrade head` + 与 ORM `metadata.create_all` 对比表/列差异

---

## 管理后台 admin-h5（新）

极简 MVP，纯静态 HTML/JS（无构建链），调用后端 admin API：

```
admin-h5/
├── index.html    # 单页：陪诊师审核列表 + 详情抽屉 + 通过/驳回按钮
├── app.js        # fetch + admin token 注入 + 调用 /api/v1/admin/companions/*
├── styles.css
└── README.md     # 本地启动 / 部署到 OSS+CDN 指南
```

**对应后端能力：**

- `services/admin_audit.py` + `models/admin_audit_log.py`：所有审核动作写审计表
- `api/v1/admin/*`：`GET /admin/companions?status=pending`、`POST /admin/companions/{id}/review`
- 独立 `ADMIN_TOKEN` 环境变量 + bearer 校验，与用户 JWT 隔离（B1 / `0498b9a`）

**当前覆盖范围：** 仅陪诊师资质审核（MVP）。订单争议处理、用户管理、报表等仍走数据库直连或后续迭代（见 D-029 backlog）。

---

## 决策与文档索引（新）

### ADR / Decision Log

| 编号 | 主题 | 状态 |
|------|------|------|
| ADR-0026 | 统一 outbound 可靠性装饰器（timeout/retry/circuit breaker） | ✅ 已实施 |
| D-018 | APScheduler 选型（vs Celery / RQ） | ✅ 已实施 |
| D-019 | APScheduler 多副本部署策略（leader election） | 📄 文档化 |
| D-020 | WS 同用户连接数限制（默认 3） | ✅ 已实施 |
| D-027 | 支付回调日志 TTL + OSS 归档 | ✅ 已实施 |
| D-028 | 零提交日告警机制 | ✅ 已实施 |
| D-029 / D-030 | Sprint W17 范围 + 16 项 backlog | 🔄 进行中 |
| D-031 | fix 与 test 在「原子失败」语义下的优先级 | ✅ 已实施 |
| D-032 | 采用 XcodeGen 管理 iOS 项目文件 | ✅ 已实施 |

### 关键文档

- `docs/DEV_SETUP.md`：本地开发 + schema 变更 checklist + 测试账号
- `docs/MIGRATION_AUDIT_2026-04-17.md`：model vs PG schema 差异审计
- `docs/observability-spec.md`：日志/指标/告警 SOP
- `docs/credentials/checklist.md`：生产凭证 backlog + ICP 备案 checklist
- `docs/qa/uat-checklist.md`：发布前 UAT 清单（支付/SMS/部署/回滚/小程序提审）
- `docs/submission/wechat-screenshots.md`：小程序提审截图清单
- `docs/decisions/sprint-w17-backlog.md`：Sprint W17 16 项 feature backlog
- `docs/discuss/`：A21-13 支付备选 provider / A21-14 in-progress→in-service tab 改名讨论
- `TECH_DEBT.md`：已知技术债登记（含 TD-CI-01 / TD-OPS-01 / TD-FE-01 / TD-PAY-01）
