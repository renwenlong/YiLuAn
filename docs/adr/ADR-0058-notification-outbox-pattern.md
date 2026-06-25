# ADR-0058: 通知 Outbox 模式（事务一致性 + 可靠投递）

- **状态**: Accepted（帝君 2026-06-25 拍板立项，override 架构师 deferred 建议——见 §0 风险声明）
- **日期**: 2026-06-25
- **决策者**: 魈（架构师，技术方案），凝光（PM，业务骨架），帝君（立项授权）
- **关联**: S3-ARCH-OUTBOX-PATTERN（develop/P2）/ BACKLOG-OUTBOX-PATTERN（原 backlog，本 ADR 升格）/ ADR-0026（外呼可靠性装饰器）/ ADR-0032（资金对账）/ ADR-0035（scheduler-lock）/ code-walkthrough.md（notification.py 拆 outbox 建议）

---

## 0. ⚠️ 架构师风险声明（说一次，记录在案）

原 `BACKLOG-OUTBOX-PATTERN` 的触发条件是「Top1 上线后通知失败率 > 0.5% 或资金通知阻塞主事务被告警」。**当前 Top1 未真上线（REAL-LAUNCH 仍 not-started），该阈值无真实数据**。我（架构师）06-24 曾建议 deferred，理由：

1. **设计参数缺真实数据校准**：重试退避曲线、最大重试次数、死信阈值、sweeper 频率，理想应按真实失败模式（失败率分布、失败类型、恢复时间）定。无真流量 → 这些参数只能按经验拍，后续可能要调。
2. **当前主事务通知未实测出过问题**：premature optimization 风险。

**帝君已 override 立项**——这是帝君的决定权。本 ADR 据此执行，但**设计上做防御**：所有可调参数走配置（feature flag + env），上线后按真实数据校准，不写死。AC-7 要求 feature flag 隔离 + 可一键回退旧同步路径，正是为应对"参数需调"。

**本 ADR 的价值（即使提前做也成立的部分）**：notification.py 同 session 污染主事务 commit 是**结构性缺陷**（不依赖流量大小），事务一致性（G1）是确定性正确改进，与流量无关。可靠投递（G2）的参数才依赖真实数据。

---

## 1. 痛点（evidence-first，引 repo 实证）

- `notification.py`：通知 `create_notification` 与业务事务在同一 DB session。`code-walkthrough.md` 明确："通知触发与业务事务在同一 session，长链路通知失败会污染主事务 commit—— 应拆 outbox"。
- `dead_letter.py`（已有 `record_dead_letter` + `app/api/v1/admin/dead_letters.py` 查询）：**只落库无 retry worker**——死信不自动重投。
- `ADR-0032` / `incremental.py`：当前仓库**无 outbox/event-bus**，对账线用 in-process queue + sweeper 临时方案。
- `idempotency.py`（`IdempotencyKey` 表）：API 入口幂等，**非**投递层去重（层次不同，见 §2 决策 C）。

---

## 2. 技术决策点与方案对比（架构师拍板）

### 决策 A：outbox 落地形态——DB table vs Redis Streams/Kafka？

| 方案 | 优 | 劣 |
|---|---|---|
| **A1 DB outbox table + sweeper** ✅ | 与业务事务同 DB → 天然支持「同事务原子写入」(G1 核心); 复用现有 Postgres, 零新基础设施; 与 ai_summary_enqueue outbox-lite 同模式 (团队已熟); ADR-0032 对账也想要同款 → 可复用 | sweeper 轮询有延迟 (秒级, 通知场景可接受); 高吞吐时 DB 压力 (当前流量远未到) |
| A2 Redis Streams | 低延迟; 高吞吐 | ❌ Redis 与业务 DB 非同事务 → G1 原子性破 (需额外 2PC 或 transactional outbox 仍要 DB 兜底); 引入新可靠性面 |
| A3 Kafka | 工业级吞吐/持久化 | ❌ 重型基础设施, 当前团队无 Kafka 运维; 严重过度工程 (PM 非目标已明确"不强制 MQ") |

**决定：A1 DB outbox table + sweeper**。G1 事务一致性要求 outbox 写入与业务事务**原子**——只有同 DB 同事务能天然保证。Redis/Kafka 跨存储破原子性。且当前流量远未到 DB outbox 瓶颈，引入 MQ = 过度工程。

### 决策 B：投递 worker——复用 ai_summary_enqueue.py outbox-lite vs 新建？

| 方案 | 决定 |
|---|---|
| **复用 ai_summary_enqueue.py 的 scheduler-lock + batch 模式** ✅ | 该模式已验证: `acquire_scheduler_lock` 防多副本重复消费 (ADR-0035 §3 red line) + batch size 限单轮占锁时长 + 唯一约束幂等 enqueue。outbox worker **照搬此架构**: 新建 `notification_outbox_worker.py`, 整段包 scheduler-lock, 每轮捞 N 行 pending outbox 投递。**不是复制代码而是复用模式**——通知 outbox 与 AI digest 是不同 domain, 各自独立 worker, 但 worker 骨架 (lock+batch+幂等) 同构。 |

### 决策 C：幂等——复用 idempotency.py（IdempotencyKey 表）？

**不复用**。`IdempotencyKey` 表是 **API 入口幂等**（user_id + endpoint + key），层次是"防客户端重复提交请求"。outbox 投递幂等是"防同一通知投递多次"，层次不同。

**决定**：outbox 表自带 `event_dedup_key` 唯一约束（业务事件 → outbox 行 1:1，重复 enqueue 同事件被唯一约束挡）。投递侧用 outbox 行的 `status` 状态机（pending→delivering→delivered/failed）+ 乐观锁防并发投递。**投递目标侧**（如推送服务）若需端到端幂等，由 outbox 行 id 作幂等键传给下游。

### 决策 D：死信——复用 dead_letter.py vs 扩展 retry worker？

**复用 + 扩展**。`dead_letter.py` 的 `record_dead_letter` + admin 查询 endpoint 直接复用（超最大重试的 outbox 行 → `record_dead_letter`）。**缺的 retry worker 本 ADR 补**：outbox worker 本身就是 retry 引擎（pending/failed 行按退避重投，超阈值才进死信）。所以不是给 dead_letter 加 retry，而是 outbox worker 承担重试，dead_letter 只接终态。

### 决策 E：是否升格独立 ADR？

**是，本 ADR-0058**。原 BACKLOG 只在 PRD-002-003 提名，无独立设计。outbox 是结构性架构改造，需独立 ADR 沉淀决策。

---

## 3. 设计概要（给 design/develop task 细化）

### 3.1 outbox 表 schema（草案，develop 阶段细化）

```
notification_outbox:
  id            UUID PK
  event_dedup_key  TEXT UNIQUE NOT NULL  -- 业务事件唯一键 (防重复 enqueue)
  payload       JSONB NOT NULL           -- 通知内容快照 (user_id/type/title/body/target...)
  status        ENUM(pending,delivering,delivered,failed,dead) NOT NULL DEFAULT pending
  retry_count   INT NOT NULL DEFAULT 0
  max_retries   INT NOT NULL DEFAULT <config>
  next_retry_at TIMESTAMPTZ              -- 退避调度
  last_error    TEXT
  created_at    TIMESTAMPTZ NOT NULL
  delivered_at  TIMESTAMPTZ
  -- index: (status, next_retry_at) 供 worker 高效捞 pending/到期 failed
```

### 3.2 写入路径（G1 原子性）

业务 service 在**业务事务内**调 `enqueue_notification_outbox(session, event)` → INSERT outbox 行（status=pending）。业务事务 commit → outbox 行与业务数据**同事务落库**。业务回滚 → outbox 行也回滚（AC-1）。**关键**：enqueue 不发通知，只写表。

### 3.3 投递路径（G2/G3 异步可靠）

`notification_outbox_worker`（复用 ai_summary_enqueue 架构）：
1. 整段包 `acquire_scheduler_lock`（防多副本）
2. 捞 `status=pending OR (status=failed AND next_retry_at<=now)` 的 N 行
3. 逐行：status→delivering（乐观锁）→ 调实际投递（现有 notify_* 通道）→ 成功 delivered / 失败 retry_count++ & 算 next_retry_at（指数退避）
4. retry_count >= max_retries → status=dead + `record_dead_letter`（复用 dead_letter.py）

### 3.4 feature flag 隔离（AC-7 + §0 风险防御）

`NOTIFICATION_OUTBOX_ENABLED`（env，默认 False）：
- False → 走旧同步 `create_notification`（当前行为，零变更）
- True → 走 outbox 路径

可一键回退。退避/重试/sweeper 参数全走 config，上线后按真实数据校准（§0）。

---

## 4. 实施拆解（develop task 候选）

| 子任务 | 内容 |
|---|---|
| **DEV-1 outbox 表 + model** | migration + SQLAlchemy model + enqueue helper（事务内写入） |
| **DEV-2 outbox worker** | notification_outbox_worker.py（复用 ai_summary_enqueue scheduler-lock+batch）+ 退避重试 + 死信对接 |
| **DEV-3 业务接入 + feature flag** | notification.py 各 notify_* 点改为 enqueue（flag True 时）+ flag 隔离 |
| **TEST** | 对应 test task：AC-1~8 全覆盖（原子性/隔离/重试/死信/非阻塞/不回归/可回退/技术层） |

> develop 阶段需 PM 凝光据本 ADR 补 AC-8（技术层验收）。

---

## 5. 后果

### 正面
- G1 事务一致性：结构性缺陷修复（与流量无关的确定性改进）
- G2/G3：可靠投递 + 异步解耦，复用现有 scheduler-lock/dead_letter 基础设施，新增面最小
- feature flag 隔离 → 零风险灰度 + 可回退

### 负面 / 权衡（§0 已声明）
- 投递参数（退避/重试/死信阈值/sweeper 频率）当前按经验拍，需真上线数据校准（已走 config 防御）
- sweeper 轮询秒级延迟（通知场景可接受）
- premature 风险：当前主事务通知未实测出问题；但 G1 部分即使提前做也正确

### 后续
- 上线后按真实失败数据校准投递参数
- ADR-0032 对账线可复用本 outbox 基础设施（同 DB outbox 模式）
