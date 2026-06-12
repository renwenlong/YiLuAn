# ADR-0048 — AI 就诊准备包预算控件 + Prompt 版本化 + 双层关键词过滤

> 状态：**Accepted** · 作者：魈 · 日期：2026-06-05 · Accept 日期：2026-06-06 · r1 amend：2026-06-12 `CarryItemsSummary` 分类字典
> 关联：PRD-003 §4 S3-REQ-002 / ADR-0040 distributed circuit breaker + alertmanager / PRD-003 v0.3 §8 Q3 架构评估 + 刻晴 tester review §1 AC#8 强约束（独立 config）+ §2 AC-4 可测建议（关键词维护方）+ PRD-003 v0.2 §2.2.1 carry_items_summary 脱敏分类
> 触发：S3-REQ-002 AI 就诊准备包 / 帝君 2026-06-05 09:52 UTC v0.3 Owner Accept
> Owner Approval：**Accepted by 帝君 @ 2026-06-06 03:28 UTC**（PR #189 merge `5f7f193`；review 闭环：PM final approve + 胡桃 dev review 4+2 + 刻晴 5 补充全合）

---

## 1. 背景

PRD-003 S3-REQ-002 引入 AI 就诊准备包：基于服务档位 + 医院 + 科室 + 用户主诉，AI 生成 4 块内容（携带材料、到院前注意事项、可能问诊问题、陪诊师关注点）。

架构 §8 Q3 已拍：

1. **必须新起 AIBudgetGuard 中间件**（成本预算 + 降级 + alert）
2. **必须复用现有 LLM call layer**（不重复造）
3. **必须 trace_id 全链路**（admin 可查）
4. **必须双层禁区关键词过滤**（输入 prompt + 输出文本）
5. **PromptVersion 版本化**（git tag + db migration 双锁）

刻晴 tester review §1 AC#8 强约束：S3 AI 成本配置必须与 S2 `ai_summary_*` 分轴，避免双轴误算。

---

## 2. 选型对比

### 2.1 AIBudgetGuard 实施

| 候选 | 描述 | 评估 |
|---|---|---|
| **A. 中间件层 + 双轴配置（S2 / S3 独立）** | 新起 AIBudgetGuard，单订单 + 日成本双门限，S2/S3 独立 budget pool | ✅ 推荐 |
| B. LLM call layer 内嵌（每个 caller 自查）| 每个 AI 调用方自实现限额 | ❌ 重复代码 + 易漏 + 难调试 |
| C. 全局单门限 | S2 + S3 共享 budget pool | ❌ 刻晴强约束反对（S2 摘要短 vs S3 准备包长，单订单成本量级不同）|
| D. 不做预算控件（信任 LLM provider 限流）| 依赖 OpenAI rate limit | ❌ 成本不可控（rate limit ≠ budget），灰度可能烧穿月度 budget |

**A 推荐理由**：
1. 中间件层 = 单一职责，所有 AI 调用走同一处 budget check
2. 双轴配置 = S2 摘要 / S3 准备包独立 pool，避免互相挤占
3. 刻晴 review §1 AC#8 强约束采纳：`s3_prep_cost_per_order` 与 `s2_ai_summary_cost_per_order` 分离
4. 与 ADR-0040 alertmanager 集成 fire 告警

### 2.2 Owner 拍板：**A. 中间件层 + 双轴配置**（架构推荐，待 Owner Accept）

### 2.3 Prompt 版本化实施

| 候选 | 描述 | 评估 |
|---|---|---|
| **A. git tag + DB migration 双锁** | prompt 文件入 git + 版本号入 DB `prompt_versions` 表 | ✅ 推荐 |
| B. 仅 git tag | prompt 文件入 git，运行时按 env 读最新 | ❌ 历史订单 prompt 版本无法溯源 |
| C. 仅 DB 存储 | prompt 全入 DB，运行时按版本号查 | ❌ git diff 看不到 prompt 变更历史，code review 失效 |
| D. 写死硬编码 | 不版本化 | ❌ 无法 A/B 测试 + 历史溯源 |

**A 推荐理由**：
1. git tag = code review + 变更历史可追
2. DB `prompt_versions` 表 = 运行时按版本号查 + 历史订单 trace_id 关联确切 prompt 版本
3. 双锁 = 任一缺失 fail-fast（启动时 git tag 与 DB 校验）

---

## 3. AIBudgetGuard 设计

### 3.1 双轴配置（刻晴 review §1 AC#8 强约束 + 胡桃 dev review #2/#3）

```python
# backend/app/config.py

class Settings(BaseSettings):
    # S2 AI 摘要（已存在）— **保持现名做 BC 真源** (胡桃 review #3)
    ai_per_order_budget_yuan: float = 0.05
    ai_daily_budget_yuan: float = 50.0
    ai_summary_enabled: bool = True

    # S3 AI 就诊准备包（本 ADR 新增）— deepseek 按 ¥ 报价, 单位统一 yuan (胡桃 review #2)
    s3_prep_cost_per_order_yuan: float = 0.10       # 准备包内容更长，单价 2x S2
    s3_prep_daily_budget_yuan: float = 100.0        # 日预算独立 2x S2
    s3_prep_enabled: bool = True
    s3_prep_fallback_threshold_pct: int = 90        # 日预算用到 90% → warn + admin alert
```

**配置真源**：
- S2: **保留现有** `ai_per_order_budget_yuan=0.05` / `ai_daily_budget_yuan=50.0`，不改名，不迁移，零 BC break（胡桃 review #3）
- S3: 新增 `S3_PREP_COST_PER_ORDER_YUAN=0.10` / `S3_PREP_DAILY_BUDGET_YUAN=100.0`
- 灰度起步值（PRD §7 指标）: 单订单 ≤ ¥0.10 / 日预算 ≤ ¥100
- 灰度 1 周后按真实数据调整

**fallback threshold 状态机（刻晴补充 #4）**：

| 日预算使用率 | 状态 | 行为 |
|---|---|---|
| 0-89% | NORMAL | 正常调用 LLM |
| 90-99% | WARN | 允许调用 + fire `ai_budget_soft_warning_{axis}` admin alert |
| 100%+ | EXHAUSTED | 强制 fallback 通用模板 + fire `ai_budget_exhausted_{axis}` warning |

### 3.2 BudgetGuard 中间件

```python
# backend/app/services/ai_budget_guard.py

class AIBudgetGuard:
    """所有 AI 调用前置 check：单订单 + 日预算双门限"""

    def __init__(self, axis: BudgetAxis):  # BudgetAxis.S2_SUMMARY / S3_PREP
        self.axis = axis
        self.cost_per_order_limit_yuan = settings.get_cost_limit_yuan(axis)
        self.daily_budget_limit_yuan = settings.get_daily_budget_yuan(axis)

    def check_and_reserve(
        self,
        order_id: str,
        estimated_cost_yuan: float,
    ) -> BudgetCheckResult:
        """返回 ALLOW / FALLBACK_TO_TEMPLATE / REJECT_PERMANENTLY"""

        # 1. 单订单门限
        if estimated_cost_yuan > self.cost_per_order_limit_yuan:
            return BudgetCheckResult.FALLBACK_TO_TEMPLATE(
                reason=f"estimated cost ¥{estimated_cost_yuan} exceeds per-order limit ¥{self.cost_per_order_limit_yuan}"
            )

        # 2. 日预算门限（Redis 原子计数）
        today_spent = redis.get(f"ai_budget:{self.axis}:{today_str()}") or 0
        usage_ratio = (today_spent + estimated_cost_yuan) / self.daily_budget_limit_yuan
        if usage_ratio >= 1.0:
            fire_alert(
                alert_name=f"ai_budget_exhausted_{self.axis}",
                severity='warning',
                axis=self.axis,
                today_spent=today_spent,
                limit=self.daily_budget_limit_yuan,
            )
            return BudgetCheckResult.FALLBACK_TO_TEMPLATE(
                reason=f"daily budget exhausted: ¥{today_spent} / ¥{self.daily_budget_limit_yuan}"
            )

        # 3. 软门限（90-99%: warn + admin alert, 但不 reject）
        if usage_ratio >= 0.9:
            fire_alert(
                alert_name=f"ai_budget_soft_warning_{self.axis}",
                severity='info',
                axis=self.axis,
                usage_ratio=usage_ratio,
            )

        # 4. 预扣
        redis.incrbyfloat(f"ai_budget:{self.axis}:{today_str()}", estimated_cost_yuan)
        return BudgetCheckResult.ALLOW(reservation_id=uuid4())

    def report_actual_cost(
        self,
        reservation_id: str,
        actual_cost_yuan: float,
        estimated_cost_yuan: float,
    ):
        """LLM 调用完成后回补差额"""
        diff = actual_cost_yuan - estimated_cost_yuan
        redis.incrbyfloat(f"ai_budget:{self.axis}:{today_str()}", diff)
```

### 3.3 BudgetAxis enum

```python
class BudgetAxis(str, Enum):
    S2_SUMMARY = "s2_summary"     # S2 AI 摘要
    S3_PREP = "s3_prep"            # S3 AI 就诊准备包
    # 未来新 AI 用途加新 axis（如 S4 客服 AI、S5 ASR 转录）
```

**关键约束**：
- 不允许跨 axis budget 互调
- 新增 axis 必须更新 Settings + check 函数 + alertmanager rule

---

## 4. 双层禁区关键词过滤

### 4.1 关键词维护方（刻晴 review §2 AC-4 可测建议 + 凝光 PR #189 P1 建议）

**首批关键词列表来源**：凝光（PM）+ 医疗顾问 review（PRD-003 v0.3 §4.4 AC-4 强化）

**维护方式**：
- 落 git: `docs/medical-content/prohibited-keywords.yml`
- 版本控制：每次更新需 PR + 医疗顾问 review approve
- 运行时：backend 启动时加载 + hot reload（admin 触发）
- admin-v2 提供"关键词查看 + 命中统计"页面（仅查看不编辑）
- 真要编辑：走 PR + 医疗顾问 review，不允许 admin 后台直改

**前后端双层禁编辑（凝光 PR #189 P1）**：
- 前端：admin-v2 关键词页面 read-only UI，不渲染 edit / save 按钮（产品层禁编辑）
- 后端：不存在 `POST/PUT/DELETE /admin/ai-blocklist` endpoint（API 层禁编辑）
- 任何 admin 关键词查看操作入 audit_log：`action=ai_blocklist_viewed` + `admin_id` + `timestamp` + `category_filter`
- 防御层：即使 admin-v2 前端被绕过（curl 直调），backend 也无对应 endpoint 可改


**hot reload 时序（刻晴补充 #5）**：
- admin 触发 `POST /admin/ai-blocklist/reload` 后，所有 backend 实例必须 ≤5s 读到新版本
- 实现：Redis pub/sub topic `ai_blocklist_reload` 广播 `{version, git_commit_hash, triggered_by_admin_id, triggered_at}`
- 每个 backend 实例收到事件后重新加载 `docs/medical-content/prohibited-keywords.yml` + 更新内存版本号
- reload 成功写 metric `ai_blocklist_reload_success_total{instance=...}`；失败 fire `ai_blocklist_reload_failed` warning
- S3-TEST-002 必加 reload 时序用例：两副本 backend 同时运行，admin trigger 后 ≤5s 两副本 `/debug/ai-blocklist-version` 均返回新 version

### 4.2 双层过滤设计

```python
# backend/app/services/ai_prep_filter.py

PROHIBITED_PATTERNS = load_yaml("docs/medical-content/prohibited-keywords.yml")
# 示例:
# - category: diagnosis
#   patterns: ["诊断为", "确诊", "怀疑得了", "是否得了"]
# - category: dosage
#   patterns: ["mg", "几片", "饭前/饭后服用", "剂量"]
# - category: prescription
#   patterns: ["处方", "开药", "建议服用"]

class AIPrepKeywordFilter:
    """双层过滤：输入 prompt + 输出文本"""

    def filter_input(self, user_input: str) -> FilterResult:
        """L1: 用户主诉 / chief_complaint 入 prompt 前过滤"""
        for category, patterns in PROHIBITED_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, user_input):
                    metrics.inc(f"ai_prep_filter_l1_blocked_{category}")
                    return FilterResult.BLOCKED(
                        layer="L1_INPUT",
                        category=category,
                        pattern=pattern,
                    )
        return FilterResult.ALLOW

    def filter_output(self, ai_response: str) -> FilterResult:
        """L2: AI 返回文本过滤（防 LLM 越界生成）"""
        for category, patterns in PROHIBITED_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, ai_response):
                    metrics.inc(f"ai_prep_filter_l2_blocked_{category}")
                    return FilterResult.BLOCKED(
                        layer="L2_OUTPUT",
                        category=category,
                        pattern=pattern,
                    )
        return FilterResult.ALLOW
```

### 4.3 命中处理

```
[用户主诉 input]
       |
       v
   L1 filter check
       |
   BLOCKED ─→ 直接 fallback 通用模板 + 记录 fallback_reason=L1_BLOCKED_{category}
       |
       v ALLOW
   prompt construction + LLM call
       |
       v
   AI response
       |
       v
   L2 filter check
       |
   BLOCKED ─→ fallback 通用模板 + 记录 fallback_reason=L2_BLOCKED_{category}
       |
       v ALLOW
   写入 preparation_packages 表 + 用户可见
```

### 4.4 灰度监控指标（PRD-003 v0.3 §7）

- `ai_prep_filter_l1_blocked_total{category=...}` — L1 拦截率
- `ai_prep_filter_l2_blocked_total{category=...}` — L2 拦截率（必须很低，否则 prompt 质量需调整）
- `ai_prep_fallback_ratio` — fallback 总比例（≤ 10%，PRD §7 强化点指标）
- alertmanager rule: L2 拦截率 > 5% → warning（LLM 越界生成增多）

---

## 5. PromptVersion 版本化

### 5.1 Git 端

```
docs/ai-prompts/
  ├── s3_prep/
  │   ├── v1.0.0/
  │   │   ├── system_prompt.md
  │   │   ├── user_prompt_template.md
  │   │   └── meta.yml      # model, temperature, max_tokens
  │   └── v1.1.0/
  │       ├── system_prompt.md
  │       └── ...
```

**git tag**: `prompt-s3_prep-v1.0.0` 标定版本，PR 必须含 tag 才能 merge。

> r3 (2026-06-09)：路径从 `s3-prep` （带横杠）改为 `s3_prep` （下划线）对齐 ``BudgetAxis.S3_PREP.value``，避免 run-time 的 dash/underscore 转换逻辑。同 axis 枚举为源于一。

### 5.2 DB 端

```sql
CREATE TABLE prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    axis VARCHAR(32) NOT NULL,           -- 'S3_PREP' / 'S2_SUMMARY'
    version VARCHAR(32) NOT NULL,         -- semver
    model VARCHAR(64) NOT NULL,           -- 'gpt-4o-mini' / 'claude-3.5-sonnet'
    temperature FLOAT NOT NULL,
    max_tokens INTEGER NOT NULL,
    git_commit_hash VARCHAR(40) NOT NULL, -- 关联 git 端 prompt 文件 commit
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    activated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (axis, version)
);

CREATE UNIQUE INDEX idx_active_prompt_per_axis
  ON prompt_versions(axis, is_active) WHERE is_active = TRUE;
```

**启动时 fail-fast 校验**：

```python
# backend/app/main.py

def validate_prompt_versions_at_startup():
    """启动时校验：DB 中 is_active=TRUE 的 prompt 与 git 端文件存在 + commit hash 匹配"""
    for axis in [BudgetAxis.S3_PREP, BudgetAxis.S2_SUMMARY]:
        active_db = db.query(PromptVersion).filter_by(axis=axis, is_active=True).one_or_none()
        if not active_db:
            raise StartupError(f"No active prompt for axis={axis}")

        git_path = Path(f"docs/ai-prompts/{axis.lower()}/{active_db.version}/system_prompt.md")
        if not git_path.exists():
            raise StartupError(f"DB-active prompt version {active_db.version} missing in git: {git_path}")

        # 胡桃 dev review 细节: git_blame_commit 用 subprocess 调 `git log -n 1 -- <path>`，
        # 不引入 GitPython 依赖（避免新增 runtime dependency）。
        git_commit = git_blame_commit(git_path)
        if git_commit != active_db.git_commit_hash:
            raise StartupError(
                f"Git commit mismatch for {axis} v{active_db.version}: "
                f"DB={active_db.git_commit_hash} vs git={git_commit}"
            )
```

### 5.3 历史订单 trace_id 关联

```sql
ALTER TABLE preparation_packages ADD COLUMN
    prompt_version_id UUID NOT NULL REFERENCES prompt_versions(id);
```

**作用**：
- admin 查任意历史订单可知用了哪个 prompt 版本生成
- LLM 输出问题排查可定位到确切 prompt + model + temperature
- 灰度 A/B 测试可按 prompt_version_id 切流量

---

## 6. trace_id 全链路

### 6.1 trace_id 派生

```python
trace_id = f"ai-prep-{order_id_short}-{uuid4().hex[:8]}"
# 例: ai-prep-a1b2c3d4-ef567890
```

### 6.2 全链路传递

```
[Order created]
    │
    v (trace_id 生成)
[backend.prep.requested event]
    │
    v
[AIBudgetGuard.check_and_reserve(trace_id=...)]
    │
    v
[L1 filter (trace_id=...)]
    │
    v
[LLM call (header X-Trace-Id: ai-prep-...)]
    │
    v
[L2 filter (trace_id=...)]
    │
    v
[Save to preparation_packages (trace_id=...)]
```

### 6.3 admin 查询

```python
# backend/app/api/v1/admin/prep_packages.py

@router.get("/admin/prep-packages/{order_id}/trace")
def get_prep_trace(order_id: str):
    return {
        "order_id": order_id,
        "trace_id": ...,
        "prompt_version": ...,
        "model": ...,
        "estimated_cost_yuan": ...,
        "actual_cost_yuan": ...,
        "filter_l1_result": ...,
        "filter_l2_result": ...,
        "llm_response_raw": ...,        # 完整 LLM 原始返回
        "fallback_reason": ...,          # 如有降级
        "generation_time_ms": ...,
    }
```

---

## 7. 数据模型 + ABAC 数据访问层（PRD-003 v0.3 §4.4 AC-6 + §2.2 红线强制）

### 7.0 字段级 ABAC 投影矩阵（陪诊师不可见用户病史原文）

**红线**：PRD-003 §2.2 + AC-6 明示陪诊师端**不允许任何路径**见用户病史原文（主诉 / 可能问诊问题 / 到院前注意事项）。本节定义字段级访问控制矩阵 + API 层 ABAC 投影（PM 推方案 1）+ 单元测断言 + 集成测哨兵。

**字段级访问矩阵**：

| 字段 | 用户 | 陪诊师 | admin | 备注 |
|---|---|---|---|---|
| `id` | ✅ | ✅ | ✅ | 通用 |
| `order_id` | ✅ | ✅ | ✅ | 通用 |
| `status` | ✅ | ✅ | ✅ | 状态字段 |
| `carry_items` | ✅ | ⚠️ summary 仅 | ✅ | 陪诊师仅看脱敏摘要（条数 + 类别），不见具体内容 |
| `pre_visit_notes` | ✅ | ❌ | ✅ | **病情主诉相关，陪诊师禁见** |
| `possible_questions` | ✅ | ❌ | ✅ | **病情主诉相关，陪诊师禁见** |
| `companion_focus_points` | ⚠️ optional | ✅ | ✅ | 陪诊师专用关注点（用户可选展示）|
| `user_checked_items` | ✅ | ✅ | ✅ | 用户勾选状态（用于陪诊师协助提醒）|
| `trace_id` | ❌ | ❌ | ✅ | admin trace 专用 |
| `prompt_version_id` | ❌ | ❌ | ✅ | admin trace 专用 |
| `model` / `actual_cost_yuan` / `generation_time_ms` | ❌ | ❌ | ✅ | admin trace 专用 |
| `fallback_reason` | ❌ | ❌ | ✅ | admin trace 专用 |

### 7.0.1 API 层 ABAC 强制（PM 推方案 1）

**Endpoint 投影矩阵**：

```python
# backend/app/api/v1/users/prep_packages.py
@router.get("/users/orders/{order_id}/prep-package", response_model=UserPrepPackageView)
def get_prep_for_user(order_id: str, current_user: User = Depends(get_current_user)):
    """用户视图：全字段除 admin trace"""
    ...

# backend/app/api/v1/companions/prep_packages.py
@router.get("/companions/orders/{order_id}/prep-package", response_model=CompanionPrepPackageView)
def get_prep_for_companion(order_id: str, current_companion: Companion = Depends(get_current_companion)):
    """陪诊师视图：强制剔除 pre_visit_notes / possible_questions；carry_items 仅返摘要"""
    ...

# backend/app/api/v1/admin/prep_packages.py
@router.get("/admin/prep-packages/{order_id}", response_model=AdminPrepPackageView)
def get_prep_for_admin(order_id: str, current_admin: Admin = Depends(get_current_admin)):
    """admin 视图：全字段含 trace"""
    ...
```

**Pydantic schema 强制字段过滤**：

```python
# backend/app/schemas/prep_package.py

class _BasePrepFields(BaseModel):
    id: UUID
    order_id: UUID
    status: PrepStatus
    user_checked_items: dict

class UserPrepPackageView(_BasePrepFields):
    """用户视图：完整内容（除 admin trace）"""
    carry_items: list[CarryItem]
    pre_visit_notes: list[PreVisitNote]
    possible_questions: list[PossibleQuestion]
    companion_focus_points: list[FocusPoint]

class CompanionPrepPackageView(_BasePrepFields):
    """陪诊师视图：pre_visit_notes / possible_questions 字段不存在（schema 层硬约束）
    carry_items 仅返摘要（条数 + 类别）
    """
    carry_items_summary: CarryItemsSummary  # {total_count: int, categories: list[str]}不返具体内容
    companion_focus_points: list[FocusPoint]
    # pre_visit_notes / possible_questions / trace_* 字段在 schema 中根本不存在

class AdminPrepPackageView(_BasePrepFields):
    """admin 视图：全字段含 trace"""
    carry_items: list[CarryItem]
    pre_visit_notes: list[PreVisitNote]
    possible_questions: list[PossibleQuestion]
    companion_focus_points: list[FocusPoint]
    trace_id: str
    prompt_version_id: UUID
    model: str
    estimated_cost_yuan: Decimal
    actual_cost_yuan: Decimal
    generation_time_ms: int
    fallback_reason: str | None
```

**关键设计**：
- 陪诊师 schema **完全不包含** `pre_visit_notes` / `possible_questions` 字段 → 即使 service 层有 bug 漏过滤，Pydantic 序列化时会**直接 drop** 不在 schema 定义的字段（字段级硬约束）
- 不是 `Optional[None]`也不是空字符串 — 字段**根本不存在于响应**
- `carry_items_summary` 替代 `carry_items` 给陪诊师 = 显式 API 不对称设计（一个字段名不在另一个响应内）

**r1 amend（2026-06-12，S3-DEV-002-COMPANION-CARRY-ITEMS-SUMMARY）**：

`CarryItemsSummary` 字面定义如下：

```python
class CarryItemsSummary(BaseModel):
    total_count: int
    categories: list[str]
```

`categories` 只能使用 PRD-003 v0.2 §2.2.1 的安全展示名，按固定顺序输出：

1. `证件凭证`
2. `支付材料`
3. `就医资料`
4. `药品用品`
5. `医疗设备`
6. `日常用品`
7. `饮食补给`
8. `出行辅助`
9. `其他`

补充红线：
- `total_count = len(carry_items)`；`categories` 去重后按固定顺序输出。
- 陪诊师 response 禁止出现原始物品名、药名、器械名、疾病/症状/科室推断、单类别计数。
- 示例：`["胰岛素笔", "血糖仪", "身份证"]` → `{total_count: 3, categories: ["证件凭证", "药品用品", "医疗设备"]}`；不得出现 `糖尿病` / `胰岛素` / `血糖` 字面。
- MVP 使用确定性映射表，不调用 LLM 做分类，避免模型推断病情。

详细业务字典：`docs/design/companion-carry-items-summary-design.md`。

**Schema 变更兼容性（OpenAPI breaking change disclose，魈 PR #294 review 建议 #1）**：

本 r1 amend 把陪诊师 `prep-package` response 的 `carry_items_summary` 字段类型从 `str | None`（PR #233 临时 placeholder）改为 `CarryItemsSummary | None`（`{total_count: int, categories: list[str]}`）。这是 OpenAPI schema 上的 **breaking change**（type discriminator 从 `string` → `object`），客户端反序列化口径会变。

影响范围（必同步推三端 PR，hutao impl 时一并交付）：
- **iOS**：`CompanionPrepPackage` model 加 `CarryItemsSummary` struct，旧 `String?` 字段必删；MoshiCodable/JSON Decoder 触发。
- **wxapp（微信小程序）**：陪诊师订单详情 page data 解构必更，`{{prepPackage.carry_items_summary}}` 由字符串改对象，wxml `<text>` 渲染必拆为 `total_count` + `categories.join('、')`。
- **admin-h5**：admin 调试视图（若有）同步改。

impl 起手准入条件（PM 守门）：
- 后端 PR 必同时（同一 sprint）出三端跟进 PR（可分仓但需引用同一 task ID）
- schemathesis CI gate 跑过（`scripts/qa/openapi_contract_diff.py` 会 diff 出 type 变化并标红，需 PR description 显式 disclose）
- 三端任一端 PR 未合 → 后端 PR 不解锁灰度开关

**MVP 映射表维护方（魈 PR #294 review 建议 #2）**：

- **初版词条**：凝光（PM）out（v0 已在 `docs/design/companion-carry-items-summary-design.md` §3 + §4 落盘）
- **后续扩词 / 调整映射**：PM 主导提案 → dev/architect review → PM 双签合并；扩词 PR 不强制 ADR amend
- **加新分类（第 10 类及以上）/ 改类目排序 / 拆分既有分类**：必走 ADR amend（本 ADR 走 r2、r3…amend，PM + 架构师 + Owner 三签）
- **删词（缩窄映射）**：PM 单签可推（不影响 ABAC 红线），但需 changelog 标注
- **denylist 红线（疾病/药名/科室推断）**：PM + 架构师双签，触红线词永久不进映射 value 侧

**映射表实物 location（魈 PR #294 review 建议 #3 反驳）**：

魈建议「hardcode in Python (`carry_items_categorizer.py`)」以拿加载性能 + 单测覆盖 + git 历史。PM 反驳：

- 加载性能：模块级 `_MAPPING: dict = {...}` 单次 import 即 cache，与 hardcode 等价（无 yaml 反复解析问题）
- 单测覆盖：yaml 同样可 `yaml.safe_load` 进单测 fixture，覆盖率不受存储格式影响
- git 历史：yaml 改动 diff 比 py dict literal 更易 review，PM 可不依赖 dev 直接提 PR
- **核心理由**：PM 是维护方，yaml 让 PM 可独立扩词（不动 py 代码 = 不踩越权红线）；hardcode py 则每次扩词都要 dev 改源码，与「初版 PM own」职责矛盾

**结论**：采用 yaml + py loader 双轨：
- `docs/medical-content/carry-items-category-mapping.yml` —— PM 维护的真源
- `backend/app/services/carry_items_categorizer.py` —— dev 实装 loader（启动加载到模块级 dict，性能等价 hardcode）+ ABAC denylist 守门 + 单测 fixture 引用同一 yaml
- yaml asset-presence integration test 必加（防 ADR-0051 反案 #24 Docker COPY 漏 yml 翻车）

详细业务字典：`docs/design/companion-carry-items-summary-design.md`。

### 7.0.2 单元测断言（ABAC 字段级硬约束）

```python
# tests/api/v1/test_prep_package_abac.py

def test_companion_view_must_not_contain_pre_visit_notes(client, companion_token, sample_order):
    """陪诊师端响应**绝不能**包含 pre_visit_notes 字段（病史主诉）"""
    resp = client.get(
        f"/api/v1/companions/orders/{sample_order.id}/prep-package",
        headers={"Authorization": f"Bearer {companion_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "pre_visit_notes" not in body  # ABAC 红线
    assert "possible_questions" not in body  # ABAC 红线
    assert "trace_id" not in body  # admin 字段不外泄
    assert "carry_items" not in body  # 改为 summary
    assert "carry_items_summary" in body  # 仅摘要

def test_user_view_includes_full_content(client, user_token, sample_order):
    """用户端必须能见全内容（但不含 admin trace）"""
    resp = client.get(
        f"/api/v1/users/orders/{sample_order.id}/prep-package",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    body = resp.json()
    assert "pre_visit_notes" in body
    assert "possible_questions" in body
    assert "trace_id" not in body

def test_admin_view_includes_trace(client, admin_token, sample_order):
    """admin 端必须含完整 trace"""
    resp = client.get(
        f"/api/v1/admin/prep-packages/{sample_order.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    body = resp.json()
    assert "trace_id" in body
    assert "actual_cost_yuan" in body
    assert "fallback_reason" in body
```

### 7.0.3 集成测哨兵（防 view 跨调用穿越 + 字段集封闭检查）

```python
# tests/integration/test_prep_package_abac_sentinel.py

def test_companion_cannot_access_user_endpoint(client, companion_token, sample_order):
    """陪诊师 token 调用 /users/ endpoint 必须 403"""
    resp = client.get(
        f"/api/v1/users/orders/{sample_order.id}/prep-package",
        headers={"Authorization": f"Bearer {companion_token}"},
    )
    assert resp.status_code == 403

def test_user_cannot_access_admin_endpoint(client, user_token, sample_order):
    """用户 token 调用 /admin/ endpoint 必须 403"""
    resp = client.get(
        f"/api/v1/admin/prep-packages/{sample_order.id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403

def test_companion_view_response_field_set_locked(client, companion_token, sample_order):
    """陪诊师视图字段集是封闭集 — 防 schema 漂移引入新泄露字段"""
    resp = client.get(
        f"/api/v1/companions/orders/{sample_order.id}/prep-package",
        headers={"Authorization": f"Bearer {companion_token}"},
    )
    EXPECTED_FIELDS = {
        "id", "order_id", "status", "user_checked_items",
        "carry_items_summary", "companion_focus_points",
    }
    actual_fields = set(resp.json().keys())
    assert actual_fields == EXPECTED_FIELDS, (
        f"陪诊师视图字段集漂移! 新字段={actual_fields - EXPECTED_FIELDS}, "
        f"缺字段={EXPECTED_FIELDS - actual_fields}"
    )
```

### 7.0.4 ABAC 4 层防御（与 ADR-0046 §3.3 WORM 4 层防御同款架构）

| 层 | 防御 |
|---|---|
| 1. Schema 层 | Pydantic `CompanionPrepPackageView` 不定义 `pre_visit_notes` / `possible_questions` 字段 — 序列化时自动 drop |
| 2. Endpoint 层 | 三个独立 endpoint（`/users/` / `/companions/` / `/admin/`）+ Depends 鉴权强制角色 |
| 3. Service 层 | `get_prep_for_companion()` 内部仅 SELECT 投影到 schema 字段集（DB 层 select 列裁剪）|
| 4. 测试层 | 单元测 + 集成测哨兵（上述 §7.0.2 / §7.0.3）→ CI required |

### 7.1 `preparation_packages` 表

```sql
CREATE TABLE preparation_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL UNIQUE REFERENCES orders(id),
    status prep_status NOT NULL DEFAULT 'pending',
    -- 内容（4 块）
    carry_items JSONB,                            -- 携带材料
    pre_visit_notes JSONB,                         -- 到院前注意事项
    possible_questions JSONB,                      -- 可能问诊问题
    companion_focus_points JSONB,                  -- 陪诊师关注点
    -- 元数据
    prompt_version_id UUID REFERENCES prompt_versions(id),
    trace_id VARCHAR(64),
    model VARCHAR(64),
    estimated_cost_yuan NUMERIC(8, 6),
    actual_cost_yuan NUMERIC(8, 6),
    generation_time_ms INTEGER,
    fallback_reason TEXT,                          -- 降级原因（L1_BLOCKED / L2_BLOCKED / BUDGET_EXHAUSTED / LLM_ERROR）
    -- 用户勾选状态
    user_checked_items JSONB,                      -- 哪些 carry_items 已勾选
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE prep_status AS ENUM (
    'pending',                    -- 初始
    'generating',                  -- apscheduler cron job 持锁中
    'active',                      -- AI 生成成功
    'active_fallback_template',    -- 降级到通用模板（fallback_reason 必填）
    'generation_failed'            -- LLM error + 重试 3 次失败（不能 fallback）
);
```

### 7.2 通用模板 fixture

```yaml
# docs/medical-content/prep-fallback-template.yml
carry_items:
  - 身份证 / 医保卡 / 就诊卡
  - 既往病历本 + 检查报告
  - 现金 + 移动支付备用
  - 水杯 + 简餐（如需空腹检查）
pre_visit_notes:
  - 提前 30min 到达
  - 检查项目需空腹的请前晚 22 点后禁食禁水
  - 穿宽松衣物便于检查
possible_questions:
  - 主要症状是什么？持续多久了？
  - 之前有没有相关检查 / 治疗经历？
  - 家族病史？
companion_focus_points:
  - 协助挂号 / 缴费 / 取报告
  - 协助记录医生医嘱
  - 不替代医疗判断
```

---

## 8. 实施分阶段

| Phase | Task | Owner | 周期 |
|---|---|---|---|
| P0 | DB migration (preparation_packages + prompt_versions)  | 胡桃 | 0.25d |
| P1 | AIBudgetGuard middleware + Redis 双门限计数 | 胡桃 | 0.5d |
| P2 | 关键词清单首批 + 双层过滤 impl | 凝光 list + 胡桃 impl | 0.5d |
| P3 | Prompt v1.0.0 + 通用模板 fixture | 凝光 + 医疗顾问 review | 1d（外部依赖）|
| P4 | apscheduler cron: prep.generate + fallback 逻辑 | 胡桃 | 0.5d |
| P5 | API: order detail 加 prep_package + 用户勾选 | 胡桃 | 0.5d |
| P6 | admin-v2: prep trace 查询页 + 关键词命中统计 | 胡桃 | 1d |
| P7 | 灰度 10 单 + 质量评估 | 凝光 + 刻晴 | 1 周（业务监控）|

**总估** ~4d 实施 + 1 周灰度

---

## 9. 实施 Acceptance（魈 review 阶段硬核）

| AC | 标准 | 验证方式 |
|---|---|---|
| AC-1 | S2 / S3 budget 完全独立（互不挤占）| Redis key 隔离测 + alert metric 标签验 |
| AC-2 | 单订单超 cost limit → fallback 通用模板（不发起 LLM call）| 故障注入测 |
| AC-3 | 日预算耗尽 → 所有新订单 fallback + alert fire | budget 模拟耗尽测 |
| AC-4 | L1 拦截输入 / L2 拦截输出，均记录 fallback_reason + metric | 关键词 fuzz 测 |
| AC-5 | prompt_version DB 与 git 端 commit hash 匹配 fail-fast | 启动时校验测 |
| AC-6 | 每个 prep package 记录 trace_id + prompt_version_id + actual_cost | 历史订单查询测 |
| AC-7 | fallback_ratio ≤ 10% (灰度 1 周后)  | metric 业务监控 |
| AC-8 | 通用模板 fixture 4 块齐 + 无医疗建议字样 | content review |

---

## 10. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LLM 越界生成医疗建议（L2 漏拦）| 中 | 合规风险 | L2 命中即降级 + alert + 灰度期人工审 100 单 |
| 灰度期成本超预算 | 中 | 月度账单爆炸 | AIBudgetGuard 双门限 + 90% soft warning |
| Prompt 版本 git/DB 不同步 | 低 | 启动失败 | fail-fast 启动校验 |
| 关键词清单过严 → 大量 fallback | 中 | 用户感知 AI 不工作 | 灰度期监控 fallback_ratio + 人工调整清单（走 PR + 医疗顾问 review）|
| 关键词清单过松 → L1 漏拦危险输入 | 中 | LLM 生成危险内容 | L2 兜底 + 关键词清单定期 review（季度）|
| Redis 故障导致 budget 计数丢失 | 低 | 短期超 budget | Redis 持久化 + 启动时从 DB 重建当日累计 |

---

## 11. 相关 ADR

- **ADR-0040 distributed circuit breaker + alertmanager**（本 ADR 复用 alert fire 体系）
- **ADR-0046 contract storage extension**（兄弟 ADR）
- **ADR-0047 service contract & insurance domain**（兄弟 ADR）

---

## 12. 实施授权

待 v0.3 三签（PM/架构/测试）+ 帝君 Owner Accept → 凝光拆 S3-REQ-002 develop task → 本 ADR Accept → 凝光出关键词清单 + 医疗顾问 review → 胡桃 implement → 灰度。

---

## 13. 变更记录

- **r1（2026-06-05）**：Draft 初版，吸收刻晴 tester review §1 AC#8 强约束（S2/S3 budget 分轴）+ §2 AC-4 可测建议（关键词维护方 admin 配置 + 后端 hot reload + 凝光 list + git 版本控制）
- **r2（2026-06-05）**：吸收凝光 PR #189 business review **P0 红线**
  - §7.0 新增字段级 ABAC 投影矩阵 + API 层 ABAC 强制（PM 推方案 1）
  - §7.0.1 Pydantic schema 字段级硬约束（陪诊师 schema 完全不包含 `pre_visit_notes` / `possible_questions` 字段，Pydantic 序列化时自动 drop）
  - §7.0.2 单元测断言 ABAC 字段级硬约束（3 case：companion 不见原文 / user 见全内容 / admin 见 trace）
  - §7.0.3 集成测哨兵（companion token 访问 /users/ 必 403 / 字段集封闭检查防 schema 漂移）
  - §7.0.4 ABAC 4 层防御架构（Schema/Endpoint/Service/测试，与 ADR-0046 §3.3 WORM 4 层同款架构）
  - §4.1 admin 关键词查看页加 `ai_blocklist_viewed` audit_log + 前后端双层禁编辑（凝光 P1 建议）
- **r3（2026-06-05）**：吸收刻晴补充 #4/#5 + 胡桃 dev review #1/#2/#3/细节
  - §3.1 货币单位从 `*_usd` 统一改为 `*_yuan`（deepseek 按 ¥ 报价），并保留现有 S2 `ai_per_order_budget_yuan` / `ai_daily_budget_yuan` 作为真源，新增 `s3_prep_*` 配置实现零 BC break
  - §3.1 明示 fallback threshold 状态机：0-89% NORMAL / 90-99% WARN + admin alert / 100%+ EXHAUSTED 强制 fallback
  - 全文 `Celery` 统一改为 `apscheduler cron job`，对齐 backend 实跑依赖
  - §4.1 加 hot reload 时序：admin 触发后 ≤5s 全 backend 实例更新 + S3-TEST-002 reload 时序用例
  - §5.2 `git_blame_commit` 明示用 subprocess 调 `git log -n 1 -- <path>`，不引 GitPython runtime dependency
