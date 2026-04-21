# 医路安外部凭证 / 资源依赖追踪

> 本文档追踪上线前必须就位的 5 个外部凭证 / 资源 Blocker。
> 状态：Pending | In Progress | Done
> 责任人默认 = 用户（项目负责人）

---

## B-01 微信支付商户号 + APIv3 + 证书 zip

**状态：** Pending
**责任人 / 催办人：** 用户

### 所需材料

- 微信支付商户号（`WECHAT_PAY_MCH_ID`）
- APIv3 密钥（32 字节，`WECHAT_PAY_API_KEY_V3`）
- 商户 API 证书 zip（含私钥 PEM + 证书序列号）
  - `WECHAT_PAY_CERT_SERIAL`
  - `WECHAT_PAY_PRIVATE_KEY_PATH`
  - `WECHAT_PAY_PLATFORM_CERT_PATH`
- 支付回调 HTTPS URL（`WECHAT_PAY_NOTIFY_URL`，需域名 + ICP 备案后配置）
- 微信小程序 AppID（`WECHAT_APP_ID`，真实值）

### 提交方式

1. 登录 [微信支付商户平台](https://pay.weixin.qq.com) 申请商户号。
2. 在「API 安全」页面设置 APIv3 密钥、下载证书 zip。
3. 将上述值写入 Azure Key Vault，环境变量挂载到容器。

### 预计耗时

商户号审核 1-3 工作日（需营业执照）。

### 最近一次催办

- 2026-04-21 — A21-07 状态回填：仍 Pending，等待用户启动商户号申请；建议本周内同步评估「连连支付 / Adyen / Pingpp」备份方案（A21-13）以降低单点风险
- 2026-04-20 — 等待用户提交

### 阻塞影响

- 真实微信支付流程（当前使用 mock provider）
- 生产环境支付回调验签
- 下单 → 支付 → 回调 → 退款全链路回归

---

## B-02 阿里云 SMS AccessKey + 模板 ID

**状态：** Pending
**责任人 / 催办人：** 用户

### 所需材料

- 阿里云 RAM 子账号 AccessKey ID（`SMS_ACCESS_KEY`，最小权限：仅 Dysmsapi）
- AccessKey Secret（`SMS_ACCESS_SECRET`）
- 短信签名（`SMS_SIGN_NAME`，如「医路安」，需审核通过）
- OTP 验证码模板 ID（`SMS_TEMPLATE_CODE`）
- 通用通知模板 ID（`SMS_NOTIFY_TEMPLATE_CODE`）
- 可选：区域（`SMS_REGION`，默认 `cn-hangzhou`）

### 提交方式

1. 登录 [阿里云短信服务控制台](https://dysms.console.aliyun.com) 申请签名 + 模板。
2. 在 RAM 控制台创建子账号，仅授予 `AliyunDysmsFullAccess`。
3. 将 AK/SK 写入 Azure Key Vault。

### 预计耗时

签名审核 1-2 工作日；模板审核 1 工作日。

### 最近一次催办

- 2026-04-21 — A21-07 状态回填：阿里云 SMS Provider 代码层 4-20 已落地（commit 7d8a7d0），仍缺真实 AK/SK 与签名审核；签名通常需 1-2 工作日，建议**本周内**至少先把签名「医路安」提交审核，凭证可后补
- 2026-04-20 — 等待用户提交

---

## B-03 ACR / 生产资源（K8s 集群 / RDS / Redis）

**状态：** Pending
**责任人 / 催办人：** 用户

### 所需材料

- Azure 订阅 ID（`AZURE_SUBSCRIPTION_ID`）
- Azure 资源组（建议 `yiluan-rg`，区域 `eastasia`）
- Azure Service Principal JSON（`AZURE_CREDENTIALS`）
- ACR（Azure Container Registry）名称 + 登录凭证（`ACR_USERNAME` / `ACR_PASSWORD`）
- Azure Key Vault 名称（建议 `yiluan-kv`）
- Container Apps 环境名（建议 `yiluan-env`）
- PostgreSQL Flexible Server 管理员账号 + 初始密码
- Staging / Production DB 连接串（`STAGING_DATABASE_URL` / `PRODUCTION_DATABASE_URL`）
- Azure Cache for Redis 实例名 + access key
- Application Insights 连接串（`APPLICATIONINSIGHTS_CONNECTION_STRING`）
- Log Analytics Workspace ID + Key

### 提交方式

1. 在 Azure Portal 创建资源组及上述资源。
2. 使用 `az ad sp create-for-rbac` 创建 Service Principal。
3. 将凭证写入 GitHub Secrets（见下方汇总表）及 Azure Key Vault。

### GitHub Secrets 汇总

| Secret 名 | 用途 |
|-----------|------|
| `AZURE_CREDENTIALS` | `azure/login` Service Principal |
| `ACR_USERNAME` / `ACR_PASSWORD` | 推送镜像到 ACR |
| `STAGING_DATABASE_URL` | Staging Alembic 迁移 |
| `PRODUCTION_DATABASE_URL` | Production Alembic 迁移 |

### 预计耗时

Azure 资源创建 < 1 小时（自助）；需 Azure 订阅已开通。

### 最近一次催办

2026-04-20 — 等待用户提交

### 阻塞影响

- CI/CD 部署流水线（`deploy.yml`）
- Staging / Production 环境搭建
- Alembic 生产迁移
- 监控告警接入

---

## B-04 域名 + ICP 备案

**状态：** Pending
**责任人 / 催办人：** 用户

> **重点 Blocker**：ICP 备案未完成前，网站不能解析到国内服务器。

### 所需材料

| # | 材料 | 说明 |
|---|------|------|
| 1 | **营业执照**（彩色扫描件） | 统一社会信用代码清晰可辨 |
| 2 | **法人身份证正反面** | 有效期内，照片清晰 |
| 3 | **网站负责人身份证正反面** | 可与法人不同；需在备案系统做人脸核验 |
| 4 | **域名证书** | 从域名注册商控制台下载（阿里云 / 腾讯云） |
| 5 | **域名实名认证截图** | 域名持有者须与备案主体一致 |
| 6 | **网站建设方案书** | 部分管局要求；描述网站用途、内容、技术架构 |

### 提交方式

1. 在**阿里云备案系统**（或腾讯云备案系统）提交初审。
2. 云服务商初审通过后，提交至**通信管理局**（北京管局）终审。
3. 终审通过后获得 ICP 备案号（如 京ICP备XXXXXXXX号）。

### 预计耗时

- 云服务商初审：1-2 工作日
- 通信管理局终审：**7-15 工作日**（北京管局）
- 总计：**约 10-20 工作日**

### 注意事项

1. **备案号下来前，网站域名不能解析到国内服务器**（否则会被封堵）。
2. **公安备案**需在 ICP 备案通过后 **30 日内**到 [全国互联网安全管理服务平台](http://www.beian.gov.cn) 完成。
3. 域名持有者必须与备案主体（营业执照）一致，不一致需先做域名过户。
4. 微信小程序后台「request 合法域名」需填写已备案域名（`https://api.yiluan.com`）。
5. 建议的域名：
   - 生产 API：`api.yiluan.com`
   - Staging API：`api-staging.yiluan.com`

### 最近一次催办

- 2026-04-21 — A21-08 推进：B-04 ICP 备案 6 项主体资料 checklist（见上表）今日与用户对齐齐备性；**关键路径**：本资料齐备后阿里云初审 1-2 工作日 + 北京管局终审 7-15 工作日，是当前**所有外部 Blocker 中耗时最长**的一项，必须本周内提交否则影响 5 月发布窗口
- 2026-04-20 — 等待用户提交

### 阻塞影响

- **所有国内生产环境部署**（域名无法解析到国内服务器）
- 微信小程序后台域名白名单配置
- 微信支付回调 URL 配置（依赖 B-01）
- SSL 证书签发（依赖域名）
- 微信小程序审核提交（需合法域名）

---

## B-05 Apple 开发者账号

**状态：** Pending
**责任人 / 催办人：** 用户

### 所需材料

- Apple Developer Program 组织账号（$99/年）
- 需要一个 Apple ID 作为 Account Holder
- D-U-N-S 编号（组织类型申请需要；如无需先申请，约 1-2 周）

### 提交方式

1. 在 [Apple Developer](https://developer.apple.com/programs/) 注册组织类型开发者账号。
2. 提交 D-U-N-S 编号 + 组织信息。
3. Apple 审核通过后即可使用。

### 预计耗时

- 已有 D-U-N-S：审核 1-3 工作日
- 无 D-U-N-S：额外 7-14 工作日申请

### 最近一次催办

2026-04-20 — 等待用户提交

### 阻塞影响

- iOS App Store 发布
- TestFlight 内测分发
- 推送通知证书（APNs）配置
- iOS 签名 + Archive

---

> 以上凭证 / 资源准备好后通知团队，Phase 2 真实接入可随时切换。
> 当前所有开发使用 mock provider 先行推进，架构已预留切换能力。
> Provider 抽象详见 `backend/app/services/providers/payment/` 及 `backend/app/services/providers/sms/`。
> 运维段对齐 `docs/deployment.md` §16 环境变量清单与 `.github/workflows/deploy.yml`。
