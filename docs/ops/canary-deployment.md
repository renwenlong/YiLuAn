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

## 4.6 E+B 务实兜底路径（推荐 D+0 起跳方案）

> 背景：S2-TEST-004 灰度回归 acceptance §1 原要求 "真 wxpay 下单→支付→回调" 硬路径。但现实：真 wxpay 商户号 + ICP 备案 + 公网域名 是周级周期，会极大延后灰度上路。魈 + 刻晴 + PM 2026-06-04 同推 **E+B 务实兜底**：分两步跳过这个卡。

### 路径拆解

| 阶段 | E 阶段（立即起跳） | B 阶段（后补真签名） |
|---|---|---|
| 支付 provider | mock-pay-stub 内部 callback 链路 | ngrok 隔离补跑 §1.1 真 wxpay 签名一条 case |
| 覆盖 acceptance | §1.2~§1.6（CB 抖动 / 退款平账 / 空 txn_id 拒 / 同 txn_id 幂等 / WS / callback 链路）+ §4 AI 成本 + §5 回滚演练 + §6 四方签字 | 仅 §1.1 真 wxpay 下单→支付→回调验证签名/证书链路 |
| 外部资源 | **零**（不需帝君提供任何账号） | ngrok authtoken 一项（帝君注册 ngrok.com 5min） |
| 门锁占比 | §§1-6 中占 ~50%+ 路径（业务逻辑全走通，仅缺真签名验证） | 补上后 §1 全部过，灰度门可推全 |
| 启动设置 | `PAYMENT_PROVIDER=mock` + `MOCK_PAY_BASE_URL=http://mock-pay-stub:8001` | E 保留，并行起 ngrok 代理 + 另一份 `env.canary.b.local` 启 WeChat provider |

### E 阶段启步（0 外部资源）

```bash
cd ~/repo/YiLuAn/deploy
# 已在 staging 起栈则跳过 build。mock-pay-stub 已 OPS-011 落盘
export PAYMENT_PROVIDER=mock
export MOCK_PAY_BASE_URL=http://mock-pay-stub:8001
./up.sh staging --profile staging  # mock provider 本身已 healthy
# 刻晴 §1.2~1.6 + §4 + §5 + §6 起跑。§1.1 注 "E 阶段跳过，待 B 阶段补"
```

### B 阶段补跑（需 ngrok authtoken）

```bash
# 1. 安装 ngrok（PM 主 tree）
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc > /dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install -y ngrok
ngrok config add-authtoken <帝君提供的 authtoken>

# 2. 起 ngrok 隧道指向 staging nginx:18080
ngrok http 18080 > /tmp/ngrok.log &
sleep 3
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import json,sys;print(json.load(sys.stdin)['tunnels'][0]['public_url'])")
echo "ngrok URL: $NGROK_URL"

# 3. 配 wxpay 沙箱走 ngrok callback
cat > deploy/env.canary.b.local <<EOF2
PAYMENT_PROVIDER=wechat
WECHAT_PAY_MCH_ID=<沙箱 mch_id>
WECHAT_PAY_API_V3_KEY=<沙箱 v3 key>
WECHAT_PAY_NOTIFY_URL=$NGROK_URL/api/v1/payments/wechat/callback
EOF2
./up.sh staging --env-file deploy/env.canary.b.local

# 4. 刻晴跑 §1.1 真 wxpay 下单→支付→回调，验签名/证书链路
# 5. §1.1 PASS 后、灰度门全颁 §1 清单
```

### 帝君最小输入 checklist

**E 阶段（0 输入）**：PM 可自助起，不卡。

**B 阶段（1 项输入）**：帝君仅需提供 ngrok authtoken（免费版即可，5min 注册），其余微信支付沙箱号 PM 代申请。如帝君有现成公网域名可替代 ngrok。

### 与 A 路径关系

- E+B 走通后灰度路径已证明。A（真接入）只是生产环境换真商户号 + 公网域名，本质是配置替换不是逻辑重走。
- A 路径依然按本文档 §2.2 说明个别项 checklist 完成，但开启后可以与灰度上线同期。

## 5. 反向引用

- ADR-0028 灰度发布与回滚机制
- ADR-0001 微信支付
- ADR-0041 支付域/业务域状态机解耦（验证 payment_state=paid + OrderStatus 不流转）
- S2-OPS-001 灰度回滚阈值 Prometheus alert rules
- S2-OPS-010 staging Prometheus/AM/Grafana wire-up（PR #145）
- S2-OPS-011 本 task（灰度通道 + feature flags + runbook）
- S2-TEST-004 灰度前手动回归 checklist（本通道是其前置）
- `docs/ops/canary-rollback-runbook.md` 配套回滚步骤
