# 陪诊服务 APP — 实施方案

## Context

开发一款医疗陪诊服务平台 APP - 医路安 。连接需要就医陪伴的患者与专业陪诊师，提供全程陪诊、半程陪诊、代办等服务。部署在 Azure 上。

## 技术选型

| 层级 | 技术 |
|------|------|
| iOS | SwiftUI + MVVM + Combine |
| 微信小程序 | 原生框架 (WXML + WXSS + JS) |
| 后端 | Python 3.11 + FastAPI (async) |
| 数据库 | PostgreSQL 15 (Azure Flexible Server) |
| 缓存 | Redis 7 (Azure Cache for Redis) |
| 文件存储 | Azure Blob Storage |
| 容器 | Azure Container Apps |
| 实时通信 | WebSocket (Redis pub/sub 跨实例) |
| 支付 | 模拟支付 (MVP) |

---

## 项目结构

### 后端 `backend/`

```
backend/
├── alembic/                   # 数据库迁移
├── app/
│   ├── main.py                # FastAPI 入口, CORS, 中间件
│   ├── config.py              # pydantic-settings 环境变量
│   ├── database.py            # AsyncEngine, SessionLocal
│   ├── dependencies.py        # get_db, get_current_user
│   ├── api/v1/               # REST 端点
│   │   ├── auth.py           # OTP登录, JWT刷新
│   │   ├── users.py          # 用户资料
│   │   ├── companions.py     # 陪诊师列表/详情
│   │   ├── orders.py         # 订单CRUD+生命周期
│   │   ├── reviews.py        # 评价
│   │   ├── chat.py           # 聊天历史(REST)
│   │   ├── notifications.py  # 通知
│   │   └── hospitals.py      # 医院数据
│   ├── ws/                   # WebSocket
│   │   ├── manager.py        # ConnectionManager (Redis pub/sub)
│   │   └── chat.py           # WS端点 /ws/chat/{order_id}
│   ├── models/               # SQLAlchemy ORM
│   ├── schemas/              # Pydantic 请求/响应
│   ├── services/             # 业务逻辑层
│   ├── repositories/         # 数据访问层
│   ├── core/                 # JWT, Redis, APNs
│   └── tasks/                # 后台任务
├── tests/
├── Dockerfile
├── docker-compose.yaml       # 本地开发: postgres + redis
└── requirements.txt
```

### 微信小程序 `miniprogram/`

```
miniprogram/
├── app.js / app.json / app.wxss   # 小程序入口
├── config/index.js                 # 环境配置 (API地址)
├── services/                       # 网络请求层
│   ├── api.js                     # wx.request 封装 + Bearer 注入 + 401 自动刷新
│   ├── auth.js                    # 微信登录, Token刷新, OTP, 手机绑定
│   ├── user.js / order.js         # 用户/订单 API
│   ├── companion.js / hospital.js # 陪诊师/医院 API
│   ├── chat.js                    # 聊天消息 API
│   └── websocket.js               # WebSocket 封装 + 心跳 + 重连
├── store/index.js                  # 简单响应式全局状态 (observer 模式)
├── utils/                          # 工具函数
│   ├── token.js                   # JWT 存取 + 过期检测
│   ├── validate.js                # 手机号/验证码校验
│   ├── format.js                  # 日期/价格/手机号格式化
│   └── constants.js               # 服务类型/订单状态枚举
├── components/                     # 7 个可复用组件
│   ├── service-card/              # 服务类型卡片
│   ├── order-card/                # 订单摘要卡片
│   ├── companion-card/            # 陪诊师列表项
│   ├── rating-stars/              # 评分星星 (展示/交互)
│   ├── empty-state/               # 空状态占位
│   ├── loading-overlay/           # 加载遮罩
│   └── chat-bubble/               # 聊天气泡
├── pages/                          # 14 个页面
│   ├── login/                     # 微信一键登录
│   ├── role-select/               # 角色选择
│   ├── patient/home/              # 患者首页
│   ├── patient/create-order/      # 创建订单 (多步表单)
│   ├── patient/order-detail/      # 患者订单详情
│   ├── companion/home/            # 陪诊师工作台
│   ├── companion/available-orders/# 待接订单
│   ├── companion/order-detail/    # 陪诊师订单详情
│   ├── orders/                    # 我的订单列表
│   ├── chat/list/                 # 会话列表
│   ├── chat/room/                 # 聊天室 (WebSocket)
│   ├── companion-detail/          # 陪诊师资料
│   ├── review/write/              # 写评价
│   └── profile/                   # 个人中心
└── __tests__/                      # Jest 单元测试 (33个)
```

### iOS `YiLuAn/`

```
YiLuAn/
├── YiLuAn/
│   ├── YiLuAnApp.swift          # @main, 根据登录态路由
│   ├── Core/
│   │   ├── Networking/
│   │   │   ├── APIClient.swift       # URLSession 封装
│   │   │   ├── APIEndpoint.swift     # 端点枚举
│   │   │   ├── AuthInterceptor.swift # JWT注入+401刷新
│   │   │   └── WebSocketClient.swift # WebSocket封装+重连
│   │   ├── Storage/
│   │   │   └── KeychainManager.swift # Token安全存储
│   │   └── Models/                   # Codable 模型
│   ├── Features/
│   │   ├── Auth/          # 登录, OTP, 角色选择
│   │   ├── Patient/       # 患者首页, 创建订单, 订单详情
│   │   ├── Companion/     # 陪诊师首页, 可接订单, 我的订单
│   │   ├── Chat/          # 聊天列表, 聊天室
│   │   ├── Review/        # 写评价, 评价列表
│   │   ├── Notifications/ # 通知中心
│   │   └── Profile/       # 个人资料
│   └── SharedViews/       # 通用组件
└── YiLuAnTests/
```

---

## 数据库设计

### 核心表

| 表 | 说明 |
|---|------|
| `users` | 用户身份 (phone, role, display_name, avatar_url) |
| `patient_profiles` | 患者扩展 (紧急联系人, 病历备注, 偏好医院) |
| `companion_profiles` | 陪诊师扩展 (实名, 资质, 评分, 接单数, 服务区域, 认证状态) |
| `hospitals` | 医院参考数据 (名称, 地址, 等级, 经纬度) |
| `orders` | 核心订单 (patient_id, companion_id, hospital_id, service_type, status, 预约时间, 价格) |
| `order_status_history` | 状态变更审计 |
| `chat_messages` | 聊天消息 (order_id, sender_id, type, content) |
| `reviews` | 评价 (order_id, rating 1-5, comment) |
| `payments` | 模拟支付记录 |
| `notifications` | 站内通知 |
| `device_tokens` | APNs 设备注册 |

### 订单状态机

```
created → accepted → in_progress → completed → reviewed
created → cancelled_by_patient
accepted → cancelled_by_patient (可能扣费)
accepted → cancelled_by_companion
```

### 定价规则 (MVP)

| 服务类型 | 价格 |
|---------|------|
| 全程陪诊 | ¥299 |
| 半程陪诊 | ¥199 |
| 代办 | ¥149 |

---

## API 设计 (共 ~35 个端点)

| 模块 | 关键端点 |
|------|---------|
| **Auth** | `POST /auth/send-otp`, `POST /auth/verify-otp`, `POST /auth/refresh`, `POST /auth/wechat-login`, `POST /auth/bind-phone` |
| **Users** | `GET/PUT /users/me`, `PUT /users/me/patient-profile`, `POST /users/me/avatar` |
| **Companions** | `GET /companions` (筛选/排序), `GET /companions/{id}`, `POST /companions/apply` |
| **Orders** | `POST /orders`, `GET /orders`, `POST /orders/{id}/accept/start/complete/cancel` |
| **Chat** | `GET /chats/{order_id}/messages`, `WS /ws/chat/{order_id}` |
| **Reviews** | `POST /orders/{id}/review`, `GET /companions/{id}/reviews` |
| **Payment** | `POST /orders/{id}/pay`, `POST /orders/{id}/refund` |
| **Notifications** | `GET /notifications`, `POST /notifications/device-token` |
| **Hospitals** | `GET /hospitals` (搜索/筛选) |

---

## 实施阶段 (7个阶段)

### Phase 0: 项目脚手架 (2-3天)
- 后端: FastAPI 初始化, SQLAlchemy async, Alembic, docker-compose (PG+Redis), BaseRepository, pytest
- iOS: Xcode 项目, APIClient, KeychainManager, Codable 模型桩
- **验证:** 健康检查返回200, iOS启动无报错, docker-compose 正常运行

### Phase 1: 认证系统 (3-4天)
- 后端: users 表, OTP (Redis TTL 300s, 开发模式接受 `000000`), JWT (access 30min, refresh 7天)
- iOS: LoginView, OTPInputView, RoleSelectionView, AuthViewModel, AuthInterceptor
- **验证:** 完整登录流程, JWT 静默刷新

### Phase 2: 用户资料 + 医院数据 (2-3天)
- 后端: patient/companion profiles, 头像上传 Blob Storage, 医院种子数据
- iOS: ProfileView, EditProfileView, HospitalPickerView, 头像上传
- **验证:** 资料编辑, 医院搜索, 头像上传

### Phase 3: 订单系统 — 核心路径 (4-5天)
- 后端: 订单CRUD, 状态机, 定价, 取消规则, 可接订单查询
- iOS: CreateOrderView (多步表单), OrderDetailView, PatientHome, CompanionHome, AvailableOrders
- 模拟支付: 即时确认
- **验证:** 完整订单生命周期: 创建→支付→接单→开始→完成

### Phase 4: 实时聊天 (3-4天)
- 后端: WebSocket + Redis pub/sub, 消息持久化, 已读回执
- iOS: WebSocketClient (自动重连+指数退避), ChatViewModel (合并WS流+REST历史), ChatRoomView
- **验证:** 双方实时收发文字/图片, 历史消息加载

### Phase 5: 评价系统 (1-2天)
- 后端: 提交评价, 评分聚合 (反规范化 avg_rating), 分页查询
- iOS: WriteReviewView, ReviewListView, StarRatingView
- **验证:** 评价后陪诊师评分更新

### Phase 6: 推送通知 (2-3天)
- 后端: APNs 集成, 通知生成 (订单变更/新消息/新订单), 设备token管理
- iOS: 推送权限请求, 通知处理, NotificationListView, 深度链接
- **验证:** 订单状态变更+新消息触发推送

### Phase 7: Azure 部署 + 收尾 (3-4天)
- Azure Container Apps + PostgreSQL Flexible + Redis Cache + Blob Storage + Key Vault
- 后端: 请求ID, 结构化日志, 速率限制, API文档
- iOS: 骨架屏, 错误处理, 下拉刷新, 空状态, App图标
- GitHub Actions CI/CD
- **验证:** 全功能在 Azure staging 环境 E2E 测试

---

## Azure 基础设施

```
iOS App ──────HTTPS/WSS──────►
                                 Azure Container Apps (1-5 replicas, WebSocket enabled)
微信小程序 ──HTTPS/WSS──────►
                              │               │
                    PostgreSQL Flexible    Redis Cache
                    (B1ms, Private VNet)   (Basic C0)

                       Blob Storage (avatars, chat-images)
                       Key Vault (secrets)
                       Container Registry (Docker images)
```

---

## 关键设计决策

| 决策 | 原因 |
|------|------|
| Redis pub/sub 管理 WebSocket | 多实例部署时保证消息可达 |
| 反规范化 avg_rating | 陪诊师列表页是高频读路径, 避免 JOIN 聚合 |
| 人类可读 order_number (PZ20260329xxxx) | 客服沟通方便, UUID 不适合口头传达 |
| WebSocket JWT 通过 query 参数 | WebSocket API 不支持自定义 header |
| 模拟支付 | 真实支付需企业资质审核, 与开发并行无依赖 |
| Repository 模式 | 隔离数据访问, 便于单元测试 mock |

---

## 验证方式

- **后端:** pytest + pytest-asyncio, 覆盖率 80%+ services 层, 集成测试覆盖全订单生命周期 (44 tests)
- **iOS:** XCTest 单元测试 ViewModels, XCUITest 核心流程
- **微信小程序:** Jest 单元测试, 覆盖 services / store / utils 层 (33 tests)
- **E2E:** docker-compose 本地全栈测试; Azure staging 部署后完整流程验证
- **手动测试:** iPhone SE (小屏) + iPhone 15 Pro (大屏), iOS 17+; 微信开发者工具
