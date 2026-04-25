# ADR-0028: Canary Release & Rollback Plan

- **状态:** Proposed
- **日期:** 2026-04-24
- **作者:** Arch（首席架构师）
- **相关:**
  - `docs/deployment.md`（D-037 已落地 nginx /metrics 白名单 + Prometheus scrape）
  - `docs/runbook-go-live.md`（A10/A12 上线手册）
  - `docs/MIGRATION_AUDIT_2026-04-17.md`（schema/migration 审计）
  - `deploy/prometheus/alerts.yml`（5 条告警规则）
  - 晨会决议 `Q:\OpenClaw\yiluan-standup\2026-04-24.md`（Sprint W18 议题预览）

---

## 1. 背景（Context）

YiLuAn 即将进行**首次正式上线**。Sprint W17 收尾时仍存在 5 个 Blocker（B-01 微信支付、B-02 阿里云短信、B-03 部署、B-04 HTTPS、B-05 App Store）。即使全部 Blocker 解锁，仍面临以下首发风险：

1. **真实流量未验证**：所有 e2e 用例跑在 mock provider 上，真实微信支付回调、阿里云短信回执从未在生产经过完整链路。
2. **真实并发未验证**：`/metrics` 上 24h 基线尚未采集，告警阈值都是估算值。
3. **新数据库 schema 未验证**：`alembic upgrade head` 在 staging 跑过，但生产数据规模、历史数据分布与 staging 不同。
4. **回滚链路未演练**：`docs/runbook-go-live.md` 包含上线步骤，但**没有形式化的回滚预案**与回滚演练记录。
5. **微信小程序与 iOS 客户端无法快速回滚**：客户端发版周期 3-5 工作日，一旦后端协议不兼容，必须保证后端可回滚。

晨会架构师明确：**"ADR-0028（灰度发布 / 回滚预案）应在 Sprint W18 开头补齐"**。本 ADR 即为该决议落地，目标是把"首次上线"从一个**离散事件**变成一个**可观测、可控制、可回退的渐进过程**。

---

## 2. 选项分析（Options）

我们考虑三种发布策略：

### 选项 A：全量发布 + 快速回滚

一次性把所有流量切到新版本；如出现问题，依赖镜像 tag 回滚 + alembic downgrade。

| 维度 | 评估 |
|---|---|
| 实施成本 | **低**（无需额外基础设施） |
| 回滚速度 | 流量回滚 ~2 分钟（pull 旧镜像 + restart）；DB 回滚视情况 5-30 分钟 |
| 风险 | **高** —— 100% 用户在故障窗口暴露；如果 bug 与新数据共生（写入了破坏性数据），DB 回滚后数据不可逆 |
| 基础设施 | 现有：单 region、Nginx、Docker Compose、PG 主从 |
| 适用场景 | 早期 PoC、内部工具，不适合 toC 医疗服务 |

### 选项 B：Nginx 加权灰度（**推荐**）

通过 nginx `split_clients` 模块，按 cookie 或 IP hash 把流量按百分比切到新旧两组 upstream。新旧版本**同时运行**，数据库共享同一实例（强制要求 schema 向后兼容）。

| 维度 | 评估 |
|---|---|
| 实施成本 | **中** —— 需准备 nginx 配置模板 + 双 upstream（new/stable）+ 灰度演练脚本 |
| 回滚速度 | **流量层 < 30 秒**（nginx -s reload 把权重切回 100% stable） |
| 风险 | **低** —— 渐进灰度（1% → 10% → 50% → 100%）下，故障爆炸半径可控；自动回滚条件触发时只影响新版本流量 |
| 基础设施 | 在现有 Nginx + Docker Compose 上即可实现；只需多跑 1 个新版本容器组 |
| 适用场景 | toC 服务首次上线、需要按真实流量逐步验证的场景。**与晨会"灰度发布回滚演练"测试空白区一一对应** |

### 选项 C：蓝绿部署 + Feature Flag

维护两套完整环境（蓝/绿），通过 LB 切换；新功能用 Feature Flag 控制开关。

| 维度 | 评估 |
|---|---|
| 实施成本 | **高** —— 需要两套完整资源（含 PG、Redis）、Feature Flag 服务（如 Unleash / LaunchDarkly）、CI/CD 双轨 |
| 回滚速度 | LB 切换 < 10 秒；Feature Flag 关闭瞬时 |
| 风险 | 极低（已有同流量验证），但**双环境 PG 数据同步本身是新风险源**（CDC 或双写） |
| 基础设施 | 需要 ~2 倍当前资源、新增 Feature Flag 平台 |
| 适用场景 | 中后期成熟产品、有多环境运维基线团队。**对当前 7 人虚拟团队 + 单 region 单 PG 架构过重** |

---

## 3. 决策（Decision）

**采用选项 B：Nginx 加权灰度发布。**

### 理由

1. **风险/成本比最优**：在不引入新基础设施依赖（不需要 LB 切换、不需要 Feature Flag 平台）的前提下，把"全量上线"的风险曲线削平。
2. **复用既有资产**：nginx（D-037 /metrics 白名单已就绪）、Prometheus + 5 条告警（`deploy/prometheus/alerts.yml`）、go-live runbook 都可直接对接。
3. **回滚最快**：故障时 nginx 权重 30 秒内归零，比镜像回滚快一个数量级。
4. **与上线节奏匹配**：晨会预测正式上线日可能滑到 5/2 之后，正好留出 W18 第一周准备灰度基础设施 + 演练。
5. **保留升级路径**：W19+ 如确需蓝绿/Feature Flag，可在选项 B 基础上演进，无需推倒重来。

---

## 4. 实施细节（Implementation）

### 4.1 灰度阶段

| 阶段 | 新版本流量 | 观察窗口 | 准入条件（进入下阶段） | 回滚条件 |
|---|---|---|---|---|
| Stage 1 | **1%** | 30 分钟 | 5 条告警全绿 + p95 延迟与 stable 持平（±15%） | 见 4.3 自动回滚 |
| Stage 2 | **10%** | 30 分钟 | 同上 + 业务指标（订单创建、支付回调）无异常下降 | 同上 |
| Stage 3 | **50%** | 30 分钟 | 同上 + DB 连接池、Redis QPS 无尖峰 | 同上 |
| Stage 4 | **100%** | 持续 24h | —— | 同上（24h 内仍可回滚） |

每阶段切流量后**强制等待 30 分钟**，期间值班 Ops + Backend 实时盯盘 Grafana + Alertmanager 通知通道。

### 4.2 阈值（沿用 `deploy/prometheus/alerts.yml`）

灰度期间**直接复用**已有 5 条告警，不新增：

1. `OutboundFailureRateHigh` —— 出站调用失败率 > 20% 持续 5 分钟（P1）
2. `CircuitBreakerOpen` —— 任一 provider 熔断器开路 > 1 分钟（P1）
3. `OrderCreationDrop` —— 订单创建率较 1h 前下跌 > 80% 持续 5 分钟（P1）
4. `PaymentCallbackFailureRateHigh` —— 支付回调失败率 > 10% 持续 5 分钟（P1）
5. `ReadinessProbeFailure` —— `/readiness` 失败 > 2 分钟（P0）

### 4.3 自动回滚条件

满足**任一**条件即触发自动回滚（nginx 权重归零）：

- HTTP 5xx 错误率 > **1%** 持续 **2 分钟**（新版本 upstream 维度）
- `/readiness` 探针失败（即触发上述 P0 告警 `ReadinessProbeFailure`）

实现：`ops/scripts/canary_drill.sh` 内置该判定逻辑（演练阶段以 mock 方式校验）；生产由 Alertmanager → 企业微信 webhook 通知值班 + 一段轻量 watcher 脚本执行 `nginx -s reload`。**watcher 脚本将在 W18 配合 PM 提供 webhook URL 后产出**（追踪 issue：A-2604-07）。

### 4.4 手动回滚 SLA

任何值班人员观察到下列情况，**5 分钟内**必须执行手动回滚（参见 `docs/RUNBOOK_ROLLBACK.md` 场景 A）：

- 业务指标异常但未触发自动阈值（如订单创建率下跌 50% 但未到 80%）
- 客户端用户大规模反馈（>10 起且关联同一行为）
- 任一 P1 告警持续 5 分钟未自愈

### 4.5 数据库迁移策略

**核心原则：在灰度窗口内，新旧版本必须共享同一 schema，且 schema 必须同时被新旧版本接受。**

1. **Alembic 必须可逆**：所有 `upgrade()` 必须有对应的 `downgrade()`；merge revision 例外但需 ADR-level 审批。`backend/scripts/check_migration_reversibility.py` 在 CI 跑一次硬门，分类输出可逆 / 不可逆 / 需手动验证三类。基线报告：`docs/MIGRATION_REVERSIBILITY_REPORT.md`。
2. **破坏性变更两步发布（Expand-Contract）**：
   - **Step 1（与上一版本兼容的 expand）**：仅添加新列、新表、新索引；旧版本忽略。先发布并完成灰度。
   - **Step 2（contract）**：删列、改类型、加 NOT NULL 等破坏性变更必须延迟到下个发布周期，前提是上个版本已 100% 流量稳定运行 ≥ 24h。
3. **历史基线引用**：本次首发涉及的 schema 与 enum 状态以 `docs/MIGRATION_AUDIT_2026-04-17.md` 为准（payments 4 列 + orderstatus enum 已对齐，downgrade 已实现）。
4. **灰度期间禁止裸跑 `alembic upgrade head`**：所有 migration 必须在灰度发布**前**于 staging 跑通，且生产侧由 go-live runbook 在 Stage 0（流量切换前）执行。

### 4.6 通知与值班

- 灰度上线日：Ops 主值班，Backend / Frontend / QA 各 1 人备班，PM 监盘
- 通知通道：Alertmanager → 企业微信 webhook（待 PM 提供 URL，A-2604-07）
- 灰度日志：每阶段开始/结束 / 异常事件，由 Ops 在 `docs/runbook-go-live.md` 同目录追加 `release-log-YYYY-MM-DD.md`

---

## 5. 后果（Consequences）

### 正面

- 首发风险显著降低，故障爆炸半径被压缩到 ≤ 流量百分比
- 回滚链路明确、可演练、可重复执行
- 与已有可观测性资产（Prometheus + 5 条告警 + /metrics 白名单）形成闭环
- Alembic 可逆性硬门进入 CI，长期降低 schema 退化风险

### 负面 / 成本

- 增加运维心智负担：每次发布都需要 ≥ 2 小时灰度窗口（4 阶段 × 30 分钟）
- nginx 配置复杂度上升：从单 upstream 变成双 upstream + split_clients
- 灰度期间需要双倍后端资源（new + stable 容器组并存）
- 迫使所有 schema 变更走 Expand-Contract，开发周期变长

### 风险与缓解

- **风险：cookie 分流可能导致同一用户在灰度阶段切换体验不一致**
  - 缓解：使用 cookie 持久化（`canary_bucket`，30 天有效），同一浏览器/小程序会话稳定落入同一桶
- **风险：watcher 脚本本身故障**
  - 缓解：手动回滚 SLA 5 分钟兜底；演练时验证 watcher 与手动两条路径
- **风险：灰度时新版本写入了旧版本无法解析的数据**
  - 缓解：Expand-Contract + ADR-0028 4.5 节强制要求；CI 增加协议向后兼容性检查（W18 跟进）

### 后续动作（W18+）

1. 配合 A-2604-07 落地 Alertmanager → 企业微信 webhook
2. 产出 watcher 自动回滚脚本（基于 alert webhook payload）
3. 在 staging 环境跑一次端到端灰度演练（`ops/scripts/canary_drill.sh` mock + 真实 staging 切流量）
4. 把 Expand-Contract 流程写入 `docs/WORKFLOW.md`
5. 评估 Sprint W19+ 是否需要演进为蓝绿部署（视用户规模）

---

## 6. 决议状态流转

- **2026-04-24** Proposed（本 ADR 提出）
- **TBD** Accepted（W18 演练通过 + Ops/Backend/PM 三方签署后）
- 一旦 Accepted，本 ADR 中的"实施细节"成为强制规范
