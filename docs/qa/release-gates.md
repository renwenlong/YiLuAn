# YiLuAn Release Gates

> 单一来源：CI fail 即禁止 merge / release。绕过需 Owner 双签。
> 当前 W19/W20 阶段维护人：刻晴（测试）+ 魈（架构 reviewer）。

---

## 1. 总览

| Gate | 触发 | 引入 | Mark / 脚本 | 维护 |
|---|---|---|---|---|
| `pytest -m money_safety` | 每个 PR + 主分支 | S2-TEST-001 / ADR-0026r1 | `tests/services/test_money_safety_contract.py` 等 | 刻晴 |
| `pytest -m share_security` | 每个 PR + 主分支（过渡期 continue-on-error） | S2-TEST-002 / ADR-0036 §3.5 | `tests/services/share/test_share_security.py` | 刻晴 |
| OpenAPI 字段契约 diff | 每个 PR | S2-TEST-002 / PRD-001 §6.C AC#22 | `scripts/qa/openapi_contract_diff.sh` | 刻晴 |
| 微信 schema 校验 | 每个 PR | S2-TEST-002 / PRD-001 §6.C AC#23 | `scripts/qa/wechat_openapi_check.sh` | 刻晴 |
| iOS `APIEndpointTests` 反序列化 | iOS-tests workflow | S2-TEST-002 / PRD-001 §6.C AC#24 | `ios/YiLuAnTests/APIEndpointTests.swift` | 刻晴 |
| Alembic up/down smoke | 每个 PR | alembic-smoke.yml | 既有 | 魈 |

---

## 2. money_safety 详解

**目的**：资金线（PSP 回调 / 退款 / 钱包 ledger / 对账）契约不漂移。

**覆盖**（首版 ≥9 case，含 1 条 hypothesis property-based fuzz）：

1. `record_callback_or_skip` 空 transaction_id 必须拒绝（ADR-0035 §3 P0-C；当前 `xfail strict=True` 占位，待 S2-DEV-007 修复后转 XPASS）
2. 重复 (provider, txn_id) 幂等 False
3. 同 provider 不同 txn / 不同 provider 同 txn 各自独立
4. raw_body 超长截断不抛
5. wallet_ledger pay/refund 双账方向相反金额相等
6. `create_refund` 金额超 paid_amount 拒绝
7. `handle_pay_callback` 未知 order_number 返回 None 不副作用
8. Hypothesis fuzz：任意 (provider, txn_id) 序列满足 idempotency property

**运行**：
```bash
cd backend && python -m pytest -m money_safety -v
```

**违规处理**：fail 直接打回 PR；xfail strict=True 触发 XPASS 时说明 P0-C 已修，去 xfail 即可。

---

## 3. share_security 详解

**目的**：Top1 家庭陪诊家属端鉴权/分享/AI 摘要的 negative & abuse 全覆盖。

**覆盖（计划 / S2-TEST-002 实施）**：

| 用例族 | 来源 |
|---|---|
| 过期 token → 401 | ADR-0036 §3.5 / PRD §6.B AC#13 |
| revoked token → 401（含 WS 主动断开 4013） | ADR-0036 §3.5 / PRD §6.B AC#14 |
| 跨订单 token IDOR → 403（含 JWT 拼接 / 路径替换 / openid 复用 3 类） | PRD §6.B AC#16 + 刻晴 review AC#16b |
| distinct openid > 5 / 24h 滚动窗口 → 告警 + 自动 revoke | PRD §6.B AC#17（窗口约束见刻晴 review） |
| share_session JWT 篡改 / 过期 / alg=none → 401 | ADR §3.5 |
| WS 上行写帧 → close 4012 | ADR §3.5 |
| per-token WS 连接 > 3 → 拒 | ADR §3.5 |
| scope=progress_only 拉影像 → 403 | PRD §6.B AC#21 |
| OTP 频控（同号 1min 1 / 1h 5）/ 爆破锁（错 5 次锁 10min）/ 复用拒绝 | 刻晴 review AC#21b + 魈 review F2 频控 |

**运行**：
```bash
cd backend && python -m pytest -m share_security -v
```

**过渡期**：S2-DEV-002/003 未落地前 CI 允许 `continue-on-error: true`，避免空 collect 阻塞。S2-DEV-002 done 当天去掉 `continue-on-error`。

---

## 4. 跨端契约三件套（S2-TEST-002）

PRD-001 §6.C AC#22-25。develop done 的客观门槛，无人工放行口。

1. **OpenAPI baseline diff**：`scripts/qa/openapi_contract_diff.sh` 导出 `/openapi.json` → 与 `docs/api/openapi-baseline.json` 比对 ADR-0036 §2.7 七字段（`share_token / share_scope / share_expires_at / share_revoked_at / share_session / patient_name_masked / digest_url`）名称/类型/必填性。任意变更 → `exit 1` → CI fail → 必须 ADR 修订 + 双签放行（不能改 baseline 蒙混）。
2. **微信 schema 校验**：`scripts/qa/wechat_openapi_check.sh` 跑 `openapi-typescript` 生成 d.ts，wechat services 层 ts-check 通过。
3. **iOS 反序列化**：`ios/YiLuAnTests/APIEndpointTests.swift` 6 端点请求/响应模型 `Codable` 反序列化断言。

> S2-DEV-002 接入前 iOS 用例先 `XCTSkip("await S2-DEV-002")`。

---

## 5. 红线 / 不可绕过

| 场景 | 处理 |
|---|---|
| 任一 release gate fail | merge 禁止；必须修复或走 Owner 双签 + 留 issue 跟踪 |
| `money_safety` xfail strict=True 转 XPASS | 立即去 xfail，确认 P0-C 修复落地 |
| 跨端契约 baseline 改动 | 必须 ADR 修订 PR 内同时改 baseline，单独改 baseline = 退回 |
| 灰度期触发 Prometheus 三档阈值 | 立即按 S2-OPS-001 runbook 回滚（关 F2 入口） |

---

## 6. 变更日志

- 2026-05-29 — S2-TEST-001 启动，引入 `money_safety` mark + 9 contract case + CI step。share_security / 契约三件套作为 W20 D1-D3 计划占位。
- 2026-05-29 — S2-TEST-002 done：share_security 23 case（13 pass + 1 skip + 9 xfail strict）接入 ShareService 真路径。OpenAPI diff / wechat openapi-typescript / iOS ShareEndpointContractTests stub 落盘。CI 3 新 step 接入。
- 2026-05-29 — S2-TEST-003 done：iOS APIClient401RefreshTests 7 stub + ios-test-plan 落盘。已扫真代码确认 `guard !isRefreshing else { return }` 是 P0-B 真 bug。
- 2026-05-29 — S2-DEV-003 (WS) 落地后：N6/N7/N7b 升级为 source-grep contract 断言（4012/4013/4014 close code + /ws/share/{token} 路由锁），避让 WS TestClient + FastAPI lifespan 合跑 hang 问题（胡桃 commit cddd5ed 记）。真 WS 负向在 tests/test_ws_share.py 独立 job 跑。剩余 6 xfail：N3b IDOR / N5 alg=none / N4 cron / N9a/b OTP / N7 真并发。
