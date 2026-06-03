# YiLuAn 灰度通道部署文档

> S2-OPS-011 配套；S2-TEST-004 灰度回归 §1 / §5 硬阻塞前置
> 范围：staging 灰度环境（独立于生产，但接真 wxpay 商户号）

---

## 1. 灰度通道与 staging mock 的关系

| 维度 | staging (mock) | canary (本文档) | production |
|---|---|---|---|
| `PAYMENT_PROVIDER` | mock | **wechat** (真 wxpay 商户号) | wechat |
| `SMS_PROVIDER` | mock | **aliyun** (真验证码) | aliyun |
| nginx 公网可达 | 否（127.0.0.1） | **是**（HTTPS + 真域名） | 是 |
| `WECHAT_PAY_NOTIFY_URL` | 内部 mock-pay-stub | **公网回调** | 公网回调 |
| 真实用户流量 | 0 | 0（团队内部测试） | 真实 |
| 数据库 | staging-pg（隔离） | canary-pg（独立） | prod-pg |
| Feature flags | 默认 | **灰度门可热切** | 默认 |
| 监控告警 | 内部 webhook dry-run | **真企业微信群** | 真企业微信群 |

**核心约束**：灰度通道**用真支付链路 + 真短信，但用户范围限制为团队内部**。一旦发现问题立即按 [canary-rollback-runbook.md](./canary-rollback-runbook.md) 回滚。

---

## 2. 拉起灰度通道前置 checklist

### 2.1 服务前置

- [ ] S2-OPS-010 staging Prometheus/AM/Grafana 实拉跑通（PR #145）
- [ ] Grafana dashboard 三档实时图可见
- [ ] Alertmanager webhook 真 fire 到企业微信群（不能是 dry-run）

### 2.2 配置前置

- [ ] 微信支付商户号 + API V3 密钥（运营从微信支付商户平台拿）
- [ ] 微信支付证书（apiclient_cert.pem + apiclient_key.pem）
- [ ] 公网域名 + HTTPS 证书（nginx）
- [ ] 阿里云短信 AccessKey + SignName + TemplateCode
- [ ] 企业微信群机器人 webhook URL（运营 + PM 两条独立群）

### 2.3 流量前置

- [ ] 团队内部测试用户白名单（patient/companion phone 限定）
- [ ] 真实金额限制（建议单笔 ≤ ¥1，团队报销）
- [ ] 短信发送频率上限（OPS dashboard 观察）

---

## 3. canary 配置文件结构

### 3.1 deploy/env.canary（入库，仅假值/可公开）

```bash
# 复用 env.staging 多数项
include env.staging  # 概念，实际是 docker compose --env-file 多次叠加

# 区别
ENVIRONMENT=development  # 灰度仍 dev 模式便于 OTP 000000 兜底（生产前改 production）
DEBUG=false
PAYMENT_PROVIDER=wechat
SMS_PROVIDER=aliyun
WECHAT_PAY_NOTIFY_URL=https://canary.yiluan.cn/api/v1/payments/wechat/callback

# 灰度门（默认全开，回滚时热切）
FEATURE_SHARE_F2_ENABLED=true
READONLY_SHARE_SESSIONS=false
```

### 3.2 deploy/env.canary.local（不入库，真密钥）

```bash
# 微信支付
WECHAT_PAY_APP_ID=wxXXXXXXXXXXXXXXXX
WECHAT_PAY_MCH_ID=XXXXXXXXXX
WECHAT_PAY_API_V3_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
WECHAT_PAY_CERT_SERIAL=XXXXXXXXXXXXXXXXXX

# 阿里云 SMS
ALIYUN_SMS_ACCESS_KEY_ID=LTAI5XXXXXXX
ALIYUN_SMS_ACCESS_KEY_SECRET=XXXXXXXXXX
ALIYUN_SMS_SIGN_NAME=医路安
ALIYUN_SMS_TEMPLATE_CODE=SMS_XXXXXXXXX

# 企业微信告警
WECHAT_WORK_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=XXX
```

---

## 4. 拉起 / 验证 / 撤栈

### 4.1 拉起

```bash
cd ~/repo/YiLuAn/deploy
# canary 用与 staging 同样 profile，区别只在 env file
docker compose \
  --env-file env.staging \
  --env-file env.canary \
  --env-file env.canary.local \
  --profile staging \
  up -d

# 等 healthy
./up.sh staging
```

### 4.2 真支付链路验证

```bash
# 1. 用团队测试账号下单
POST /api/v1/orders {service_type: errand, amount: 1}  # ¥1

# 2. 真 wxpay 调起
POST /api/v1/orders/{id}/pay
# 期望：返回 prepay_id + sign_params + mock_success=false

# 3. 真支付（微信 App 内付款）
# 用户用微信扫码 / 调起付款

# 4. 真回调
# wxpay 回调命中 https://canary.yiluan.cn/api/v1/payments/wechat/callback
# backend log 应有 "Pay callback processed: trade_no=4200xxx... success=True"

# 5. 状态验证
GET /api/v1/orders/{id}
# 期望：payment_state=paid，OrderStatus=created（等陪诊师 accept，符合 ADR-0041）
```

### 4.3 真短信链路验证

```bash
POST /api/v1/auth/send-otp {phone: "138XXXXXXXX"}  # 真手机
# 短信应到达
# 后端 metric: sms_send_total{provider=aliyun} 增 1
```

### 4.4 灰度门热切验证

```bash
# 真起栈下测试 feature flag 热切
echo "FEATURE_SHARE_F2_ENABLED=false" >> env.canary.local
docker compose --env-file env.staging --env-file env.canary --env-file env.canary.local restart backend

# 验证 503
curl -X POST -H "Authorization: Bearer <token>" -d '{"share_scope":"full"}' \
  https://canary.yiluan.cn/api/v1/orders/<id>/shares
# 期望：503 + SHARE_F2_DISABLED

# 回滚开关
sed -i '/^FEATURE_SHARE_F2_ENABLED/d' env.canary.local
docker compose --env-file env.staging --env-file env.canary --env-file env.canary.local restart backend
```

### 4.5 撤栈

```bash
docker compose --env-file env.staging --env-file env.canary --env-file env.canary.local down -v
```

---

## 5. 反向引用

- ADR-0028 灰度发布与回滚机制
- ADR-0001 微信支付
- ADR-0041 支付域/业务域状态机解耦（验证 payment_state=paid + OrderStatus 不流转）
- S2-OPS-001 灰度回滚阈值 Prometheus alert rules
- S2-OPS-010 staging Prometheus/AM/Grafana wire-up（PR #145）
- S2-OPS-011 本 task（灰度通道 + feature flags + runbook）
- S2-TEST-004 灰度前手动回归 checklist（本通道是其前置）
- `docs/ops/canary-rollback-runbook.md` 配套回滚步骤
