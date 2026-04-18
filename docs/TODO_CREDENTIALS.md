# 医路安待办事项（需用户提供）

## 微信支付凭证（P0 - 阻塞真实上线）

下列字段是 `WechatPaymentProvider` 切换到 `settings.payment_provider="wechat"`
后正常工作所需的**全部**配置项。环境变量名与 `app.config.Settings`
中的字段对应。也可通过常量
`app.services.providers.payment.wechat.REQUIRED_PRODUCTION_SETTINGS`
程序化获取。

| 环境变量 | settings 字段 | 说明 |
| --- | --- | --- |
| `WECHAT_APP_ID` | `wechat_app_id` | 微信小程序 AppID |
| `WECHAT_PAY_MCH_ID` | `wechat_pay_mch_id` | 微信支付商户号 |
| `WECHAT_PAY_API_KEY_V3` | `wechat_pay_api_key_v3` | APIv3 32 字节密钥（用于回调 AES-GCM 解密） |
| `WECHAT_PAY_CERT_SERIAL` | `wechat_pay_cert_serial` | 商户 API 证书序列号 |
| `WECHAT_PAY_PRIVATE_KEY_PATH` | `wechat_pay_private_key_path` | 商户 API 私钥 PEM 文件绝对路径（容器内挂载点） |
| `WECHAT_PAY_NOTIFY_URL` | `wechat_pay_notify_url` | 公网 HTTPS 回调 URL，例：`https://api.example.com/api/v1/payments/wechat/callback` |
| `WECHAT_PAY_PLATFORM_CERT_PATH` | `wechat_pay_platform_cert_path` | 微信平台证书 PEM 路径（用于校验回调签名） |

切换步骤：
1. 上述字段全部填入生产环境（推荐 Azure Key Vault + 容器环境变量挂载）。
2. 设置 `PAYMENT_PROVIDER=wechat`。
3. `Settings` 自带启动期校验（见 `config.py`）：缺任一字段会在进程启动失败，不会出现 silent fallback。
4. 部署后跑回归冒烟：下单 → 支付 → 回调 → 退款。回调幂等保护见 `payment_callback_log` 表。

## 短信服务凭证（P0）
- [ ] 阿里云/腾讯云 SMS AccessKey
- [ ] 短信签名
- [ ] 短信模板 ID

## 生产环境（P0）
- [ ] Azure 订阅 / 资源组
- [ ] 域名（已备案）
- [ ] SSL 证书（或 Azure 自动签发）

## 应用发布（P1）
- [ ] 微信小程序 AppID + AppSecret（真实值）
- [ ] Apple Developer 账号（iOS 发布）

---

> 以上信息准备好后通知团队，Phase 2 真实接入可随时切换。
> 当前所有开发使用 mock provider 先行推进，架构已预留切换能力。
> Provider 抽象详见 `backend/app/services/providers/payment/`。
