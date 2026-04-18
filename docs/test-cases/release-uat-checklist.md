# 上线前手工验收清单 (Release UAT Checklist)

> 覆盖：P1-6 任务 — 真实支付 / 真实 SMS / 生产部署 / 回滚 / 审核 五大场景的**手工 UAT**（自动化已覆盖部分仅作引用，避免重复）。
> 与现有文档关系：
> - 自动化用例：`backend/tests/test_payment_callback_idempotency.py`、`backend/tests/test_sms_providers.py`（CI 已跑，本清单不重复）
> - 部署 smoke：`docs/deployment.md` §18（10 项部署后冒烟，本清单第 §C / §最终核对中**引用** smoke 1~10 项编号，不再重写）
> - 微信提审：`docs/wechat-submission-checklist.md`（本清单 §E 全引用，不重复列举）
> - 拒单/过期 UAT 模板：`docs/test-cases/reject-expiry.md`（同样格式：前置/步骤/预期/验证）
>
> 维护人：QA；最后更新：2026-04-18；适用版本：v1.0.0 首发上线起。
>
> **每条用例字段**：前置条件 / 操作步骤 / 预期结果 / 通过判断 / 责任人 / 是否阻断（🟥 阻断上线 / 🟧 需修复但可带病上线 / 🟨 仅观察）。

---

## 0. 执行约定

- 执行环境：**Staging 走全量 + Production 走灰度子集**；本清单标注 `[STAGING]` `[PROD]` `[BOTH]`。
- 真实支付/真实 SMS UAT 必须等 `WECHAT_PAY_MCH_ID`、`ALIYUN_SMS_*` 凭证就位后执行（参见 `docs/TODO_CREDENTIALS.md`）。
- 失败处理：任一 🟥 用例 FAIL → 立即按 `docs/deployment.md` §15 回滚；并在 `docs/qa/YYYY-MM-DD-uat-run.md` 记录现场。
- 责任人缩写：**QA**=测试 / **BE**=后端 / **FE**=前端 / **OPS**=运维 / **PM**=产品 / **FIN**=财务对账。

---

## A. 真实支付 UAT [BOTH]

> 自动化已覆盖：回调签名校验、幂等去重、回调日志、Provider 工厂切换、订单关闭后回调不翻状态（见 `test_payment_callback_idempotency.py`）。
> 本节验证**真实商户号 + 真实微信支付通道**的端到端表现，**不能被自动化替代**。

### A-1 小额下单 → 支付成功 e2e 🟥

**前置条件**
- 商户号 `WECHAT_PAY_MCH_ID` / APIv3 密钥 / 证书序列号 / 私钥 / 回调 URL（HTTPS 公网）已通过 Key Vault 注入；`/health` 返回的 `payment_provider=wechat`。
- 患者账号 `13800000001` 已登录小程序；钱包余额 ≥ 0.01 元的真实微信账户绑定。

**操作步骤**
1. 患者首页 → 选择测试医院 → 选定陪诊师 → 创建订单，金额设为 **0.01 元**。
2. 进入支付页 → 点「立即支付」→ 微信键盘输入支付密码（或指纹）。
3. 等待支付结果页跳转（≤ 10s）。
4. 后台查询：`SELECT status, payment_status FROM orders WHERE id=<订单ID>;` 与 `SELECT * FROM payments WHERE order_id=<订单ID>;`。

**预期结果**
- 小程序：支付结果页显示「支付成功」，3s 内自动回订单详情，状态副标题=「等待陪诊师接单」。
- DB：`orders.payment_status='paid'`，`orders.status='created'`（或派单后 `accepted`）；`payments` 新增一行 `status='success'`，`transaction_id`（微信流水号）非空。
- 微信支付商户后台 → 交易管理：能查到这笔 0.01 元订单，状态「支付成功」。
- 后端日志：`payment.notify.received` + `payment.notify.success` 各一条；无 ERROR；商户号、回调签名、out_trade_no 已脱敏（仅尾 4 位）。

**通过判断**：四处状态全部一致（小程序 / DB / 微信后台 / 日志）。

**责任人**：QA + BE 联合；FIN 对账。

---

### A-2 支付回调延迟到达 🟥

**前置条件**：A-1 已配置完成；准备 1 笔新订单 O2，金额 0.01。

**操作步骤**
1. 临时在 OPS 侧将 `payments/notify` 路由暂停 30s（如：在 Front Door 加规则返回 503）。
2. 触发支付 → 微信因 503 触发回调重试机制（4s/15s/1m/5m... 共 8 次，详见微信支付文档）。
3. 30s 后恢复路由 → 观察重试到达。
4. 同步比对 `payment_callback_log` 表新增条数。

**预期结果**
- 至少 1 次重试在 1 分钟内打到 `notify` 接口并成功。
- O2 状态最终 `paid`；`payments` 仅 1 行 `success`，**无重复**。
- `payment_callback_log` 可能有 ≥1 行（含被拒的 503 期间不算，恢复后那次为 success）。

**通过判断**：订单状态最终一致 + 无重复扣款记录 + 日志显示幂等命中。

**责任人**：QA + OPS。

---

### A-3 退款 — 全额退款 🟥

**前置条件**：A-1 已成功支付的订单 O1。

**操作步骤**
1. 后台/管理员 App 触发 O1 全额退款（金额 0.01）。
2. 等待 ≤ 30s（微信退款异步）。
3. 真实微信账户里查看「钱包 → 账单」是否有退款入账。
4. DB：`SELECT * FROM refunds WHERE order_id=<O1>;`。

**预期结果**
- O1：`payment_status='refunded'`，`status='refunded'` 或对应终态。
- `refunds` 表有 1 行 `status='success'`，金额=0.01，`refund_id`（微信退款单号）非空。
- 微信账户 24h 内（实际通常秒级）收到退款。
- 后端日志：`refund.request` + `refund.notify.success` 各一条。

**通过判断**：DB + 微信账户 + 微信商户后台「退款管理」三方一致。

**责任人**：QA + BE + FIN。

---
### A-4 退款 — 部分退款 🟧

**前置条件**：一笔金额 ≥ 1.00 元的真实订单 O3（已支付）。

**操作步骤**
1. 触发部分退款 0.50 元 → 等待回调。
2. 再触发第二次部分退款 0.30 元（剩余 0.20）→ 等待回调。
3. 触发第三次部分退款 0.30 元（**应失败，超出剩余**）。

**预期结果**
- 前两次：`refunds` 各新增 1 行 `success`；O3 状态保持 `paid`（部分退款不改主单状态，仅累计 `refunded_amount`）；`refunded_amount=0.80`。
- 第三次：返回 4xx「退款金额超出可退余额」；不写 `refunds` 行，不调用微信接口（前置校验）。
- 微信商户后台显示 2 条退款明细，剩余可退 0.20 元。

**通过判断**：累计金额正确 + 超额拒绝 + 无脏数据。

**责任人**：QA + BE。

---

### A-5 退款失败回调 🟧

**前置条件**：测试环境下可触发微信退款失败（如：通过 mock provider 临时切回，或商户余额不足场景）。

**操作步骤**
1. 触发一笔退款 → 微信返回退款失败回调（异步）。
2. 观察 `refunds` 表与订单状态。

**预期结果**
- `refunds` 表新增 1 行 `status='failed'`，`fail_reason` 字段记录微信错误码与描述。
- O 订单状态**不**回退到已退款；仍为 `paid`。
- 后端日志 ERROR 级别：`refund.notify.failed`，并触发 P1 告警通道（企业微信）。
- 管理后台「待处理退款」列表显示该笔。

**通过判断**：失败可见 + 不污染主单 + 告警送达。

**责任人**：QA + BE + OPS。

---

### A-6 异常路径 — 用户中途取消支付 🟨

**前置条件**：新订单 O4 进入支付页。

**操作步骤**
1. 唤起微信收银台 → 用户**取消**（返回键）。
2. 等待 30s。
3. 触发主动查询：管理后台调用 `POST /payments/{O4}/sync` 或等订单过期任务扫描。

**预期结果**
- O4：`payment_status='unpaid'`，`status='created'`；可继续支付或被过期任务取消。
- 无 `payments` success 行；无回调日志。
- 小程序：返回订单详情页能看到「待支付」按钮，可重试。

**通过判断**：状态停留在 unpaid + 可重试 + 无脏数据。

**责任人**：QA + FE。

---

### A-7 异常路径 — 支付超时（订单过期前未支付） 🟧

**前置条件**：新订单 O5，`expires_at = now + 2min`（开发环境配置）。

**操作步骤**
1. 创建订单后**不支付**，等待 ≥ 3 分钟。
2. 等订单过期任务扫描（最长 60s tick）。
3. 用户尝试再次进入支付页。

**预期结果**
- O5：`status='expired'`，`payment_status='unpaid'`。
- 小程序提示「订单已超时取消」，禁止再支付。
- 无微信侧调用，无 `payments` 行。
- 行为参考：`docs/test-cases/reject-expiry.md` §B-1。

**通过判断**：到点过期 + UI 阻断 + 无残留预下单。

**责任人**：QA。

---

### A-8 异常路径 — 跨日订单 / 时区边界 🟧

**前置条件**：在 UTC+8 时间 23:55 创建订单 O6，`expires_at = now + 30min`（跨入次日）。

**操作步骤**
1. 23:58 完成支付。
2. 次日 00:05 查询订单详情、支付详情、对账报表。

**预期结果**
- O6 跨日成功，`paid_at` 与 `created_at` 跨日；前端时间显示均为本地时区，无 1 天差异。
- 当日对账报表（`yyyymmdd`）依据 `paid_at` 入账，归在**支付当日**而非创建当日。
- 日志时间戳 ISO 8601 + 时区标识无歧义。

**通过判断**：报表 + UI + 日志时区一致。

**责任人**：QA + FIN。

---

### A-9 异常路径 — 重复回调（人工重放） 🟥

**前置条件**：已成功支付的订单 O1 + 抓包到的回调原文（带签名）。

**操作步骤**
1. 用 `curl` 重放 5 次相同回调到 `/api/v1/payments/notify`。
2. 比对 `payments` 与 `payment_callback_log` 行数。

**预期结果**
- 每次响应 `SUCCESS`（幂等）。
- `payments` 仍 1 行；`payment_callback_log` 行数 +5 但都标记 `idempotent_hit=true`。
- 订单状态不变，无副作用。
- 与自动化用例 `TestIdempotency::test_duplicate_callback_no_double_process` 行为一致。

**通过判断**：5 次全部幂等 + 状态不动。

**责任人**：QA。

---
## B. 真实 SMS UAT [BOTH]

> 自动化已覆盖：mask、provider 工厂、AliyunSMSProvider 占位错误、限流 60s/1h 窗口、PII 脱敏（见 `test_sms_providers.py`）。
> 本节验证**真实阿里云通道 + 真实手机号**到达性，自动化无法替代。

### B-1 OTP 真机收发 — 三网覆盖 🟥

**前置条件**
- `SMS_PROVIDER=aliyun` 已生效；签名「医路安」+ 验证码模板已审核通过。
- 准备三张真实手机卡：联通、移动、电信各 1 张；记录号码末四位。
- `/health` 显示 `sms_provider=aliyun`。

**操作步骤**
1. 三个号码各调用 `POST /api/v1/auth/sms/send` 一次。
2. 60s 内确认是否收到短信。
3. 用收到的验证码调用 `POST /api/v1/auth/verify-otp`。
4. 检查阿里云 SMS 后台「发送记录」匹配 3 条 `DELIVERED`。

**预期结果**
- 三张卡全部 60s 内收到，签名「医路安」+ 6 位数字验证码 + 模板正确。
- 验证 OTP 接口返回 JWT。
- 后端日志含 3 条 `sms.send.success`，手机号已 `138****0001` 形式脱敏。
- 阿里云后台 3 条 `DELIVERED`；无 `REJECTED`。

**通过判断**：3/3 到达 + 验证通过 + 后台与日志一致。

**责任人**：QA + OPS。

---

### B-2 限流 — 同号 60s 内第 2 次 🟥

**前置条件**：B-1 已成功发送的某号码 N1。

**操作步骤**
1. N1 触发第 1 次 send，等待返回 200。
2. 立即（< 60s）触发第 2 次 send。

**预期结果**
- 第 2 次返回 429「请求过于频繁，请 60 秒后重试」。
- 阿里云后台无第 2 条记录（被服务端拦截，未真实下发）。
- 日志：`sms.rate_limit.hit window=60s phone=138****0001`。

**通过判断**：429 + 阿里云无下发 + 节省成本。

**责任人**：QA。

---

### B-3 限流 — 1h 内第 6 次 🟥

**前置条件**：N1 在 1 小时窗口内已成功发送 5 次（间隔均 ≥ 60s）。

**操作步骤**
1. 1 小时窗口内触发第 6 次 send。

**预期结果**
- 第 6 次返回 429「单号每小时上限 5 次」。
- 阿里云后台计数仍 5 条。
- 日志：`sms.rate_limit.hit window=1h count=5`。

**通过判断**：1h 窗口准确 + 拦截。

**责任人**：QA。

---

### B-4 失败链路 — 停机 / 空号 / 关机 / 海外 🟧

**前置条件**：准备 4 个号码：
- N2 = 已停机（运营商确认）
- N3 = 空号（10 位 + 1 位随机）
- N4 = 当前关机的真实号码
- N5 = 海外号码 `+1xxxxxxxxxx`

**操作步骤**
1. 依次对 4 个号码触发 send。
2. 等待 5 分钟（异步回执）后检查阿里云回执 + DB `sms_send_log`。

**预期结果**
- N2/N3：阿里云回执 `MOBILE_NUMBER_ILLEGAL` 或 `OUT_OF_SERVICE`；`sms_send_log.status='failed'`，`fail_reason` 持久化。
- N4：可能延迟到达（开机后），或最终回执 `DELIVERY_TIMEOUT`；视为 acceptable。
- N5：服务端**前置校验拒绝**（仅支持 +86 11 位）→ 400「不支持的国家/地区号」，**不调阿里云**，节省成本。
- 任一失败均**不**影响其他号码，无连锁告警。

**通过判断**：失败可见、有 fail_reason、海外前置拦截、无误报。

**责任人**：QA + BE。

---

### B-5 速率限制告警链路 🟥

**前置条件**：模拟流量。

**操作步骤**
1. 用脚本对 10 个真实号码各发 1 次（合法），间隔 1s。
2. 同时对 1 个号码 60s 内连发 20 次（触发限流）。
3. 持续 5 分钟。
4. 检查 Application Insights / 企业微信告警通道。

**预期结果**
- 5 分钟窗口内 SMS 失败率 > 20% 或限流命中数 > 阈值 → 触发告警 14.3 §3「SMS 发送异常」。
- 企业微信收到告警卡片，含失败数、占比、TopN 触发号码（脱敏）。
- 无误报（合法的 10 条 success 不触发）。

**通过判断**：告警送达 + 内容准确 + 无狼来了。

**责任人**：QA + OPS。

---
## C. 生产部署 UAT [STAGING + PROD]

> 自动化已覆盖：Dockerfile 构建、单元测试、CI 部署管线本身（GitHub Actions）。
> 本节验证**真实生产环境**的部署链路、迁移、探针、流量切换。引用 `deployment.md` §18 smoke 1~10 不重复。

### C-1 ACR push → Container App pull 全链路 🟥

**前置条件**：本地 commit hash `S1` 已合入 main；GitHub Actions secrets 完整。

**操作步骤**
1. push 到 main 分支 → 观察 GitHub Actions：test → build-push → migrate-staging → deploy-staging。
2. 检查 ACR 是否新增 tag `YYYYMMDD-S1[:8]`。
3. 检查 Staging Container App 当前 revision 镜像 = 上一步 tag。
4. `curl https://api-staging.yiluan.com/health` 验证 `version` 字段=新版本。

**预期结果**
- 每一步绿；ACR + Container App 镜像 tag 一致；`version` 正确；总耗时 ≤ 15 分钟。

**通过判断**：流水线绿 + 镜像 tag 对得上 + 服务回新版本。

**责任人**：OPS + QA。

---

### C-2 数据库迁移 — dry-run 演练 🟥

**前置条件**：Staging DB 与 Prod schema 一致；本地有新增 alembic revision `R1`。

**操作步骤**
1. Staging：`DATABASE_URL=$STAGING_DATABASE_URL alembic upgrade head --sql > /tmp/r1.sql`（仅生成 SQL 不执行）。
2. 人工 review `/tmp/r1.sql`：是否有 `ALTER COLUMN ... TYPE`、`DROP COLUMN`、长事务、缺索引？
3. Staging 真实执行：`alembic upgrade head`。
4. `alembic current` 验证 revision = R1。
5. 跑后端 smoke：`/health` + `/api/v1/readiness` 全绿。

**预期结果**
- dry-run SQL 无破坏性语句，或破坏性语句已拆为两阶段（参见 `deployment.md` §17.3）。
- 真实 upgrade 成功；耗时 ≤ 60s（小迁移）；服务无中断。

**通过判断**：dry-run 评审通过 + 真实执行成功 + 服务可用。

**责任人**：BE + OPS。

---

### C-3 数据库迁移 — 回滚演练 🟥

**前置条件**：C-2 已执行 `R1`。

**操作步骤**
1. 在 Staging 创建一个手动备份：`az postgres flexible-server backup create ... --backup-name pre-r1-rollback-test`。
2. `alembic downgrade -1` 回到 `R0`。
3. `alembic current` 验证 = R0。
4. 重启 Container App，观察 readiness。
5. 业务侧抽样 5 条核心读 API 仍可用。
6. 再次 `alembic upgrade head` 回到 R1。

**预期结果**
- downgrade 成功；服务可用；数据无丢失（如有 `data migration` 字段，应已在评审中识别为不可逆）。
- 切换镜像后，readiness 全绿。
- 全程 ≤ 10 分钟。

**通过判断**：可双向切换 + 服务持续可用 + 备份点已留。

**责任人**：BE + OPS + QA。

---

### C-4 readiness 探针 — DB down 🟥

**前置条件**：Staging 环境（生产严禁此操作）。

**操作步骤**
1. 临时把 Staging Container App 的 `DATABASE_URL` 改成错误连接串（如端口 +1）。
2. 等待 60s。
3. `curl /api/v1/readiness`。
4. 观察 Container App revision 状态。

**预期结果**
- `/readiness` 返回 503，body 含 `db.ok=false`，`error="connection refused"`（脱敏）。
- `/health`（liveness）仍返回 200（不依赖 DB）。
- Container Apps 触发探针失败，最终重启 pod 或标记 unhealthy；流量被剔除。
- 告警 14.3 §1「Readiness 失败」企业微信送达。

**通过判断**：503 + db.ok=false + 流量剔除 + 告警送达。

**责任人**：OPS + QA。

---

### C-5 readiness 探针 — Redis down 🟥

**操作步骤**：同 C-4，但故障源为错误的 `REDIS_URL`。

**预期结果**：`/readiness` 503，`redis.ok=false`；行为与 C-4 一致；告警送达。

**通过判断**：同 C-4。

**责任人**：OPS + QA。

---

### C-6 readiness 探针 — 迁移落后 🟧

**前置条件**：本地 `alembic heads` 比 DB 当前 revision 超前 1 版（模拟镜像跑在了未迁移的 DB 上）。

**操作步骤**
1. 部署一个含新 model 的镜像，但**故意跳过** migrate job。
2. 启动后访问 `/readiness`。

**预期结果**
- `/readiness` 返回 503，body 含 `migration.ok=false`，`expected=R1, actual=R0`。
- 服务拒绝接流量；ORM 不会因 schema 不匹配崩溃在请求中。
- 告警送达。

**通过判断**：探针提前发现 schema 不匹配 + 不带病服务。

**责任人**：BE + OPS。

---

### C-7 蓝绿/滚动切换 — 会话保持 🟧

**前置条件**：multiple revision 模式开启；两个 revision `v1` `v2` 共存。

**操作步骤**
1. 流量分配 v1=50 / v2=50。
2. 用脚本：1 个用户登录拿 JWT → 连续访问 `/api/v1/users/me` 100 次。
3. 同时 1 个用户连接 WebSocket → 持续 5 分钟看是否掉线。
4. 切换流量 v1=0 / v2=100。

**预期结果**
- HTTP：100 次中两 revision 都被命中（验证负载分布），但每次返回的用户数据一致（JWT 在两版本均可解码）。
- WebSocket：切流量瞬间，**已连接**的 WS 连接保持（Container Apps 默认对长连接无强制中断），新建连接落到 v2。
- 切完后 v1 上的 WS 在自然断开后不自动重连到 v1（因 v1 流量=0）。

**通过判断**：JWT 跨版本兼容 + WS 不强断 + 新流量正确路由。

**责任人**：OPS + BE。

---
## D. 回滚 UAT [STAGING + PROD]

> 引用：`deployment.md` §15 回滚流程、§15.4 迁移降级注意事项。本节为**演练性 UAT**，确保真出事时不慌。

### D-1 镜像回滚 — 回退到前 1 版本 🟥

**前置条件**：Container App 当前 revision = `v2`，存在历史 revision `v1`。

**操作步骤**
1. `az containerapp revision list` 确认 `v1` Active=false 但仍存在。
2. `az containerapp ingress traffic set --revision-weight v1=100`。
3. 等待 30s。
4. `curl /health` 验证 `version` 字段已回 v1。
5. 抽样 5 条核心 API 仍可用。

**预期结果**
- 切换 ≤ 2 分钟；version 回退；服务无报错；用户登录态保留（JWT 兼容）。

**通过判断**：耗时达标 + 版本正确 + 业务不挂。

**责任人**：OPS。

---

### D-2 镜像回滚 — 回退到前 N (N≥3) 版本 🟧

**前置条件**：ACR 中至少有最近 3 个版本镜像；Container App 已 list 出来。

**操作步骤**
1. 直接 `az containerapp update --image yiluanacr.azurecr.io/yiluan-backend:<old-tag-3-versions-ago>` 强制部署。
2. 验证 readiness。
3. **同时检查 DB schema 是否与 N 前镜像兼容**。

**预期结果**
- 若 schema 向前兼容（无 drop column 类破坏性变更）：服务起得来；readiness 绿。
- 若 schema 已超前：readiness 503，`migration.ok=false` —— 此时必须**先按 D-3 降级 schema**。

**通过判断**：成功或正确报错（不是静默崩溃）。

**责任人**：OPS + BE。

---

### D-3 迁移回滚 — alembic downgrade 边界 🟥

**前置条件**：Staging DB 有最近 3 个 revision：`R0 → R1 → R2`，当前=R2。

**操作步骤**
1. **逐版回退**：`alembic downgrade -1` → 验证 = R1 → 再 `alembic downgrade -1` → 验证 = R0。
2. 不要直接 `alembic downgrade R0` 跳跃。
3. 每一步后跑 smoke。
4. 若某 revision 的 `downgrade()` 标注 `IRREVERSIBLE` → **不要执行 downgrade**，改走 PITR（见 D-4）。

**预期结果**
- 逐版可回；中间状态服务可用；不可逆 revision 被识别并跳过。

**通过判断**：双向可达 + 无意外破坏。

**责任人**：BE。

---

### D-4 数据修复 / 补偿任务清单 🟥

> 当 D-3 不可行（不可逆迁移、数据已损坏）时的补偿手段。本节列出**演练性**步骤；真实执行需 PM/BE 联合签字。

**操作步骤（演练）**
1. **创建止损备份**：
   ```
   az postgres flexible-server backup create \
     --resource-group yiluan-rg --name yiluan-db \
     --backup-name pre-fix-$(date +%Y%m%d-%H%M%S)
   ```
2. **PITR 恢复到一个新实例**（不要覆盖生产）：
   ```
   az postgres flexible-server restore \
     --resource-group yiluan-rg --name yiluan-db-fix \
     --source-server yiluan-db --restore-time "<T0>"
   ```
3. **导出受影响表**：`pg_dump --table=orders --table=payments yiluan-db-fix > /tmp/fix.sql`。
4. **人工 review SQL** → 拼成 patch 脚本（仅 UPDATE/INSERT，禁止 DROP/TRUNCATE 不带 WHERE）。
5. **在 Staging 演练 patch** → 比对结果。
6. **生产执行**：开事务 `BEGIN;` → 跑 patch → `SELECT` 校验影响行数 → 满意才 `COMMIT;`，否则 `ROLLBACK;`。
7. **执行后再次手动备份**用作未来追溯。

**补偿任务清单**（每项若触发，都需 BE 出 runbook）：
- [ ] 重复扣款 → 触发自动退款脚本（按 `payments` 中 `idempotent_hit` 异常筛查）
- [ ] 短信欠费/告警漏发 → 阿里云后台拉日报 → 人工电话补通知
- [ ] 订单状态卡死 → 跑 `python -m app.scripts.expire_orders_once` 强制扫描
- [ ] WebSocket 推送失败 → 切回 REST 兜底 `GET /notifications?unread_only=true`，APP 端启动时拉一次

**预期结果**：每条都有清晰 runbook；演练能完整走通；耗时 ≤ 30 分钟。

**通过判断**：runbook 齐全 + Staging 演练通过 + 影响行数与预期相符。

**责任人**：BE + OPS + PM 签字。

---

### D-5 跨版本会话/JWT 兼容 🟧

**前置条件**：v1 用 `JWT_SECRET=<S1>`，v2 也用 `<S1>`（密钥不轮换）。

**操作步骤**
1. v2 部署后，老 JWT（v1 签发）请求 `/api/v1/users/me`。
2. 切回 v1，新 JWT（v2 签发）请求同一接口。

**预期结果**
- 双向均 200，用户态保留；不强迫用户重新登录。
- 若密钥轮换则前置在文档中说明，并在 release note 提示用户重登录。

**通过判断**：双向兼容或显式 401（不可静默 500）。

**责任人**：BE。

---
## E. 审核验收 [PROD-提审窗口]

### E-1 微信小程序提审 — 引用 P1-5 全套 🟥

**前置条件**：`docs/wechat-submission-checklist.md` 已存在。

**操作步骤**：
1. 按 `wechat-submission-checklist.md` §0 TL;DR 的 5 件事逐项 ✅。
2. 按 §11 「提审 Day-of 流程」走一遍。
3. 提审备注复制 §7 模板。

**预期结果**：所有勾选项 100% 通过；提审备注完整。

**通过判断**：依据 `wechat-submission-checklist.md` 的勾选清单逐条对齐，**不在本文件重复列举**。

**责任人**：PM 主导，FE/法务/OPS 协同。

---

### E-2 iOS 提审前手工巡检（仅本地） 🟧

> 范围：iOS SwiftUI 客户端的本地巡检，**CI 不在范围**（iOS pipeline 由后续任务覆盖）。

**前置条件**：本地 macOS + Xcode 15+；iOS 17 真机；后端 Staging 可达。

**操作步骤**
1. **构建**：`xcodebuild -scheme YiLuAn -configuration Release` 无 warning（视情况按白名单豁免）。
2. **图标 / 启动图**：所有尺寸齐全，1024×1024 App Store 图标无透明、无圆角、无文字溢出。
3. **隐私清单**：`PrivacyInfo.xcprivacy` 列出所有 Required Reason API（如 `UserDefaults`、`SystemBootTime` 等）；与代码实际调用一致。
4. **第三方 SDK SDK 隐私清单**：检查微信 SDK / 微信支付 SDK 的隐私清单已 bundle。
5. **App Transport Security**：`Info.plist` 中无 `NSAllowsArbitraryLoads=true`；所有域名 HTTPS。
6. **版本号**：`CFBundleShortVersionString` 与 `CFBundleVersion` 已自增。
7. **TestFlight 内测一轮**：≥ 3 名内测人员通过核心流程（登录、下单、支付沙箱、聊天、退出）。
8. **崩溃率**：TestFlight 内测期 0 crash（或 ≤ 0.1%）。
9. **审核备注**：参考 `wechat-submission-checklist.md` §7 模板改写为 iOS 版本（账号一致：`13800000001` + OTP `000000`）。

**预期结果**：9 项全部 ✅；TestFlight 7 天无大问题反馈。

**通过判断**：内测无 P0/P1 + 隐私清单完整 + 资料齐全。

**责任人**：iOS 开发 + QA + PM。

**说明**：iOS 模拟器 CI 自动化构建在 P2 任务中独立推进，此处仅做提审窗口的人工核对。

---

### E-3 提交前最终冒烟（5 项关键场景） 🟥

**前置条件**：v1.0.0 镜像已部署到 Production；C-1 ~ C-7 全部通过。

**操作步骤**（按顺序，单人 ≤ 30 分钟）：
1. **登录**：13800000001 + 000000 → 拿到 JWT → `/users/me` 返回用户。
2. **下单**：选医院、选陪诊师、选时间 → 创建订单成功。
3. **支付**：真实微信 0.01 元 → 回调成功 → 订单 `paid`。
4. **接单 + 聊天**：13900000001 接单 → WebSocket 双向消息能收发。
5. **拒单 / 过期 / 退款** 三选一抽样：跑 `docs/test-cases/reject-expiry.md` 中的 A-1（拒单 + 自动退款）作为最终回归。

**预期结果**：5 项全绿；耗时 ≤ 30 分钟；Application Insights 无 ERROR 突增。

**通过判断**：5/5 PASS + 无新告警。

**责任人**：QA 主验，BE/OPS on-call。

**FAIL 时动作**：立即按 `deployment.md` §15 回滚到上一稳定 revision，开 P0 事故复盘。

---

## F. 提审/上线前最终核对清单（≤ 30 项 ✅）

> 上线发布同行评审会议（go/no-go）必查；缺一项不发版。覆盖 A/B/C/D/E 五大场景的 P0（🟥）项。

### 支付（P0）
- [ ] **F-01** 真实商户号已注入 Key Vault 且 `/health` 显示 `payment_provider=wechat`（A-1 前置）
- [ ] **F-02** 一笔真实 0.01 元支付端到端成功，DB / 微信后台 / 日志四方一致（A-1）
- [ ] **F-03** 一笔真实退款（全额）秒到账，`refunds` 表 success（A-3）
- [ ] **F-04** 重复回调 5 次幂等通过，无重复扣款（A-9）
- [ ] **F-05** 支付回调失败 / 退款失败 → 告警 14.3 §2 触达企业微信（A-5）

### SMS（P0）
- [ ] **F-06** 三网（联通/移动/电信）真实手机号 OTP 60s 内到达（B-1）
- [ ] **F-07** 60s 内同号第 2 次 send 返回 429 且阿里云无下发（B-2）
- [ ] **F-08** 1h 内同号第 6 次 send 返回 429（B-3）
- [ ] **F-09** 海外号码前置拦截 400，未调阿里云（B-4 N5）
- [ ] **F-10** SMS 失败率告警 14.3 §3 触达（B-5）

### 部署（P0）
- [ ] **F-11** GitHub Actions 全绿，ACR tag 与 Container App revision 一致（C-1）
- [ ] **F-12** 生产 DB 迁移 dry-run 已 BE review，无未拆分的破坏性变更（C-2）
- [ ] **F-13** 已在 Staging 完成 `alembic downgrade -1` 演练并恢复（C-3）
- [ ] **F-14** Readiness 探针对 DB / Redis / 迁移落后三种故障均能 503（C-4 / C-5 / C-6）
- [ ] **F-15** Readiness 失败告警 14.3 §1 触达（C-4）
- [ ] **F-16** `deployment.md` §18 部署后 smoke 1~10 全部 ✅（直接引用，不重复）
- [ ] **F-17** 监控告警 4 类（readiness / 支付回调 / SMS / WS-Redis）全部就位（`deployment.md` §14.3）

### 回滚（P0）
- [ ] **F-18** 镜像回滚到前 1 版本演练通过（D-1），耗时 ≤ 2 分钟
- [ ] **F-19** 回滚 runbook 列出补偿任务清单（重复扣款 / 短信欠费 / 订单卡死 / WS 失败 4 项）（D-4）
- [ ] **F-20** 已在 Staging 创建发布前手动 DB 备份 `pre-release-YYYYMMDD`（`deployment.md` §12.1）
- [ ] **F-21** PITR 流程已演练（不一定全跑，至少 OPS 知道命令）（D-4）
- [ ] **F-22** JWT 密钥本次未轮换（或已在 release note 提示）（D-5）

### 审核（P0）
- [ ] **F-23** `wechat-submission-checklist.md` §0 五件事 100% ✅（E-1）
- [ ] **F-24** 微信小程序所有域名（request/socket/uploadFile/downloadFile）已白名单（`wechat-submission-checklist.md` §3）
- [ ] **F-25** 微信支付回调 URL 已配置且 HTTPS 公网可达（`wechat-submission-checklist.md` §3）
- [ ] **F-26** 隐私协议页 + 用户协议页有 ≥ 2 处稳定入口（登录 + 设置/关于）（`wechat-submission-checklist.md` §5）
- [ ] **F-27** 高风险文案扫描（§8.3）零命中
- [ ] **F-28** iOS TestFlight 内测期 0 P0/P1（E-2）

### 最终冒烟
- [ ] **F-29** Production 五项关键冒烟（登录 / 下单 / 支付 / 接单+聊天 / 拒单回归）全部 ✅（E-3）
- [ ] **F-30** PM / BE / FE / OPS / QA on-call 名单已落到值班表，发布后 24h 待命

---

## 附录：执行产出与归档

- 每次 UAT 跑通后，QA 在 `docs/qa/YYYY-MM-DD-uat-run.md` 归档：用例编号、执行人、PASS/FAIL、问题截图链接、commit hash。
- 失败用例 → 立即开 GitHub Issue + 在 `TECH_DEBT.md` 追加条目。
- 上线后 7 天内复盘：本清单是否有遗漏？补到本文件并升级版本号（页首"最后更新"）。

---

_最后更新：2026-04-18（QA 主导）_
_关联 Action Item：今日晨会 #6_
_引用文档：`docs/deployment.md` / `docs/wechat-submission-checklist.md` / `docs/test-cases/reject-expiry.md` / `backend/tests/test_payment_callback_idempotency.py` / `backend/tests/test_sms_providers.py`_
