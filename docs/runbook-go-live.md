# 医路安（YiLuAn）Go-Live Runbook

> 目标：在 5 个生产 Blocker（B-01 ~ B-05）都解锁后，**30 分钟内完成生产上线**(灰度观察窗口除外)。
>
> 每个 Blocker 单独一节，结构统一：**前置 → 步骤 → 验证 → 回滚**。
>
> 总流程：确认所有前置 → 按 B-01 → B-02 → B-03 → B-04 → B-05 顺序执行 → §6 灰度上线 → §7 上线后 24h 监控。

> **2026-04-25 dry-run 修订:** 详见 `docs/ops/GOLIVE_DRYRUN_REPORT_2026-04-25.md`。本次修订修正了 ENV 变量名(P-01/P-02)、/readiness 字段(P-14)、阈值口径(P-15)、通道(P-12)、§18 smoke 缺失(P-11) 等共 15 处。
>
> **配套文档:**
> - `docs/RUNBOOK_ROLLBACK.md` — 回滚 SOP(场景 A/B/C)
> - `docs/ops/INCIDENT_PLAYBOOK.md` — 应急 SOP(DB / Redis / 支付 / SMS)
> - `docs/decisions/ADR-0028-canary-release-and-rollback.md` — 灰度策略
>
> **配套工具:**
> - `ops/scripts/golive_preflight.sh` — 预发布一键检查
> - `ops/scripts/deploy.sh --canary / --rollback` — 部署/回滚入口(当前 mock,真生产 TODO)
> - `ops/scripts/canary_drill.sh` — 灰度演练 mock
>
> **总耗时预算(估算):**
> - Preflight: 5-8 min
> - 5 个 Blocker 串行执行: 各 15-30 min
> - 灰度 5%→25%→50%→100% (各 30 min 观察): ~2 小时
> - 24h 上线后观察窗口

---

## 0. 通用前置（所有 Blocker 解锁前必须完成）

- [ ] **跑 `bash ops/scripts/golive_preflight.sh`,退出码 = 0**(任何 BLOCK 项都必须清除)
- [ ] `main` 分支当前 commit 已通过全套 CI（backend pytest / wechat jest / iOS CI / alembic-smoke）
- [ ] Staging 环境已用同一 commit 完整跑通（§18 smoke 10 项,见本文档末尾）
- [ ] 备份：PG 全量备份完成、WAL 归档到 OSS 确认可恢复（`docs/RUNBOOK_ROLLBACK.md` 场景 C 前置验证过）
- [ ] **估算迁移耗时:** `time alembic upgrade head` 在 staging 跑一次,填入 release-log;干跑本地空库实测 ~2.5s(30 个 revision),staging/prod 含数据估 < 60s
- [ ] Ops On-call + 产品负责人（PM）+ 一名前端 / 后端值守（**企业微信**值守群 + 电话畅通）
- [ ] 回滚包就绪：上一可用版本 tag + 对应 alembic revision 记录在案
- [ ] `ops/scripts/deploy.sh` 与 `ops/scripts/canary_drill.sh --happy-path` 本地给 ops 跑过一次
- [ ] **`/readiness` 实际字段名:** `checks.<dep>.status` (db / redis / alembic / payment / sms);不是 "wechatpay.ok=true" 之类伪字段

---

## 1. B-01 — 微信支付商户号 / APIv3 / 证书（Backend 主导）

### 前置
- [ ] 微信支付商户号审核通过（文龙处理）
- [ ] 拿到 mch_id / APIv3 密钥 / 商户私钥 + 证书序列号
- [ ] 拿到平台证书（用于回调签名验证）

### 步骤（≤10 步）—— 估算 20-30 min

> **2026-04-25 dry-run 修订:** ENV 变量名与 `backend/.env.example` + `backend/app/config.py` 对齐。原说明里的 `WECHATPAY_*` (无下划线)是错的,代码实际读的是 `WECHAT_PAY_*` 。

1. 将 `WECHAT_PAY_MCH_ID` / `WECHAT_PAY_APPID` / `WECHAT_PAY_V3_KEY` / `WECHAT_PAY_SERIAL_NO` / `WECHAT_PAY_PRIVATE_KEY_PATH`(指向容器内 PEM 文件路径) / `WECHAT_PAY_PLATFORM_CERT_PATH` 写入生产 KMS / secrets manager;证书文件另外挂载到容器(推荐 secret volume)。
   - **⚠️ 与 .env.example 反复核对** —— 预发布脚本会检查一致性。
   - **⚠️ config.py 中的字段名为 `wechat_pay_api_key_v3` 但 .env.example 现为 `WECHAT_PAY_V3_KEY`** —— 需后端后续对齐,过渡期在 secret 中同时设两名。
2. 部署到 backend 容器（滚动更新,`/readiness` 绿色后切流量）
3. 调一次沙箱下单 → 验证签名正确、回调可被平台送达（可先用 ngrok 临时转发回调 URL 到生产域名 的 `/api/v1/payment/wechat/callback`）
4. 确认回调签名验证通过（`/metrics` 中 `wechatpay_callback_signature_ok_total` 增加）
5. 关闭沙箱模式：`PAYMENT_PROVIDER=wechat` 且去掉任何 `*_SANDBOX=1` 开关,再部署一次

### 验证
- [ ] `curl https://api.yiluan.com/readiness | jq '.checks.payment.status'` 返回 `"ok"` 或 `"skipped"`(如是 mock)
- [ ] 真实 0.01 元订单支付成功（从下单→支付→回调→订单 status=paid 全链路）
- [ ] Prometheus `wechatpay_callback_signature_fail_total` = 0（15 分钟窗口）

### 回滚
- 设 `WECHATPAY_ENABLED=false` → 下单入口返回"支付暂不可用"；
- 必要时下线含新凭证的 deployment，回到上一 stable tag；
- 已成功支付订单**不动**，失败订单走人工退款流程（Ops runbook §R-01）。

---

## 2. B-02 — 阿里云 SMS 模板与签名（Backend 主导）

### 前置
- [ ] 阿里云 SMS 签名审核通过（"医路安"）
- [ ] 各模板备案：登录 OTP / 订单提醒 / 支付成功 / 评价邀请
- [ ] 拿到 AccessKey / AccessSecret（建议使用 RAM 子账号，权限仅限 SMS）

### 步骤（≤10 步）—— 估算 15-25 min

> **2026-04-25 dry-run 修订:** ENV 变量名以 `backend/.env.example` + `backend/app/config.py` 为准。原说明里的 `ALIYUN_SMS_AK_ID` / `ALIYUN_SMS_AK_SECRET` / `ALIYUN_SMS_SIGNATURE` 均错误。
>
> **⚠️ 代码当前只支持单 `ALIYUN_SMS_TEMPLATE_CODE`**(不是 4 个 OTP/订单/支付/评价模板)。多模板需 backend 后续扩展,本次上线只启用 OTP 一个。

1. Secrets：`ALIYUN_SMS_ACCESS_KEY_ID` / `ALIYUN_SMS_ACCESS_KEY_SECRET` / `ALIYUN_SMS_SIGN_NAME` 写入 KMS
2. 将 OTP 模板 ID 写入配置：`ALIYUN_SMS_TEMPLATE_CODE`
3. 切换 provider：`SMS_PROVIDER=aliyun`（从 `mock` 改）
4. 部署一次,`/readiness` 检查 `checks.sms.status == "ok"`
5. 真机拨测：用非团队号码发一次 OTP，确认收到 + 可登录

### 验证
- [ ] Prometheus `sms_send_ok_total` 开始增长，`sms_send_fail_total` ≈ 0
- [ ] 登录页 OTP 端到端跑通（真实手机号）
- [ ] `curl https://api.yiluan.com/readiness | jq '.checks.sms'` 返回 status=ok

### 回滚
- `SMS_PROVIDER=mock`，立即恢复登录可用性（开发约定 OTP = `000000`）
- 需要对当时注册失败用户做一次运营侧补偿

---

## 3. B-03 — ACR + 监控对接账号（Ops 主导）

### 前置
- [ ] 阿里云 ACR 命名空间开通
- [ ] Prometheus + Grafana + Alertmanager 实例就绪（建议托管版）
- [ ] Alertmanager webhook / 电话通道配置（钉钉群 + 电话机器人）

### 步骤（≤10 步）
1. CI 构建的镜像 push 到 ACR：`registry.cn-beijing.aliyuncs.com/yiluan/backend:<tag>`
2. 部署时拉取新镜像（改 k8s manifest / docker-compose）
3. 把 `deploy/prometheus/scrape.yml.example` 内容合并到 Prometheus 配置，reload
4. 确认 scrape target `yiluan-backend` up=1
5. 部署 `deploy/prometheus/alerts.yml` 5 条规则，Alertmanager reload
6. 配置通道：P0 告警 → **企业微信群机器人** + **电话机器人**；P1 → 企业微信群机器人(D-040 决议，不使用钉钉)
7. 测试：手动把 backend stop 1 分钟 → 确认 `BackendDown` / `ReadinessProbeFailure` 告警触发,企业微信群收到 markdown 消息

### 验证
- [ ] Grafana dashboard "YiLuAn / Overview"(`ops/grafana/yiluan-overview.json`)绿
- [ ] Alertmanager → 手机真实收到 **企业微信** + 电话告警
- [ ] `/metrics` nginx 401/403 来自 0.0.0.0/0，200 仅内网
- [ ] `curl http://<host>:5001/healthz` 返回 `dry_run=false`(表明 webhook URL 已注入)

### 回滚
- 降级到上一镜像 tag；
- 告警静默 2h（防暴雷）：`amtool silence add alertname=~".*"`

---

## 4. B-04 — 域名 / SSL / ICP 备案（PM 主导）

### 前置
- [ ] ICP 备案通过（api.yiluan.com / m.yiluan.com / admin.yiluan.com 全部）
- [ ] SSL 证书签发（建议用 ACM / Let's Encrypt）
- [ ] DNS 解析权限在手（CNAME/A 记录）

### 步骤（≤10 步）
1. DNS：api / m / admin 三个子域 A 或 CNAME 指向 LB
2. 证书部署到 nginx（`/etc/nginx/certs/`），reload nginx
3. 强制跳转：HTTP → HTTPS，HSTS max-age=63072000
4. 回源健康检查：`curl -I https://api.yiluan.com/health`
5. 微信支付 / 阿里云 SMS / 小程序域名白名单**都换成正式域名**
6. 小程序后台"服务器域名"配置更新，`requestDomain` 加入 `https://api.yiluan.com`

### 验证
- [ ] SSL Labs 评级 ≥ A
- [ ] `curl -I https://api.yiluan.com/health` 200
- [ ] 小程序真机预览不报 "未配置域名" 错误

### 回滚
- DNS 切回旧记录（TTL 保持 60s，快速切换）
- 保持旧域名 30 天双轨期

---

## 5. B-05 — Apple 开发者账号 / iOS 上架（PM + Frontend）

### 前置
- [ ] Apple Developer Program 年费缴纳完成
- [ ] App Store Connect 创建 app 条目（bundle ID = `com.yiluan.app`）
- [ ] 截图 / 描述 / 隐私政策 URL 准备好
- [ ] 内测分发：TestFlight 已设置

### 步骤（≤10 步）
1. iOS CI（`.github/workflows/ios-ci.yml`）跑绿 ✅（A-01 已做完）
2. 本地用真机 archive 一次（`Product → Archive`，Release config）
3. 上传到 App Store Connect（Transporter）
4. TestFlight：邀请内测用户（先 5 人），24h 无 crash
5. 提交审核：填写审查联系方式、测试账号（用 13700000099 / OTP 通道测试）
6. 响应审核意见（平均 48h 内有结果）
7. 通过后"手动发布"

### 验证
- [ ] TestFlight build 上架，5 人测试 24h 无 crash
- [ ] 审核状态 = "等待审核" → "审核中" → "准备发布"
- [ ] App Store 正式上架后，真机搜索可下载

### 回滚
- 通过后有问题：紧急 hotfix 版本（跳过审核可能需要 Expedited Review）
- 未通过：按 App Review 意见改，重新提交

---

## 6. 灰度上线（全部 Blocker 解锁后）

> 详见 ADR-0028。本节只列报表。

### 入口
```bash
bash ops/scripts/deploy.sh --canary --tag <release-tag>
# 干跑检查请先跑:
bash ops/scripts/canary_drill.sh --happy-path
```

### 策略
- **5% 流量**：仅团队 + 少量 beta 用户(白名单手机号),30 min 观察
- **25% 流量**：30 min 观察
- **50% 流量**：30 min 观察
- **100%**：无异常后全量、进入 24h 观察窗口

### 必须监控的指标（Prometheus + Grafana "YiLuAn / Overview"）
| 指标 | 正常 | 自动回滚阈值 | 告警名 |
|---|---|---|---|
| 5xx 率 | < 0.3% | **> 1% 持续 2 分钟** | (ADR-0028 watcher) |
| /readiness | green | **连续失败 > 2 分钟** | ReadinessProbeFailure |
| 支付回调处理耗时 P95 | < 500ms | > 2s | PaymentCallbackLatency(待加) |
| WebSocket 断连率 | < 5% | > 30% | WSDropHigh(待加) |
| DB 连接池使用率 | < 60% | > 80% | DBConnExhausted(待加) |
| SMS 失败率 | < 0.5% | > 5% | SMSFailHigh(待加) |
| iOS / 小程序 crash 率 | < 0.1% | > 1% | (App 侧上报) |

### 人工检查阈值(stage 间手动 GO/NO-GO)
该阈值与自动回滚不重叠,用于业务状态判断:
- 订单创建率下跌 > 50% (对比 1h 前) → 人工介入
- 客服反馈集中问题 ≥ 10 起 / 30 分钟 → 人工介入

### 熔断动作(达到任一阈值 → §6 决策树)
1. **首选 `bash ops/scripts/deploy.sh --rollback`**(场景 A 流量层,§30s 完成切流)
2. 调查根因,修复后重走灰度
3. 若无法短期修复：`bash ops/scripts/deploy.sh --rollback --code <prev-tag>`(场景 B 代码层)
4. 若伴随不可逆 schema 变更: 走 `docs/RUNBOOK_ROLLBACK.md` 场景 C

---

## 7. 上线后 24h 关键监控点

- [ ] 每 2h 看一次 Grafana "YiLuAn / Overview"
- [ ] 每 6h 跑一次 §18 的 10 项 smoke
- [ ] On-call 手机常在手边，企业微信 / 电话机器人通道保持
- [ ] 24h 后做一次上线回顾（成功/失败/教训），归档到 `docs/launches/<date>.md`

---

## 18. §18 Smoke 10 项(上线验收 / 24h 中抽检用)

所有项记为 [ ] 供勾选;在生产域名上跑,遇一项不过即进入§6 熔断动作。

1. [ ] `curl https://api.yiluan.com/health` 返回 200
2. [ ] `curl https://api.yiluan.com/readiness` 返回 200,5 项 checks 全 ok/skipped
3. [ ] 手机号 SMS OTP 登录(全链路 ≤ 30s)
4. [ ] Apple Sign-In 登录(iOS 真机)
5. [ ] 浏览医院列表 + 错伴列表接口 200
6. [ ] 下一笔 0.01 元订单 → 跳转微信支付 → 回调 → 订单 status=paid
7. [ ] 发一条聊天消息 → WS 实时送达
8. [ ] Admin 后台登录 + 列表获取​
9. [ ] `/metrics` 返回在内网可访问,外网 401
10. [ ] Alertmanager `curl /api/v2/status` reachable,中间件状态 ok

---

Last updated: 2026-04-23 (PM + Ops 联合起草)


---

## 8. 配置告警 (A-2604-07)

> **目标：** 把 Prometheus 已采集的 `/metrics` 指标接到 Alertmanager → 企业微信群机器人，oncall 群第一时间感知 5xx / 高延迟 / 任务积压。
>
> **决策依据：** 见 `docs/DECISION_LOG.md` D-040（不引入 Slack/钉钉，复用企业微信）。

### 前置

- [ ] Prometheus 已采集 backend `/metrics`（D-037 已完成）。
- [ ] PM 已在企业微信 oncall 群创建群机器人，拿到 webhook URL（**待 PM 提供**）。
- [ ] PM 已确认 critical 级别 oncall 邮箱组 + 邮件 SMTP 凭证（**待 PM 提供**）。

### 步骤

1. 把以下环境变量写入部署侧 secrets（**不要提交到仓库**）：
   - `WECHAT_WORK_WEBHOOK_URL` — 企业微信群机器人 webhook 完整 URL（`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...`）
   - `ONCALL_EMAIL` — critical 邮件抄送地址（逗号分隔可选）
   - `SMTP_SMARTHOST` / `SMTP_FROM` / `SMTP_USERNAME` / `SMTP_PASSWORD` — 邮件 relay 凭证
   - `ALERTMANAGER_EXTERNAL_URL` — Alertmanager 公网/内网可达 URL（用于消息中"查看告警"链接）
2. 启动 Alertmanager + wechat-work webhook 适配器(**必须从仓库根目录**运行,本次 dry-run 修正了 compose 卷路径):
   ```bash
   cd <repo-root>
   docker compose -f docker-compose.alertmanager.yml up -d
   ```
3. Prometheus 配置中加上 `alerting.alertmanagers: [{ static_configs: [{ targets: ["alertmanager:9093"] }] }]` 并 reload。
4. 烟测：手工 POST 一个测试告警 payload 到适配器 dry-run 模式，确认企业微信群收到。
   ```bash
   curl -X POST http://<host>:5001/alert -H "Content-Type: application/json" \
     -d '{"status":"firing","groupLabels":{"alertname":"SmokeTest"},"commonLabels":{"alertname":"SmokeTest","severity":"warning","service":"yiluan-api"},"alerts":[{"startsAt":"2026-04-24T15:00:00Z","endsAt":"0001-01-01T00:00:00Z","annotations":{"summary":"runbook smoke"},"labels":{}}],"externalURL":"http://localhost:9093"}'
   ```

### 验证

- [ ] `GET http://<host>:5001/healthz` 返回 `{"ok": true, "dry_run": false, ...}`（dry_run 必须为 false，否则 webhook URL 没注入）。
- [ ] 手工触发烟测告警后，oncall 群在 30s 内收到 markdown 消息（标题、级别、起止时间、查看链接齐全）。
- [ ] 在 Prometheus 中临时把 `up{job="yiluan-api"}` 的告警阈值调到必触发，确认企业微信能收到 `firing`，恢复后能收到 `resolved`。
- [ ] critical severity 告警同时有邮件抵达 `ONCALL_EMAIL`。

### 回滚

- 撤回 webhook URL（清空 `WECHAT_WORK_WEBHOOK_URL`）→ 适配器自动进入 dry-run 模式（仅日志，不再发群消息），不影响主业务。
- 或直接 `docker compose -f docker-compose.alertmanager.yml down`：Alertmanager 不可用不会影响 backend，只是失去告警通道。

### 速率限制

- 适配器内置：同 alertname 60s 内最多 3 条（`WECHAT_RATE_LIMIT_MAX` / `WECHAT_RATE_LIMIT_WINDOW_SEC` 可调）。
- Alertmanager 路由层：分组 30s wait + 5min repeat，配合应用级限流防止告警风暴洗版群。
