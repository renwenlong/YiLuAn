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
