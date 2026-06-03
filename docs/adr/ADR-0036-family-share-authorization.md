# ADR-0036: 家庭陪诊家属端 - 分享授权与只读访问模型

- **状态**：Accepted（2026-05-28，魈起草）— PRD-001 v1.1 帝君带补充批后推进
- **决策范围**:Top1「家庭陪诊家属端」MVP 的鉴权 / 数据访问边界 / WS 通道
- **关联**:帝君 2026-05-28 决议「只做 Top1 + 本周启动」;PRD-001(凝光,跨端字段表 §4 等本 ADR 回填);ADR-0031(WS+ChatService 统一);`models/family_member.py`(已存在但语义不同)

---

## 1. 背景

子女异地下单老人陪诊,付款后**完全看不见就诊过程**,这是医路安差异化最大单点(凝光 S1-REQ-001 Top1)。

MVP 要让家属看到三类信息:
- 陪诊师实时位置(订单进行中)
- 就诊进度时间轴(出发/到达/挂号/就诊/取药/结束等节点)
- 陪诊师上传的处方/检查单照片
- 当日 AI 摘要(订单完成后异步生成推送)

**核心约束**:家属端不强制注册,**降低使用门槛**是差异化关键;同时不能泄露患者 PII、不能让分享链接被无限转发滥用。

---

## 2. 决策

### 2.1 分享主体 - 不复用 `FamilyMember`

`models/family_member.py` 是 D-056「代他人下单」的关系模型,**患者数据所有者**;本期家属端是**只读观察者**,关系正交。新增独立模型 `OrderShareToken`,不耦合 FamilyMember。

> 未来如果家属端走深需要"家庭账号",再以 `FamilyMember` 为锚做合并。MVP 不做。

### 2.2 鉴权模型 - 单订单作用域 + 短链 token + 微信静默授权(双层)

**方案 A(采纳)**:

```
下单用户 → 点击「家属共享」→ 后端生成 OrderShareToken
         → 返回短链 https://m.yiluan.cn/s/<token>
         → 用户转发到家庭群

家属点击 → 小程序/H5 落地页 → 静默微信授权(只取 openid,不要 phone)
        → 后端用 token + openid 换 share_session JWT(30min)
        → 后续 REST / WS 都用 share_session JWT
```

**为什么不裸 token**:
- 裸 token 一旦泄露/被截图,无法定向回收
- 微信静默授权零摩擦(用户感知 = 同意一次"获取昵称头像"),但拿到 openid 后我们能:
  - 记录首次访问的 openid 绑定 token("白名单第一人")
  - 异常时(如同 token 出现 N 个不同 openid)触发告警/自动吊销
  - 后续做"接收记录"展示给下单人:"你妈正在看(微信昵称 xxx)"

**为什么不要求注册账号**:差异化关键,零摩擦是 Top1 价值核心。

**iOS / H5 兼容**:
- 微信小程序内 → `wx.login` 静默走通
- iOS App / 外部浏览器 → 降级为"用一次性 6 位短信验证码"路径(OTP 复用现有 Aliyun SMS Provider),用户成本略增但兜底覆盖全平台

### 2.3 OrderShareToken 数据模型

```python
class OrderShareToken(Base):
    __tablename__ = "order_share_tokens"

    id: UUID                # PK
    order_id: UUID          # FK orders, indexed
    created_by: UUID        # FK users (下单人), indexed
    token: str(32)          # URL-safe random, UNIQUE indexed (短链用)
    share_scope: enum       # full (位置+进度+影像+摘要) | progress_only (仅进度)
    expires_at: datetime    # 默认订单完成后 +24h;hard cap = 创建后 7d
    revoked_at: datetime?   # 下单人可主动吊销
    revoked_by: UUID?       # 谁吊销的(下单人 / 风控自动)

    # 访问记录(聚合,不存每次访问)
    first_accessed_at: datetime?
    first_accessor_openid: str(64)?    # 第一个访问者的 openid(white-listed)
    distinct_accessor_count: int = 0   # 不同 openid 数(>5 触发告警)
    last_accessed_at: datetime?

    created_at / updated_at
```

**关键约束**:
- **每订单最多 3 个 active token**(创建第 4 个时自动 revoke 最老的)
- **token 不可续期**,过期就再生成新 token
- **share_scope 默认 `full`**,下单人可在分享前切换为 `progress_only`(PII 敏感场景)
- **revoke 后立即失效**:所有持该 share_session JWT 的连接服务端主动断开

### 2.4 WS 通道 - 复用 `ws/chat` broker,新开只读 topic + 重连位置补偿


不另起 WsPubSubBroker 实例,**复用 ADR-0031 已有的 `WsPubSubBroker` + Redis Pub/Sub**,新增 topic:

```
现有:chat:{order_id}            # 双向聊天
新增:share:{order_id}            # 只读单向广播
```

新增 WS 端点:`/ws/share/{token}`
- 首帧 auth 改为 `{type: "share_auth", session: "<share_session_jwt>"}`
- 鉴权通过后只订阅 `share:{order_id}`,**不能发任何消息**(server 收到上行写帧直接 close 4012)
- per-token 连接数硬上限 = 3(防止 token 泄露后大量 idle 连接占资源)

**位置/进度更新的 publish 源**:
- 陪诊师端点击「到达」「就诊中」等节点 → 后端写 `order_status_history` + publish `share:{order_id}`
- 陪诊师端定时上报位置(30s / 200m 触发,已有 D-XXX)→ publish `share:{order_id}`(**不落库**,只 fanout,节省存储 + 减少 PII 留痕)
  - **断线重连补偿**:最新一条位置写 Redis cache `share:loc:{order_id}` TTL 60s;家属 WS 鉴权成功后**立即推一帧 cached 位置**,避免重连瞬间空白
  - E2E 强制覆盖「断线 10s 重连后位置点不空」(刻晴 review 红线)
- 陪诊师上传处方/检查单 → 写 OSS + publish `share:{order_id}`

### 2.5 PII 脱敏规则

| 字段 | 家属端可见 | 备注 |
|---|---|---|
| 患者姓名 | 仅首字 + ** | 「张**」 |
| 患者电话 | ❌ 不下发 | 紧急时通过下单人转 |
| 患者身份证 | ❌ 不下发 | - |
| 病情描述 / medical_notes | ❌ 不下发 | scope=full 也不给 |
| 陪诊师姓名 | ✅ 完整 | 陪诊师明知服务被家属看 |
| 陪诊师电话 | ❌ 不下发 | 客服转接 |
| 陪诊师实时位置 | ✅ (lat,lng,精度) | 仅 in_progress 状态 |
| 处方/检查单照片 | ✅ 原图 | 关键就医资产,scope=full 给 |
| AI 摘要文本 | ✅ 完整 | 已经过 LLM 脱敏 |

> 「下单人」≠ 「患者本人」(FamilyMember 代下单场景),share token **永远** 绑在 `order.booker_user_id`(下单人)维度,与患者本人是否同人无关。

### 2.6 AI 摘要 - 异步任务 + 成本封顶

- 触发:订单 status 转 `completed` 时 enqueue 异步任务(APScheduler 一次性 job 或新增 task queue)
- **调度锁强约束**:AI 摘要 job 必须通过 `@with_scheduler_lock` 装饰器接入(对齐 ADR-0035 §3 P1-A),首版即走,不许后补--避免多副本重复扣费
- 调用:DeepSeek API(`deepseek-chat`,单次输入约 2k tokens / 输出 500 tokens ≈ ¥0.005)
- **成本封顶**:
  - 单订单成本上限 = ¥0.05(超出截断不重试)
  - 日成本上限 = 配置项 `AI_DAILY_BUDGET_CNY`(默认 ¥50),超出当日不再调用、降级为"今日就诊已结束,详情可咨询陪诊师"
  - Prometheus counter `ai_summary_cost_cny_total` + alert
- 失败处理:不阻塞订单流程,降级为模板文案 + dead_letter 留痕
- **合规边界**:
  - prompt 显式约束"不得给出诊断/用药/剂量建议"
  - 输出端 post-check 命中关键词触发降级为模板文案
  - **关键词词典落配置文件** `config/ai_blocklist.yaml`(不硬编码),支持热更新
  - **post-check 单测覆盖率门槛 = 100%**,必含:1 命中触发降级 2 边界用例(如"建议**休息**"不命中)3 词典热更新生效

### 2.7 跨端字段表(给 PRD §4 回填)

| 字段名 | 类型 | 后端字段 | 出现位置 | 备注 |
|---|---|---|---|---|
| `share_token` | string(32) | `OrderShareToken.token` | 下单人端「家属共享」面板返回值 | URL-safe,短链用 |
| `share_url` | string | 拼接 | 同上 | `https://m.yiluan.cn/s/{token}` |
| `share_scope` | enum | `OrderShareToken.share_scope` | 下单人端切换;家属端只读 | `full` / `progress_only` |
| `share_expires_at` | datetime ISO8601 | `OrderShareToken.expires_at` | 双端展示 | - |
| `share_revoked_at` | datetime? | `OrderShareToken.revoked_at` | 下单人吊销后立即返回 | - |
| `share_session` | string (JWT) | 后端签发 | 家属端落地页换取,存 sessionStorage | 30min 短 TTL |
| `share_active_count` | int | 聚合 `count(active tokens)` | 下单人端展示当前几个有效分享 | 上限 3 |

REST 端点(凝光 PRD §5 用):
- `POST /api/v1/orders/{order_id}/shares` - 创建分享 token
- `GET /api/v1/orders/{order_id}/shares` - 列当前 active tokens
- `DELETE /api/v1/orders/{order_id}/shares/{token_id}` - 吊销
- `POST /api/v1/shares/{token}/session` - 家属端用 token + openid/otp 换 share_session JWT
- `GET /api/v1/shares/session/order` - 家属端用 share_session 拉当前订单只读视图
- `WS /ws/share/{token}` - 家属端实时通道

---

## 3. 方案对比(必备)

| 方案 | 描述 | 优 | 劣 | 决策 |
|---|---|---|---|---|
| A | 短链 token + 微信静默授权(采纳) | 零摩擦、可吊销、可审计、可识别"第一访客" | 落地页要做两套(微信/外部) | ✅ |
| B | 裸 token 短链,无任何鉴权 | 实现最简 | 一旦截图扩散无法回收;无法做"接收回执";扫描爬虫滥用 | ❌ |
| C | 家属必须注册账号 | 数据干净、可推送 | 摩擦极大、违背 Top1「零门槛」差异化 | ❌ |
| D | 复用 FamilyMember 关系(仅 family 可看) | 关系明确 | FamilyMember 要预录入;老人/亲戚很少提前录入;MVP 阻塞 | ❌ |

---

## 3.5 安全 negative 测试清单(强制 acceptance,刻晴 review 红线)

Top1 任何 develop task done 门槛必须覆盖以下 8 条:

1. 过期 share token → 401
2. 已 revoke 的 token → 401,且已建立的 WS 连接服务端主动 close 4013
3. 跨订单 token(A 订单 token 拉 B 订单数据)→ 403
4. 同 token N 个不同 openid,distinct > 5 → 告警 metric + 自动 revoke
5. share_session JWT 篡改 / 过期 / `alg=none` → 401
6. WS 上行写帧 → close 4012,不广播、不落库
7. per-token 连接数 > 3 → 拒第 4 个(4014)
8. `scope=progress_only` 拉影像/AI 摘要 → 403

配套 pytest mark:`pytest -m share_security`(与 `pytest -m money_safety` 同级,入 release gate)。

## 3.6 跨端契约测试(强制 develop done 门槛)

ADR-0036 §2.7 引入 7 个跨端字段 + 6 个 REST 端点 + 1 个 WS 端点,是项目**首次大规模新增跨端 schema**。Top1 的 develop task done 门槛硬要求:

- 后端 CI:导出 OpenAPI schema → diff 上次基线 → 字段漂移 PR 必须显式 review
- 微信端 CI:`openapi-typescript` 生成的 d.ts 校验 `services/*.js` 对 7 个字段的引用
- iOS CI:`APIEndpointTests` 扩展所有新模型反序列化断言(缺一个字段 fail)
- 三端任一漂移 → 直接打回 develop task,不进 review

## 4. 风险

1. **微信 jscode2session 频控**:现有 wxapp 已用,新增家属端落地页量级可能翻倍;需提前评估 `httpx` outbound 池容量。**依赖 P0-04 outbound 装饰器修复**(凝光建议清单),否则保险/支付/微信三条 outbound 链路撞同一 CircuitBreaker bug 会放大故障。
2. **位置实时性 vs 隐私**:陪诊师每 30s 上报位置是合理体验,但持续 7d 链路存在被员工"跟踪滥用"的可能。MVP 仅 in_progress 状态下推送;订单完成立即停止;不落库。
3. **AI 摘要合规**:医疗 LLM 输出有触发监管的风险。Prompt + post-check 双护栏 + 全量日志留 30d 备查 + 显性免责声明在 UI 显示。
4. **token 滥用**:上限 3 active token / 5 distinct openid 告警,但确定的恶意场景仍可绕过。MVP 接受这个残余风险,靠"下单人主动吊销"+ 风控人工 + 后续家庭账号机制兜底。
5. **OSS 处方/检查单 PII 泄露**:家属端拉图走预签名 URL(15min TTL),不暴露 OSS 直链;URL 签名失败 fallback 不展示。

---

## 5. 不在 ADR-0036 范围内

- 保险兜底 / 电子合同(Top2 押后)
- 家庭账号 / FamilyMember 合并(后续 ADR)
- 长辈端「巨字号」模式(PRD 范畴,凝光定)
- AI 报告解读(Top3 押后)

---

## 6. 后果

- **+**:Top1 三端可在 W19 PRD/ADR + W20 实施 + W21 灰度的节奏内交付
- **+**:share token 抽象足够通用,未来"陪诊师端给家属补送材料"、"客服端协助查看"都可复用
- **-**:新增 `order_share_tokens` 表 + 1 个 WS 端点 + 1 个落地页 + AI summary 异步链路,胡桃 W20 后端工作量约 5d;小程序/iOS 各 3-4d;总人天 ~15d,紧但可达
- **-**:DeepSeek API 引入新外部依赖,必须走修复后的 `outbound_call`;P0-04 是 ADR-0036 的硬依赖

---

## 7. Follow-up(不阻塞本 ADR)

- **F-1**:share token 的"接收回执"产品形态(凝光 PRD 决定)
- **F-2**:AI 摘要的 prompt 模板与 post-check 规则(W19 末出附录)
- **F-3**:share session JWT 是否需要独立签名密钥(防与主 access_token 串用),W19 实施前定
- **F-4**:风控告警阈值(5 distinct openid 是否合理)上线后基于真实数据调

---

## 8. 附录：分层错误码语义表（r1 修订 2026-06-03）

> 动因：S2-TEST-006R AC#7 复测发现术语含混——"错误的 share_token + 合法 JWT" 这种场景 nginx 在 WS upgrade 阶段就 403，不会走到 WS share_auth 返回 4001 invalid_session。两个错误码属于不同层，语义不同，客户端处理也应区分。本附录明示分层。

### 8.1 错误码层级

| 层 | 错误码 | 含义 | 触发场景 |
|---|---|---|---|
| **nginx (transport)** | `HTTP 403` | URL 路径/host 未命中、IP 黑名单、WS upgrade 被 拒 | URL 写错 share_token 厊 + 传合法 JWT；nginx 在接入 backend 前就拦 |
| **nginx (transport)** | `HTTP 404` | URL 路径不存在 | 错 endpoint |
| **FastAPI (handshake)** | `HTTP 401` | API 路径进到后端，但 share_token 在 DB 不存在 / 已 revoked / 已过期 | exchange_share_session 接口上 |
| **FastAPI (handshake)** | `HTTP 429` | OTP 频控命中 (token-cap / phone-cap) | send_share_otp / exchange_share_session |
| **WS (application auth)** | `close 4001` | WS 连接已建立 + share_auth 首帧 JWT 验证失败 (签名/aud/exp 不对) | invalid_session / bad_jwt |
| **WS (application auth)** | `close 4013` | share_token 被 owner revoke 后已建立的 WS 被服务端主动 close | revoke API 后所有存活连接被 close |
| **WS (application policy)** | `close 4012` | 客户端发上行业务写帧 (的只读 topic) | share 是只读，客户端错误发帧 |
| **WS (application policy)** | `close 4014` | per-token 连接数超 cap (默认 3) | 超额连接被拒第 4 个 |
| **WS (canary control)** | `close 4015` | 火度门热切 `READONLY_SHARE_SESSIONS=true` 拒 WS 升级 (S2-OPS-011) | 难于跳动 / 故障快速冻结斶运营手动切开关 |

### 8.2 客户端处理建议

| 错误码 | 客户端动作 |
|---|---|
| nginx 403/404 | 提示「访问链接无效」，跳回首页 / 请重新从分享链接进入 |
| FastAPI 401 (换 session 阶段) | 提示「验证码过期 / 分享已失效」，跳回 OTP 页重报 |
| FastAPI 429 | 提示「频率超限，稍后重试 / 请联系客服」。客户端不应自动重试 |
| WS close 4001 / 4013 | `ShareSessionStore.clear()` + 提示「查看链接已失效」 + 重新走 OTP |
| WS close 4012 | **调用方 bug**（客户端不应发帧）。不重连，上报错日志。 |
| WS close 4014 | 提示「同时查看设备过多（限 3），请关闭其他设备后重试」，不自动重连 |
| WS close 4015 | 提示「服务临时只读，请稍后重试」，不自动重连（火度门控制，重试频率应 ≥ 30s退避） |
| WS 网络拖动 (非 close 码) | 可重连 1-2 次，加退避。超过 fallback 提示 |

### 8.3 实现点

- `ios/YiLuAn/Features/Share/Services/ShareWebSocket.swift` 的 `close code 区分处理` 逻辑已实现 (S2-INT-006 #2)，本附录是语义文档化。
- 微信端 / admin-h5 同款处理在后续实施时反向引用本附录。
- nginx 层 403 的调试路径：查看 nginx access_log + error_log；backend log 看不到 (在 nginx 就拦 了)。

### 8.4 反向引用

- S2-TEST-006R 实测发现术语含混 (刻晴)
- ADR-0036 r1 (本修订)
