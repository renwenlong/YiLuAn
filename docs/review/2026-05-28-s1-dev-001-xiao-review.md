# 魈 — S1-DEV-001 Code Walkthrough Review 意见

**结论**：✅ **通过**。同时 S1-DES-001 可以一起收口走 awaiting-approval。

---

## 一、整体评价

胡桃的通读是**真通读不是目录翻**：
- §0 三大复用 + 三大坑直接命中 Top1 实施路径
- §1.1 表里每个模块都标了"复用点 / 坑"，新人 onboard 不用再爬源码
- §1.4 outbound 三大遗留与 ADR-0035 §3 P0-A / ADR-0026r1 完全对齐
- §5 跨端同步点表把 share 7 字段补进去 —— 实施期不会漂
- §6 W20 实施顺序（D1: 001/002/003/007 并行 / D2: 005/006 / D3: 004 收口）逻辑严密

**这份 walkthrough 实质上是 ADR-0035 架构地图的代码侧验证版**，两份合一份读就是医路安完整架构手册。

---

## 二、逐条回应胡桃 review 请求

### Q1：§1.4 outbound 三大遗留与 ADR-0035 §3 P0-A 一致么？S2-DEV-007 acceptance 够么？

✅ **完全一致**。三大遗留逐条对齐：

| 胡桃 §1.4 描述 | ADR-0035 §3 P0-A | ADR-0026r1 修复路径 | S2-DEV-007 acceptance |
|---|---|---|---|
| half-open 单成功 close | B1 | §2.1 N 连胜门槛（默认 3） | acceptance #1 + 单测 CB 状态机全转换 |
| 无 httpx 白名单 | B2 | §2.3 4xx/5xx 分流 + RequestError 进 retry | acceptance #2 + httpx 4xx/5xx 单测 |
| CB 不空转 / 长时间 idle | B3 | §2.2 CB-open 直接 raise，不进 next attempt | acceptance #3 + assert attempt 调用次数 = 1 |

**S2-DEV-007 acceptance 够，无需补**。胡桃实施时直接引 ADR-0026r1 §3 七条 acceptance 即可，含：
- 单测全状态机转换
- httpx 分流
- `outbound_circuit_state{provider}` Prometheus gauge
- 所有现有 provider 回归（wxpay / aliyun_sms / redis pubsub）
- wxpay 真实回调 staging 回归（刻晴 release gate）

### Q2：§1.1 `payment_service.py` 739 行下一轮拆 prepay / callback / refund 三 mixin —— ADR-0035 follow-up 还是新 task？

**建议：直接进 W22+ backlog，不入 ADR-0035 follow-up**。

理由：
- ADR-0035 §3 P2 已经收口了"OrderService Mixin 共享 base 注入"的演进话题，PaymentService 是同类问题不同对象
- W19/W20 资源 all-in Top1 + 生产安全五件套，重构 739 行支付服务不在关键路径
- **真实重构触发条件**：W20 Top1 引入 AI 摘要扣费后，PaymentService 增量逻辑落地到哪个文件后再拆；现在拆边界不清

**动作**：建议凝光新建 `BACKLOG-PAY-REFACTOR`（P2，触发条件：Top1 上线 + AI 扣费稳定 1 月）。我 ADR-0035 不补 follow-up，把 W22 演进话题集中在 backlog task 上更干净。

### Q3：§6 W20 D1 三件套并行顺序（001/002/003/007）与 ADR-0036 §2 期望一致么？

✅ **一致 + 1 项提醒**：

ADR-0036 §2.3 数据模型 / §2.4 WS / §2.7 端点 三块本就互相独立可并行，胡桃排序正确。

**提醒**：S2-DEV-002 (端点) 实施时**先冻 `share_session` JWT claims 结构**（建议加 `aud: "share"` + `order_id` + `share_token_id` 三字段），后续 003 (WS 鉴权) / 005 (AI 摘要触发上下文) 都要复用。先冻 claims 比先冻 endpoint shape 更重要——后者 OpenAPI baseline (004) 兜底，前者跨多个 service。

---

## 三、3 处技术细节追加（不阻塞 review）

### 1. §1.5 core/security.py share_session JWT 用 `audience claim 区分` —— 强同意，加一句

share_session JWT 与主 access_token **必须用同一密钥但不同 `aud`**，验证时强制 `aud=="share"` 才放行家属端路由；防止主 access_token 被误用做 share、share token 被误用做主接口。这条建议写进 S2-DEV-002 acceptance。

### 2. §1.1 notification.py "通知触发与业务事务同 session，应考虑拆 outbox"

✅ **同意，但本期不动**。
- Top1 share notification（"X 位家属正在查看"）量级小，同事务可接受
- outbox pattern 是一次跨多 service 的重构，需要单独 ADR
- 建议同样进 backlog（`BACKLOG-OUTBOX-PATTERN`，P2），触发条件：Top1 上线后通知失败率超 0.5% 或资金通知阻塞主事务被监控告警

### 3. §2.5 「家属端是否独立 tabBar 在 PRD 评审前定」

PRD-001 已经 done，凝光未明确这条。**架构师视角建议：家属端不要独立 tabBar，做单页 + 标签切换**——理由：
- 家属端是只读消费场景，导航复杂度低
- 独立 tabBar 会让微信审核当作"新独立应用"加大合规风险
- 单页 SPA 更适合 H5 落地页路径（外部浏览器降级走同一份代码）

胡桃实施 F2 时直接按"单页 + tab 切换（位置 / 进度 / 摘要 / 影像）"做，不用回头问凝光。**这不是 PRD 范畴是技术实现，记本 review 留痕即可**。

---

## 四、S1-DES-001 终评（与本 review 一并收口）

胡桃通读校验 = ADR-0035 架构地图的代码侧验证：
- §1 backend 模块表 ↔ ADR-0035 §1 mermaid 图 ✅ 全对齐
- §1.4 outbound 三大遗留 ↔ ADR-0035 §3 P0-A ✅ 一致
- §2-3 微信/iOS 各端总结 ↔ ADR-0035 §1 三端架构地图 ✅ 一致
- §5 跨端同步点表 ↔ ADR-0036 §2.7 字段表 ✅ 加 share 行已对齐

**S1-DES-001 验收**：ADR-0035 + ADR-0036 双双就绪、与胡桃实际通读零漂移、与凝光 PRD-001 v1.2 + 刻晴 S1-TEST-001 全闭环。可走 `awaiting-approval` 报帝君。

---

## 五、不采纳/反对

无。

---

**Review 完成时间**：2026-05-28 08:36 UTC
**Reviewer**：魈（架构师）
**下一步**：
1. 胡桃 S1-DEV-001 review 通过，按 workflow 由我 `set_status done`
2. S1-DES-001 同步走 `awaiting-approval` 报帝君
3. 胡桃继续推 S2-DEV-001~007
