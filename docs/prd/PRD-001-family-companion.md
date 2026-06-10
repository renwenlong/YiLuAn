# PRD-001 家庭陪诊家属端 + U-1 创建订单折叠式分步交互

> Task: `S2-REQ-001` ｜ 产出人：凝光（PM）｜ 状态：**v1.1（已吸收刻晴预审 5 项必补 + 3 项建议补充，待帝君批准）**
> 帝君拍板：2026-05-28 08:02 UTC — 仅 Top1 立项
> 关联：`docs/adr/ADR-0036-family-share-authorization.md`（魈 Draft，2026-05-28）
> 战略一致性：`docs/team-handover/competitive-analysis.md` § 二

---

## 0. 一句话定位

让**异地子女**在订单生命周期内**无需注册**即可实时查看陪诊全过程，把"谁付钱"变成"谁参与"，把家属从付款工具升级为产品的第二用户。

## 1. 背景与机会

详见 `docs/review/2026-05-28-competitor-analysis.md` § 五 / D-1。一句话：所有竞品都把子女当付款工具，没人把家属做成第二用户——这是医路安能拉开身位的最大单点。

## 2. 用户与场景

| 角色 | 痛点 | 本 PRD 提供能力 |
|---|---|---|
| 下单人（子女/患者本人） | 想让远方家人知道自己/家人安全 | 一键生成分享链接发家庭群；可吊销、可查看接收回执 |
| 家属（接收分享者） | "我看不见我妈在医院发生了什么" | 微信小程序静默授权 / 外部浏览器 OTP 兜底，无需注册账号 |
| 陪诊师 | 不想被各家家属各自微信骚扰 | 无新增工作，正常服务过程即被同步 |

## 3. MVP 功能范围

### F1 家属共享入口（下单人侧）
- 订单详情新增「家属共享」按钮（订单状态 ∈ {paid, in_progress, completed} 可用）
- 点击 → 调 `POST /api/v1/orders/{order_id}/shares` → 返回 `share_token` + `share_url` → 唤起微信/iOS 系统分享
- 同页可查看 active token 列表（最多 3 个）、切换 `share_scope`、主动吊销

### F2 家属分享落地页（家属侧，无注册）
- 微信小程序内 → `wx.login` 静默授权（仅 openid，不要 phone）
- 外部浏览器 / iOS App → OTP 兜底（复用现有 Aliyun SMS Provider）
- 鉴权后调 `POST /api/v1/shares/{token}/session` 换取 `share_session` JWT（30min TTL）
- 落地后展示：陪诊师位置（地图）+ 就诊进度时间轴 + 陪诊师上传的处方/检查单缩略图 + 「今日就诊摘要」入口

### F3 实时通道
- `WS /ws/share/{token}` 首帧 `{type: "share_auth", session: "<share_session_jwt>"}`
- 鉴权通过订阅 `share:{order_id}` 单向只读 topic（复用 ADR-0031 WsPubSubBroker）
- 断线重连后立即推送 Redis cached 位置帧（`share:loc:{order_id}` TTL 60s），避免空白
- 上行写帧 server close 4012、per-token 连接 > 3 拒第 4 个（4014）

### F4 AI 今日就诊摘要
- 触发：订单 status → `completed` 后异步 enqueue（必走 `@with_scheduler_lock` 装饰器，多副本不重复扣费）
- 调用：DeepSeek `deepseek-chat`，单次成本 ≈ ¥0.005
- 成本封顶：单订单上限 ¥0.05；日预算 `AI_DAILY_BUDGET_CNY` 默认 ¥50；超出降级模板文案
- 合规：prompt 显式禁诊断/用药/剂量建议；post-check 命中 `config/ai_blocklist.yaml` 关键词触发降级
- 失败处理：不阻塞订单，dead_letter 留痕

### F5 长辈端"巨字号"模式（下单人侧）
- 个人中心 toggle（默认关）
- 开启后：全局字号 +30%、按钮 +20% 高度、低对比色升 AAA、隐藏次要功能入口
- 持久化 `users.ui_preference`，跨设备同步

### F6 一键呼叫紧急联系人（下单人侧）
- 在 active share token 名单中选定一个号码作为紧急联系人
- 巨字号模式开启时，订单详情底部常驻"一键呼叫"大按钮，调系统拨号

### F7 U-1 创建订单折叠式分步（双端统一）
- 微信小程序 + iOS 统一改造为「折叠式分步」：所有步骤同屏可见但只展开当前步骤
- 步骤：① 服务类型 ② 医院 ③ 日期 ④ 患者+陪诊师确认
- 服务类型档位（名称/价格/启用状态/排序）由后端动态提供（`GET /api/v1/public/service-packages`），admin 可增删改、价格变更仅影响新订单（历史订单下单时快照不漂移）——详 ADR-0043
- 已完成步骤显示结果且可点击回改；回改后下游步骤数据不重置（除非冲突）

## 4. 跨端字段对齐（来源 ADR-0036 §2.7，严格一致）

| 字段名 | 类型 | 后端来源 | 出现位置 | 备注 |
|---|---|---|---|---|
| `share_token` | string(32) URL-safe | `OrderShareToken.token` | 下单人「家属共享」面板 | 短链 token，UNIQUE |
| `share_url` | string | 后端拼接 | 同上 | `https://m.yiluan.cn/s/{token}` |
| `share_scope` | enum (`full`/`progress_only`) | `OrderShareToken.share_scope` | 下单人可切换；家属只读 | 默认 `full` |
| `share_expires_at` | datetime ISO8601 | `OrderShareToken.expires_at` | 双端展示 | 完成 +24h，硬上限创建 +7d |
| `share_revoked_at` | datetime? | `OrderShareToken.revoked_at` | 吊销后立即返回 | - |
| `share_session` | string(JWT) | 后端签发 | 家属端 sessionStorage | TTL 30min |
| `share_active_count` | int | 聚合 `count(active tokens)` | 下单人面板 | 硬上限 3 |

### 4.1 REST 端点（来源 ADR-0036 §2.7）

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/orders/{order_id}/shares` | 创建分享 token |
| `GET` | `/api/v1/orders/{order_id}/shares` | 列当前 active tokens |
| `DELETE` | `/api/v1/orders/{order_id}/shares/{token_id}` | 吊销 |
| `POST` | `/api/v1/shares/{token}/session` | 家属端用 token+openid/otp 换 share_session JWT |
| `GET` | `/api/v1/shares/session/order` | 家属端用 share_session 拉只读订单视图 |
| `WS` | `/ws/share/{token}` | 家属端实时通道 |

## 5. PII 脱敏（来源 ADR-0036 §2.5）

| 字段 | 家属端可见 | 备注 |
|---|---|---|
| 患者姓名 | 仅首字 + ** | 「张**」 |
| 患者电话 | ❌ | 紧急时下单人转 |
| 患者身份证 | ❌ | - |
| 病情描述/medical_notes | ❌（即使 scope=full） | - |
| 陪诊师姓名 | ✅ 完整 | - |
| 陪诊师电话 | ❌ | 客服转接 |
| 陪诊师实时位置 | ✅ (lat,lng,精度) | 仅 in_progress 状态 |
| 处方/检查单照片 | ✅ 原图（OSS 预签名 URL 15min TTL） | scope=full 给 |
| AI 摘要文本 | ✅ 已 LLM 脱敏 | - |

## 6. Acceptance（刻晴预审，强制覆盖 ADR-0036 §3.5 + §3.6）

### 6.A 功能 acceptance（13 条）

1. 下单人 `POST /api/v1/orders/{order_id}/shares` 3 秒内返回 share_token + share_url
2. 单订单 active token > 3 时，新建第 4 个自动 revoke 最老的，返回值标识被替换的 id
3. 下单人 `DELETE` 吊销后，所有持该 share_session 的 WS 立即被服务端 close 4013
4. 家属点击链接首次加载 **P95 ≤ 2s、P50 ≤ 1.2s**（4G 网络）
5. WS 鉴权成功后**立即推送 Redis cached 位置帧**；断线 10s 重连位置点不空；**断线 60s+ （cached 过期）重连显示 UI 提示"位置缓存过期，等待陪诊师下次上报"不悬空旧点**；E2E 覆盖两档（10s / 90s）
6. 陪诊师位置每 30s / 200m 触发 publish，不落库（PII 留痕最小化）
7. 处方/检查单走 OSS 预签名 URL（15min TTL），不暴露 OSS 直链
8. AI 摘要单订单成本 ≤ ¥0.05，日预算 ¥50 超限自动降级模板文案
9. AI 摘要 prometheus counter `ai_summary_cost_cny_total` 上报准确
10. AI 摘要 job 必须通过 `@with_scheduler_lock`，多副本部署下重复触发只扣 1 次费
11. 巨字号模式开启后 P0/P1 页面无文字溢出/截断；跨设备登录 1 次拉取同步
12. 紧急联系人呼叫调系统拨号成功率 100%（不依赖网络）
13. U-1 折叠式分步：微信和 iOS 步骤数、字段、文案完全一致；已完成步骤回改下游数据保持

### 6.B 安全 negative（来源 ADR-0036 §3.5，**`pytest -m share_security` 入 release gate**）

14. 过期 share token → 401
15. 已 revoke 的 token → 401，且已建立的 WS 连接服务端主动 close 4013
16. 跨订单 token（A 订单 token 拉 B 订单数据）→ 403
16b. **IDOR fuzz**：anitanyc share_session JWT 拼接其他 token / 替换 order_id 路径参数 / openid 复用 这 3 类越权组合全部 403
17. 同 token **24h 滚动窗口内** distinct openid > 5 → 告警 metric + 自动 revoke（避免跨 7d 慢累积误杀家庭聚会场景）
18. share_session JWT 篡改 / 过期 / `alg=none` → 401
19. WS 上行写帧 → close 4012，不广播、不落库
20. per-token 连接数 > 3 → 拒第 4 个（4014）
21. `scope=progress_only` 拉影像/AI 摘要 → 403
21b. **OTP 兑底链路负向测试**（F2 外部浏览器/iOS App 路径）：同号 1min 1 次 / 1h 5 次频控；错 5 次锁 10min 爆破防护；用过即作废复用拒绝；全部入 `pytest -m share_security`
21c. **OTP 成本/粒度反滥用**（魈补充）：单 token / 24h ≤ 5 次发码；单手机号 / 1h ≤ 3 个不同 token 绑定；超限转人工；同样入 `pytest -m share_security`

### 6.C 跨端契约 / develop done 门槛（来源 ADR-0036 §3.6，刻晴反馈改硬门槛）

22. 后端 CI：导出 OpenAPI schema → diff 上次基线 → **diff 涉及 § 4 七字段名/类型/必填性任意变更 → CI fail，必须 ADR 修订 + 双签放行**，不留人工放行口
23. 微信端 CI：`openapi-typescript` 生成 d.ts 校验 `services/*.js` 对 7 个字段引用
24. iOS CI：`APIEndpointTests` 扩展所有新模型反序列化断言（缺一个字段 fail）
25. 三端任一漂移 → 直接打回 develop task，不进 review

### 6.D AI 合规 post-check（来源 ADR-0036 §2.6）

26. `config/ai_blocklist.yaml` 关键词词典命中 → 输出降级为模板文案
27. 边界用例（如"建议**休息**"）不命中、不误降
28. 词典热更新生效（不重启服务）
29. AI post-check 单测覆盖率 = 100%（命中/边界/热更新三类必含）

### 6.E PRD 评审

30. 刻晴预审 acceptance 通过；魈 ADR-0036 已 Accepted；帝君拍板 → 三签齐才进入 develop

### 6.F 补充性 acceptance（刻晴建议补充项，非阻塞）

31. AC#11 巨字号测试基准：PM 提供 P0/P1 页面清单 ≥10 个，每页跑视觉回归对比基线（清单随 PRD 交付附件交刷晴）
32. AC#9 prometheus `ai_summary_cost_cny_total` **含异常分支（请求失败/超时/降级）也必须计数**，避免只测 happy path
33. AC#12 紧急联系人：**调起拨号面板成功率 100%**；**接通率不在产品 SLA 内**（避免线上数据被错误归因）

### 6.G P0/P1 页面清单（巨字号视觉回归基线）

MVP 巨字号模式应覆盖以下 12 个页面无文字溢出/截断：
1. `pages/patient/home`（患者首页）
2. `pages/patient/create-order`（创建订单 U-1 折叠式）
3. `pages/patient/order-detail`（订单详情）
4. `pages/patient/pay-result`
5. `pages/orders`（我的订单）
6. `pages/chat/room`
7. `pages/notification`
8. `pages/profile`
9. `pages/profile/settings`（巨字号 toggle 所在页）
10. 【家属共享】面板（F1）
11. 【一键呼叫紧急联系人】按钮页（F6）
12. 【今日就诊摘要】展示页（F4）

iOS 对应视图同名覆盖。视觉回归基线附在 P1-09 iOS 测试体系中交付。

## 7. 不做（MVP 外）

- 家庭账号体系 / FamilyMember 合并（见 ADR-0036 §5 Follow-up）
- 家属反向下单
- 家属与陪诊师即时聊天（仅查看，避免管理混乱）
- 医保卡共享
- 多语言（仅简中）
- 保险兜底 / 电子合同（Top2 押后，已与魈对齐不入 ADR-0036）
- AI 报告解读（Top3 押后）

## 8. 排期

- W19：本 PRD 定稿 + ADR-0036 Accepted + 刻晴预审 acceptance + 帝君拍板
- W20 拆分（供甘雨排板）：
  - **D1-D3 后端 freeze**：OrderShareToken 模型、REST 端点 6 个、WS topic、OpenAPI schema baseline、调度锁 + AI 封顶骨架
  - **D4-D10 三端并行联调**：后端完成全量接口 + 微信小程序 + iOS 同步实现；U-1 折叠式分步双端启动
  - **D11-D14 灰度**：10% 患者订单，监控 AI 成本 / 分享转化率 / per-token distinct openid 分布
- W22：复盘决定 Top2/Top3 是否启动（`BACKLOG-TOP23-OBSERVE`）

## 9. 风险（PRD 视角，技术风险见 ADR-0036 §4）

| 风险 | 缓解 |
|---|---|
| 处方图片含敏感信息脱敏不完整被外泄 | OCR + 人工抽检 5%；上线前法务过隐私条款；OSS 预签名 URL 15min TTL |
| AI 摘要"幻觉"误导用户 | UI 顶部固定"AI 生成仅供参考"免责；post-check 关键词双护栏；陪诊师手动覆盖入口列入 V1.1 |
| 分享 token 群里被转发到非家属 | 默认 7d hard cap + 下单人可吊销 + distinct openid > 5 告警自动 revoke；链接即权限不强权限 |
| 折叠式分步在小屏 iPhone SE 上拥挤 | 设计阶段出 320/375/414 三档稿；真机测 |
| 微信 jscode2session 频控 | 依赖 W19-03（P0-04 outbound 装饰器修复）；监控 outbound 池容量 |

### 硬依赖声明（release gate 级别）

- **P0-04 outbound 修复不收口，F2 不进灰度**（魈 + 刻晴双签认可）
- **`pytest -m share_security` 与 `pytest -m money_safety` 同级入 release gate**，任一失败禁上线
- §6.C 跨端契约 AC#22-25 为 develop done 客观条件，不留人工放行口

---

## 附

- ADR：`docs/adr/ADR-0036-family-share-authorization.md`（魈 Draft 2026-05-28）
- 战略文档：`docs/team-handover/competitive-analysis.md` § 二
- 历史决策：帝君 2026-05-28 08:02 UTC（仅 Top1 立项）
- v0.1 / v1.0 历史版本：git 历史可查

## 附 B：Review 意见追溯（v1.0 预审 → v1.1 修订）

### 刻晴 review（8 项全采纳）

| Review 点 | 处置 | 反映 |
|---|---|---|
| 1. AC#5 断线门槛偏弱 | ✅ 采纳 | 加 60s+ UI 提示 + 90s E2E |
| 2. AC#16 IDOR fuzz | ✅ 采纳 | 新增 AC#16b |
| 3. AC#17 distinct openid 缺时间窗 | ✅ 采纳 | 明定 24h 滚动窗口 |
| 4. AC#22 OpenAPI diff 软门槛 | ✅ 采纳 | 改硬门槛 CI fail + ADR 修订 + 双签 |
| 5. F2 OTP 路径负向测试 | ✅ 采纳 | 新增 AC#21b |
| 6. 巨字号页面清单 | ✅ 采纳 | 新增 §6.G 12 页清单 + AC#31 |
| 7. AC#9 异常分支计数 | ✅ 采纳 | AC#32 明写 |
| 8. AC#12 拨号语义 | ✅ 采纳 | AC#33 调起拨号面板成功率 vs 接通率 |

### 魈 review（1 补充 + 3 微调 全采纳）

| Review 点 | 处置 | 反映 |
|---|---|---|
| 1. F2 OTP 成本/粒度反滥用（1 token/24h≤5 / 1 手机/1h≤3 token） | ✅ 采纳，与刻晴 AC#21b 双维并存 | 新增 AC#21c |
| 2. §8 W20 排期拆 D1-D3/D4-D10/D11-D14 | ✅ 采纳 | §8 重写 |
| 3. AC#4 加 P95/P50 分布约束 | ✅ 采纳 | P95≤2s / P50≤1.2s |
| 4. §9 P0-04 硬依赖前置声明 | ✅ 采纳，刻晴加票 | §9 新增「硬依赖声明」块 |

**红线双签确认**：
- P0-04 outbound 修复不收口 → F2 不进灰度（魈+刻晴）
- `pytest -m share_security` = `pytest -m money_safety` 同级 release gate
- §6.C AC#22-25 为 develop done 客观条件，不留人工放行口

---

## 附 C：帝君报批与补充（2026-05-28 08:29 / 08:31 UTC）

### C.1 帝君报批

- 08:29 帝君对 PRD-001 v1.1 表态「带补充批」
- PM 先 `set_status done`，依甘雨流程纠偏将两条补充走 patch task `S2-REQ-002` 落地（v1.1 已 done 不可回退）

### C.2 帝君补充意见（两条全采纳）

**补充 1：AI 预算灰度后复评**
- ¥0.05/订单 + ¥50/日 是灰度 10% 默认值
- 正式放量前按灰度实际成本数据复评后再调
- 已在 §3 F4 章节增加备注

**补充 2：灰度退出标准写死并报备 → §8.1**

| 阈值 | 观察窗口 | 退出动作 |
|---|---|---|
| 核心 5xx 错误率 > **2%** | 连续 30min | 立即回滚（关闭 F2 入口，已发 token 保留 read-only） |
| share token 滥用率（`distinct_openid_revoke_total / shares_created_total`） > **5%** | 连续 2h | 立即回滚 |
| AI 摘要降级率（成本超限 + post-check 命中 + provider 失败 合计） > **20%** | 连续 4h | 立即回滚 |

**重启灰度的逆向验证条件**（满足才能重新放量）：
- 5xx 错误率回落 ≤ 0.5% 且稳定 6h
- token 滥用率 ≤ 1% 且稳定 12h
- AI 降级率 ≤ 5% 且成本在预算内

**阈值定义者**：凝光（PM）
**报备途径**：本文档 + 群聊同步 + Prometheus alert rule 入仓
**报备时间**：2026-05-28（patch 落地时）

### C.3 流程纠偏认账

甘雨指出：「带补充批」≠「先 done 再补」，应当走 v1.2 patch task 而不是覆盖 v1.1 已 done 文档。**认账**。今后 Owner「带条件批」「带补充批」等含追加要求的批准，应该：
1. 先 done 已对齐部分（避免阻塞下游）
2. 立即起 patch task（保留追溯链）
3. patch task acceptance 含「群里报备 Owner」

## 附 D：F8 灰度安全 / read-only UX 文案规范（S2-PRD-016）

> 关联：ADR-0053 §7/§8、`S2-OPS-A-METRIC-DASHBOARD-READONLY` design PR #248、`S2-PRD-016-READONLY-UX-COPY`。  
> 原则：**backend 不向前端返回内部 reason 原文**；前端只根据 `reason_category` 映射产品文案，避免泄露灰度、凭据、安全、举报方等敏感信息。

### D.1 API 错误码与响应结构

read-only 用户访问写操作（POST/PUT/PATCH/DELETE）时，后端返回：

| 字段 | 值 | 说明 |
|---|---|---|
| HTTP status | `403` | 读取操作 GET 不受影响 |
| `error_code` | `USER_READONLY` | 三端统一识别只读状态 |
| `reason_category` | `GRAY_REVOKE` / `GRAY_ANOMALY` / `CREDENTIAL_LEAK` / `COMPLIANCE_REPORT` | 产品文案枚举，非后端原始 reason |
| `message` | 可选通用兜底文案 | 前端优先使用 i18n key，不依赖后端自由文本 |

禁止返回：灰度 region、内部扫描器命中细节、凭据泄露判定细节、举报人或举报内容、管理员内部备注、`reason_detail` 原文。

### D.2 UX 文案 4 场景分级

| 场景 | `reason_category` | 标题文案 | 说明文案 | 行动入口 |
|---|---|---|---|---|
| mock 灰度 revoke | `GRAY_REVOKE` | 账户进入只读模式 | 请重新登录后继续操作。 | 重新登录 |
| real 灰度异常 | `GRAY_ANOMALY` | 服务异常，账户暂时只读 | 当前服务正在恢复中，请稍后重试；如持续出现，请联系客服。 | 稍后重试 / 联系客服 |
| 真凭据泄露 / 安全事件紧急吊销 | `CREDENTIAL_LEAK` | 为保障账户安全，账户已切换为只读模式 | 为保护您的账户与订单信息，部分写操作已临时限制。请联系客服处理。 | 联系客服 |
| 合规举报 / 单用户合规只读 | `COMPLIANCE_REPORT` | 账户当前处于只读模式 | 详情请联系客服。 | 联系客服 |

### D.3 三端 i18n key 规范

三端（iOS / wxapp / admin-h5）统一使用以下 key 形态：

```text
error.readonly.<reason_category>.title
error.readonly.<reason_category>.description
error.readonly.<reason_category>.action
```

示例：

```text
error.readonly.CREDENTIAL_LEAK.title = 为保障账户安全，账户已切换为只读模式
error.readonly.CREDENTIAL_LEAK.description = 为保护您的账户与订单信息，部分写操作已临时限制。请联系客服处理。
error.readonly.CREDENTIAL_LEAK.action = 联系客服
```

### D.4 客服联系入口

当 `reason_category` 为 `CREDENTIAL_LEAK` 或 `COMPLIANCE_REPORT` 时，三端必须展示联系客服入口，并至少提供以下通道之一；平台配置齐全后展示三通道：

1. 客服微信
2. 平台在线表单
3. 客服电话

客服入口文案保持中性，不指责用户，不暗示用户违规，不披露举报方或内部安全判断。

### D.5 监控 reason label 与 UX reason_category 映射

PR #248 metric design 的 monitoring `reason` label 是监控统计口径；本节 `reason_category` 是用户体验口径。两者映射如下，避免 frontend / backend / 监控三方 enum drift：

| monitoring reason label | UX `reason_category` | 说明 |
|---|---|---|
| `credential_leak` | `CREDENTIAL_LEAK` | 安全事件，用户只看到安全保护文案 |
| `compliance_report` | `COMPLIANCE_REPORT` | 合规只读，用户只看到联系客服文案 |
| `admin_kick` | `GRAY_REVOKE` | mock/人工灰度 revoke 场景 |
| `auto_scanner` | `GRAY_ANOMALY` | real 灰度异常或自动扫描器触发 |
| `user_request` | 不展示 read-only 文案 | 用户主动登出/撤销，不属于 read-only UX 场景 |

### D.6 业务边界守则

- 不诊断用户风险，不写“您的账号异常/违规”等指责性措辞。
- 不暴露后端技术细节，例如 region、token_version、scanner、Redis、灰度批次。
- 不透露举报方、举报内容、内部客服备注或安全调查结论。
- 不把 read-only 描述为永久处罚；统一表述为“当前 / 暂时 / 临时限制”。
- GET 读取不受影响；仅写操作受限。
