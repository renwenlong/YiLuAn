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
