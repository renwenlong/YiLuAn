# S3-PRD-001-V12-F8-RECOMMENDATION-FILTER-SPEC — PRD-001 §F8 推荐过滤 spec v1 final

> Owner: 凝光（PM）
> 关联 task: `S3-PRD-001-V12-F8-RECOMMENDATION-FILTER-SPEC`（design / P2 / PM own）
> 触发: 魈 11:30 UTC sessions_send + 刻晴 S3-TEST-006 PR #272 evidence-first verify PR #270 缺口
> 起 spec 时间: 2026-06-11 11:50 UTC
> v1 final 时间: 2026-06-11 14:08 UTC（吸收魈 review approve + 3 拍板）
> 架构师 review: 魈 14:05 UTC sessions_send approve — 7 项 section 全 ✅ pass
> Lock 条件: 帝君 Owner Accept（业务措辞 #3/#4 + 整体 spec）→ 合入 PRD 主文档 v1.1 → v1.5 patch

## v1 draft → v1 final changelog

- §1.2/§2.1/§4 字段集 align：`recommended` / `recommendation_rank` / `total_eligible` / `filtered_uncertified_count` 4 字段归 `COMMON_FIELDS_WHITELIST`（魈拍 B，理由：endpoint envelope 元数据 ≠ 跨域字段族，加前缀会污染 ADR）
- §2.2 全列表 endpoint 排序行为锁定 (a)：跟推荐 endpoint 一致 verified > pending_supplement > uncertified + tie-breaker (rating DESC, completed_orders DESC, created_at ASC)（魈拍 a，理由：一致性 > 灵活性，前端两个 endpoint 排序逻辑统一）
- §2.1 endpoint URL 锁定 `GET /v1/companions/recommendations`（魈 ratify，与 11:30 UTC 拍板一致）
- §0 fact-check 追加 spec drift 归责注脚：魈 own 自己 11:30 UTC sessions_send 写「PRD-001 v1.2 §F8」是 spec drift，trust 了 ADR-0046 §3.5 r2 内 reference 而未 verify 主 PRD 头部 status line
- §5 6 未决 → 5 项已答（魈 #1/#2/#5 + PM 自决 #6），剩 #3/#4 等帝君业务措辞
- §6 主 PRD patch 版本号锁定 v1.5（跳过 v1.2/v1.3/v1.4，commit msg 内 changelog 写明历史 reference 但 0 patch 的事实）

---

## 0. fact-check 实证

PM 起手 verify：
1. **PRD-001 主文档** `docs/prd/PRD-001-family-companion.md` 当前是 **v1.1**（line 3 状态字面）
2. **§F8 资质透明度 spec** 在主 PRD **完全不存在**（grep `^##`/`^###` 0 hit）
3. **PM checklist v1** (`docs/qa/s3-prd-001-004-pm-business-acceptance-checklist-v1.md`) 引用「PRD-001 v1.4 §F8」
4. **ADR-0046 §3.5 r2** 已锁 `companion_cert_*` 第 4 域前缀（line 288）
5. **6 处文档** 引用 PRD-001 v1.2/v1.4 §F8 spec：design/qa/yml/adr/review

**结论**：PRD-001 v1.2 (魈消息) / v1.4 (刻晴 checklist) **版本号不一致**，且 spec 从未真正进主 PRD — 历史 §F8 全靠 PM checklist + ADR-0046 字段集对齐 + 刻晴 AC test 三方默契，spec 主源缺。

**本 task 本质**：补主 PRD §F8 spec 字面 + 拆 hutao impl task + 修复版本号 drift。

### 0.1 spec drift 归责（魈 14:05 UTC own）

魈在 11:30 UTC sessions_send 写「PRD-001 v1.2 §F8」是 spec drift — trust 了 ADR-0046 §3.5 r2 内 reference (`# r2: PRD-001 v1.2 §F8 资质透明度 ¨ AC-F8-7`) 而**未 grep 主 PRD 头部 status line verify**。

**归责链**：
- 主 PRD 是 SSoT（single source of truth）
- ADR 内 reference 是 promise，不等于主 PRD 已 patch v1.2
- drift 由 PM patch task 闭环（本 task v1.5 patch 即闭环）

**evidence-first SOP 第 9 点候选**（魈起，PM 同意）：
> 引用 PRD/ADR 版本号前必 grep 主文档头部 status line verify，不能 trust 跨文档 reference。

---

## 1. AC#1 PRD-001 §F8 推荐过滤 spec 字面（input/output/sort/分页/cert_status 过滤逻辑）

### 1.1 业务规则（来源 PM checklist PM-005-9 + AC-F8-5）

**核心硬约束**：
1. **未认证陪诊师不进首屏推荐位**（`recommended=true` 或 top3）
2. **排序优先级**：已认证（verified）> 临时证明补交中（pending_supplement）> 未认证（uncertified）
3. **admin 不得 override 未认证进 top3**（admin endpoint 内置守门）

### 1.2 cert_status 字段集（与 ADR-0046 §3.5 align）

| 字段 | 值域 | 业务语义 |
|---|---|---|
| `companion_cert_status` | enum: `verified` / `pending_supplement` / `uncertified` | 资质三态（PM-005-1~2） |
| `companion_cert_type` | enum: `nurse` / `health_manager` / `none` | 证件类型（PM-005-3） |
| `companion_cert_updated_at` | ISO timestamp | 状态变更时间，用于 cache invalidate 判活 |
| `recommended` | bool | 推荐位标识，本 spec 是过滤入口（归 COMMON_FIELDS_WHITELIST，魈拍 B） |
| `recommendation_rank` | int | top3 内部排序位（1/2/3，超出 3 = null）（归 COMMON_FIELDS_WHITELIST，魈拍 B） |

**字段命名**：
- `companion_cert_*` 资质字段遵从 ADR-0046 §3.5 r2 positive list 前缀（line 288），通过 schemathesis CI gate
- `recommended` / `recommendation_rank` / `total_eligible` / `filtered_uncertified_count` 4 字段归 `COMMON_FIELDS_WHITELIST`（魈 14:05 UTC 拍 B，与 `total`/`page`/`page_size`/`has_more` 等 endpoint envelope 元数据同类，不污染域前缀 namespace）

**ADR-0046 r2 mechanism 延展使用，不需新 r3 amend**。具体补丁（魈给字面）：

```python
COMMON_FIELDS_WHITELIST = {
    # ... 既有 ...
    "recommended",
    "recommendation_rank",
    "total_eligible",
    "filtered_uncertified_count",
}
```

此补丁在 hutao 实装 S3-DEV-006 时合入 `scripts/qa/openapi_contract_diff.py`，由魈 review approve。

### 1.3 排序算法（spec 完整）

```python
# backend/app/services/recommendation.py (待 hutao 实装)

CERT_RANK = {
    "verified": 0,           # 已认证 → 最高
    "pending_supplement": 1, # 临时证明补交中 → 中
    "uncertified": 2,        # 未认证 → 排除 top3
}

def sort_companions_for_recommendation(companions: list[Companion]) -> list[Companion]:
    """
    PM-005-9 排序规则:
    - 已认证 > 临时证明补交中 > 未认证
    - 同 cert_status 内按 (rating DESC, completed_orders DESC, created_at ASC)
    - 未认证陪诊师永远不进 top3 (即使 admin override recommended=true)
    """
    return sorted(
        companions,
        key=lambda c: (
            CERT_RANK[c.companion_cert_status],
            -c.rating,                  # 高评分优先
            -c.completed_orders,        # 完单多优先
            c.created_at,               # 早注册优先
        ),
    )

def filter_top3_recommendations(sorted_companions: list[Companion]) -> list[Companion]:
    """
    PM-005-9 守门:
    - 取 cert_status != "uncertified" 的前 3 个进首屏推荐位
    - 不足 3 个时返回实际数（不补未认证）
    - admin 即使设 recommended=true,uncertified 仍被过滤
    """
    eligible = [c for c in sorted_companions if c.companion_cert_status != "uncertified"]
    return eligible[:3]
```

### 1.4 admin override 守门（PM-005-9 第 3 条）

admin-v2 编辑陪诊师页面：
- 数据库字段：`companion_profiles.admin_recommended_override BOOLEAN NULL`（架构决策 2026-06-12 00:58Z 魈拍、凝光 ratify · 方案 C · 反案 #16 catch-all 命名）
  - NULL = 未 override，使用 service 默认计算（`cert_status != "uncertified"`）
  - true / false = admin 显式 override，service 层优先该值
- 业务规则（service 层伪代码）：
  ```python
  final_recommended = (
      profile.admin_recommended_override
      if profile.admin_recommended_override is not None
      else (profile.cert_status != "uncertified")
  )
  ```
- **硬约束（不可绕过）**：即使 `admin_recommended_override=true` 但 `cert_status="uncertified"`，`filter_top3_recommendations` 永远过滤掉该陪诊师。即数据库写入成功（不报错）但**推荐 endpoint 仍不返回**。admin override 不绕过 §1.3 cert_status 守门。
- admin-v2 UI：
  - 详情页加 toggle 控件，展示当前 `admin_recommended_override` 值 + 允许 override + 清除 override（设回 NULL）
  - 当 `cert_status="uncertified"` 且 admin 尝试设 `admin_recommended_override=true` 时，加 warning toast「该陪诊师未认证，无法进入首屏推荐位（业务规则锁定）」（toast 文案与 §F8.5 admin override warning 一致，最终文案待帝君拍板）
- 审计：复用现有 `AdminAuditLog`（`backend/app/models/admin_audit_log.py`），`action_type="set_admin_recommended_override"`，记录 `before_value` / `after_value` / `admin_user_id` / `target_companion_id`

**ADR 注**：本 1 字段扩展不足以独立 ADR 阈值；与 ADR-0046（contract storage）主题无关，不 amend。后续 admin 字段若累计 ≥ 2 时再 raise refactor task 评估拆 `companion_admin_settings` 表（YAGNI 触发条件）。

**实施 task**：`S3-DEV-006-FOLLOWUP-ADMIN-OVERRIDE`（P2，hutao own，魈 review）

### 1.5 分页规则

- 首屏推荐位：固定 top 3（无翻页）
- 全列表 endpoint：`page_size=20`，`page` 默认 1，最大 100 页（防爬虫）
- 已认证陪诊师不足 3 个时（早期冷启动场景）：返回实际数 + 显式 `total_eligible` 字段

---

## 2. AC#2 endpoint signature + response schema

### 2.1 推荐 endpoint（首屏 top3）

**Endpoint**: `GET /v1/companions/recommendations` ⭐ 魈 11:30 UTC 拍板 + 14:05 UTC ratify

**Auth**: required（家属 token / 下单人 token / 共享落地页 token 均可）

**Query params**:
| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `city` | string | 用户当前 city | 城市过滤（默认从 token 取） |
| `service_type` | string | null | 服务类型过滤（陪诊师专长） |
| `limit` | int | 3 | 首屏推荐位数量（max 3） |

**Response schema** (200 OK):

```json
{
  "items": [
    {
      "companion_id": "uuid",
      "companion_name_masked": "李**",
      "companion_avatar_url": "/static/...",
      "companion_cert_status": "verified",
      "companion_cert_type": "nurse",
      "companion_cert_updated_at": "2026-06-11T03:07:00Z",
      "rating": 4.8,
      "completed_orders": 152,
      "recommended": true,
      "recommendation_rank": 1
    }
  ],
  "total_eligible": 47,
  "filtered_uncertified_count": 3
}
```

**Response 字段守则**:
- 不返回 `companion_phone` / `companion_id_card` / `companion_cert_url`（ADR-0046 §3.5 ABAC）
- 不返回 `companion_real_name`（PII 脱敏 mask）
- 不返回 admin 内部备注 / cert_url 原始 URL
- `filtered_uncertified_count` 用于运营观察未认证数量，不暴露具体 ID

**Error response** (404 / 403):

```json
{
  "error_code": "NO_ELIGIBLE_COMPANIONS",
  "message": "当前城市暂无可推荐的已认证陪诊师"
}
```

### 2.2 全列表 endpoint（区分推荐 endpoint）

**Endpoint**: `GET /v1/companions`

**排序行为锁定 (a)**（魈 14:05 UTC 拍）：跟推荐 endpoint 一致
- 三态优先级：verified > pending_supplement > uncertified
- 同 cert_status 内 tie-breaker：`(rating DESC, completed_orders DESC, created_at ASC)`
- **区别仅在不过滤 uncertified**（uncertified 排末尾但展示），由前端按 PM-005-1 三态徽章展示

理由（魈 own）：
- 一致性 > 灵活性，前端两 endpoint 排序逻辑统一，减少认知负担
- PRD-001 §F2 share landing + §F8 推荐已锁三态优先级，全列表与之矛盾会让用户预期错位
- 全列表只是过滤口径不同（不删 uncertified），排序逻辑 100% 复用推荐 endpoint
- 前端「按 created_at 排」需求是 admin 工具场景，走 admin endpoint（不在 v1 用户端 scope）

本 endpoint 实装细节不在本 spec scope，但**排序行为锁定**写入本 spec 作为合约规则，S3-DEV-006 后 hutao 维护 `/v1/companions` 时必须遵守。

---

## 3. AC#3 拆 S3-DEV-006-RECOMMENDATION-API 子 task（hutao own）

```yaml
title: S3-DEV-006-RECOMMENDATION-API
type: develop
priority: P2
assignee: hutao
depends_on:
  - S3-PRD-001-V12-F8-RECOMMENDATION-FILTER-SPEC  # 本 task done 后启动
acceptance:
  - AC#1: 实装 GET /v1/companions/recommendations endpoint（top3 推荐过滤 + 排序）
  - AC#2: service 层 sort_companions_for_recommendation + filter_top3_recommendations 函数
  - AC#3: admin override 守门：cert_status=uncertified 永远不进 top3（unit test）
  - AC#4: response schema 含 companion_cert_status / recommended / recommendation_rank / total_eligible / filtered_uncertified_count
  - AC#5: schemathesis positive list 验证 `companion_cert_*` 前缀（ADR-0046 §3.5 r2）
  - AC#6: ABAC 4 层防御：endpoint 层不返回 cert_url / phone / id_card / real_name
  - AC#7: city / service_type query 过滤 + limit max 3 限制
  - AC#8: NO_ELIGIBLE_COMPANIONS 异常路径（无已认证陪诊师时 404）
  - AC#9: pytest unit + integration test + schemathesis CI gate 全绿
  - AC#10: admin-v2 UI warning toast「该陪诊师未认证，无法进入首屏推荐位」(前端联动，可拆 frontend 子 task)
```

---

## 4. AC#4 cert_status 字段集对齐 ADR-0046 §3.5（魈 14:05 UTC 拍 B）

**字段归类锁定**：
- `companion_cert_status` / `companion_cert_type` / `companion_cert_updated_at` → ADR-0046 §3.5 r2 `S3_NEW_FIELD_PREFIXES` 第 4 域 `companion_cert_*`（已锁，sticking with r2）
- `recommended` / `recommendation_rank` / `total_eligible` / `filtered_uncertified_count` → `COMMON_FIELDS_WHITELIST`（魈 14:05 UTC 拍 B）

**魈拍 B 理由**：
| 选项 | 评 |
|---|---|
| (A) ADR-0046 r3 加 `recommendation_*` 前缀 | over-engineer。positive list 前缀是**跨域字段族**，不是**单 endpoint 元数据**。recommendation_* 只服务推荐 endpoint，不会被 contract/share/insurance/preparation/feedback/companion_cert 复用。加前缀污染 ADR。 |
| **(B) list 进 `COMMON_FIELDS_WHITELIST`** ⭐ | 这 4 字段是 endpoint envelope 元数据（pagination/sorting/总数），跟 `total` / `page` / `page_size` / `has_more` 等同类。COMMON_FIELDS_WHITELIST 就是干这个的。推荐 endpoint 不需要特殊前缀 namespace。 |
| (C) schemathesis 跳过本 endpoint | 退路，失契约约束。不允。positive list 必须强约束所有 endpoint。 |

**实装位置**：`scripts/qa/openapi_contract_diff.py` 在 S3-DEV-006 PR 内由 hutao 加 4 字段进 COMMON_FIELDS_WHITELIST，魈 review approve（不需新 ADR amend）。

---

## 5. 未决问题（v1 final 状态：5 项已答，2 项等帝君业务措辞）

| # | 问题 | 拍板 | 拍板者 |
|---|---|---|---|
| 1 | endpoint URL：`/v1/companions/recommendations` | ✅ 已锁定 | 魈 11:30 UTC 拍 + 14:05 UTC ratify |
| 2 | `recommendation_*` 字段归类 | ✅ (B) list 进 COMMON_FIELDS_WHITELIST | 魈 14:05 UTC |
| 3 | admin override warning toast 文案 | ⏳ 等帝君 — PM 草稿「该陪诊师未认证，无法进入首屏推荐位（业务规则锁定）」 | 帝君（业务措辞） |
| 4 | NO_ELIGIBLE_COMPANIONS 文案 | ⏳ 等帝君 — PM 草稿「当前城市暂无可推荐的已认证陪诊师」 | 帝君（业务措辞） |
| 5 | 全列表 endpoint 排序行为 | ✅ (a) 跟推荐 endpoint 一致 | 魈 14:05 UTC |
| 6 | 主 PRD 文档 patch 版本号 | ✅ v1.5 — 跳过 v1.2/v1.3/v1.4（commit msg changelog 写明历史 reference 但 0 patch 的事实，未来 grep 不困惑） | PM 自决定 + 魈 14:05 UTC 同意 |

---

## 6. 主 PRD 文档 patch 内容（待 Owner Accept 合入）

待本 spec draft Owner Accept 后，PM 起 patch task 把以下 section 合入 `docs/prd/PRD-001-family-companion.md`：

```markdown
### F8 陪诊师资质透明度（S3-REQ-005，v1.5 新增）

> 来源：S3-PRD-001-V12-F8-RECOMMENDATION-FILTER-SPEC + PM checklist v1
> Lock 条件：魈 architecture review + 帝君 Owner Accept

#### F8.1 资质三态徽章
（详见本 spec §1.1）

#### F8.2 推荐过滤算法
（详见本 spec §1.3）

#### F8.3 endpoint signature
（详见本 spec §2.1）

#### F8.4 admin 守门
（详见本 spec §1.4）
```

---

## 7. 不做（本 task scope 外）

- ❌ backend code 实装（拆 S3-DEV-006 给 hutao）
- ❌ S3-DEV-005 已 done scope 改动（PR #270 已 merge）
- ❌ PR #270 回滚
- ❌ frontend admin-v2 UI warning toast 实装（拆 frontend 子 task 给 hutao）
- ❌ schemathesis positive list amend（等魈 ADR-0046 r3 决定）

---

## 8. PM 自检（反案 #14/#17/#20 部首区 typo enforce）

- 「资质」「认证」「推荐」「排序」「过滤」「证件」「陪诊师」无错别字 ✅
- 字段名小写下划线一致 `companion_cert_status` / `recommendation_rank` ✅
- enum 值小写一致 `verified` / `pending_supplement` / `uncertified` ✅
- 「医路安科技有限公司」3 字一致 ✅（不用 OCR 易混字）

---

## 9. 下一步

1. ✅ 本 draft 落盘（11:55 UTC）
2. ✅ sessions_send 给魈 review — 14:05 UTC 收魈 ratify approve + 3 拍板（§5 #1/#2/#5）
3. ✅ sessions_send 给帝君 review — 等回业务措辞 §5 #3/#4
4. ✅ spec v1 → v1 final（14:08 UTC，吸收魈 3 拍 + spec drift 注脚 + COMMON_FIELDS_WHITELIST 补丁字面）
5. ⏳ 等帝君业务措辞 → set task `in-review` → 魈 set done (作为 reviewer 角色)
6. ⏳ Owner Accept → 拆 S3-DEV-006-RECOMMENDATION-API 子 task 给 hutao（10 AC 已就绪 §3）
7. ⏳ 起 PRD 主文档 v1.1 → v1.5 patch task
8. ⏳ 通知 hutao S3-DEV-006 待启动 (depends_on 本 task done)
9. ⏳ 通知刻晴 S3-DEV-006 启动后可拆 S3-TEST-007 推荐 endpoint E2E test task
