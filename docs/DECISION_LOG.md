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
