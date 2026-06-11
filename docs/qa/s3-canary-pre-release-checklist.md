# 医路安 S3 — 灰度前手动回归 Checklist

> **S3-TEST-004** | S3 灰度上线最后一道闸 | 维护：刻晴（测试）
> 范围：S3 阶段新功能 (PRD-001 v1.4 / PRD-002 / PRD-003 / PRD-004) 的 staging 真实环境验收
> 规则：**全部 PASS 才放灰度**。任一 FAIL 阻塞 S3 灰度启动。
> 与 CI gate 互补 — 本清单是 CI **不能**覆盖的 staging 真实环境验收（k6 SLO / 跨副本一致 / WORM 合同 / Azure Blob 真传 / WS 真 broker fanout / 灰度 5%→25%→100% 真演 / 回滚演练）。
> 复用 S2-TEST-004 模式 (`docs/qa/canary-pre-release-checklist.md`)，本 checklist 是 S2 之上 **delta**（S2 项保持 retest，S3 新加项是本表重点）。

---

## 0. 执行前置

### 0.1 环境前置

- [ ] staging 环境部署最新 `main` 分支 (commit hash: `_____________`)
- [ ] S2 灰度 checklist (`docs/qa/canary-pre-release-checklist.md`) **全部 PASS** + 签字落
- [ ] CI gate 全绿（4 required check: Backend Tests / Docker Build Verification / WeChat Mini Program Tests / Build & Test (iOS Simulator)）
- [ ] Prometheus + Alertmanager + Grafana dashboard 接 S3 新指标（详见 §7）

### 0.2 Secrets 前置 (S3 新增三 salt)

- [ ] `CONTRACT_PSEUDONYM_SALT` 首次 prod 曝光前一次性高熵 random (`python -c "import secrets; print(secrets.token_urlsafe(64))"`)，入 secrets vault **不入 git**
- [ ] `PII_HASH_SALT` + `PII_ENVELOPE_KEY` 同上，三 salt **互不雷同**
- [ ] **S3 prod 上线 gate**: 三 salt 全部与 dev default 不同且互不雷同 — 验证命令：
  ```bash
  docker exec backend python -c "from app.config import settings; \
    s = [settings.contract_pseudonym_salt[:8], settings.pii_hash_salt[:8], settings.pii_envelope_key[:8]]; \
    assert len(set(s)) == 3 and all(x != '00000000' for x in s), f'salt 雷同/dev default: {s}'; print('OK', s)"
  ```
- [ ] `ADMIN_API_TOKEN` 等敏感环境变量已注入（非默认值，fail-fast 校验通过）
- [ ] `feedback` 模块 Azure Container + SAS 已配置（ADR-0049 §3, S3-DEV-004）

### 0.3 数据迁移前置

- [ ] alembic upgrade head 跑通 + 关键新表存在: `service_contracts`, `user_feedbacks`, `feedback_attachments`, `companion_profiles.certification_*`
- [ ] alembic downgrade -1 真演 → upgrade head 再演（双向幂等）
- [ ] WORM 合同存储 namespace `contracts/{year}/{month}/{order_id}_{contract_hash}.pdf` 落 Azure Container 不报错

---

## 0b. 测试分层（魈 #104 review 澄清，S3 延续）

| 层 | 依赖 | 跑在哪 | 结果一致性 |
|----|------|--------|-----------|
| **单元 pytest（>1500）** | conftest 内存 SQLite + FakeRedis | 任何环境，无需 Docker | 与本地 dev 栈**完全解耦**，pre-push hook 已强制 |
| **集成测试（含 Docker smoke）** | 真实 PG + Redis + Azure Blob (devstoreaccount1) | **统一用 `./up.sh dev` 容器栈** | 依赖真实中间件，必须固定栈 |
| **staging 真验（本 checklist §1-§6）** | 真 PG + 真 Redis + 真 Azure Blob + 真 wxpay | staging 环境 | 不可 mock，本 checklist 全量手动 |

---

## 1. S2 回归验证 (复用 S2-TEST-004)

> **必须 retest** — 防 S3 改 share 域 / cache / WS 影响 S2 已 done 功能。

- [ ] 资金线 §1 (S2 checklist) — 7 项全 PASS（wxpay 真回调 / CB 状态机 / 退款平账 / 空 txn_id / 幂等）
- [ ] Share Token §2 (S2 checklist) — 11 项全 PASS（双端真机 + scope + WS replay + audience 锁）
- [ ] IDOR §3 (S2 checklist) — 6 项全 PASS（403 / alg=none / openid 风控 / OTP 频控）
- [ ] AI 摘要 §4 (S2 checklist) — 7 项全 PASS（¥0.05 / ¥50 cap / CB 降级 / post-check / 热更新 / 多副本去重 / 并发竞态）
- [ ] 回滚演练 §5 (S2 checklist) — 4 项全 PASS（告警 / F2 关入口 / runbook ≤5min / 三档逆向）

**S2 任一 FAIL → 阻塞 S3 灰度。**

---

## 2. S3 信任前置 (PRD-003 S3-REQ-003 / ADR-0054 / S3-DEV-003)

> 三端 (iOS / 微信 / patient web) 资质 cert 字段一致 + WS 推送 + a11y / 文案合规。

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 2.1 | 患者端 staging 创建陪诊师订单 → `GET /api/v1/users/orders/{order_id}/precheck-status` | 返回 4 card (companion_cert / insurance / prep_package / contract), 字段含 `companion_cert_status`, `cert_type`, `cert_no`, `cert_verified_at` | ⬜ | | |
| 2.2 | 微信小程序家属端打开订单详情 cert-card 组件 | 4 字段展示, 不暴露原图, **不出现"职业背书"文案** | ⬜ | | |
| 2.3 | iOS 家属端打开订单详情 trust-precheck UI (r4 Swift Native) | 同 2.2, XCUITest matching | ⬜ | | |
| 2.4 | WS 通道 `/api/v1/ws/v1/orders/{order_id}/precheck` 连接成功 | first frame auth → 后续 `precheck.status.updated` / `precheck.all_ready` / `precheck.blocked` event 收到 | ⬜ | | |
| 2.5 | admin 后台改 `companion_profiles.verification_status` 从 pending → verified | WS 推 `precheck.status.updated`, 客户端 5s 内收到 + HTTP refetch | ⬜ | | |
| 2.6 | `companion_cert_status_changed` 专用 WS event (BUG-005 缺口) | **当前后端未实现** — Bug 锁记 `S3-BUG-005-CERT-WS-EVENT-SCHEMA-VS-IMPL-DRIFT` (P1, in-review), 灰度前必须修法 B (改 schema doc 字面) 或修法 A (实装 event) | ⬜ | | |
| 2.7 | 未认证 (verification_status=None/pending/rejected) 陪诊师 `companion_cert_status` 字段不暴露原图 | ABAC 4 层守住, sentinel 字段拒绝 | ⬜ | | |
| 2.8 | 未认证陪诊师不进首屏推荐 `/api/v1/companions/recommendations` | **当前端点未实现** — AC#5 缺口锁 (S3-TEST-006 xfail strict=False), PM-005-6 task 待拆 | ⬜ | | |
| 2.9 | 文案 lint: 三端 trust UI 不出现 "权威认证" / "国家级" / "100% 安全" 等违规承诺 | grep 全 0 命中 | ⬜ | | |
| 2.10 | a11y: 三端 trust card 通过 contrast ≥4.5:1, screen reader 朗读 cert_type + cert_no 完整 | iOS VoiceOver / 微信无障碍 / web NVDA | ⬜ | | |

## 3. S3 反馈采集 (PRD-004 S3-REQ-004 / ADR-0049 / S3-DEV-004)

> 8 个 endpoint (multipart 含附件) + ABAC 4 层 (admin 看全 / 陪诊师只看 admin 脱敏摘要 + 自己申诉 / 不看用户原文/截图/联系方式)

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 3.1 | 用户订单完成页提交反馈 (multipart, 含 1 张截图) | 201 + feedback_id 返回; 截图入 Azure container `feedback_attachments/{year}/{month}/{feedback_id}_{uuid}.{ext}` | ⬜ | | |
| 3.2 | 家属共享落地页提交反馈 (share session JWT 鉴权, 不需要 access token) | 201 + ABAC 1 验证 share_session aud 锁 | ⬜ | | |
| 3.3 | 客服 admin 代录反馈 | 201 + `created_by_role=admin` 标记 | ⬜ | | |
| 3.4 | admin-v2 处理反馈 (status pending → in_progress → resolved / closed) | 4 状态机转换合法; 跨态拒绝 | ⬜ | | |
| 3.5 | admin 人工脱敏生成陪诊师摘要 (`companion_summary`) | 摘要不含用户原文敏感字 + 不含截图原图 URL | ⬜ | | |
| 3.6 | 陪诊师端 GET `/api/v1/companions/me/feedbacks` | 只返回 admin 脱敏后的 `companion_summary` + severity + status + 自己申诉, **不见用户原文/截图/电话** (ABAC layer 4 sentinel) | ⬜ | | |
| 3.7 | 陪诊师端 POST 申诉 | 201, `appeal_status=pending` | ⬜ | | |
| 3.8 | 补充反馈 (新 row + `feedback_parent_id` 串版本链) | 原 row 不改, 新 row 关联 parent | ⬜ | | |
| 3.9 | S3 阶段**不做 AI 自动摘要** — 验证无 DeepSeek 调用 + 无 `BudgetExhausted` 触发 | metric `ai_summary_call_total{module=feedback}` = 0 | ⬜ | | |
| 3.10 | Azure container + SAS smoke (startup healthcheck) | `feedback_startup_healthcheck.py` 启动时 ping Azure container 成功; SAS 签发可上传 | ⬜ | | |
| 3.11 | `feedback_lifecycle` 模块 (AC#9) | **当前未实现** — S3-TEST-005 xfail strict=True 锁缺口, 灰度前必须实装 | ⬜ | | |

## 4. S3 资质透明度 / Share 9 字段契约 (PRD-001 v1.4 §F8 / ADR-0046 §3.5 / S3-DEV-005)

> share endpoint 9 字段 sub-object 契约 + cache invalidate + WS cert event + 未认证不暴露

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 4.1 | 患者端创建 share token → 家属端拉 `GET /api/v1/shares/session/order` | 返回 `companion` sub-object 含 9 字段 (display_name / avatar / verification_status / cert_type / cert_no / cert_verified_at / 不含 real_name / 不含 phone / 不含 cert_image_url) | ⬜ | | |
| 4.2 | OpenAPI contract diff (CI: `Backend §2.7 contract diff`) | 4.1 字段集与 `docs/api/openapi.json` + `docs/api/share-contract-baseline.json` 一致, drift 0 | ⬜ | | |
| 4.3 | schemathesis fuzz from OpenAPI (反案 #11 asset-presence) | 4 verification_status (pending / verified / rejected / None) 全 case schema 合规 | ⬜ | | |
| 4.4 | S3-BUG-004 regression: `companion.name` = display_name 优先, fallback "陪诊师", **不出 real_name** | 100 次随机 fuzz no real_name 泄漏 (ABAC layer 1 red-line sweep) | ⬜ | | |
| 4.5 | admin 后台 `POST /api/v1/admin/cache/invalidate` (cards=companion_cert, order_id=X) | 200 + broadcast=False; 下一次 GET share 立即拿到新 cert 状态 | ⬜ | | |
| 4.6 | `precheck:order:{order_id}` Redis cache hit/miss metric | hit rate ≥80% (热订单 100 次访问); invalidate 后 next read miss + refetch DB | ⬜ | | |
| 4.7 | WS 通道收到 `precheck.status.updated` (cert change) 触发客户端 refetch | UI 5s 内更新 cert_status | ⬜ | | |

## 5. S3 服务合同 + 保险 (PRD-003 S3-REQ-001 / ADR-0046 / ADR-0047 / S3-DEV-001)

> WORM 合同 + 双签 + 真 Azure WORM container + 7 年保留

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 5.1 | 用户下单 + 支付成功 → 异步生成电子服务合同 (PDF) | 落 Azure namespace `contracts/{year}/{month}/{order_id}_{contract_hash}.pdf`; `service_contracts` 表入 row | ⬜ | | |
| 5.2 | 合同 hash 公式: `SHA-256(order_id || contract_template_version || patient_pseudonym || companion_id || price || service_time_start)` | 计算一致, fixture verify | ⬜ | | |
| 5.3 | WORM policy: 已生效合同尝试覆盖上传 | Azure 拒绝 (HTTP 409 / 412 immutability lock), backend 返回 422 + 不更新 row | ⬜ | | |
| 5.4 | 三端 (user / companion / admin) 只读拉合同 SignedReadURL | ViewerRole TTL 正确 (user/companion 15min, admin 60min) | ⬜ | | |
| 5.5 | 陪诊责任险 trigger 异步购险 | 保单号入 `service_contracts.insurance_policy_no` 字段 | ⬜ | | |
| 5.6 | 7 年保留 retention policy | Azure container `Immutable Storage with versioning` 启用 ≥ 7 年 (2033+) | ⬜ | | |
| 5.7 | 合同 PDF 不含完整 PII (患者姓名只显脱敏 hash / 陪诊师 ID 不显完整身份证) | grep PDF text 0 命中 | ⬜ | | |

## 6. S3 staging quantitative E2E (k6 SLO + 跨副本一致)

> **S3-TEST-003-PRECHECK-CROSS-REPLICA-E2E** AC#6 / AC#7 — 多副本 hot reload + k6 压测

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 6.1 | k6 压测 100 RPS × 5min `/api/v1/users/orders/{order_id}/precheck-status` | p95 ≤200ms, error rate <0.1% | ⬜ | | |
| 6.2 | precheck cache hot reload (改 `ai_blocklist.yaml`) | ≤5s 跨副本 (≥3 replicas) 全部生效 (`commit_sha` metric 一致) | ⬜ | | |
| 6.3 | precheck 4 card 状态机 multi-replica race (并发改 verification_status) | last-write-wins + cache invalidate 跨副本不悬挂旧值 | ⬜ | | |
| 6.4 | WS broker fanout (real Redis, 不用 FakeRedis) | 3 replicas 同订阅, admin 改 cert → 3 副本全收到 | ⬜ | | |
| 6.5 | AI budget guard 跨副本 (BUDGETGUARD) | 100 并发请求 同订单 AI 摘要, 总扣费 ≤ 单次, 不双扣 | ⬜ | | |

## 7. 灰度三阶段放量 (mock → 5% canary → 25% → 100%)

> S2 模式延续, S3 阶段每次放量都要 retest §2-§6 sample 项

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 7.1 | mock 流量 100% (内部 staging) | §1-§6 全 PASS | ⬜ | | |
| 7.2 | 5% canary (团队内部白名单 10 人) 真 wxpay + 真 SMS | 5xx ≤0.5%, 无 P0 alert 触发 ≥6h | ⬜ | | |
| 7.3 | 5% canary 阶段 §2.1 + §3.1 + §4.1 + §5.1 sample retest | 全 PASS | ⬜ | | |
| 7.4 | 25% canary (扩内部) | 5xx ≤0.5%, AI budget 单日 ≤¥50, 合同生成 0 失败 | ⬜ | | |
| 7.5 | 25% canary 阶段 §2.5 (WS) + §3.4 (admin 流转) + §4.5 (cache invalidate) sample retest | 全 PASS | ⬜ | | |
| 7.6 | 100% (放量) | 5xx ≤2% / 30min 持续监控 + 每日 AI 成本预警 | ⬜ | | |

## 8. 回滚演练 (S3 新增三场景, 必须真演)

> S2 §5 retest + S3 新增三场景

| # | 验收项 | 期望 | 结果 | 执行人 | 时间 |
|---|--------|------|------|--------|------|
| 8.1 | 触发 5xx > 2% / 30min | Alertmanager 告警 + 回滚决策 (S2 §5.1 retest) | ⬜ | | |
| 8.2 | 关闭 F8 入口 (信任前置 UI) | 三端 trust card 隐藏, 已发 share token 保留 read-only | ⬜ | | |
| 8.3 | 关闭 F-feedback 入口 (反馈采集) | 用户端 / 家属端反馈按钮隐藏, admin-v2 处理已收反馈不受影响 | ⬜ | | |
| 8.4 | 关闭服务合同 trigger (S3-REQ-001) | 新订单不再异步生成合同, 已生成合同仍可拉; 用户端订单详情合同入口隐藏 | ⬜ | | |
| 8.5 | runbook 可操作性 (S3 amend) | 值班人按 `docs/ops/canary-rollback-runbook.md` (含 S3 三 flag) 5min 内完成回滚 | ⬜ | | |
| 8.6 | WORM 合同回滚不可逆 | 灰度期间生成的合同 WORM 7y 保留, 不能因回滚删除 | ⬜ | | |

## 9. S3 监控告警新指标 (Prometheus + Alertmanager 接入)

> S3 新功能必须有专属 metric, 否则灰度盲飞

| # | 指标 | 告警阈值 | 接入 | 结果 |
|---|------|---------|------|----|
| 9.1 | `precheck_status_request_total` / `_latency_seconds` | p95 >500ms 持续 10min | ⬜ | ⬜ |
| 9.2 | `share_companion_cert_view_total` (按 verification_status 分维) | rejected ratio >5% 持续 1h | ⬜ | ⬜ |
| 9.3 | `feedback_submit_total` / `_attachment_upload_total` | submit fail rate >2% 持续 30min | ⬜ | ⬜ |
| 9.4 | `feedback_attachment_storage_error_total` | error >0 持续 5min | ⬜ | ⬜ |
| 9.5 | `service_contract_generation_duration_seconds` | p95 >30s 持续 1h | ⬜ | ⬜ |
| 9.6 | `service_contract_worm_immutability_violation_total` | >0 立即 alert | ⬜ | ⬜ |
| 9.7 | `precheck_cache_hit_ratio` | <60% 持续 1h | ⬜ | ⬜ |
| 9.8 | `companion_recommendation_filter_excluded_total` (AC#5) | (端点未实装前 skip) | ⬜ | ⬜ |

---

## 10. 放行签字

| 角色 | 签字 | 时间 | 结论 |
|------|------|------|------|
| 测试（刻晴） | | | ⬜ 全 PASS |
| 架构（魈） | | | ⬜ 技术放行 |
| PM（凝光） | | | ⬜ 业务放行 |
| Owner（帝君） | | | ⬜ 灰度批准 |

> 任一 FAIL 项必须记录原因 + 处理决策（修复后重测 / 接受风险带 known issue 上线 / 推迟灰度）。

---

## 附 A: 已知缺口 (灰度前必须解决)

1. **S3-BUG-005** (`CERT-WS-EVENT-SCHEMA-VS-IMPL-DRIFT`, P1, in-review) — `companion_cert_status_changed` event 后端未实装, doc 提及但 0 代码; **修法 A 实装 OR B 改 doc 字面**, 灰度前必须二选一收口
2. **AC#5 recommendation endpoint** (S3-TEST-006 xfail strict=False) — `/api/v1/companions/recommendations` 端点不存在; 等 PM-005-6 (PR #274) 拆出后再补该 endpoint + filter
3. **AC#9 feedback_lifecycle** (S3-TEST-005 xfail strict=True) — `feedback_lifecycle` 模块未实装; 灰度前必须实装
4. **AC#3 share endpoint cache 接入** — `build_share_order_view` 直读 DB 无 cache 层; 等 `S3-ADR-0046-SHARE-CACHE-SPEC-RATIFY` (架构师 魈, P3) 拍 A (不加) / B (拆 S3-DEV-007) 后实施

## 附 B: S3 阶段未做 (灰度 scope 外, 不阻塞)

- AI 自动摘要 reply 反馈 (PRD-004 S3 明确不做, 等 S4)
- 法大大 / e签宝 真 CA 签章 (PRD-003 S3 不做, 等 V1.1)
- BI 报表 / SLA 自动催办 / NPS / 电话客服系统 (ADR-0049 §1 范围限制)
- F2 → F8 之外的家属端新 UI (本 sprint 不动)

---

## 附 C: 复用资源

- S2-TEST-004 模板: `docs/qa/canary-pre-release-checklist.md`
- canary 部署: `docs/ops/canary-deployment.md`
- canary 回滚 runbook: `docs/ops/canary-rollback-runbook.md`
- INCIDENT_PLAYBOOK: `docs/ops/INCIDENT_PLAYBOOK.md`
- ADR-0028 灰度发布与回滚原则
- ADR-0046 合同存储扩展
- ADR-0049 反馈领域模型
- ADR-0054 precheck UI native pivot
- PRD-001 v1.4 §F8 / PRD-003 / PRD-004
