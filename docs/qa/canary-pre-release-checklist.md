# 医路安 Top1 家属端 — 灰度前手动回归 Checklist

> **S2-TEST-004** | 灰度上线最后一道闸 | 维护：刻晴（测试）
> 规则：**全部 PASS 才放灰度**。任一 FAIL 阻塞 D11 灰度启动（凝光排期硬前置）。
> 与 CI gate（`pytest -m money_safety` / `pytest -m share_security`）互补——本清单是 CI **不能**覆盖的 staging 真实环境验收。

---

## 0. 执行前置

- [ ] staging 环境部署最新 `feature/team-iteration` 分支
- [ ] CI gate 全绿（money_safety + share_security + 跨端契约三件套）
- [ ] `ADMIN_API_TOKEN` 等敏感环境变量已注入（非默认值，P0-11 fail-fast 校验通过）
- [ ] Prometheus + Alertmanager + Grafana dashboard 已挂（S2-OPS-001）

---

## 1. 资金线（接熔断器后必验）

> 背景：支付路径接了 outbound circuit breaker（ADR-0026r1），CI 不能打真实微信支付，必须 staging 真实回调验。

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 1.1 | staging 真实 wxpay 下单 → 支付 → 回调 | 订单状态 paid，ledger 入账一行 | ⬜ | | |
| 1.2 | 回调走 outbound CB 正常路径 | CB closed 状态，回调成功 | ⬜ | | |
| 1.3 | 模拟 PSP 抖动触发 CB open | 回调降级入 dead_letter，不丢账 | ⬜ | | |
| 1.4 | CB 状态机 open→half-open（N=3 连胜）→closed | Prometheus metric 正确记录三态转换 | ⬜ | | |
| 1.5 | 退款真实回调 → ledger 平账 | in/out 双账方向相反金额相等 | ⬜ | | |
| 1.6 | 空 transaction_id 回调（P0-C 验证） | 拒绝 + `payment_callback_empty_txn_total` counter +1 | ⬜ | | |

## 2. Share Token 端到端（双端真机）

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 2.1 | 患者端生成分享 → 拿到 share_url | active cap=3，第 4 个自动 revoke 最旧 | ⬜ | | |
| 2.2 | 微信家属端静默路径（wx_openid）换 session | 返回 share_session JWT（含 aud=share） | ⬜ | | |
| 2.3 | iOS / 浏览器家属端 OTP 路径换 session | OTP 6 位验证通过，频控生效 | ⬜ | | |
| 2.4 | 家属端拉脱敏订单视图 | 患者姓名脱敏（张**）、电话/身份证/medical_notes 屏蔽 | ⬜ | | |
| 2.5 | scope=progress_only 拉影像/AI 摘要 | can_view_images=false，影像 403 | ⬜ | | |
| 2.6 | WS 进度推送 + 位置 cache replay | 连接后先收 location_replay 再收 share_auth_ok | ⬜ | | |
| 2.7 | 断线 10s 重连 | 位置点不空 | ⬜ | | |
| 2.8 | 断线 90s 重连（cache 60s 已过期） | UI 提示"位置缓存过期，等待下次上报"，不悬空旧点 | ⬜ | | |
| 2.9 | token revoke 后已建立 WS | close 4013 主动断开 | ⬜ | | |
| 2.10 | 上行写帧 / per-token 连接 > 3 | close 4012 / 4014 | ⬜ | | |

## 3. IDOR / 越权（staging 真实 endpoint）

> CI 层 xfail 的 N3b / N5 alg=none 在此真验。

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 3.1 | A 订单 token 拉 B 订单数据 | 403 | ⬜ | | |
| 3.2 | share_session JWT 拼接 / order_id 路径替换 / openid 复用 | 全部 403 | ⬜ | | |
| 3.3 | JWT alg=none 攻击 | 401 | ⬜ | | |
| 3.4 | distinct openid > 5 / 24h 滚动窗口 | 自动 revoke + 告警 counter | ⬜ | | |
| 3.5 | OTP 错 5 次 | 锁号 10min | ⬜ | | |

## 4. AI 摘要成本 & 合规（实测）

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 4.1 | 单订单 AI 摘要成本 | ≤ ¥0.05（worst-case token 截断生效） | ⬜ | | |
| 4.2 | 日累计触发 ¥50 封顶 | BudgetExhausted → 模板降级，不再调 DeepSeek | ⬜ | | |
| 4.3 | DeepSeek 走 outbound CB | PSP 抖动时 AI 调用降级，不阻塞主流程 | ⬜ | | |
| 4.4 | post-check 关键词命中（"建议服用/确诊为/请按 X 剂量"） | 命中即降级模板，不输出违规医疗建议 | ⬜ | | |
| 4.5 | ai_blocklist.yaml 热更新 | 改词典不重启生效 | ⬜ | | |
| 4.6 | `@with_scheduler_lock` 多副本去重 | AI job 不重复扣费 | ⬜ | | |

## 5. 回滚演练（必须真演一次）

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 5.1 | 触发 5xx > 2% / 30min | Alertmanager 告警 + 回滚决策 | ⬜ | | |
| 5.2 | 执行回滚：关 F2 入口开关 | 新分享入口关闭，已发 token 保留 read-only | ⬜ | | |
| 5.3 | runbook 可操作性 | 值班人按 runbook 5min 内完成回滚 | ⬜ | | |
| 5.4 | 重启灰度逆向验证 | 三档逆向阈值（5xx≤0.5%/6h 等）满足才放量 | ⬜ | | |

---

## 6. 放行签字

| 角色 | 签字 | 时间 | 结论 |
|------|------|------|------|
| 测试（刻晴） | | | ⬜ 全 PASS |
| 架构（魈） | | | ⬜ 技术放行 |
| PM（凝光） | | | ⬜ 业务放行 |
| Owner（帝君） | | | ⬜ 灰度批准 |

> 任一 FAIL 项必须记录原因 + 处理决策（修复后重测 / 接受风险带 known issue 上线 / 推迟灰度）。
