# 医路安 — 医疗陪诊服务平台

连接需要就医陪伴的患者与专业陪诊师，提供全程陪诊、半程陪诊、代办跑腿等服务。

---

## 技术选型

| 层级 | 技术 | 说明 |
|------|------|------|
| **iOS** | SwiftUI + MVVM + Combine | 原生 iOS 客户端, iOS 17+ |
| **微信小程序** | 原生框架 (WXML + WXSS + JS) | 14 页面, 7 组件, Observer 状态管理 |
| **后端** | Python 3.11 + FastAPI (async) | 异步全链路, Pydantic v2 校验 |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic | asyncpg 驱动, Repository 模式 |
| **数据库** | PostgreSQL 15 | Azure Flexible Server (生产) / SQLite aiosqlite (测试) |
| **缓存** | Redis 7 | OTP 存储 (TTL 300s), 发送频率限制 (TTL 60s) |
| **认证** | JWT (python-jose) | Access Token 30min + Refresh Token 7天 |
| **HTTP 客户端** | httpx (async) | 微信 jscode2session API 调用 |
| **文件存储** | Azure Blob Storage | 头像、聊天图片 |
| **容器** | Docker + Azure Container Apps | python:3.11-slim, 1-5 replicas |
| **实时通信** | WebSocket + Redis pub/sub | 跨实例消息路由 |
| **支付** | 模拟支付 (MVP) | 即时确认, 无需企业资质 |

### 后端依赖

```
fastapi[standard]    uvicorn[standard]    sqlalchemy[asyncio]
asyncpg              aiosqlite            alembic
redis[hiredis]       httpx                python-jose[cryptography]
pydantic-settings    python-multipart     passlib[bcrypt]
```

---

## 项目结构

### 后端 `backend/`

```
backend/
├── app/
│   ├── main.py                # FastAPI 入口, CORS, 异常处理器, 路由挂载
│   ├── config.py              # pydantic-settings: DB/Redis/JWT/微信/Azure/APNs
│   ├── database.py            # create_async_engine + async_sessionmaker
│   ├── dependencies.py        # get_db, get_current_user (JWT 解析)
│   ├── exceptions.py          # AppException 体系 (400/401/403/404/409)
│   ├── api/v1/
│   │   ├── auth.py            # OTP登录 + 微信登录 + JWT刷新 + 手机绑定
│   │   └── users.py           # 用户资料 CRUD
│   ├── models/
│   │   ├── base.py            # DeclarativeBase + UUID PK mixin
│   │   └── user.py            # users 表 (phone, wechat_openid, role...)
│   ├── schemas/
│   │   ├── auth.py            # OTP/微信/刷新/绑定 请求+响应
│   │   └── user.py            # UpdateUserRequest
│   ├── services/
│   │   ├── auth.py            # AuthService (OTP, JWT, 微信登录, 手机绑定)
│   │   ├── user.py            # UserService (查询, 更新)
│   │   └── wechat.py          # WeChatAPIClient (jscode2session)
│   ├── repositories/
│   │   ├── base.py            # BaseRepository[T] 泛型 (CRUD)
│   │   └── user.py            # UserRepository (by_phone, by_wechat_openid)
│   └── core/
│       ├── security.py        # JWT 签发/验证
│       └── redis.py           # Redis 连接管理
├── tests/                     # 44 个 pytest-asyncio 测试
│   ├── conftest.py            # SQLite 内存 DB + FakeRedis + fixtures
│   ├── test_auth.py           # 32 个认证测试
│   └── test_wechat_auth.py    # 12 个微信认证测试
├── Dockerfile                 # python:3.11-slim 多阶段构建
├── docker-compose.yaml        # api + postgres:15-alpine + redis:7-alpine
├── requirements.txt
└── pyproject.toml             # black + ruff + pytest 配置
```

### 微信小程序 `wechat/`

```
wechat/
├── app.js / app.json / app.wxss    # 入口: onLaunch 检查 token → 路由
├── config/index.js                  # API_BASE_URL, WS_BASE_URL
├── services/                        # 8 个网络服务模块
│   ├── api.js                      # wx.request Promise 封装 + Bearer 注入 + 401 队列刷新
│   ├── auth.js                     # wechatLogin, refreshToken, sendOTP, bindPhone, logout
│   ├── user.js                     # getMe, updateMe
│   ├── order.js                    # getOrders, createOrder, orderAction
│   ├── companion.js / hospital.js  # 陪诊师/医院查询
│   ├── chat.js                     # getChatMessages
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
├── pages/                           # 14 个页面
│   ├── login/                      # 微信一键登录
│   ├── role-select/                # 角色选择 (患者/陪诊师)
│   ├── patient/home/               # 患者首页 (3服务卡片 + 推荐陪诊师)
│   ├── patient/create-order/       # 多步表单 (服务→医院→日期→确认)
│   ├── patient/order-detail/       # 患者订单详情 + 操作
│   ├── companion/home/             # 陪诊师工作台 (统计+待接单)
│   ├── companion/available-orders/ # 待接订单列表
│   ├── companion/order-detail/     # 陪诊师订单详情 + 操作
│   ├── orders/                     # 我的订单 (状态Tab筛选 + 下拉/上拉)
│   ├── chat/list/                  # 会话列表
│   ├── chat/room/                  # 聊天室 (WebSocket 实时)
│   ├── companion-detail/           # 陪诊师资料页
│   ├── review/write/               # 写评价
│   └── profile/                    # 个人中心 (含手机绑定入口)
└── __tests__/                       # 33 个 Jest 单元测试
    ├── setup.js                    # wx 全局对象 mock
    ├── services/                   # api(6), auth(7), user(3), order(3)
    ├── store/                      # store(4)
    └── utils/                      # token(4), format(3), validate(2)
```

### iOS `YiLuAn/`

```
YiLuAn/
├── YiLuAn/
│   ├── YiLuAnApp.swift             # @main, 根据登录态路由
│   ├── Core/
│   │   ├── Networking/
│   │   │   ├── APIClient.swift      # URLSession 封装
│   │   │   ├── APIEndpoint.swift    # 端点枚举
│   │   │   ├── AuthInterceptor.swift# JWT注入 + 401静默刷新
│   │   │   └── WebSocketClient.swift# WebSocket + 指数退避重连
│   │   ├── Storage/
│   │   │   └── KeychainManager.swift# Token Keychain 安全存储
│   │   └── Models/                  # Codable 模型
│   ├── Features/
│   │   ├── Auth/                    # 登录, OTP, 角色选择
│   │   ├── Patient/                 # 患者首页, 创建订单, 订单详情
│   │   ├── Companion/              # 陪诊师首页, 可接订单, 我的订单
│   │   ├── Chat/                    # 聊天列表, 聊天室
│   │   ├── Review/                  # 写评价, 评价列表
│   │   ├── Notifications/          # 通知中心
│   │   └── Profile/                # 个人资料
│   └── SharedViews/                 # 通用组件
└── YiLuAnTests/
```

---

## 数据库设计

### 已实现 — `users` 表

当前 Phase 0-1 已实现的核心用户表，基于 SQLAlchemy 2.0 Mapped 声明式：

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | UUID | PK, default uuid4 | 用户唯一标识 |
| `phone` | String(20) | UNIQUE, nullable, indexed | 手机号 (微信用户初始为 NULL) |
| `wechat_openid` | String(128) | UNIQUE, nullable, indexed | 微信 OpenID |
| `wechat_unionid` | String(128) | UNIQUE, nullable, indexed | 微信 UnionID (多平台) |
| `role` | Enum("patient", "companion") | nullable | 用户角色 (注册后选择) |
| `display_name` | String(100) | nullable | 显示名称 |
| `avatar_url` | String(500) | nullable | 头像 URL |
| `is_active` | Boolean | default True | 账号启用状态 |
| `created_at` | DateTime(tz) | server_default now() | 创建时间 |
| `updated_at` | DateTime(tz) | onupdate now() | 更新时间 |

> **UNIQUE + nullable 设计**: PostgreSQL UNIQUE 约束允许多个 NULL 值，因此微信用户初始无手机号不会冲突。

### 缓存设计 (Redis)

| Key 模式 | TTL | 说明 |
|----------|-----|------|
| `otp:{phone}` | 300s (5分钟) | OTP 验证码存储 |
| `otp:rate:{phone}` | 60s | OTP 发送频率限制 |

### 规划中 — 完整数据库

以下表将在后续 Phase 中逐步实现：

| 表 | Phase | 说明 |
|----|-------|------|
| `patient_profiles` | Phase 2 | 患者扩展 (紧急联系人, 病历备注, 偏好医院) |
| `companion_profiles` | Phase 2 | 陪诊师扩展 (实名, 资质, 评分, 接单数, 服务区域, 认证状态) |
| `hospitals` | Phase 2 | 医院参考数据 (名称, 地址, 等级, 经纬度) |
| `orders` | Phase 3 | 核心订单 (patient→companion, hospital, service_type, status, 预约时间, 价格) |
| `order_status_history` | Phase 3 | 订单状态变更审计日志 |
| `payments` | Phase 3 | 模拟支付记录 |
| `chat_messages` | Phase 4 | 聊天消息 (order_id, sender_id, type, content, 已读回执) |
| `reviews` | Phase 5 | 评价 (order_id, 1-5 星, 文字评论) |
| `notifications` | Phase 6 | 站内通知 |
| `device_tokens` | Phase 6 | APNs 设备注册 |

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

### 已实现端点 (9 个)

#### 基础

| 方法 | 端点 | 认证 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 健康检查 → `{"status": "healthy"}` |
| GET | `/api/v1/ping` | 无 | API 连通性测试 |

#### 认证 Auth — `POST /api/v1/auth/*`

| 方法 | 端点 | 认证 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/auth/send-otp` | 无 | `{phone}` | `{message}` — OTP 发送至手机 (Redis TTL 300s, 限频 60s) |
| POST | `/auth/verify-otp` | 无 | `{phone, code}` | `TokenResponse` — 验证 OTP, 返回 JWT (开发模式接受 `000000`) |
| POST | `/auth/refresh` | 无 | `{refresh_token}` | `RefreshTokenResponse` — 刷新 Access Token |
| POST | `/auth/wechat-login` | 无 | `{code}` | `TokenResponse` — 微信 code → openid → JWT (开发 bypass: `dev_test_code`) |
| POST | `/auth/bind-phone` | Bearer | `{phone, code}` | `UserResponse` — 微信用户绑定手机号 (OTP 验证) |

#### 用户 Users — `/api/v1/users/*`

| 方法 | 端点 | 认证 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/users/me` | Bearer | — | `UserResponse` — 当前用户信息 |
| PUT | `/users/me` | Bearer | `{role?, display_name?, avatar_url?}` | `UserResponse` — 更新用户资料 |

#### 数据模型

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
  updated_at: datetime
```

### 规划中端点 (~26 个)

| 模块 | Phase | 端点 |
|------|-------|------|
| **Companions** | Phase 2 | `GET /companions` (筛选/排序), `GET /companions/{id}`, `POST /companions/apply`, `PUT /users/me/patient-profile`, `POST /users/me/avatar` |
| **Hospitals** | Phase 2 | `GET /hospitals` (搜索/筛选) |
| **Orders** | Phase 3 | `POST /orders`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/accept`, `POST /orders/{id}/start`, `POST /orders/{id}/complete`, `POST /orders/{id}/cancel` |
| **Payment** | Phase 3 | `POST /orders/{id}/pay`, `POST /orders/{id}/refund` |
| **Chat** | Phase 4 | `GET /chats/{order_id}/messages`, `WS /ws/chat/{order_id}` |
| **Reviews** | Phase 5 | `POST /orders/{id}/review`, `GET /companions/{id}/reviews` |
| **Notifications** | Phase 6 | `GET /notifications`, `PUT /notifications/{id}/read`, `POST /notifications/device-token`, `DELETE /notifications/device-token` |

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
          ┌──────────────────────┐
          │  Azure Key Vault     │
          │  (secrets)           │
          └──────────────────────┘
```

### 后端分层架构

```
Request → API Route → Service → Repository → Database
                        ↓
                    Exceptions → 全局异常处理器 → HTTP Response
```

| 层级 | 职责 | 示例 |
|------|------|------|
| **API Route** | 请求校验, 依赖注入, HTTP 响应 | `auth.py`, `users.py` |
| **Service** | 业务逻辑, 事务编排 | `AuthService.verify_otp()` |
| **Repository** | 数据访问, SQL 查询封装 | `UserRepository.get_by_phone()` |
| **Schema** | Pydantic 请求/响应模型 | `TokenResponse`, `UserResponse` |
| **Model** | SQLAlchemy ORM 映射 | `User` (users 表) |

### 异常处理体系

| 异常 | HTTP 状态码 | 使用场景 |
|------|------------|----------|
| `BadRequestException` | 400 | OTP 过期/错误, 无效请求 |
| `UnauthorizedException` | 401 | JWT 无效/过期, 账号禁用 |
| `ForbiddenException` | 403 | 权限不足 |
| `NotFoundException` | 404 | 资源不存在 |
| `ConflictException` | 409 | 手机号已被占用 |

---

## 实施阶段

| Phase | 名称 | 状态 | 后端 | 前端 |
|-------|------|------|------|------|
| **0** | 项目脚手架 | ✅ 完成 | FastAPI + SQLAlchemy async + Docker + BaseRepository + pytest | Xcode 项目 + APIClient + 小程序骨架 |
| **1** | 认证系统 | ✅ 完成 | users 表, OTP, JWT, 微信登录, 手机绑定 (44 tests) | iOS: Login/OTP/RoleSelect; 小程序: 14 页面 + 7 组件 (33 tests) |
| **2** | 用户资料 + 医院 | 🔲 规划 | patient/companion profiles, 头像上传, 医院种子数据 | ProfileView, HospitalPicker |
| **3** | 订单系统 | 🔲 规划 | 订单 CRUD, 状态机, 定价, 模拟支付 | CreateOrder 多步表单, OrderDetail, 双角色首页 |
| **4** | 实时聊天 | 🔲 规划 | WebSocket + Redis pub/sub, 消息持久化 | ChatRoom (WS + REST 历史) |
| **5** | 评价系统 | 🔲 规划 | 评价提交, avg_rating 反规范化 | WriteReview, StarRating |
| **6** | 推送通知 | 🔲 规划 | APNs 集成, 通知生成, 设备管理 | 推送权限, 通知列表, 深度链接 |
| **7** | 部署收尾 | 🔲 规划 | 日志, 速率限制, API 文档, CI/CD | 骨架屏, 错误处理, App 图标 |

---

## 关键设计决策

| 决策 | 原因 |
|------|------|
| Redis pub/sub 管理 WebSocket | 多实例部署时保证消息可达 |
| 反规范化 avg_rating | 陪诊师列表页是高频读路径, 避免 JOIN 聚合 |
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

---

## 验证方式

| 目标 | 工具 | 覆盖范围 | 数量 |
|------|------|----------|------|
| **后端** | pytest + pytest-asyncio | Services 层 80%+, 认证全流程 | 44 tests ✅ |
| **微信小程序** | Jest | services / store / utils 全覆盖 | 33 tests ✅ |
| **iOS** | XCTest + XCUITest | ViewModels 单测 + 核心流程 UI 测试 | 规划中 |
| **E2E** | docker-compose | 本地全栈集成测试 | 规划中 |
| **手动** | 真机 | iPhone SE (小屏) + iPhone 15 Pro, iOS 17+; 微信开发者工具 | — |

### 本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
docker compose up -d              # PostgreSQL + Redis
uvicorn app.main:app --reload     # http://localhost:8000
pytest -v                         # 44 tests

# 微信小程序
cd wechat
npm install
npm test                          # 33 Jest tests
# 用微信开发者工具打开 wechat/ 目录

# API 文档
# Swagger UI: http://localhost:8000/docs
# ReDoc:      http://localhost:8000/redoc
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL async URL | `sqlite+aiosqlite:///./dev.db` |
| `REDIS_URL` | Redis 连接 URL | `redis://localhost:6379` |
| `SECRET_KEY` | JWT 签名密钥 | **(必需)** |
| `WECHAT_APP_ID` | 微信小程序 AppID | `""` |
| `WECHAT_APP_SECRET` | 微信小程序 AppSecret | `""` |
| `CORS_ORIGINS` | 允许的跨域来源 | `["*"]` |
| `ENVIRONMENT` | 运行环境 | `development` |
