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


---

## 7. Resolution (post-merge update)

**Fix merge sha**: `95df4c1` (PR #282) at **2026-06-11 23:25 UTC**

**实际暴露窗口**: ~6h (17:20 UTC 发现 → 23:25 UTC merge)
- vs PM target 2-3h: **超出 +3h** (CI 重跑 + rebase 后再 CI 重跑各占 ~1.5h)

**Resolution steps applied** (PR #282 commit `95df4c1`):
1. 新增 `CompanionDirectoryView` schema (`backend/app/schemas/companion.py:75`) — list 端无 PII
2. 新增 `CompanionDirectoryDetailView` schema (`backend/app/schemas/companion.py:109`) — detail 端无 PII
3. `GET /v1/companions/` 切到 `list[CompanionDirectoryView]` (`backend/app/api/v1/companions.py:26`)
4. `GET /v1/companions/{id}` 切到 `CompanionDirectoryDetailView` (`backend/app/api/v1/companions.py:98`)
5. 新增 sentinel test `backend/tests/test_abac_companions_public_view.py` (134 行, 字面 assert response 中无 `real_name` / `certification_no` 字面 hit)
6. ABAC L2 layer: `_to_public_view(p)` 调用 `share.mask_name` SSoT 生成 `pseudonym_name` (例如 "陈*师傅")
7. OpenAPI regen + drift-check pass

**ABAC compliance verified** (post-merge PM 字面 grep):
- `/v1/companions/` (list) → `CompanionDirectoryView` ✅ 无 real_name/certification_no
- `/v1/companions/{id}` (detail) → `CompanionDirectoryDetailView` ✅ 无 real_name/certification_no
- `/v1/companions/me` (self) → `CompanionDetailResponse` ✅ (ABAC self ADR-0049 §6.1, 本人看本人 OK)
- `POST /v1/companions/apply` (用户申请) → `CompanionDetailResponse` ✅ (用户填自己 real_name)
- `PUT /v1/companions/me` (本人更新) → `CompanionDetailResponse` ✅ (ABAC self)

---

## 8. Post-merge Actions (PM 凝光 own)

- [x] **2026-06-11 23:25 UTC**: PR #282 merged `95df4c1`
- [x] **2026-06-11 23:30 UTC**: PM 字面 verify 5/5 项 ABAC compliance pass
- [ ] **TBD**: admin force purge production cache (`/v1/companions` list + recommendation cache)
- [ ] **TBD**: 起 cron 监控 24h 微信小程序 + iOS 列表页崩溃率 (检查点 6h/12h/18h/24h)
- [ ] **TBD**: 起前端 nullable handling 2 task (微信/iOS, P1, hutao, 等 S3-DEV-006 主线 merge 后)
- [ ] **TBD**: 法务通知 (待帝君拍板)
- [ ] **TBD**: 运营通知 (待帝君拍板)
- [ ] **TBD**: 对外披露决策 (待帝君拍板, PM 默认推荐: 不主动公告)

---

## 9. Lessons Learned

1. **CI rebase overhead**: 反案 #14 (rebase 后 CI 全 reset 必须重跑) 在 P0 流程下放大风险. PR #281 incident doc merge 后, PR #282 mergeState=BEHIND → `gh pr update-branch` 又触发一次完整 CI reset, 直接加 ~1.5h. **建议**: P0 fix PR 不要插队 merge 其他 PR (incident doc 可以等 fix 一起 merge), 或并行起 P0 PR 时先 freeze 其他 main merge.

2. **ABAC schema 设计原则确认 (新 SOP)**: 任何 public-facing endpoint 必须用 dedicated ViewModel (e.g. `CompanionDirectoryView`), 不能直接复用包含 PII 的 base model (e.g. `CompanionListResponse`). schema 名字面区分 `Directory` (公开) vs `Detail/Full` (admin/self).

3. **sentinel test 是反案 #16 catch-all grep 自动化**: `test_abac_companions_public_view.py` 字面 assert response 中无 `real_name` / `certification_no` 字面 hit — 不依赖 PR diff 肉眼看, CI 强制守. 推荐复制为模板, 任何 ABAC-critical endpoint 必带.

4. **Detection gap**: 此 PII 字段进入 list schema 的具体时间未明确 (git blame 待补). PR review 未拦截原因 = 当时还没有 ABAC sentinel test framework. 已补.

5. **Mean Time to Detect (MTTD)**: 此 bug 在 prod 暴露多久 (具体时间) 待补. 评估 ABAC 历史欠账总规模 (其他类似 endpoint 是否也漏) 应由魈 own 起独立 audit task.

