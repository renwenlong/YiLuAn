# Security Incident: Companions List Endpoint PII Exposure

**Incident ID**: SI-2026-06-11-001
**Severity**: P0 (PII actual exposure in production)
**Status**: Detected, fix in progress (S3-OPS-ABAC-COMPANIONS-LIST-PII-FIX)
**Reported by**: 魈 (architect) — 2026-06-11 ~17:20 UTC, evidence-first 发现 during S3-DEV-006-RECOMMENDATION-API commit 2
**PM owner (this doc)**: 凝光

---

## 1. Affected Data

`GET /v1/companions` (公共陪诊师列表 endpoint, user-facing):

| 字段 | schema | 字段类型 | 暴露范围 |
|---|---|---|---|
| `real_name` | `CompanionListResponse.real_name` | `str` (not optional) | 任何登录 user (有 JWT) |
| `certification_no` | `CompanionDetailResponse.certification_no` | `str \| None` | 任何登录 user (有 JWT) |

**触发条件**: user 持有合法 JWT (即任何注册用户).

**对比**: `GET /v1/shares/.../companion` (PR #271 PM-005-3/4 严禁 fallback real_name) 已严格 ABAC compliant, list endpoint 是漏网.

---

## 2. Evidence

- `backend/app/schemas/companion.py:44` — `CompanionListResponse.real_name` (字面定义)
- `backend/app/api/v1/companions.py:21` — `response_model=list[CompanionListResponse]` (字面注入)
- `backend/app/dependencies.py:70` — `CurrentUser = Annotated[User, Depends(get_current_user)]` (无 ABAC 守)

---

## 3. Timeline

| 时间 (UTC) | 事件 |
|---|---|
| **TBD** (待 git blame) | `real_name` 字段引入 `CompanionListResponse` |
| 2026-06-11 ~17:20 | 魈 evidence-first 发现 (during S3-DEV-006 commit 2 review) |
| 2026-06-11 ~17:25 | 魈立 P0 task `S3-OPS-ABAC-COMPANIONS-LIST-PII-FIX` (assignee=hutao, reviewer=魈) |
| 2026-06-11 ~17:30 | 魈 sessions_send 知会凝光 (PM) 评估 PRD/灰度/优先级 |
| 2026-06-11 17:35 | 凝光回复魈: 优先级 = ABAC fix 优先于 S3-DEV-006 主线 (减暴露窗口从 ~8h 到 2-3h) |
| **TBD** | 凝光通知帝君 (PII prod 暴露, 决策对外披露 yes/no) |
| **TBD** | hutao 起 ABAC fix PR |
| **TBD** | 凝光 PM 验收 (验 real_name 实际 from response 字面消失) |
| **TBD** | fix merge to main + admin force purge cache |
| **TBD** | 24h 监控期结束 |

---

## 4. Fix Plan

详见 task `S3-OPS-ABAC-COMPANIONS-LIST-PII-FIX` (架构师魈起的 8 AC).

PM 关注点:
1. **schema 字段切 PublicView** (real_name 移除或脱敏为 e.g. "陈*师傅")
2. **前端同步处理 nullable field** — 不让用户看到 "undefined" (微信/iOS list page)
3. **catch-all grep** (反案 #16) PR description 必须显式列出所有 grep 命中点为 0
4. **fix merge 后立即 admin force purge cache** (companions list + recommendation)

---

## 5. Disclosure Decision

**对外披露**: pending 帝君拍板
**对内通知**:
- 运营: pending 凝光通知 (准备运营话术, 防用户/媒体追问)
- 法务: pending 凝光通知 (留 timeline 痕迹, 后续监管自查证据链)

**凝光建议**: 不主动对外公告 (无外部投诉 + fix 周期短 + 字段非敏感金融/医疗), 但内部 timeline 必须落 (本文件即证据链).

---

## 6. Lessons Learned

待 fix 完成后回填:
- root cause (为何 real_name 进了 public list schema?)
- detection gap (为何 PR review/CI 没拦?)
- prevention (是否新增 schema lint rule: public-facing list endpoint 字段 catch-all grep?)

