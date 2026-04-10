# 医路安（YiLuAn）上线任务拆解

**生成日期：** 2026-04-10  
**目标：** 在 2~3 周内把当前 MVP 推进到可上线发布版本  
**范围：** 微信小程序优先上线；iOS 进入 TestFlight / 次阶段正式发布  

---

## 一、任务总览

### P0（必须完成，阻塞上线）
1. 真实支付接入（微信支付）
2. 真实短信接入（阿里云 / 腾讯云）
3. 生产环境部署（API / PostgreSQL / Redis / Blob / 域名 / HTTPS）
4. 生产安全配置收口
5. 小程序审核与合规资料
6. 平台运营最小后台能力（陪诊师审核 / 订单干预 / 退款处理）

### P1（建议同步推进）
7. 发布前回归测试与压测
8. 监控、日志、告警
9. 关键页面 UI/UX 收口
10. iOS 内测发布准备

### P2（可延后）
11. 优惠券 / 营销 / 数据看板
12. 更精细的角色权限系统
13. iOS 自动化测试体系

---

## 二、按角色拆解任务

## 1）架构师（Arch）

### A1. 上线架构冻结
- **目标**：冻结 v1 上线范围，避免继续加需求
- **输出**：`docs/release-v1-scope.md`
- **内容**：
  - 微信小程序为第一发布端
  - iOS 仅做内测 / 次阶段发布
  - 后端保持单体，不拆微服务
  - 后台管理系统只做 MVP
- **验收标准**：范围清晰、P0/P1/P2 明确、全员认可

### A2. 支付/退款边界设计
- **目标**：明确订单状态与支付状态边界
- **涉及文件**：
  - `backend/app/services/order.py`
  - `backend/app/models/order.py`
  - `backend/app/models/payment.py`
- **输出**：`docs/payment-architecture.md`
- **关键决策**：
  - 支付成功回调是否直接驱动订单状态
  - 退款是同步还是异步确认
  - 幂等键使用订单号还是支付单号
- **验收标准**：状态机图 + 回调时序图 + 异常场景表

### A3. 后台管理 MVP 边界
- **目标**：控制后台范围，防止过度开发
- **建议只做 4 项能力**：
  1. 陪诊师审核
  2. 订单查询与强制状态干预
  3. 退款审核/执行
  4. 用户封禁/解封
- **输出**：`docs/admin-mvp-scope.md`

---

## 2）资深后端开发（Backend）

### B1. 微信支付接入
- **优先级**：P0
- **目标**：从模拟支付切换到真实支付
- **涉及模块**：
  - `backend/app/api/v1/orders.py`
  - `backend/app/services/order.py`
  - `backend/app/services/wallet.py`
  - `backend/app/models/payment.py`
  - 新增 `backend/app/services/payment_wechat.py`
  - 新增 `backend/app/api/v1/payments.py`
- **子任务**：
  1. 创建统一下单接口
  2. 保存支付单记录
  3. 处理支付回调验签
  4. 处理退款接口与回调
  5. 保证幂等（重复回调不重复更新）
- **验收标准**：
  - 支付成功后订单状态正确变化
  - 回调重复调用不出错
  - 退款链路可验证

### B2. 真实短信服务接入
- **优先级**：P0
- **涉及文件**：
  - `backend/app/services/auth.py`
  - `backend/app/config.py`
  - 可能新增 `backend/app/services/sms.py`
- **子任务**：
  1. 对接阿里云 / 腾讯云短信
  2. 保留 mock provider 作为开发模式
  3. 增加短信发送失败重试/日志
  4. 限频策略复核
- **验收标准**：测试手机号能收到真实验证码

### B3. 生产配置收口
- **优先级**：P0
- **涉及文件**：
  - `backend/app/config.py`
  - `.env.example`
  - 新增 `.env.production.example`
- **必须修改**：
  - `debug` 改为环境控制
  - `environment=production`
  - 替换 dev JWT secret
  - `cors_origins` 改白名单
  - 微信 / Azure / SMS 配置可注入
- **验收标准**：本地/测试/生产配置分层清晰

### B4. 后台管理接口（MVP）
- **优先级**：P0
- **建议新增**：
  - `backend/app/api/v1/admin_companions.py`
  - `backend/app/api/v1/admin_orders.py`
  - `backend/app/api/v1/admin_users.py`
- **接口范围**：
  - 陪诊师审核通过/驳回
  - 查询订单、人工改状态、发起退款
  - 用户禁用/恢复
- **验收标准**：运营角色可最小化干预平台流程

### B5. 安全与稳定性补丁
- **优先级**：P1
- **内容**：
  - JWT 时间处理弃用告警修复
  - 上传文件大小/类型校验
  - 回调接口签名校验
  - 审计日志补充
- **验收标准**：关键高风险点全部有防护

---

## 3）资深前端开发（Frontend）

### F1. 微信小程序支付链路改造
- **优先级**：P0
- **涉及目录**：
  - `wechat/pages/patient/create-order`
  - `wechat/pages/patient/order-detail`
  - `wechat/services/api.js`
  - `wechat/utils/constants.js`
- **子任务**：
  1. 支付前确认页
  2. 拉起微信支付
  3. 支付结果页 / 失败重试
  4. 退款状态展示
- **验收标准**：用户能从下单顺畅走到支付完成

### F2. 小程序审核必备页面与入口
- **优先级**：P0
- **页面/功能**：
  - 隐私政策页
  - 用户协议页
  - 服务协议页
  - 客服 / 联系我们入口
  - 注销账号 / 删除账户说明（如适用）
- **验收标准**：满足微信小程序审核要求

### F3. 陪诊师审核状态与信任表达优化
- **优先级**：P1
- **目标**：增强平台可信度
- **页面**：
  - `wechat/pages/companion/profile`
  - `wechat/pages/companion/setup`
- **优化内容**：
  - 审核状态标签
  - 资料缺失提示
  - 身份认证进度

### F4. iOS 发布准备
- **优先级**：P1
- **涉及目录**：
  - `ios/YiLuAn/Features/*`
  - `ios/YiLuAn/Core/Networking/*`
- **子任务**：
  1. 冒烟测试关键路径
  2. 修复明显 UI/状态问题
  3. 准备 TestFlight 元数据
- **验收标准**：至少具备稳定内测能力

---

## 4）产品经理（PM）

### P1. 上线需求冻结
- **优先级**：P0
- **输出**：`docs/release-checklist.md`
- **内容**：
  - 本次发布包含什么 / 不包含什么
  - 审核资料清单
  - 发布成功定义

### P2. 合规文档准备
- **优先级**：P0
- **输出文档**：
  - `docs/privacy-policy.md`
  - `docs/terms-of-service.md`
  - `docs/service-agreement.md`
- **验收标准**：小程序和 iOS 都可直接引用

### P3. 运营流程设计
- **优先级**：P0
- **内容**：
  - 陪诊师审核 SOP
  - 退款处理 SOP
  - 纠纷处理 SOP
  - 客服响应路径
- **输出**：`docs/ops-playbook.md`

### P4. 版本发布节奏
- **优先级**：P1
- **建议**：
  - 第 1 周：支付 / 短信 / 配置 / 合规
  - 第 2 周：后台 MVP / 回归测试 / staging 发布
  - 第 3 周：小程序提审 / iOS TestFlight / 正式发布

---

## 5）UI / UE / UX 设计（Design）

### D1. 关键路径收口
- **优先级**：P1
- **重点页面**：
  - 下单页
  - 订单详情页
  - 支付结果页
  - 钱包页
  - 陪诊师资料审核页
- **目标**：降低认知负担、提升信任感

### D2. 品牌与风格统一
- **优先级**：P1
- **输出**：`docs/ui-guidelines.md`
- **内容**：
  - 主色 / 辅助色
  - 按钮等级
  - 状态标签（待支付/已接单/服务中/已完成/退款中）
  - 空状态 / 错误态统一风格

### D3. 审核合规视觉检查
- **优先级**：P0
- **内容**：
  - 隐私协议可见性
  - 价格透明
  - 退款规则可见
  - 联系客服路径明确

---

## 6）测试（QA）

### Q1. 发布前回归清单
- **优先级**：P0
- **输出**：`backend/tests/release_regression_checklist.md`
- **必测场景**：
  1. OTP 登录
  2. 微信登录
  3. 患者下单
  4. 支付成功 / 失败 / 取消
  5. 陪诊师接单
  6. 开始服务 / 完成服务
  7. 评价
  8. 聊天 / 通知
  9. 退款

### Q2. 支付专项测试
- **优先级**：P0
- **内容**：
  - 回调幂等
  - 重复点击支付
  - 退款边界
  - 网络中断恢复

### Q3. 性能与稳定性检查
- **优先级**：P1
- **内容**：
  - 登录 / 下单 / 订单列表压测
  - WebSocket 长连接稳定性
  - Redis / PostgreSQL 基本负载验证

### Q4. iOS 冒烟清单
- **优先级**：P1
- **内容**：
  - 登录
  - 下单
  - 订单状态流转
  - 聊天
  - 通知

---

## 7）运维 / DevOps（Ops）

### O1. Staging/Production 环境搭建
- **优先级**：P0
- **建议架构**：
  - Azure Container Apps（API）
  - Azure Flexible PostgreSQL
  - Azure Redis
  - Azure Blob Storage
  - 自定义域名 + HTTPS
- **输出**：`docs/deployment-plan.md`

### O2. GitHub Actions 扩展为 CD
- **优先级**：P1
- **当前已有**：测试流水线
- **新增目标**：
  - build image
  - deploy to staging
  - 手动 promote to production
- **涉及文件**：`.github/workflows/test.yml`（或新增 deploy workflow）

### O3. 监控告警
- **优先级**：P1
- **内容**：
  - API 错误率
  - 响应时间
  - 支付回调失败率
  - WebSocket 在线数
  - PostgreSQL 连接数
- **验收标准**：至少有日志和关键告警

### O4. 密钥管理
- **优先级**：P0
- **内容**：
  - JWT secret
  - WeChat app secret
  - 支付密钥
  - Azure 存储连接串
  - SMS 密钥
- **验收标准**：不落仓库，统一通过环境变量或 Secret Manager 注入

---

## 三、推荐执行顺序（按周）

## Week 1：上线阻塞项清除
- Arch：支付/退款边界冻结
- Backend：真实支付、真实短信、生产配置
- Frontend：小程序支付页与协议页
- PM：审核资料、协议文档
- QA：支付专项测试用例
- Ops：staging 环境搭建

## Week 2：平台治理 + 联调
- Backend：后台管理接口 MVP
- Frontend：后台或运营端最小前台（如需要）
- QA：全链路回归
- Ops：日志监控、部署自动化
- Design：关键页面体验收口

## Week 3：发布冲刺
- 小程序提审
- iOS TestFlight
- 生产环境发布
- 发布后监控观察

---

## 四、今日可立即开工的 Top 5

1. **Backend：设计并接入微信支付真实链路**
2. **Backend：切换短信 provider，从 mock 到真实服务**
3. **Ops：准备 staging 环境与生产配置模板**
4. **PM：输出小程序审核清单与协议文档**
5. **QA：列出支付/退款全链路测试用例**

---

## 五、里程碑定义

### M1：功能可发布
- 真实支付完成
- 真实短信完成
- 配置与安全完成

### M2：系统可运营
- 后台管理 MVP
- 监控告警
- 运营 SOP

### M3：产品正式上线
- 小程序审核通过
- 生产环境稳定运行
- 首批真实用户可完成交易闭环

---

## 六、一句话结论

> 医路安现在最需要的不是“更多功能”，而是围绕支付、部署、合规、运营的收口执行。谁先把这四件事打通，谁就在真正推动上线。
