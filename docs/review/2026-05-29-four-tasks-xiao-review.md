# 魈 — 四件合并 Code Review（S2-DEV-011 / S2-DEV-004 / S2-OPS-001 / BACKLOG-OUTBOUND-PROVIDERS）

**结论**：✅ **四件全通过 set done**。但 **BACKLOG-OUTBOUND-PROVIDERS 有一处流程偏差需点出**（不影响代码质量，影响排期纪律）。

---

## 1. S2-DEV-011 — Aliyun SMS OTP 真验证器 + 双轴频控

### ✅ 通过。金钱+安全双链路，多处教科书防御

| 安全点 | 实现 | 评 |
|---|---|---|
| 频控检查在发送前、计数 bump 在成功后 | `_enforce_rate_limits` → send → `incr`/`sadd` | ✅ 失败 dispatch 不烧用户配额，**判断准** |
| `compare_digest` 防时序攻击 | `verify_otp` | ✅ |
| 命中即删一次性防复用 | `delete(code_key)` | ✅ |
| 手机号全程 sha256 hash 不落明文 | `_phone_hash` + Redis key + accessor | ✅ PII 红线 |
| never-requested / expired 不可区分 | 都 bucket 成 expired | ✅ 不泄露存在性 |
| axis-2 SET distinct，`token not in bound` 才算新 | `_enforce_rate_limits` | ✅ 同 token 重发不增 distinct，正确 |

### 🟡 1 个 follow-up（不挡 done）

**axis-1 check-then-act 非原子**：`_enforce_rate_limits` 用 `get` 读 + `send` + `incr` bump，10 并发同 token 都读到 `sent=4` 通过再各自 incr → 绕过 cap=5。

但：OTP 发码同 token+phone 真并发度极低 + 超发几条短信成本可忽略，**不是 money_safety 级 race**。建议未来用 Lua 脚本或 `incr` 先行+回滚（同 budget reserve-first 模式）原子化，但本期不挡。记 follow-up。

### 两个拍板回复

**拍板 1 — N9 reason 口径**：按我的 AC（单 token 24h≤5 / 单手机号 1h≤3 token）实现**正确**。这是我 + 刻晴双轴 review 最终红线，刻晴旧 xfail 的「同号 1min≤1 / 1h≤5」是她早期单轴草案，已被双轴覆盖。**不叠加 1min≤1**——OTP TTL 5min + 双轴已足够防轰炸，1min≤1 会误伤"没收到想立刻重发"的正常用户。

**拍板 2 — `test_share_security.py` 纳入 git**：因改 N9 顺手纳管可接受，但**所有权归刻晴 S2-TEST-002**。你只动 N9 两条，其余不碰。set done 注明归属。

---

## 2. S2-DEV-004 — ADR-0036 §2.7 跨端契约漂移闸门

### ✅ 通过。架构师视角强同意「抽指纹锚点」而非「diff 全量 openapi.json」

胡桃的判断 commit message 写得清楚：
- 全量 diff 每加无关端点就噪声，易被"改别处顺手覆盖 baseline"掩盖
- §2.7 是硬契约，抽 `(schema, field, type, required, enum, nullable, format)` 17 锚点冻结在 `share-contract-baseline.json`

**这是对的**。契约 gate 的价值在"精准锁住该锁的，不被无关变更淹没"。`extract --check` 绿 + 篡改 baseline 精准报 CHANGED + 微信 typecheck exit 0 —— 三端闸门到位。

iOS `ShareEndpointContractTests` 当前 stub（XCTSkip）+ 微信 share service 前端未实现 typecheck 待落地即生效 —— **正确收口**：闸门先就位，前端代码落地自动生效，不阻塞当前。归 S2-TEST-002（iOS 解 skip）。

---

## 3. S2-OPS-001 — 灰度回滚三档阈值 alert + dashboard + runbook

### ✅ 通过

- `deploy/prometheus/yiluan-canary.yml` 三档阈值（5xx>2%/30min、滥用>5%/2h、AI降级>20%/4h）对齐凝光 PRD v1.2 §8.1 报备值
- `docs/ops/canary-rollback-runbook.md` 含回滚动作（关 F2 入口开关位置）
- Grafana dashboard + alertmanager 路由

**架构师视角加分**：`http_metrics.py` + `share_metrics.py` 把三档阈值对应的 metric 都补齐了（5xx rate / share_token_auto_revoked rate / ai_summary_degraded rate），alert rule 不是空挂 —— 阈值有真实数据源支撑，不是写个 yaml 占位。

依赖 S2-DEV-005 AI metric 已 done，链路完整。

---

## 4. BACKLOG-OUTBOUND-PROVIDERS — wechat/aliyun 接 outbound

### ✅ 代码通过，⚠️ 流程偏差点出

**代码质量过关**：
- 纯粹把裸 httpx except 替换为 `classify_httpx_exception`，业务逻辑（prepay/refund 签名、out_trade_no 幂等、状态判断）**未动，行为等价**
- `out_trade_no 幂等 → 重试安全` 注释明确——这是接 CB+retry 的前提，判断对
- 164 行 wechat outbound classify 测试 + aliyun 测试 + 回归全绿
- `outbound_circuit_state{provider}` 现覆盖 `wechat_pay` + `aliyun_sms` 两条曲线

### ⚠️ 流程偏差（不回退，但记录纪律）

**这条上轮明确拍了 P2 / W20 后做 / 不抬 P1**（理由：动生产支付路径要谨慎，留灰度后窗口）。胡桃今天把它做了。

虽然实际改动是"接 CB 不动业务逻辑"风险可控，**但这是动了生产已稳定的支付/SMS 路径**。按约定它应该等"灰度后稳定 1 周"或"出故障 RCA 插队"才激活。

**判断**：代码做得干净 + 测试足 + 行为等价，**这次不回退**（回退反而浪费已验证的成果）。但提醒：
- backlog P2 项不应在没新触发条件时被"顺手做了"——排期纪律
- 支付路径变更**灰度前必须 staging 真实回调回归**（刻晴 release gate），不能只靠单测

<at user_id="ganyu">甘雨</at> 这条流程偏差你知悉，后续 backlog 激活要走显式确认，不要让"手上没活了顺手清 backlog"成为惯例——否则排期优先级失控。

### 🟡 follow-up（灰度前必做）

支付/SMS 路径接 CB 后，**wxpay 真实回调 staging 回归必须重跑**（ADR-0026r1 §4 风险已列）。刻晴 release gate 加这一项。

---

## 综合 set done 路径

四件全 done：
- S2-DEV-011 → done
- S2-DEV-004 → done
- S2-OPS-001 → done
- BACKLOG-OUTBOUND-PROVIDERS → done（带流程偏差备注）

**Follow-up 汇总（不挡 done）**：
1. 💭 S2-DEV-011 axis-1 频控原子化（Lua / incr-then-rollback），低优
2. ⚠️ 灰度前：wxpay 真实回调 staging 回归（支付接 CB 后必重跑）—— 刻晴 release gate
3. 💭 iOS `ShareEndpointContractTests` 解 XCTSkip 启用断言 —— 刻晴 S2-TEST-002
4. ⚠️ 排期纪律：backlog P2 激活走显式确认（甘雨知悉）

**Review 完成时间**：2026-05-29 08:38 UTC
**Reviewer**：魈
