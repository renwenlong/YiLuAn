# 医路安（YiLuAn）决策日志

> 目的：记录虚拟团队在推进过程中形成的关键决策，确保后续可追溯、可复盘。

---

## 2026-04-10

### D-001 虚拟团队自治执行
- **参与角色**：Arch / Backend / Frontend / PM / Design / QA / Ops
- **背景**：用户明确授权团队内部自行做常规工程决策，不需逐项请示。
- **决策**：
  1. 常规工程方案由团队内部评审后直接执行。
  2. 仅在产品方向、外部资质、真实支付开通、生产高风险操作等事项上升级给用户。
  3. 每次重要决策必须写入本日志；重大架构问题另写 ADR。
  4. 代码按阶段自行提交，保证过程可追踪。
- **影响范围**：全项目研发、测试、部署、发布流程
- **后续动作**：建立 ADR 目录与提交规范

### D-002 当前发布策略
- **参与角色**：Arch / PM / Frontend / Ops
- **背景**：项目当前处于 MVP 向正式上线过渡阶段。
- **决策**：
  1. 微信小程序优先作为第一发布端。
  2. iOS 先进入 TestFlight/内测，不阻塞第一阶段上线。
  3. 近期工作聚焦支付、部署、合规、后台治理四个方向。
- **影响范围**：排期、资源投入、上线节奏
- **状态**：执行中

### D-003 支付架构重构方案
- **参与角色**：Arch / Backend
- **背景**：原 pay_order 直接在 OrderService 内创建 Payment 记录，硬编码 status="success"，无法对接真实支付。
- **候选方案**：
  A. 在 OrderService 内直接调用微信支付
  B. 抽出独立 PaymentService，支付领域入口
  C. 引入第三方聚合支付
- **决策**：方案 B。
- **原因**：OrderService 已 450+ 行，支付/退款/回调是独立领域，应该分离；mock 要保留给测试环境。
- **已完成**：Phase 1 — PaymentService 骨架 + mock provider + 回调端点 + Payment 模型扩展
- **待完成**：Phase 2 — 微信支付 v3 SDK 真实接入（需商户凭证）
- **状态**：Phase 1 已完成，已提交 `50a9042`

### D-004 并行任务依赖分析与分区约定
- **参与角色**：Arch / Backend / Ops / PM / Frontend
- **背景**：多项 P0 任务需并行推进，用户要求确认不存在互相依赖。
- **决策**：
  1. 并行组 A（立即开工）：SMS 接入 / 后台管理 MVP / 合规文档 / 前端支付改造
  2. 并行组 B（组A部分完成后）：前端审核合规页面（依赖合规文档）/ 生产配置收口
  3. 串行：部署方案（依赖生产配置）→ 小程序提审（依赖全部完成）
  4. config.py 分区约定：SMS、Payment、生产配置各占独立区域，禁止越界修改
- **详细依赖图见**：`docs/discussions/2026-04-10-parallel-dependency.md`
- **状态**：已确认，执行中

---

## 2026-04-11

### D-005 微信支付回调验签方案
- **参与角色**：Arch / Backend
- **背景**：微信支付 v3 回调需要验签以确保通知来源真实性。有两个实现路径：A. 使用 wechatpay-python 或 wechatpy 第三方库；B. 基于 cryptography 库手动实现 RSA-SHA256 验签。
- **候选方案**：
  A. 使用第三方 SDK（wechatpay-python / wechatpy）自带验签
  B. 手动实现：cryptography 库解析证书 + RSA-SHA256 验签
- **决策**：方案 B — 手动实现，基于 cryptography 库
- **原因**：
  1. 第三方 SDK 版本更新滞后，API v3 支持不完整
  2. cryptography 已在依赖中（JWT 间接引用），无新增依赖
  3. 验签逻辑仅数十行，手动实现可控性更强
  4. 避免 SDK 抽象泄漏与版本锁定风险
- **影响范围**：`app/services/payment/wechat_provider.py` 中 `verify_callback` 方法
- **后续动作**：实现 verify_callback 并编写单元测试覆盖正常/篡改/过期场景
- **状态**：已确认，待实现

### D-006 生产配置安全策略
- **参与角色**：Backend / Ops
- **背景**：项目即将进入部署阶段，需确保生产环境不会因配置遗漏或错误导致安全事故。
- **决策**：
  1. 在 `config.py` 添加 `model_validator(mode='after')` 生产模式校验：
     - `ENVIRONMENT=production` 时，`JWT_SECRET_KEY` 不能是开发默认值，否则拒绝启动
     - `ENVIRONMENT=production` 时，`DEBUG` 必须为 `false`
     - `ENVIRONMENT=production` + `PAYMENT_PROVIDER=wechat` 时，检查微信支付四项凭证完整性
     - `ENVIRONMENT=production` + `SMS_PROVIDER!=mock` 时，检查 SMS 四项凭证完整性
  2. 新增 `.env.example` 配置模板，标注所有配置项及中文说明
  3. 新增 `/api/v1/health` 和 `/api/v1/readiness` 健康检查端点
- **原因**：
  1. 防止带着开发密钥部署生产，避免 JWT 被伪造
  2. 防止生产环境开启 debug 暴露堆栈信息
  3. 确保支付/短信等关键服务凭证齐全，避免运行时才发现配置缺失
  4. 健康检查端点为 K8s / 负载均衡器提供存活/就绪探针
- **影响范围**：`backend/app/config.py`、`backend/.env.example`、`backend/app/api/v1/health.py`
- **状态**：已完成

---

## 2026-04-13

### D-007 微信支付回调验签与解密实现
- **参与角色**：Backend
- **背景**：D-005 决策确认采用手动 cryptography 方案实现微信支付 v3 回调验签。`verify_callback` 中 `_verify_signature` 和 `_decrypt_resource` 仅有 TODO 框架，需落地实现。
- **决策**：
  1. `_verify_signature`: 从 headers 提取 Wechatpay-Timestamp/Nonce/Signature/Serial，构造 `{timestamp}\n{nonce}\n{body}\n` 验签字符串，用微信平台公钥做 RSA-SHA256 (PKCS1v15) 验证
  2. `_decrypt_resource`: 用 api_key_v3 (32 字节) 作为 AES-256-GCM 密钥，解密 resource.ciphertext (base64)，nonce 和 associated_data 作为 GCM 参数
  3. 平台证书从本地 PEM 文件加载（路径通过 `WECHAT_PAY_PLATFORM_CERT_PATH` 配置），模块级 `_platform_cert_cache` 字典缓存，线程安全
  4. mock 兼容：`_has_credentials=False` 时跳过验签直接解析 body，不影响现有 mock 测试
- **原因**：
  1. 延续 D-005 方案 B 决策，cryptography 已在依赖链中
  2. 本地证书加载方案简单可靠，无需在线拉取证书
  3. 缓存避免每次回调都读文件
- **影响范围**：`backend/app/services/payment_service.py`、`backend/app/config.py`（新增 `wechat_pay_platform_cert_path`）、`backend/requirements.txt`
- **测试覆盖**：新增 `tests/test_wechat_verify_callback.py`（9 个用例）：正常验签、签名篡改失败、缺少 header、AES-GCM 正常解密、密钥错误解密失败、mock 模式跳过、无凭证跳过、证书缓存验证
- **状态**：已完成

### D-008 /readiness 端点返回 503
- **参与角色**：Backend / Ops
- **背景**：`/readiness` 端点在数据库或 Redis 检查失败时仍返回 HTTP 200，导致 K8s 就绪探针误判服务可用。
- **决策**：
  1. `/readiness` 增加 Redis 连通性检查（SET + GET）
  2. 数据库或 Redis 任一检查失败 → 返回 HTTP 503 + `{status: "not_ready", db: "ok"|"error", redis: "ok"|"error"}`
  3. 全部通过 → HTTP 200 + `{status: "ready", db: "ok", redis: "ok"}`
  4. `/health` 保持无状态快速响应（liveness probe），仅返回 200
- **原因**：就绪探针必须准确反映后端依赖可用性，否则负载均衡器会将流量发往不可用实例
- **影响范围**：`backend/app/api/v1/health.py`、`backend/tests/test_health.py`
- **状态**：已完成

### D-009 账号注销策略（软删除 + 脱敏）
- **参与角色**：Arch / Backend
- **背景**：用户需要注销账号的能力，需符合数据保护要求，同时保留业务数据可追溯性。
- **候选方案**：
  A. 硬删除 — 直接从数据库删除用户记录
  B. 软删除 — 标记 deleted_at，保留记录
  C. 软删除 + 延迟清除 + 脱敏（推荐）
- **决策**：方案 C — 软删除 + 即时脱敏
- **原因**：
  1. 硬删除会导致订单等关联数据孤立，无法追溯
  2. 纯软删除不满足隐私数据最小化要求
  3. 软删除 + 脱敏兼顾数据完整性和隐私合规
- **实现细节**：
  1. User 模型新增 `deleted_at: Optional[datetime]` 字段和 `is_deleted` 属性
  2. `DELETE /api/v1/users/me` 端点：验证身份 → 取消进行中订单 → 脱敏敏感字段 → 设置 deleted_at
  3. 脱敏策略：手机号 → SHA256 哈希前16位，姓名 → '已注销用户'，微信 OpenID/UnionID/头像 → NULL
  4. 设置 `is_active=False` 阻止后续登录
  5. 已注销用户通过 token 或 OTP/微信登录时返回 401 "Account has been deleted"
- **影响范围**：`app/models/user.py`、`app/services/user.py`、`app/api/v1/users.py`、`app/dependencies.py`、`app/services/auth.py`
- **状态**：已完成

---

## 2026-04-14

### D-010 注销时活跃订单分级处理
- **参与角色**：Arch / Backend / QA
- **背景**：D-009 确定了账号注销策略（软删除 + 脱敏），但未定义注销时如何处理用户仍在进行中的订单。用户可能同时以患者和陪诊师身份持有活跃订单。
- **候选方案**：
  A. 拒绝注销 — 存在活跃订单时阻止注销
  B. 全部取消 — 统一取消并全额退款
  C. 分级处理 — 根据订单状态采用不同策略
- **决策**：方案 C — 分级处理
- **原因**：
  1. 方案 A 用户体验差，用户无法自主完成注销
  2. 方案 B 对已在进行中（陪诊师已出发）的订单不公平
  3. 分级处理兼顾公平性和用户权益
- **实现细节**：
  1. `pending (created)` → 直接取消，无退款（未被接单，无损失）
  2. `accepted` → 取消 + 100% 全额退款（已接单但未开始服务）
  3. `in_progress` → 取消 + 50% 退款（服务已部分完成）
  4. `completed / reviewed` → 不处理（保留历史记录）
  5. 双向查询：同时检查 `patient_id` 和 `companion_id`
  6. 退款通过 `PaymentService.create_refund()` 复用已有流程
  7. `BadRequestException` 静默处理重复退款（幂等保护）
  8. 全部在同一数据库事务中执行，失败则整体回滚
- **影响范围**：`app/services/user.py`（`_cancel_active_orders` 方法）
- **测试覆盖**：`tests/test_account_deletion_orders.py`（6 个用例：各状态处理、双角色查询、无订单场景、重复退款幂等）
- **落地提交**：`5689685`
- **状态**：已完成

### D-011 支付回调时间戳防重放（5分钟窗口）
- **参与角色**：Arch / Backend
- **背景**：D-007 实现了回调验签和解密，但未防御重放攻击。攻击者可截获合法回调通知并重复发送，导致订单状态被多次修改。
- **候选方案**：
  A. 仅依赖签名验证（不防重放）
  B. 基于数据库去重（记录已处理的 nonce）
  C. 时间戳窗口检查（简单有效）
  D. 时间戳 + nonce 去重（最严格）
- **决策**：方案 C — 时间戳窗口检查，5分钟有效期
- **原因**：
  1. 方案 A 不防重放，有安全风险
  2. 方案 B 需要额外数据库表，增加复杂性
  3. 方案 C 实现简单（约 10 行代码），微信官方也建议做时间戳验证
  4. 5 分钟窗口兼顾网络延迟容忍和安全性
  5. 后续如有更高安全需求可升级到方案 D
- **实现细节**：
  1. 从回调 headers 获取 `Wechatpay-Timestamp`
  2. 计算 `abs(current_time - callback_time)`
  3. 超过 300 秒（5分钟）则拒绝，返回错误
- **影响范围**：`app/services/payment_service.py`（`verify_callback` 方法）
- **测试覆盖**：`tests/test_payment_service.py`（sign_params 格式验证 + 防重放 + 过期拒绝，3 个用例）
- **落地提交**：`fc5717a`
- **状态**：已完成

### D-012 PyJWT 迁移（python-jose → PyJWT 2.9.0）
- **参与角色**：Backend / Arch
- **背景**：项目原使用 `python-jose[cryptography]` 进行 JWT 编解码，但该库已停止维护（最后更新 2021 年），每次 import 会触发 `DeprecationWarning`，累计导致测试报告中出现 329 个 warnings。
- **候选方案**：
  A. 继续使用 python-jose，忽略 warnings
  B. 迁移到 PyJWT（活跃维护，Python JWT 社区标准）
  C. 迁移到 authlib
- **决策**：方案 B — 迁移到 PyJWT 2.9.0
- **原因**：
  1. python-jose 已弃用，存在潜在安全风险
  2. PyJWT 是 Python JWT 领域最活跃的库，社区支持好
  3. API 几乎兼容，迁移成本极低（`jose.jwt` → `jwt`）
  4. 迁移后 DeprecationWarning 329 → 0
  5. authlib 功能过重，项目只需 JWT 编解码
- **实现细节**：
  1. `requirements.txt`: `python-jose[cryptography]` → `PyJWT>=2.9.0`
  2. `app/core/security.py`: `from jose import jwt` → `import jwt`
  3. 测试 mock 路径更新
  4. 验证所有 303 个后端测试通过，warnings 从 ~322 降到 3（仅剩 SQLAlchemy collection warnings）
- **影响范围**：`backend/requirements.txt`、`backend/app/core/security.py`、`backend/tests/test_auth.py`
- **落地提交**：`fc5717a`
- **状态**：已完成

---

## 2026-04-15

### D-013 CD 自动化骨架（暂禁用自动触发）
- **参与角色**：Ops / Backend / Arch
- **背景**：Sprint 进入部署准备阶段，需要 GitHub Actions Deploy workflow 骨架，但 Azure ACR/ACA 尚未完成配置，贸然开启自动推送会失败刷屏。
- **候选方案**：
  A. 先写 deploy workflow 但保持手动触发（workflow_dispatch）
  B. 等 ACR 完全就绪再一起写
  C. 写好后立即开启 push/tag 自动触发
- **决策**：方案 A — 骨架先行，`on: workflow_dispatch` + 注释掉的 `on: push/tags`
- **原因**：
  1. 骨架对齐 Dockerfile / ACR 镜像命名等约定，避免后期返工
  2. 手动触发便于单次验证，不产生无效告警
  3. ACR 凭证到位后只需 uncomment 自动触发段即可启用
- **影响范围**：`.github/workflows/deploy.yml`、`docs/deployment.md`
- **后续动作**：B-04（Azure ACR 创建）完成后恢复 push 自动触发
- **落地提交**：`2a51adb`（禁用 Deploy 自动触发）+ `dc38ef1` 批次
- **状态**：执行中（等 ACR）

### D-014 iOS 端功能对齐 + XCTest 测试覆盖策略
- **参与角色**：iOS / QA / Arch
- **背景**：iOS 端长期落后于小程序，MVP 阶段需要补齐用户旅程并建立基础测试。macOS CI runner 暂未到位，无法跑 XCTest。
- **候选方案**：
  A. 等 macOS runner 再补测试
  B. 本地可跑的 XCTest + 暂不接 CI
  C. 用 iOS 快照测试框架（SnapshotTesting 等）
- **决策**：方案 B — 先在本地 XCTest 建立 57 条用例覆盖主要旅程，CI 接入延后到 macOS runner 就位
- **原因**：
  1. 测试覆盖比 CI 接入更紧迫——先保证有断言，再谈自动化
  2. SwiftUI + XCTest 是苹果原生方案，无额外依赖
  3. 57 条覆盖登录/订单/聊天/钱包/评价等关键路径，达到与小程序的可比线
- **影响范围**：`ios/YiLuAnTests/*`、`PROJECT_STATUS.md`
- **落地提交**：`49d6ead`（23 用例首批）+ `bf046db`（+34 用例，补齐至 57）
- **遗留 TD**：TD-03 iOS CI 接入（需 macOS runner 或 self-hosted）
- **状态**：功能对齐 + 本地测试已完成；CI 接入待办

### D-015 iOS / 小程序 token 刷新与 API 文档统一
- **参与角色**：Frontend / iOS / Backend
- **背景**：前端（小程序 + iOS）刷新 token 逻辑各写一份，行为不一致；Swagger 文档注释残缺。
- **决策**：
  1. 统一由 `refreshToken` 服务层封装：access 过期前 60s 触发；失败直接 logout
  2. iOS 侧 `NetworkClient` 中间件化，同一套拦截
  3. 所有 `@router.*` 装饰器补齐 `summary` / `description`，Swagger /docs 中文可读
- **影响范围**：`wechat/services/api.js`、`ios/YiLuAn/Services/NetworkClient.swift`、`backend/app/api/v1/*`
- **落地提交**：`a54049f`
- **状态**：已完成

---

## 2026-04-16

### D-016 订单状态机扩展：`rejected_by_companion` + `expired`
- **参与角色**：Backend / Arch / PM / Frontend
- **背景**：原状态机只允许 `created → accepted / cancelled_by_patient`，实际业务中陪诊师需要「拒单」能力，长时间无人接单的订单也应自动过期，否则订单流会挂死。
- **候选方案**：
  A. 复用 `cancelled_by_companion`（不区分主动/被动）
  B. 新增 `rejected_by_companion` + `expired` 两个独立状态
  C. 用一个通用的 `cancelled` + 在 metadata 中记录原因
- **决策**：方案 B — 新增两个独立终态
- **原因**：
  1. 语义清晰：拒单影响陪诊师接单率，自动过期不影响；统计/风控需要区分
  2. 状态机约束更严格：`rejected_by_companion` 只能从 `created` 转入，避免误操作
  3. 对前端/运营后台展示更友好（不同文案、不同 icon）
- **实现细节**：
  1. 新增 `OrderStatus.rejected_by_companion` / `OrderStatus.expired`
  2. `ORDER_TRANSITIONS` 明确允许 `created → {rejected_by_companion, expired}`；两者均为终态
  3. `Order` 增加 `expires_at: datetime`，默认 `created_at + ORDER_EXPIRY_HOURS`（4h）
  4. `POST /orders/{id}/reject`：陪诊师权限校验 + 仅 created 可用 + 自动退款 + 通知患者
  5. `POST /orders/check-expired`：被动 API 扫描；后续接入定时器（见 D-018）
  6. 通知链路：`notify_order_rejected` / `notify_order_expired` 走新的实时推送通道
- **影响范围**：`backend/app/models/order.py`、`services/order.py`、`api/v1/orders.py`、alembic migration、小程序 `companion/order-detail` + `patient/order-detail`
- **落地提交**：`24e437a`（+802/-26，20 文件）
- **测试**：`test_order_notifications_reject_expiry.py` 12 条用例
- **状态**：已完成

### D-017 实时通知 + 聊天融合（WebSocket 推送 + 订单自动建会话）
- **参与角色**：Backend / Frontend / Design
- **背景**：订单状态变化（新单/接单/拒单/过期/消息）需要实时触达用户，同时用户期待「下单即可聊天」的连贯体验。
- **候选方案**：
  A. 纯轮询（patient 客户端定时拉列表）
  B. 服务端推送通知 + 聊天走独立通道
  C. 通知 WebSocket + 订单创建时自动创建 ChatMessage 占位，统一在聊天页承载系统通知
- **决策**：方案 C — 通知 WebSocket + 聊天/通知融合
- **原因**：
  1. 轮询浪费流量且延迟高
  2. 用户对「订单」和「消息」认知是连续的——分两个入口反而割裂
  3. 服务端只需一个 WebSocket 通道（`/ws/notifications`）+ 现有聊天表，无新实体
- **实现细节**：
  1. 新增 `/api/v1/ws/notifications` 端点：JWT 鉴权 + ping/pong 心跳 + 进程内 `_notification_connections: dict[str, list[WebSocket]]`
  2. `create_notification` 同步调用 `push_notification_to_user`（best-effort）
  3. `OrderService.create_order` 在创建订单后生成 `ChatMessage(type=system, content="订单已创建...")`
  4. 前端：`notificationWs.js`（81 行）——自动重连（指数退避 1→30s，最多 5 次）+ 30s 心跳；chat-bubble 组件新增 `system` 类型样式
  5. 聊天列表显示「新订单」徽标 + 未读数
- **遗留风险**：
  1. 单进程内存模式——多副本部署时推送只能到达同一实例的连接 → 记录为 D-019（TD-06）
  2. 连接断开清理依赖 WebSocket `finally` 块；极端情况可能残留
- **影响范围**：`backend/app/api/v1/ws.py`（+63）、`services/notification.py` / `order.py`、小程序聊天/通知相关页面
- **落地提交**：`05aa228`（+331/-27，11 文件）
- **状态**：已完成

---

## 2026-04-17

### D-018 过期订单自动扫描：APScheduler 集成 FastAPI
- **参与角色**：Backend / Arch / Ops
- **背景**：D-016 引入 `expired` 状态后，`check_expired_orders` 仅作为被动 API 存在，必须有定时驱动才真正生效。架构师晨会标记为 P0 合并项。
- **候选方案**：
  A. APScheduler 内嵌 FastAPI 进程（`AsyncIOScheduler`）
  B. Celery Beat + worker（独立进程）
  C. 系统 cron / Azure Timer Trigger 定期 POST `/orders/check-expired`
  D. 客户端触发（查询订单时顺带检查）
- **决策**：方案 A — APScheduler 内嵌
- **原因**：
  1. MVP 规模下任务简单、体积小，单独起 Celery 部署成本过高
  2. `AsyncIOScheduler` 与 FastAPI 事件循环无缝对接，无需额外进程协调
  3. 方案 C 依赖外部服务健康度（cron 机器挂了就没人扫），内嵌更可控
  4. 方案 D 不可控（用户长时间不访问订单就永不过期）
  5. 未来若任务量增大，可平滑迁移到 Celery Beat（任务函数已抽离）
- **实现细节**：
  1. `app/tasks/scheduler.py`：`create_scheduler` + `start_scheduler` + `shutdown_scheduler`
  2. 任务 `scan_expired_orders_job` 每 **60 秒**扫描一次（兼顾响应性和 DB 压力）
  3. 任务内复用 `OrderService.check_expired_orders`，保持业务逻辑单一入口
  4. `AsyncIOScheduler` 配置：`coalesce=True`、`max_instances=1`、`misfire_grace_time=30s`
  5. FastAPI lifespan 注册 start/shutdown；`SCHEDULER_ENABLED=false` 可关闭（CLI/测试场景）
- **多副本部署**：
  - 使用 Redis `SET NX EX` 作为 **best-effort** 分布式锁（key: `yiluan:scheduler:expired-orders:lock`，TTL=50s）
  - Redis 不可用时退化为本实例执行（日志告警），不阻塞业务
  - 严格互斥（Redlock / PG advisory lock）作为后续改进项，当前 MVP 单副本足够
- **影响范围**：`backend/app/tasks/scheduler.py`（新）、`main.py` lifespan、`config.py` 新增 `scheduler_enabled`、`requirements.txt` 引入 `APScheduler>=3.10`
- **测试**：`tests/test_scheduler.py` 7 条用例（正常扫描 / 无过期订单 / 异常容错 / 分布式锁跳过 / 锁退化 / 调度器注册）
- **落地提交**：`91d79f0`
- **状态**：已完成（**2026-04-17 升级至生产级 PG advisory lock**，见下方 Update）

#### Update 2026-04-17 — 升级为 PostgreSQL advisory lock（生产级）
- **变更动机**：MVP 阶段 `SET NX EX` 为 best-effort 锁，存在两类风险：
  1. Redis 时钟漂移 / TTL 比任务长 → 跨副本可能出现并发扫描（重复取消过期订单）
  2. Redis 故障时退化为"全实例独立执行"，多副本会撞车
  这两者在 ACA 扩容后会成为真实事故源，必须在扩容前彻底解决。
- **候选方案评估**：
  - A. **PostgreSQL advisory lock**：强一致、由 DB 原生保证；客户端崩溃时锁随连接释放，不会僵死；无新增依赖（已强依赖 PG）
  - B. Redlock（redis-py 或 pottery）：需要 3+ Redis 节点才算真 Redlock，单节点 Redis 并不比 SET NX EX 更强；Azure Cache for Redis 单副本部署不满足
  - C. ZooKeeper / etcd：过度设计，引入新组件运维成本
- **决策**：方案 A — PostgreSQL advisory lock
- **实现（`backend/app/core/distributed_lock.py`）**：
  1. `PostgresAdvisoryLock(session, key)` 异步上下文管理器：进入时 `SELECT pg_try_advisory_lock(bigint)`，退出时 `pg_advisory_unlock(bigint)`；`key` → 稳定 sha1 前 8 字节映射为 signed int64
  2. `RedisNXLock(redis, key, ttl)`：保留原 `SET NX EX` 语义，作为**非 PG 环境（本地/测试/降级）**回退
  3. `acquire_scheduler_lock(session, redis_client, key, ttl)` 工厂：按 `session.get_bind().dialect.name` 自动选择
- **同连接保证（PG advisory 关键约束）**：`scan_expired_orders_job` 先 `async with async_session()` 建立单一 session，然后在**同一 session 内**加锁、执行 `check_expired_orders`、commit、unlock。session 生命周期内不会归还连接池，确保 lock/work/unlock 在同一物理连接上。
- **异常安全**：
  1. `PostgresAdvisoryLock.__aenter__` 出错 → 视为"未获取"，跳过本轮（不阻塞业务）
  2. 业务代码抛异常 → `__aexit__` 仍会执行 unlock（上下文管理器语义）
  3. 连接断开 → PG 原生自动释放锁
- **兼容性**：
  - `SCHEDULER_ENABLED` 开关保持不变
  - 旧 `_try_acquire_lock` 保留为 `[DEPRECATED]` helper（向后兼容），新代码统一使用 `acquire_scheduler_lock`
  - SQLite 测试环境自动降级为 `RedisNXLock`，无需改动现有测试行为
- **测试新增（共 14 条，累计 21 条）**：`lock_key_to_bigint` 稳定性 / PG 锁获取成功 / PG 锁被他人持有跳过 / PG 锁异常降级 / PG 锁业务异常仍 unlock / Redis 锁四种语义 / 工厂方言选择 3 条 / 端到端 PG 路径（dialect mock + execute patch）2 条
- **测试数变化**：scheduler 模块 7 → 21 条；backend 总计 339 → 353（全绿）
- **收益**：
  1. 多副本真正去重（DB 强一致），消除"时钟漂移/TTL 过短"事故面
  2. 无需额外组件，部署拓扑不变
  3. 连接断开自动释放，免 TTL 调参烦恼

### D-019 WebSocket 多副本可扩展性技术债（预留）
- **参与角色**：Arch / Backend / Ops
- **背景**：D-017 的 `_notification_connections` 是进程内 dict，本次**暂不实现**分布式；架构师要求登记为显式技术债，说明现状、风险、迁移路径和触发时机。
- **现状**：
  - WebSocket 连接状态仅存在于单进程内存
  - 单实例部署（当前 ACA 默认）无问题
  - 即便连接落在实例 A，`create_notification` 也会尝试向所有实例内的该用户连接推送——但只有实例 A 的 dict 里有
- **风险（按严重度）**：
  1. **高**：横向扩容到 2+ 副本后，跨副本通知丢失率 ≈ `1 - 1/N`，用户可能收不到新订单推送
  2. **中**：蓝绿/滚动发布期间旧实例已关闭但客户端尚未重连，短暂推送丢失
  3. **低**：单实例 OOM 时所有连接一次性失联（已由客户端自动重连覆盖）
- **候选迁移方案**：
  A. **Redis Pub/Sub**：每个实例订阅同一个频道，推送写频道后所有实例 fanout 到本地连接（推荐）
  B. **消息队列（NATS / Kafka）**：更重，过度设计
  C. **粘性会话（sticky session）+ 按用户 hash 路由**：依赖 LB 能力，ACA 支持有限
- **倾向方案**：A（Redis Pub/Sub）
  - 复用现有 Redis（已部署）
  - 实现增量小：`NotificationService.push_notification_to_user` 内部改为 Redis `PUBLISH`，新增订阅 worker 把频道消息 fanout 到本地 dict
  - 兼容现有 API，零客户端改动
- **触发时机（必须迁移的信号）**：
  - 任一：ACA 扩容到 ≥2 副本；或 DAU > 1000 需要负载均衡；或观测到跨实例通知丢失
  - 估算：上线 2~4 周内
- **影响面**：`backend/app/api/v1/ws.py`、`services/notification.py`；无数据库 schema 变更
- **工作量估算**：1~1.5 人日（含测试）
- **对应 TD 编号**：TD-06 / A-13
- **状态**：已落地（2026-04-17，见下方 Update）

#### Update 2026-04-17 — Redis Pub/Sub broker 落地
- **实现方案**：方案 A（Redis Pub/Sub）
- **新模块**：`backend/app/ws/pubsub.py` — `WsPubSubBroker`
  1. 每副本启动时 `start()` 订阅统一频道（默认 `yiluan:ws:notifications`，可配 `WS_PUBSUB_CHANNEL`），生成一个监听协程 `_listen_loop`
  2. 本副本维护 `_local: dict[user_id, list[WebSocket]]`
  3. `push_to_user(user_id, payload)` 同时：① 本地投递 `_deliver_local` ② `redis.publish(channel, {origin, user_id, payload})`
  4. listen loop 收到消息时：若 `origin == self.instance_id` → 跳过（避免自回显）；否则 → 投递本地
  5. `instance_id` 由 `pid + uuid4` 生成，首次启动稳定在本进程生命周期内
- **开关 & 配置**：
  - `WS_PUBSUB_ENABLED`（默认 True）：为 False 时完全跳过 Pub/Sub，退回单机模式（本地开发/测试适用）
  - `WS_PUBSUB_CHANNEL`（默认 `yiluan:ws:notifications`）：多环境隔离可改
- **降级策略**：
  1. `redis_client=None` 或 `enabled=False` → 单机模式
  2. `subscribe()` 异常 → `start()` 不抛，记录告警日志，退化为单机模式
  3. `publish()` 运行中异常 → 日志告警，不影响本地投递（best-effort）
  4. 单个 WS 发送异常 → 仅该连接丢失，不阐闭全局 broker
- **高级改造点**：
  - `backend/app/api/v1/ws.py`：订阅/注销转为 `broker.register/unregister`，push helper 保留向后兼容签名，内部改调 broker
  - `backend/app/services/notification.py`：`create_notification` 用 `get_current_broker()` 取用全局 broker；未启动时（测试未走 lifespan 的情形）使用临时禁用 broker（无副作用）
  - `backend/app/main.py` lifespan：新增 `start_ws_pubsub` / `stop_ws_pubsub`
  - `backend/app/config.py`：新增 `ws_pubsub_enabled` / `ws_pubsub_channel`
  - 聊天 WebSocket（`/ws/chat/{order_id}`）仍维持单机内存广播：聚焦优先级；后续按需一并迁移（框架已就绪）
- **测试（`backend/tests/test_ws_pubsub.py`，12 条）**：
  1. 单机模式（enabled=False）本地投递
  2. 无 Redis（redis=None）降级投递
  3. 启用模式本地投递 + publish
  4. 自回显抑制（同 instance_id 不再重复投递）
  5. **多实例集成**：A 推送 → B 的 WS 收到（核心用例）
  6. 用户同时连在 A/B 两实例：两处均收到（本地 + pubsub）
  7. register/unregister 计数
  8. 单 WS send_text 失败不影响其他
  9. Redis 订阅失败 → `start()` 不抛异常，降级单机
  10. publish 失败 → 本地仍成功
  11. lifespan helper：`start_ws_pubsub` / `get_current_broker` / `stop_ws_pubsub` 语义
  12. listen loop 容错：忽略 非-JSON / 缺字段消息，仅投递合法消息
- **测试数变化**：backend 353 → 365（全绿）；总 555
- **压测数据**：本封未做微服务集群级别的压测（需要真实 Redis + 多副本），已登记为后续用户验收时验证项
- **回滚预案**：`WS_PUBSUB_ENABLED=false` 可立即关闭 Pub/Sub，退化单副本内存广播；业务行为与升级前一致（同实例连接的用户仍能收到通知、跨实例则丢失，与 D-017 原行为一致）。极端情况可 `git revert` 本次 commit 直接回到 D-017 单副本模式。
- **最终架构**：
  ```
  [客户端 WS] ──连接──▶ 副本A broker (_local) ◀──▶ Redis Pub/Sub ◀──▶ 副本B broker (_local) ◀──连接── [客户端 WS]
                                                           (fanout 到所有 broker，每 broker 再投递到本地连接)
  NotificationService.create_notification
    ├── DB 写入
    └── broker.push_to_user
           ├── 本地直送
           └── publish → 其他副本 listen loop → 其他副本本地投递
  ```

#### Update 2026-04-17 — 聊天通道 `/ws/chat/{order_id}` 也迁移到 Redis Pub/Sub
- **背景**：D-019 首批只迁移了通知通道，聊天通道仍是单副本内存广播。多副本部署时同订单参与者若落在不同实例会丢消息。
- **设计**：复用 `WsPubSubBroker`，通过泛化 `key_field`（user_id / order_id）一份实现跑两个 broker：
  - 通知 broker：`key_field="user_id"`，`channel=yiluan:ws:notifications`
  - 聊天 broker：`key_field="order_id"`，`channel=yiluan:ws:chat`
  两个 broker 共享同一个 Redis 连接但使用独立 channel，互不干扰；listen loop / 自回显抑制 / 降级策略全部复用。
- **新增入口**：
  - `WsPubSubBroker.publish_to_room(order_id, payload)` — 聊天业务语义别名（内部仍是 `push_to_key`）
  - `start_ws_chat_pubsub` / `stop_ws_chat_pubsub` / `get_current_chat_broker` / `get_ws_chat_broker_from_app`
- **频道 & 消息体**：`yiluan:ws:chat`，envelope `{origin, order_id, payload: {id, order_id, sender_id, type, content, is_read, created_at}}`
- **配置开关**（默认 True）：
  - `WS_CHAT_PUBSUB_ENABLED`
  - `WS_CHAT_PUBSUB_CHANNEL`（默认 `yiluan:ws:chat`）
- **降级策略**：与通知通道完全一致 — Redis 不可用时 `start()` 不抛异常、退化为单机内存；`publish` 失败仅告警不影响本地投递
- **API 契约**：前端 / iOS 零改动，WS 消息格式保持不变
- **权限/心跳**：保持 D-017 行为 — 仅订单参与者可 join，ping/pong 心跳不变；新增 JSON 解析容错（脏数据不断连接）+ 消息长度上限 4000 字符（防大 payload）
- **影响点**：
  - `backend/app/ws/pubsub.py` — `WsPubSubBroker` 泛化 key_field + 新增 chat broker helpers
  - `backend/app/api/v1/ws.py` — 聊天 endpoint 改用 chat broker.publish_to_room，移除进程内 `_connections` dict
  - `backend/app/main.py` — lifespan 新增启动/停止 chat broker
  - `backend/app/config.py` — 新增 `ws_chat_pubsub_*` 两项
- **测试（追加 8 条，合计 20 条 ws_pubsub 测试）**：
  1. 聊天 broker 单机模式投递
  2. 同 broker 下不同 order 房间隔离
  3. 双实例 fanout（核心用例）
  4. 双实例 + 双 order 不串台
  5. 自回显抑制
  6. publish 失败不影响本地
  7. lifespan helper (`start_ws_chat_pubsub` / `get_current_chat_broker`)
  8. 通知 broker 与聊天 broker 同 bus 共存不串扰
- **测试数变化**：backend 365 → 373（全绿）；wechat 133 / iOS 57；总 555 → 563
- **回滚预案**：`WS_CHAT_PUBSUB_ENABLED=false` 即可退回单副本聊天广播；聊天在多副本下会出现之前的丢消息行为，但单副本部署完全不受影响

---

## 决策记录模板

### D-XXX 标题
- **参与角色**：
- **背景**：
- **候选方案**：
- **决策**：
- **原因**：
- **影响范围**：
- **后续动作**：
- **状态**：待执行 / 执行中 / 已完成 / 已废弃

---

### D-020 WebSocket 同用户并发连接数限制（踢最老）

- **背景**：D-019 Pub/Sub 多副本架构落地后，理论上同一 user_id 可以无限挂连接（多设备/异常客户端）。本地 _local dict 里 list 无上限，存在被攻击 / 泄漏隐患。
- **决策**：每副本本地维度对单个 user_id 的连接数做软限制（默认 3），超限时关闭最老的一条（list[0]），接入新连接。
- **关键点**：
  1. 只在通知 WS（/ws/notifications）做限制——broker key_field=user_id；聊天 WS 的 key 是 order_id（订单参与者硬上限 2 人，无需限流）。
  2. 策略选「踢最老」而非「拒新连接」——多设备登录场景用户总是期望「最近的设备能用」，拒新连接会让用户一脸懵。
  3. 只在本地表生效；Pub/Sub 架构下实际上限 ≈ N × replicas，仍可接受。
  4. 关闭老连接用 close code=4008，reason=Replaced by newer connection，便于客户端识别。
- **配置**：WS_MAX_CONNECTIONS_PER_USER=3；设 0 表示不限制。
- **实现**：WsPubSubBroker.register_with_cap(key, ws, max_connections) 原子返回需要踢的 WS 列表，endpoint 调用方负责 close。测试覆盖：范围内正常 / 踢最老 / 0=不限 / 批量溢出。
- **回滚**：设 WS_MAX_CONNECTIONS_PER_USER=0 或代码侧走普通 register()。
- **相关**：D-017（WS 通知基础设施）、D-019（Pub/Sub 多副本）。

### D-019 Update（2026-04-17）APScheduler 部署文档

- 新增 docs/scheduler.md：调度任务清单、开关、多副本 advisory lock、故障排查、扩展模板。
- 触发原因：D-018 advisory lock 落地后缺少面向运维 / 新任务开发者的单一入口文档，本次补齐。



---

### D-021 (2026-04-17) /readiness 就绪探针 + /health 纯 liveness

- **上下文**：TD-OPS-01。当前 `/health` 和 `/api/v1/health` 都是纯 liveness，生产部署（ACA / K8s）需要区分 liveness 和 readiness：进程活着 vs 依赖就绪。
- **决策**：新增 `GET /readiness`，挂在两个位置：
  1. 根路径 `/readiness`（对齐 ACA / K8s 默认探针惯例）
  2. `/api/v1/readiness`（对齐现有 API 前缀，便于内部使用）
  检查项：
  - DB：通过现有 `async_session` 执行 `SELECT 1`
  - Redis：调用 `app.state.redis.ping()` + `set/get` 回读（兼容 mock 注入异常的测试路径）
  返回格式：
  - 成功：200 `{"status":"ready","checks":{"db":"ok","redis":"ok"}}`（保留 `db`/`redis` 扁平字段向后兼容）
  - 任一失败：503 `{"status":"not_ready","checks":{"db":"error: <class>: <msg>","redis":"ok"}}`
- **放弃方案**：把 readiness 内嵌到 `/health`（会破坏 liveness 语义，导致 K8s 误杀容器）
- **实现文件**：
  - `backend/app/api/v1/health.py`：`_run_readiness_checks` + `_readiness_response` 可复用函数
  - `backend/app/main.py`：根路径 `/readiness` 复用 v1 health 里的函数
- **测试**：`backend/tests/test_health.py` 从 8 → 9，新增根路径两个 case + 错误消息包含 `error:` 前缀断言；fake_redis 添加 `ping()` 方法
- **curl 验证**（Docker 容器内）：
  - `/health` → 200 `{"status":"healthy","version":"0.1.0"}`
  - `/api/v1/health` → 200 `{"status":"ok","timestamp":...}`
  - `/readiness` → 200 `{"status":"ready","checks":{"db":"ok","redis":"ok"},...}`
  - `/api/v1/readiness` → 200 同上
  - 停 db 容器：`/readiness` → 503 `{"status":"not_ready","checks":{"db":"error: InterfaceError: ... connection is closed","redis":"ok"},"db":"error","redis":"ok"}`
- **影响**：后端测试 392 → 394。`/health` 保持不查依赖，K8s livenessProbe 不会因 DB/Redis 抖动误杀容器。
- **关联**：TD-OPS-01（此次清除）。

### D-022 (2026-04-17) PG-alembic smoke CI + alembic check pre-commit

- **上下文**：TD-CI-01。pytest 主路径走 SQLite 内存 + `Base.metadata.create_all()`，绕过 alembic；生产 Docker 用 PG + `alembic upgrade head`。2026-04-17 曝光 payments 4 列 + orderstatus 2 个枚举值 model 改了但迁移脱钩，测试全绿却 Docker 部署失败（见 docs/MIGRATION_AUDIT_2026-04-17.md）。
- **决策**：三层防护同时上：
  1. **Smoke tests（真 PG）**：新增 `backend/tests/smoke/test_pg_alembic_smoke.py`，5 个 test：
     - `test_alembic_upgrade_head_no_error`：module autouse fixture 对真 PG 跑 `alembic upgrade head`，+ 显式查 `alembic_version` 非空
     - `test_order_status_enum_has_9_values`：`enum_range(NULL::orderstatus)` 必须 == `{created, accepted, in_progress, completed, reviewed, cancelled_by_patient, cancelled_by_companion, rejected_by_companion, expired}`
     - `test_payments_has_wechat_columns`：`information_schema.columns` 含 `trade_no / prepay_id / refund_id / callback_raw`
     - `test_crud_user_order_payment_roundtrip`：user → hospital → order(rejected_by_companion) → order(expired) → payment(含全 wechat 列)，readback 校验
     - `test_alembic_check_no_drift`：`alembic check` 返回 0，无 drift
     标记 `@pytest.mark.smoke`；`pyproject.toml` 默认 `addopts = "-m 'not smoke'"`，显式 `pytest -m smoke` 启用。
  2. **GitHub Actions**：新增 `.github/workflows/ci-smoke.yml`，2 jobs：
     - `unit-tests`：现有 SQLite 路径 pytest
     - `smoke-pg`：services: postgres:15-alpine + redis:7-alpine → `alembic upgrade head` → `alembic check` → `pytest -m smoke`
  3. **pre-commit**：`.pre-commit-config.yaml` + `scripts/alembic_check_hook.py`。hook 对本地 PG（默认 docker-compose db）跑 `alembic check`；PG 不可达时优雅跳过（exit 0）并提示，CI 会兜底强制。
  4. **env.py 改造**：`backend/alembic/env.py` 支持 `ALEMBIC_DATABASE_URL` / `DATABASE_URL` env 覆盖，CI / smoke / pre-commit 可按需切换 URL。
- **放弃方案**：
  - SQLite 跑 alembic check：SQLite 不支持 `ALTER CONSTRAINT`，`d6e7f8a9b0c1_add_payment_unique_constraint` 迁移直接炸（batch mode 侵入太大）；改用真 PG。
  - 把 smoke 合并进 `test.yml`：保持独立 workflow 便于维护（smoke 偏慢，触发模式不同）。
- **本地验证**：
  - `pytest -q` → 394 passed, 5 deselected
  - `pytest -m smoke -q` → 5 passed, 394 deselected（对 docker-compose db）
  - `python scripts/alembic_check_hook.py` → `No new upgrade operations detected`
- **关联**：TD-CI-01（此次清除）、D-020 / D-019（迁移审计工作的延续）。


---
## D-023 (2026-04-18) - 支付 Provider 抽象 + 回调幂等加固 (P0-1, Action #1)

**背景**：原 `payment_service.py` 把 mock / wechat 实现写在同一文件；回调端点没有持久化的幂等键，依赖 `Payment.status` 终态判断，重复回调风险高。

**决策**：
1. 抽出 `backend/app/services/providers/payment/` 包：`base.py` 定义 `PaymentProvider` + `OrderDTO` / `RefundDTO`；`mock.py` / `wechat.py` 各自实现；`factory.get_payment_provider()` 按 `settings.payment_provider` 路由。
2. 新增 `payment_callback_log` 表 + 唯一约束 `(provider, transaction_id)`，回调端点先 INSERT、命中 IntegrityError 即视为重复，立刻返回 SUCCESS 而不再触发 `handle_pay_callback`。INSERT 用 SAVEPOINT 保护以避免污染外层 session。
3. `payment_service.py` 保留 `MockPaymentProvider` / `WechatPaymentProvider` / `PaymentProvider` / `_platform_cert_cache` re-export，零改动通过既有 38 个支付测试。
4. 退款 provider 异常路径：当前选择**不持久化** `status=failed` 审计行（避免 SAVEPOINT + 提前 commit 污染外层事务），换为「surface 400 + 允许重试」。后续若需要审计行，建议拆出独立的 `payment_event_log` 表并由独立 session 写入。

**迁移**：`c8d9e0f1a2b3_add_payment_callback_log.py`（手写，含 unique constraint + 两个 index + downgrade）。已本地 `alembic upgrade head` / `downgrade -1` / `alembic revision --autogenerate --check` 通过。

**验证**：`pytest backend/tests` 全绿 407 passed (+13 新增)。

**风险 / 待复核**：
- `record_callback_or_skip` 在 `transaction_id` 为空时默认返回 True（处理），可能在异常 provider 行为下导致重复处理。建议 Phase 2 在 wechat 回调路径上 enforce `transaction_id` 必填。
- 退款失败审计行的取舍是否符合财务侧期望，待 Arch 复核。
- `WechatPaymentProvider.query` 仍是 NotImplementedError，待真实接入时补齐。



---

## D-024 (2026-04-18) — SMS Provider 抽象 + 单号限频 (P0-2, Action #2)

**背景 / 问题**

P0-1 已经把支付落到 `app.services.providers.payment` 包里（mock / wechat 两套实现 + factory + base）。短信链路当时仍然挤在单文件 `app/services/sms.py`：

- `AliyunSMSProvider` / `TencentSMSProvider` 在缺凭证时**静默 fallback 成 mock 并返回 True**——一旦生产忘了配齐 AccessKey，OTP 看上去“发送成功”但实际无短信送达，用户被锁号、监控指标也是绿的。
- 限频只有 `AuthService.send_otp` 里粗暴的 60s `setex`，没有 1h 总量上限，缺少结构化错误码，日志也没有统一脱敏。
- 没有跟 P0-1 一样的 `REQUIRED_PRODUCTION_SETTINGS` 契约常量，运维无法程序化检查“真上线还差几项”。

**决策**

1. 新增 `app/services/providers/sms/` 子包，结构与 payment 包对齐：
   - `base.py`：`SMSProvider` 抽象类（`send_otp` / `send_notification`） + `SMSResult` dataclass（`ok` / `code` / `message` / `provider` / `extra`） + `mask_phone_sms()` 助手（保留前 3 + 后 4，例 `138****0001`，比 `core.pii.mask_phone` 更接近常见 OTP 审计日志的格式约定）。
   - `mock.py`：`MockSMSProvider`，无网络调用，dev 环境继续 stdout 打印 OTP，日志仅输出脱敏号；万能 OTP `000000` 仍由 `AuthService.verify_otp` 在 `environment == "development"` 时生效（provider 不持有该约定）。
   - `aliyun.py`：`AliyunSMSProvider` **严格占位**——`send_otp` / `send_notification` 直接 `raise NotImplementedError`，并在 ERROR 日志里打印 `REQUIRED_PRODUCTION_SETTINGS` 清单（手机号脱敏）。彻底拒绝 silent fallback，宁可启动失败也不要装作能发短信。
   - `factory.py`：按 `settings.sms_provider` 路由 (`mock` / `aliyun`)，未知值带 WARNING 回落 mock。
   - `__init__.py`：导出 `SMSProvider` / `SMSResult` / `MockSMSProvider` / `AliyunSMSProvider` / `ALIYUN_REQUIRED_PRODUCTION_SETTINGS` / `get_sms_provider` / `SMSRateLimiter` / `mask_phone_sms`。

2. 新增 `providers/sms/rate_limit.py::SMSRateLimiter`：
   - 60s 窗口：Redis `INCR + EXPIRE`，单号默认上限 1。
   - 1h 窗口：Redis `ZSET`（成员 = `时间戳:uuid` 防同微秒冲突）+ `ZREMRANGEBYSCORE` 滑动剔除，默认上限 5。
   - 阈值通过 `settings.sms_rate_limit_per_minute` / `sms_rate_limit_per_hour` 可调（用 `getattr` 默认值 1/5，先不强行加 Settings 字段以保持向后兼容；待运维需要调参时再升级）。
   - 返回 `RateLimitDecision(allowed, reason, retry_after_seconds)`，`reason ∈ {ok, per_minute_exceeded, per_hour_exceeded}`。
   - 同时支持 in-process fallback（无 Redis 时单进程可用，方便单测；生产必须接 Redis）。

3. `AuthService.send_otp` 切换到新 limiter + 新 provider：
   - 限流命中时抛 `BadRequestException`，错误信息保留旧 substring `"60 seconds"` 防止前端 / 既有测试断言失效。
   - 仍然写 `otp:rate:{phone}` 旧 key（外部仪表盘观测用），但**真相源**是新 limiter。
   - 不再根据 `settings.sms_provider == "mock"` 走 print 旁路；统一通过 provider 走，避免出现两条代码路径。

4. **不引入新表**：限流计数全部走 Redis（KV + ZSET），无 alembic 迁移。这是有意决定——
   - 写 PG 限流表会显著拖慢 OTP 接口。
   - Redis TTL 已能满足 60s/1h 窗口语义。
   - 对“需要审计追溯每次发送”的需求，建议另起 `sms_send_log` 表，**作为后续 D-XXX 单独提案**，不与本次限频耦合。

5. 旧 `app/services/sms.py` 保持不变（仍导出 `MockSMSProvider` / `AliyunSMSProvider` / `TencentSMSProvider` / `SMSProvider` / `get_sms_provider`），既有 `tests/test_sms.py` 不动。新代码请从 `app.services.providers.sms` 导入；旧路径作为 legacy re-export 在下一次 cleanup 周期再删（标记 TODO，未列入本次范围以缩小爆炸半径）。

**测试覆盖**（全部新增于 `backend/tests/test_sms_providers.py`）

- `mask_phone_sms`：CN 11 位 → `138****0001`；带 `+86` → `+86138****0001`；空值 / 短号边界。
- `MockSMSProvider`：`send_otp` / `send_notification` 返回 `SMSResult(ok=True)`；日志含脱敏号、不含原始号（PII 断言）。
- `factory`：默认 mock / `aliyun` → `AliyunSMSProvider` / 未知值带 WARNING 回落 mock。
- `AliyunSMSProvider` 占位：`send_otp` / `send_notification` 抛 `NotImplementedError`；异常 message 或 ERROR 日志中包含全部 `REQUIRED_PRODUCTION_SETTINGS`；日志仍脱敏。
- `SMSRateLimiter`（in-process + FakeRedis 双路径覆盖）：
  - 同号 60s 内第 2 次 → `per_minute_exceeded`。
  - 同号 1h 内第 6 次 → `per_hour_exceeded`（用 monkeypatch 把 60s 阈值放宽到 999 单独验证 1h 窗口）。
  - 不同号互不干扰。
- 抽象基类两个方法默认抛 `NotImplementedError`。

为支持新 limiter，`tests/conftest.py::FakeRedis` 增补 `incr` / `expire` / `ttl` / `zadd` / `zcard` / `zremrangebyscore`（最小够用版，不实现真正 TTL 流逝）。

**回归结果**

`pytest backend/tests`：428 passed, 5 deselected（之前基线 ≥407，本次新增 21 个测试用例，无既有用例被破坏，包含 `test_auth.py::test_send_otp_rate_limit` 因保留 `"60 seconds"` 字面量而绿）。

**待办（不纳入本次提交，未来工单）**

- TODO-SMS-01：实现 `AliyunSMSProvider` 真实 Dysmsapi HMAC-SHA1 调用 + 退避重试 + BizCode → SMSResult.code 映射。
- TODO-SMS-02：`sms_send_log` 表（审计追溯）+ Grafana 看板（成功率 / p95 / 模板维度）。
- TODO-SMS-03：把 `settings.sms_rate_limit_per_minute` / `_per_hour` 升级为正式 Settings 字段（含生产 validator）。
- TODO-SMS-04：legacy `app/services/sms.py` 删除窗口（建议下次 sprint 完成迁移后执行）。

**关联**

- D-023（支付 Provider 抽象）—— 本次复用其结构与契约风格。
- `docs/TODO_CREDENTIALS.md` —— 阿里云 SMS 段同步追加（8 项配置）。
- `app.services.providers.sms.aliyun.REQUIRED_PRODUCTION_SETTINGS` —— 程序化获取入口。

---

## 2026-04-20

### D-027 payment_callback_log 与 sms_send_log 加 30 天 TTL

- **ID**：D-027
- **提议人**：Arch
- **状态**：Accepted
- **背景**：
  回调幂等表 payment_callback_log 与短信发送审计表 sms_send_log 当前无清理策略，长期增长会拖慢查询、占用磁盘。
  对账场景需要至少 30 天历史数据，更早的可归档到对象存储。
- **决策**：
  1. 两张表加 created_at 索引（如未加），便于时间范围查询
  2. 用 Alembic migration 加定时清理任务（或在 backend/app/scheduler 注册一个 daily job）
  3. 删除前先归档：导出为 ndjson + 上传到 OSS，按"YYYY/MM/yyyymmdd-table.ndjson.gz"路径
  4. 归档成功后才物理删除（事务级保障）
  5. 归档保留期：阿里云 OSS 1 年（按月归档），1 年后转冷归档
- **影响**：
  - 正面：表大小可控，查询性能稳定；满足审计 + 对账需要
  - 负面：需要 OSS 桶资源（B-03 一并申请）；调度任务有失败风险，需告警
  - 实施依赖：OSS 凭证（B-03）；如未到位则先写 Alembic migration + scheduler 骨架，归档逻辑 stub
- **关联**：ADR-0026（外呼装饰器调用 sms / payment 都会写日志表）、B-03（OSS 桶资源）
- **实施排期**：
  - 4/22 前完成 Alembic migration + scheduler 注册（Backend）
  - B-03 到位后接入真实 OSS 归档（Ops）

### D-028 零提交日预警机制

- **ID**：D-028
- **提议人**：Arch + PM
- **状态**：Accepted
- **背景**：4/19 全天 0 commit 是发布收口期以来首次出现，为了防止"等待性怠速"持续蔓延延迟发布，需要建立预警机制。
- **决策**：
  1. 工作日（周一至周五）连续 2 日 0 commit 自动触发 Sprint 复盘
  2. 一旦触发，Sprint 健康度从黄灯升级为红灯
  3. 周末（周六/周日）零提交不计入预警
  4. 每日晨会必须显式记录"昨日 commit 数"作为仪表板指标
- **影响**：
  - 正面：早期发现工程节奏问题，避免发布前夜爆雷
  - 负面：周一晨会需要复盘上周末延伸的工作进度
- **关联**：ADR-0026（外呼装饰器，4/19 滑期事项）、A14 本身

---

## 2026-04-21

### TD-PAY-02 取消/退款失败的持久化记录（follow-up，未排期）

- **ID**：TD-PAY-02（Tech-Debt / Payment）
- **状态**：Logged，未排期
- **关联**：D-031、commit d06867a（C6）、A21-01
- **背景**：C6 把 `/cancel` 在自动退款失败时的语义从「吞错保留 200」翻转为「显式 400 + 整体回滚」。`app.database.get_db` 在异常时 `session.rollback()`，因此 `PaymentService.create_refund` 在 provider 抛错之前**不会**留下任何 `Payment` 行；之前的 `order.status` 改动和 history 也被一并回滚。失败的退款尝试目前**只存在于结构化日志中**（`payment_service.py:348` ERROR + `order.py:301` `auto_refund_failed`），数据库没有审计行。
- **问题**：运维 / 客服无法用 SQL 查询「过去 24h 哪些订单尝试退款失败」；监控只能基于日志告警，缺少强一致对账面。
- **可选方案（待评估）**：
  1. **Outbox 表**：新增 `refund_attempt_log`，在 provider 调用前用独立 session/事务写入，provider 成功/失败后再 update 终态。优点是与业务事务解耦；代价是引入 2PC-lite 协调。
  2. **SAVEPOINT 逃生口**：在 `cancel_order` 内对「写失败审计行」单独开 SAVEPOINT，rollback 业务变更但保留审计行。实现轻，但要求所有路径都正确处理 SAVEPOINT 边界，易出错。
  3. **接受现状 + 强化结构化日志告警**：保持代码不变，依赖 ELK / 日志平台对 `auto_refund_failed` 做计数告警。零改动，但缺少强一致审计。
- **当前判断**：MVP 阶段方案 3 可接受；进入 Phase 2 真实微信渠道之前必须升级到方案 1 或 2。
- **触发条件**：接入真实微信支付 v3 商户号之前；或出现首例需要事后对账的退款失败客诉。
- **Owner**：Backend（待指派），Arch review

### TD-OPS-02 callback/sms 日志清理 job（follow-up，待实现）

- **ID**：TD-OPS-02（Tech-Debt / Ops）
- **状态**：Logged，未实现
- **关联**：D-027、A21-02-partial、**D-033（sms_send_log 已建表，纳入清理范围）**
- **上下文**：A21-02-partial 已为 `payment_callback_log` 增加 `expires_at` 字段+索引，应用层后续在写入新行时填 `now() + 90d`。本次 migration 不含后台清理 job，也不回填历史数据（历史行 `expires_at = NULL`）。
- **待实现工作**：
  1. 在 `backend/app/scheduler` 增加每日 job，覆盖 **两张表**（`payment_callback_log`、`sms_send_log`）：
     - 删除 `expires_at < now()` 的行
     - 对 `expires_at IS NULL` 的历史行使用 fallback 策略（按 `created_at < now() - 90d` 判定）
  2. 写入路径同步：`payment_callback.py` 在 INSERT 时填充 `expires_at = now() + 90d`（sms_send_log 已在 wrapper 中默认填充，无需补做）
  3. 归档：D-027 决策中提到 OSS NDJSON 归档（待 B-03 OSS 接入完成后再做，本任务只做删除）
  4. 指标：`cleanup_deleted_total{table=payment_callback_log}` Counter
- **Owner**：Backend
- **优先级**：P2（数据量增长前不阻塞，但建议在 30 天内完成首个清理 job 上线）

### A21-02b sms_send_log 表设计与字段落地（follow-up，已落地 D-033）

- **ID**：A21-02b
- **状态**：✅ 已落地（2026-04-21，D-033）— migration `d1e2f3a4b5c6_add_sms_send_log`、model `app/models/sms_send_log.py`、wrapper `app/services/providers/sms/logging_wrapper.py`、12 用例 `tests/test_sms_send_log.py`，全套 585 passed / 0 failed。详见 D-033。
- **关联**：D-027、A21-02-partial
- **背景**：D-027 原文同时覆盖 `payment_callback_log` 和 `sms_send_log` 两张表，但代码库当前没有 `sms_send_log` 表（无 model、无 migration、SMS provider 调用从未落库）。A21-02-partial 仅完成 payment 半边；SMS 半边拆出本任务。
- **待架构师决策的 schema 项**：
  1. **字段集**：provider / phone / template_code / sign_name / biz_id / status / response_code / response_msg / created_at / expires_at / 是否关联 user_id
  2. **PII 策略**：phone 是否 mask 后入库（参考 `app/core/pii.py::mask_phone`）；是否同时存原文+hash 用于查询
  3. **唯一约束 / 去重**：是否需要 `(provider, biz_id)` 或类似唯一键防重发
  4. **写入入口**：直接改 `SMSProvider.send` 吃 db session，还是上层 `app/services/sms.py` 包一层；写入失败是否回滚短信发送
  5. **是否本次同时改造调用路径**：建表+写入一次到位，还是先建表后接
- **Owner**：Arch（schema 决策）→ Backend（落地）
- **优先级**：P2（SMS 量上来前不阻塞）


---

## TD-FE-01 — admin-h5 陪诊师资质材料图片预览

**记录时间：** 2026-04-21
**类型：** 技术债（Tech Debt） / 待办（Backlog）
**Owner：** Backend → Frontend（接力）
**优先级：** P3

### 现状
admin-h5 MVP（commit `cf48099`，A21-04）只渲染 `certifications` 文本字段：因为后端当前 `CompanionApplication.certifications` 字段是 `string`（自由文本备注），而非图片 URL 列表，前端只能展示纯文本，无法预览陪诊师上传的资质材料图片。

### 影响
- ✅ 不阻塞审批闭环：运营仍可基于现有文本字段完成接单/驳回操作，MVP 上线不受影响。
- ⚠️ v2 体验缺失：审核体验显著低于真实业务需求，运营需要离线查看截图/原图，效率低；也不利于后续合规留痕。

### 待办
1. **Backend：**
   - ER 设计：在 `CompanionApplication` 上新增 `certifications_files: list[str]`（存放对象存储 key 或 URL）。
   - DB：Alembic migration 新增字段（JSON / ARRAY 二选一，倾向 JSON 兼容 SQLite 测试）。
   - API：上传接口（companion 端，multipart → 对象存储 → 返回 key），admin API 返回签名 URL 列表。
   - 不破坏旧 `certifications` 文本字段，并行存在。
2. **Frontend（admin-h5）：**
   - 列表页/详情页渲染缩略图网格，点击放大。
   - 兼容老数据（`certifications_files` 为空时回退到只展示文本）。

### 决策口径
- 字段并存（不删除 `certifications` 文本）：保留运营备注用途。
- 命名 `certifications_files` 而非 `certification_images`：考虑未来可能扩展到 PDF。

### 关联
- 主仓 commit `cf48099` —— admin-h5 MVP 初版，确认了文本-only 展示的临时方案。
- A21 follow-up 三件套：本条与 A21-14 / A21-13 / A21-10 同批落档，串入 v2 backlog。

## D-032 iOS \u5de5\u7a0b\u6587\u4ef6\u58f0\u660e\u5f0f\u5316\uff08XcodeGen\uff09

**\u65e5\u671f\uff1a** 2026-04-21
**Owner\uff1a** Arch + Ops
**\u80cc\u666f\uff1a** A21-10 iOS CI workflow stub \u63ed\u793a ios/ \u76ee\u5f55\u7f3a .xcodeproj\uff0c\u662f CI \u8fdc\u671f\u8dd1\u4e0d\u8d77\u6765\u7684\u5355\u70b9\u969c\u788d\uff1bREADME \u8981\u6c42\u5728 Xcode UI \u91cc\u624b\u52a8\u70b9 7 \u6b65\u5efa\u5de5\u7a0b\uff0conboarding \u4f53\u9a8c\u5dee\u4e14\u4e0e CI \u4e0d\u4e00\u81f4\u3002

**\u51b3\u7b56\uff1a** \u91c7\u7528 [XcodeGen](https://github.com/yonaskolb/XcodeGen)\uff0c\u4ee5 ios/project.yml \u4f5c\u4e3a\u5de5\u7a0b\u552f\u4e00\u58f0\u660e\u6e90\uff1a
- *.xcodeproj \u5165 .gitignore\uff0c\u672c\u5730\u4e0e CI \u5747\u7528 xcodegen generate \u5b9e\u65f6\u751f\u6210
- Swift \u6587\u4ef6\u589e\u5220\u81ea\u52a8\u540c\u6b65\uff0c\u514d\u53bb Xcode UI \u624b\u52a8\u52fe\u9009
- iOS CI workflow \u53bb\u6389 STUB \u6807\u8bb0\uff0c\u7b2c\u4e00\u6b65 brew install xcodegen + xcodegen generate\uff0c\u968f\u540e\u8d70\u6807\u51c6 xcodebuild test

**\u53d6\u820d\uff1a** XcodeGen \u589e\u52a0\u4e00\u9879\u4f9d\u8d56\uff08\u5f00\u53d1\u8005\u65b0\u673a\u5668\u9700 brew install\uff09\u6362\u53d6\u300c\u5de5\u7a0b\u6587\u4ef6\u9650\u5b9a\u5728\u4ee3\u7801 review \u8303\u56f4\u5185\u300d+\u300cCI \u53ef\u91cd\u590d\u751f\u6210\u300d+\u300conboarding \u4ece 7 \u6b65\u70b9\u6309\u538b\u7f29\u5230 1 \u884c\u547d\u4ee4\u300d\u4e09\u9879\u6536\u76ca\uff0c\u6536\u76ca\u8fdc>\u6210\u672c\u3002

**\u9a8c\u8bc1\u80fd\u529b\uff1a** Windows \u672c\u673a\u65e0\u6cd5\u8dd1 xcodegen / xcodebuild\uff0c\u4ec5 yaml \u8bed\u6cd5\u9a8c\u8bc1\u901a\u8fc7\u3002\u6700\u7ec8\u8fde\u8d2f\u9a8c\u8bc1\u4f9d\u8d56\u9996\u6b21 CI run\uff0c\u9884\u8ba1 4/22 \u5408\u5e76\u540e\u89c2\u5bdf\u3002

**\u5173\u8054\uff1a** A21-10 follow-up\uff1bA8 \u5b8c\u6210\u3002


---

## D-033 — `sms_send_log` 表 5 项设计决策定论 (2026-04-21)

**背景：** A21-02b follow-up 长期挂在「等架构师拍板」状态。本次一次性敲定 5 项决策并落地。

**决策：**

1. **字段集**：表 `sms_send_log` 不包含 `params` 列。OTP / 通知模板参数（含明文 OTP）一律不入库，避免 PII 二次泄漏。审计需要时通过 `template_code` + 业务侧调用日志关联。
2. **手机号列方案 D（双列）**：
   - `phone_masked VARCHAR(20)`：脱敏后字符串（来自 `app.core.pii.mask_phone`，11 位号 → `138******34`）。供人眼可读。
   - `phone_hash VARCHAR(64) INDEXED`：SHA-256(phone + salt) hex。供「按号查记录」检索。
   - salt 来源：`Settings.pii_hash_salt`（环境变量 `PII_HASH_SALT`，默认 `yiluan-dev-salt-do-not-use-in-prod`，**生产必须覆盖**）。
3. **唯一约束方案 A**：DB 层 **无任何唯一约束**。重发 / 防爆破由业务层负责（已有 OTP brute-force protection commit `ce4259e`）。日志表是审计/最终一致写入路径，不应阻断业务。
4. **写入入口方案 A**：在 `app/services/providers/sms/factory.py::get_sms_provider()` 用 `LoggingSMSProviderWrapper` 包一层。**所有 provider 自动落库**，`Provider.send_*` 接口签名 / 实现保持不变，outbound 装饰器（A5/A21-03）语义不受影响。
5. **本次范围**：宽 — 建表 + ORM model + factory 接入 + 全套测试（12 用例）+ alembic 双向验证 + 文档收尾，一次到位。

**实施落地点：**

| # | 决策 | 文件 / 符号 |
|---|------|-------------|
| 1 | 无 `params` 列 | `backend/alembic/versions/d1e2f3a4b5c6_add_sms_send_log.py::upgrade()` 表定义 |
| 2 | `phone_masked` + `phone_hash` 双列 | 同上 + `backend/app/models/sms_send_log.py` + `backend/app/core/pii.py::hash_phone()` |
| 3 | 无 DB 唯一约束 | `d1e2f3a4b5c6_add_sms_send_log.py` 仅 4 个普通索引（`ix_sms_send_log_{phone_hash,biz_id,created_at,expires_at}`），无 unique constraint |
| 4 | factory wrapper 自动落库 | `backend/app/services/providers/sms/logging_wrapper.py::LoggingSMSProviderWrapper` + `factory.py::get_sms_provider()` 包装 |
| 5 | 宽范围一次到位 | `backend/tests/test_sms_send_log.py`（12 用例，全套 585 passed / 0 failed） |

**配套字段：**

- `expires_at = now() + 90d`（与 D-027 / `payment_callback_log` 一致）。索引 `ix_sms_send_log_expires_at` 供 TD-OPS-02 清理 job 使用。
- `user_id BIGINT NULLABLE FK→users.id ON DELETE SET NULL`：调用方上下文有则填，无则 NULL（不强制 fixture 化所有调用点）。
- `status VARCHAR(16) DEFAULT 'pending'`：生命周期 `pending → success | failed`。

**Alembic 验证：** 本地 SQLite stamp 至 `6bf94c0a3831`（payment unique constraint 之前）后 `upgrade head`，确认创建 `sms_send_log` 表 + 4 个索引；`downgrade -1` 后表 + 索引全部清理干净。PG 待真机验证。

**测试基线：** 573 → 585 passed, 0 failed（1 xfail / 5 deselected 均为既有用例）。

**关联：**

- A21-02b follow-up（`docs/FOLLOWUP.md` 中状态由「等架构师」改为「已落地 D-033」）
- TD-OPS-02（清理 job 范围扩至 `sms_send_log`）
- D-027（90d TTL 规约）
- 失败教训：A21-02-partial commit `38897f6` — 本次坚持 `op.create_table` + `op.create_index`，不用 `op.batch_alter_table`，避免 SQLite batch 模式重写无名约束。

---

## D-034 手机号绑定前置校验 + 错误码标准化 (2026-04-21)

**背景**：产品发现现有系统存在“用户未绑定手机号就能下单/接单/申请资质”的潜在隐患——只有患者下单页做了前端 modal 拦截，陪诊师接单、陪诊师资质申请、管理员审核通过 3 条路径完全没有校验。一旦数据库出现 `user.phone = NULL` 的订单或陪诊师，客服阶段无法联系当事人。

**讨论过程**：多角色讨论（后端工程师 / 小程序前端 / 安全 / 产品）得出一致结论——后端必须加硬兑底；同时借机把错误码结构化标准化，便于全端未来引入“机器可读 error_code”。三个原本争议点最终全部敲定做入本期：
1. iOS 端本期要做
2. 错误码统一重构本期要做
3. 陪诊师资质审核通过（verify）时要检查 phone（陪诊师本人的 phone，不是资质 profile 的）

**决定**：

### 1. 错误码基础设施（backend/app/core/error_codes.py）
- 新增常量表 `error_codes.py`，第一个机器可读错误码：`PHONE_REQUIRED`
- `BadRequestException` 扩展签名支持 `error_code` + `message`：
  - `raise BadRequestException("请先绑定手机号", error_code="PHONE_REQUIRED")`
  - FastAPI 错误 body 变为 `{"detail": {"error_code": "PHONE_REQUIRED", "message": "..."}}`
  - 未传 `error_code` 时仍然返回旧的 `{"detail": "..."}` 字符串格式（向后兼容）

### 2. Service 层 guard（4 处）
- `OrderService.create_order` — 患者下单
- `OrderService.accept_order` — 陪诊师接单
- `CompanionProfileService.apply` — 陪诊师提交资质申请
- `AdminAuditService.verify_companion` — 管理员审批通过（检查陪诊师本人 `user.phone`）
- 同时删除了 `companion_name = user.display_name or user.phone` 这种 fallback（phone 不应作为展示名）

### 3. 小程序前端
- `services/api.js` 拦截层：检测 400 + `error_code == PHONE_REQUIRED` → 弹 modal → 跳转 `bind-phone` 页（带 redirect 参数，绑完回到原页面）
- 陪诊师可接订单列表页 (`companion/available-orders`) 前置 modal
- 陪诊师订单详情页 (`companion/order-detail`) 前置 modal
- 资质申请页 (`companion/setup`) 已有 phoneBound 校验，未改动
- 患者下单页原有 modal 保留

### 4. iOS 端
- `APIError` 新增 `case phoneRequired(message: String)`
- `ErrorResponse` 自定义 `init(from:)` 支持两种 detail 格式（string / dict）
- `APIClient.execute` + `requestVoid` 在 400 遇到 PHONE_REQUIRED 时抛 `.phoneRequired`
- 新增 `Core/Extensions/PhoneRequiredAlert.swift` view modifier，挂在页面 NavigationStack 上即可自动弹 alert + sheet 推 BindPhoneView
- `OrderViewModel` + `CompanionProfileViewModel` 新增 `@Published var phoneRequiredMessage`，私有 `handleError()` 统一分流
- 已挂 modifier 的 view：`CreateOrderView`、`CompanionSetupView`
- 陪诊师接单 View iOS 端暂未实装（只有 VM 支持），VM 改动已就绪，future-ready

### 5. 测试
- 新增 `backend/tests/test_phone_required_guards.py` 5 个测试用例覆盖 4 条路径 + 1 条向后兼容（legacy detail 字符串格式）
- 后端总计 **590 passed**（基线 585 → 590）
- 小程序 **176 passed**（基线 165 → 176，团队进度）
- iOS 无本地 build 环境，代码改动保守，依赖 CI 验证

**影响面**：
- API 破坏性兼容：**无**。未带 `error_code` 的旧异常路径 detail 仍是字符串；新路径 detail 是 `{error_code, message}` 对象。小程序 / iOS 端都已升级兼容两种格式。
- 数据迁移：无
- 依赖：无新增依赖

**负责人**：虚拟工程团队（本次由文龙决策拍板）

**关联**：
- 产品背景：客服阶段“用户未绑定手机号”无法联系的潜在风险
- 后续可复用：`error_codes.py` 常量表为将来引入 `PAYMENT_REQUIRED`、`VERIFICATION_REQUIRED` 等机器可读错误码铺好基础设施


---

## 2026-04-21 (\u7eed)

### D-035 \u6269\u5c55 error_code \u4f53\u7cfb\uff1aPAYMENT_REQUIRED / VERIFICATION_REQUIRED + iOS \u966a\u8bca\u5e08\u63a5\u5355 View\n- **\u53c2\u4e0e\u89d2\u8272**\uff1aBackend / iOS / Frontend\n- **\u80cc\u666f**\uff1aD-034 \u843d\u5730 PHONE_REQUIRED \u540e\uff0c\u53d1\u73b0 **\u4e24\u4e2a\u9057\u6f0f\u7684\u670d\u52a1\u5c42\u6f0f\u6d1e**\uff1a\n  1. ccept_order \u53ea\u6821\u9a8c\u624b\u673a\u53f7\u3001**\u672a\u6821\u9a8c\u8d44\u8d28\u662f\u5426\u901a\u8fc7**\u2014\u2014\u672a\u5ba1\u6838\u7684\u966a\u8bca\u5e08\u80fd\u7406\u8bba\u4e0a\u76f4\u63a5\u63a5\u5355\uff1b\n  2. start_order / confirm_start_service **\u672a\u6821\u9a8c\u8ba2\u5355\u662f\u5426\u5df2\u652f\u4ed8**\u2014\u2014\u672a\u4ed8\u6b3e\u7684\u8ba2\u5355\u6709\u673a\u4f1a\u88ab\u76f4\u63a5 start\u3002\n- **\u51b3\u7b56**\uff1a\n  1. \u65b0\u589e VERIFICATION_REQUIRED\u3001PAYMENT_REQUIRED \u4e24\u4e2a error_code \u5e38\u91cf\uff1b\n  2. Backend\uff1a\u5728 ccept_order \u52a0 verification guard\uff1b\u5728 start_order + confirm_start_service \u52a0 payment guard\uff1b\n  3. iOS\uff1aAPIError \u65b0\u589e .paymentRequired / .verificationRequired case\uff0cAPIClient \u7edf\u4e00\u5206\u53d1\uff1bViewModel \u539f\u5148 **\u5b58\u5728\u65e0\u9650\u9012\u5f52 bug** (handleError \u2192 handleError) \u4e00\u540c\u4fee\u6b63\uff1bOrderDetailView \u6302\u4e0a\u4e09\u79cd alert modifier\uff1b\n  4. \u5c0f\u7a0b\u5e8f\uff1aservices/api.js \u62d3\u5c55 guard \u5904\u7406\uff0c_skipPhoneRequiredHandler \u5347\u7ea7\u4e3a _skipGuardHandlers (\u5411\u540e\u517c\u5bb9\u4fdd\u7559\u65e7\u53c2\u6570)\uff1b\n  5. iOS OrderDetailView \u540c\u65f6\u8865\u9f50\u966a\u8bca\u5e08 **\u62d2\u5355 / \u8bf7\u6c42\u786e\u8ba4\u5f00\u59cb** \u4e24\u4e2a\u7f3a\u5931\u7684\u52a8\u4f5c\u6309\u94ae\u3002\n- **\u6d4b\u8bd5**\uff1a\n  - Backend\uff1a+4 \u4e2a\u65b0 guards \u6d4b\u8bd5 (VERIFICATION/PAYMENT) \u00d7 2 \u79cd\u89d2\u5ea6\uff0c\u9769\u547d\u6027\u66f4\u65b0 companion_client fixture \u4e3a **idempotent seed profile**\u... [truncated]

---

## 2026-04-24

### D-038 上线前 polish 冻结- **参与角色**：Arch / Frontend
- **背景**：Sprint W17 进入上线就绪阶段，全栈 853 用例全绿，5 个外部依赖 Blocker（B-01～B-05）仍在。`polish-backlog.md` 中尚有 10 项 UI 微调（tabBar 高亮、钱包页金额字体一致性等）待合入；继续在发布周合入将放大回归面，与 Sprint Goal（上线就绪）冲突。
- **决策**：本周（4/24 起至本 Sprint 收尾）**禁止合入 polish-backlog 任何 UI 微调** PR；所有微调统一延后至 Sprint W18 灰度发布完成后批量合入并集中回归。
- **影响范围**：微信小程序 + iOS 端所有非阻塞型视觉/交互优化。Bug 修复、合规性文案修改、Blocker 相关改动不在冻结范围内。
- **负责人**：Arch（守门）+ Frontend（执行 / 拒绝 PR）
- **关联**：Sprint W17 上线就绪目标、`polish-backlog.md`、A-2604-04
- **状态**：执行中

### D-039 iOS CI 4/24 EOD 硬截止
- **参与角色**：Frontend / Ops
- **背景**：iOS CI 自 D-029 立项以来始终未拿到第一次绿色 run，`b989b27` 已优化 simulator destination 动态查询。Blocker B-05（App Store 上线）的风险评估必须建立在 CI 至少跑通一次的基础上，否则发布走 TestFlight 备用方案的判断缺少数据支撑。
- **决策**：iOS GitHub Actions macOS workflow 必须在 **2026-04-24 EOD 前**出现至少一次完整绿色 run。若未达成，视为 B-05 风险升级，立即启动 TestFlight 备用方案——本地 Archive + 手工上传 TestFlight 进行内测验证，不再阻塞发布节奏。
- **影响范围**：iOS 发布路径、B-05 评估方法学、QA 回归策略（CI 不绿则回退到本地手工跑测）。
- **负责人**：Frontend（盯死 workflow 排障）+ Ops（macOS runner / image 侧支援）
- **关联**：D-029（iOS CI 立项）、B-05（App Store 上线 Blocker）、`b989b27`（dynamic simulator destination）、A-2604-04
- **状态**：执行中（截止 2026-04-24 EOD）


---

## D-040 (2026-04-24) — Alertmanager 走企业微信群机器人，不再引入新的 IM 系统

**Owner:** Ops
**关联:** A-2604-07 / 配置告警通道（runbook-go-live.md "配置告警" 小节）
**类型:** 决策

### 背景

Alertmanager 已经接入 Prometheus，需要选择一个面向 oncall 的通知通道。候选：

1. **Slack** — 海外团队主流，但内部并未部署；需要单独账户与翻墙。
2. **钉钉机器人** — 可用，但全员日常 IM 已是企业微信，再多一个系统增加噪音与切换成本。
3. **企业微信群机器人**（采用） — 全员都在用，oncall 群已存在，机器人 webhook 接入零成本。
4. **Email-only** — 响应延迟过大，仅作为 critical 兜底。

### 决策

- 默认通道：**企业微信群机器人**，通过本仓库内的 wechat-work webhook 适配器（`ops/alertmanager/wechat-work-webhook.py`）转发。
- critical 级别：企业微信 + email 双通道。
- webhook URL 通过环境变量 `WECHAT_WORK_WEBHOOK_URL` 注入；未设置时适配器进入 dry-run 模式（仅日志，不会因为缺配置而崩溃）。
- 同 alertname 60s 内最多 3 条，由适配器侧做应用级限流，避免告警风暴洗版群。

### 不做

- 不引入 Slack/钉钉。
- 不在仓库中硬编码任何真实 webhook URL（PM 提供后由部署侧通过环境变量注入）。

### 待办

- [ ] PM 提供企业微信 oncall 群机器人 webhook URL → 写入部署环境变量 `WECHAT_WORK_WEBHOOK_URL`。
- [ ] PM 提供 critical 级别 oncall 邮箱组 → 写入 `ONCALL_EMAIL` 与 SMTP 凭证（`SMTP_SMARTHOST` / `SMTP_FROM` / `SMTP_USERNAME` / `SMTP_PASSWORD`）。


---

## D-041 (2026-04-25) — 金额字段 Float → Decimal(10,2) 全链路迁移 (ADR-0030)

### 背景

`Order.price` / `Payment.amount` / `SERVICE_PRICES` 长期使用 `Float`（PG `DOUBLE PRECISION`），存在 IEEE 754 风险：299 * 0.5 在浮点下偶发 149.49999999999997，退款比例、对账聚合、yuan→fen 转换链路上累积误差有可能引发资金差错。TD-ARCH-03。

### 决策

后端"内部精确、对外兼容"：

- **模型层**：`Order.price` / `Payment.amount` 改 `Numeric(10, 2)`，类型 `Decimal`。
- **服务层**：`SERVICE_PRICES`、Provider DTO（`OrderDTO.amount_yuan` / `RefundDTO.total_yuan` / `refund_yuan`）、`PaymentService` / `WalletService` / admin 退款比例全部 `Decimal`；yuan→fen 用 `int(round(amount * 100))`，舍入用 `quantize(Decimal('0.01'), ROUND_HALF_UP)`。
- **Schema 层**：Pydantic 用 `field_serializer` 把 `Decimal` 输出为 JSON `number`（`299.0`），**API 出参契约不变**。
- **迁移**：`a1d0c0de0030_money_to_decimal_adr_0030.py`，PG 用 `USING ::numeric(10,2)` 强转，SQLite 走 `batch_alter_table`，含 downgrade。
- **三端**：小程序 `formatPrice` 兼容 number / 字符串入参，**零改动**（仅加 ADR-0030 注释锚定契约）；iOS `Order.price` / `Payment.amount` 早期已是 `Decimal`。

### 验证

- 后端全量回归：**880 passed / 15 skipped / 108s**（基线 867 + 新增 13 锁契约用例 `tests/unit/test_decimal_money.py`：精度、舍入边界、yuan→fen、API 序列化形态）。
- iOS：72 个 XCTest 用例覆盖（12 文件 / 867 行），ViewModel/Model 层均已 Decimal。

### 未尽事项 / 已知小坑

- Swift `Decimal` 默认 Codable 经 Double 中转，理论上对极小数有精度风险。当前金额仅 2 位小数、API 输出形态固定，未触发；后续可加自定义 `init(from:)` 或 `JSONDecoder.decimalDecodingStrategy` 兜底。归入新技术债 TD-IOS-01（轻量，非阻塞）。
- 数据库现存 Float 数据迁移到 Numeric(10,2) 时由 PG 隐式 round；ops 部署前需在 staging 跑一次 `SELECT count(*) FROM orders WHERE price::numeric(10,2) <> price` 确认无超精度脏数据。
