# Docs Cleanup Report — 2026-04-29

> **执行人**：subagent (docs-cleanup-serial)
> **分支**：`chore/docs-cleanup-2026-04-29`（基于 main `6bbe839`）
> **范围**：99 个非代码非功能性文档（`*.md` / `*.json` 在 docs/、reviews/、discussions/、test-cases/、各子目录 README）

## 摘要

| 指标 | 数值 |
|---|---|
| 总文件数 | 99 |
| 删除（Deleted） | 18 |
| 更新（Updated） | 12 |
| 保留无改（Kept-as-is） | 69 |

---

## 处置明细

| Path | Action | Reason | Updates Applied |
|---|---|---|---|
| README.md | Updated | Sprint 标记从 W17 推进到 W18 Day 3；测试数 573/165/57 → 1101/256/57 | 顶部 metadata 行 |
| PROJECT_STATUS.md | Updated | 同上；追加 W18 进展（TD-MONEY-01 M1–M3 / D-049-D-052 / Helm 骨架）；Blocker 等待天数 +6 | 文末新增 2026-04-29 段 |
| TEAM.md | Kept-as-is | 永续治理文档，团队结构稳定 | — |
| TASK_BREAKDOWN.md | Updated | P2 合规文档清单引用了已被合并删除的 lowercase privacy/terms 文件 | 改为 `PRIVACY_POLICY.md` / `TERMS_OF_SERVICE.md` |
| polish-backlog.md | Kept-as-is | 内容已是 W17/W18 进行中状态，多条目带 commit hash | — |
| CLAUDE.md | Kept-as-is | 给 Claude Code 的项目导览，与代码结构一致 | — |
| backend/CLAUDE.md | Kept-as-is | 同上，backend 范围 | — |
| backend/README.md | Kept-as-is | 简短启动说明，与代码一致 | — |
| backend/tests/e2e/README.md | Kept-as-is | E2E 测试说明，准确 | — |
| admin-h5/README.md | Kept-as-is | admin-h5 现存且文档对齐 | — |
| design/README.md | Kept-as-is | 设计资源说明，稳定 | — |
| ios/README.md | Kept-as-is | iOS 项目结构 + ios-tests workflow 引用，准确 | — |
| ios/scripts/README_screenshots.md | Kept-as-is | 截图脚本说明 | — |
| ops/grafana/README.md | Kept-as-is | grafana 看板说明 | — |
| ops/scripts/README.md | Kept-as-is | 含 2026-04-24 sample 时间戳，仍对应 A-2604-06 落地 | — |
| wechat/components/README.md | Kept-as-is | 组件说明，准确 | — |
| wechat/scripts/README.md | Kept-as-is | 极简脚本说明 | — |
| wechat/submission/screenshots/README.md | Kept-as-is | 截图清单，对齐提审材料 | — |
| infra/helm/yiluan/README.md | Kept-as-is | 与 Action #10 Helm 骨架对齐 | — |
| docs/admin-mvp-scope.md | Kept-as-is | ADR 状态 Accepted，与 admin-h5 实现一致 | — |
| docs/COVERAGE_TODO.md | Updated | 测试基线 80% → 92%，未达 98%，仍是 W19 推进项 | 文末新增 2026-04-29 段 |
| docs/CRON_TASKS.md | Updated | 缺少 W18 新增 3 个 reconciliation jobs | 追加补充表 |
| docs/DECISION_LOG.md | Updated | D-004 引用了已删除的 discussions/2026-04-10-parallel-dependency.md | 标注归档 |
| docs/deployment.md | Kept-as-is | 部署清单，与 ACR / Container Apps 对齐 | — |
| docs/DEV_SETUP.md | Kept-as-is | 本地开发规范，准确 | — |
| docs/empty-state-design.md | Kept-as-is | 空状态设计稿，稳定 | — |
| docs/ios-ci.md | Kept-as-is | W18 / D-039 状态行已写明 gate | — |
| docs/ios-smoke-test.md | Kept-as-is | 烟测脚本说明 | — |
| docs/MESSAGE_LINK_AUDIT_2026-04-17.md | Kept-as-is | 被 ADR-0030 / 其他 ADR 引用，作为追溯材料 | — |
| docs/MIGRATION_AUDIT_2026-04-17.md | Kept-as-is | 被 ADR-0028 / RUNBOOK_ROLLBACK 引用 | — |
| docs/MIGRATION_REVERSIBILITY_REPORT.md | Kept-as-is | 被 RUNBOOK_ROLLBACK / runbook-go-live 引用 | — |
| docs/observability.md | Kept-as-is | v1.0 spec，对齐 D-037 / Prometheus 落地 | — |
| docs/PRIVACY_POLICY.md | Kept-as-is | iOS App Store 提交版，含完整章节；lowercase 副本已删除 | — |
| docs/privacy-policy.md | **Deleted** | UPPERCASE 版本是正式 v1.0 / iOS 提交版（13KB），lowercase 版是早期 4/10 简版（3.6KB），两者内容不一致；保留 UPPERCASE，删除 lowercase | git rm |
| docs/PRODUCT_BACKLOG.md | Updated | 引用了已归档的 reviews/2026-04-20-pm.md 与 SPRINT_PLAN_2026-04-21 | 改为指向 REVIEW_2026-04-20.md 总报告 |
| docs/PROVIDER_FREEZE.md | Kept-as-is | D-052 freeze 当日（2026-04-29）发布，最新 | — |
| docs/REVIEW_2026-04-20.md | Updated | 7 角色单 review 已归档，本汇总作为唯一存档 | 文末加 2026-04-29 归档说明 |
| docs/RUNBOOK_ROLLBACK.md | Kept-as-is | rollback runbook，引用 ADR-0028 仍有效 | — |
| docs/runbook-go-live.md | Kept-as-is | 30 分钟上线 runbook，与 W18 计划对齐 | — |
| docs/scheduler.md | Kept-as-is | APScheduler 部署指南，结构未变 | — |
| docs/SPRINT_PLAN_2026-04-21.md | **Deleted** | W17 sprint 已结束（W18 Day 3 进行中）；无外部引用 | git rm |
| docs/STAGING_REHEARSAL_RUNBOOK.md | Kept-as-is | D-044 staging rehearsal runbook，保留有效 | — |
| docs/TECH_DEBT.md | Updated | 多项 W18 期间技术债已落地 | 文末追加 2026-04-29 snapshot |
| docs/TERMS_OF_SERVICE.md | Kept-as-is | iOS 提交版，正式 v1.0；lowercase 副本已删除 | — |
| docs/terms-of-service.md | **Deleted** | 同 privacy 重复策略：保留 UPPERCASE 正式版，删除 lowercase 早期版 | git rm |
| docs/test_coverage.md | Updated | 测试数 539 已严重过期（实际 1101） | 文末追加 2026-04-29 update 段 |
| docs/TODO_CREDENTIALS.md | Updated | 仍是活跃 Blocker tracker（非僵尸 TODO），W18 仍有意义 | 文末追加状态快照 |
| docs/wechat_review_qa.md | Kept-as-is | 2026-04-29 当日发布版，最新 | — |
| docs/wechat-submission-checklist.md | Updated | 2026-04-18 状态需要刷到 W18 Day 3 | 文末追加 2026-04-29 注解 |
| docs/wechat-submission-dryrun-2026-04-22.md | **Deleted** | 一次性 dry-run 报告，问题清单已全部归零，已被 wechat-submission-checklist 与 wechat_review_qa 覆盖 | git rm |
| docs/WORKFLOW.md | Kept-as-is | 开发流程文档，永续 | — |
| docs/adr/README.md | Kept-as-is | ADR 索引 | — |
| docs/adr/ADR-0001-wechat-payment.md | Kept-as-is | 历史 ADR | — |
| docs/adr/ADR-0026-outbound-reliability.md | Kept-as-is | Accepted / 已落地 | — |
| docs/adr/ADR-0029-emergency-pii-retention.md | Kept-as-is | Accepted / 已落地 D-043 | — |
| docs/adr/ADR-0030-staging-mock-environment.md | Kept-as-is | Accepted / staging mock | — |
| docs/adr/ADR-0031-websocket-chatservice-unification.md | Kept-as-is | Accepted | — |
| docs/adr/ADR-0032-money-reconciliation.md | Kept-as-is | Accepted / TD-MONEY-01 实施依据 | — |
| docs/adr/ADR-0033-money-reconciliation-scaling.md | Kept-as-is | Accepted / 2026-04-29 发布 | — |
| docs/decisions/ADR-0028-canary-release-and-rollback.md | Kept-as-is | 与 docs/adr/ 不冲突（adr/ 没有 0028）；保留 | — |
| docs/decisions/ADR-0029-expired-order-payment-handling.md | Kept-as-is | 内容是订单过期支付收尾 (TD-PAY-01)，与 adr/ADR-0029 (emergency-pii-retention) **是不同的主题**——号码冲突但内容独立，保守保留 | — |
| docs/decisions/ADR-0030-money-decimal-migration.md | Updated | 与 adr/ADR-0030 (staging-mock-environment) 号码冲突但主题不同（金额 Decimal 迁移）；引用了已删除的 SPRINT_PLAN | 改为标注归档 |
| docs/decisions/D-029_sprint_scope_2026-W17.md | **Deleted** | W17 sprint 范围决议，sprint 已结束；无外部代码引用 | git rm |
| docs/decisions/D-030_feature_backlog_decisions.md | Updated | 引用了已归档的 reviews/2026-04-20-pm.md | 改为指向 REVIEW_2026-04-20.md 总报告 |
| docs/discussions/2026-04-10-parallel-dependency.md | **Deleted** | 19 天前讨论，已落地为 D-004；无外部引用（DECISION_LOG 引用已更新为归档说明） | git rm |
| docs/discussions/2026-04-10-payment-phase2.md | **Deleted** | 19 天前讨论，已落地为 D-003 + 后续 D-023 D-007 等 | git rm |
| docs/discussions/2026-04-21-payment-backup.md | **Deleted** | A21-13 备份 PSP memo，决议截止 4/25，已落地（ADR-0033 等） | git rm |
| docs/discussions/2026-04-21-tab-naming.md | **Deleted** | A21-14 tab 命名讨论，决议 4/24，已落地 | git rm |
| docs/api/README.md | Kept-as-is | API 索引，对齐 v1 路由 | — |
| docs/api/admin-companions.md | Kept-as-is | 与 api/v1/admin/ 对齐 | — |
| docs/api/admin.md | Kept-as-is | 同上 | — |
| docs/api/auth.md | Kept-as-is | OTP / 微信 / Apple 登录端点齐 | — |
| docs/api/AUTHENTICATION.md | Kept-as-is | 鉴权概念说明 | — |
| docs/api/chats.md | Kept-as-is | 与 chats.py 对齐 | — |
| docs/api/companions.md | Kept-as-is | 与 companions.py 对齐 | — |
| docs/api/emergency.md | Kept-as-is | 与 emergency.py 对齐 | — |
| docs/api/ERROR_HANDLING.md | Kept-as-is | 错误码规范 | — |
| docs/api/health.md | Kept-as-is | 与 health.py 对齐 | — |
| docs/api/hospitals.md | Kept-as-is | 与 hospitals.py 对齐 | — |
| docs/api/notifications.md | Kept-as-is | 与 notifications.py 对齐 | — |
| docs/api/openapi.json | Kept-as-is | 由 backend 自动生成；最近一次更新 commit `3b2a2a6` (admin orders/users 详情) | — |
| docs/api/orders.md | Kept-as-is | 与 orders.py 对齐 | — |
| docs/api/patients.md | Kept-as-is | 与 patients.py 对齐 | — |
| docs/api/payment-callbacks.md | Kept-as-is | 与 payment_callback.py 对齐 | — |
| docs/api/reviews.md | Kept-as-is | 与 reviews.py 对齐 | — |
| docs/api/users.md | Kept-as-is | 与 users.py 对齐 | — |
| docs/api/wallet.md | Kept-as-is | 与 wallet.py 对齐 | — |
| docs/design/recon_copywriting.md | Kept-as-is | Action #7 (commit `35a69fc`) 当周文案 | — |
| docs/ios/APP_PRIVACY_MANIFEST.md | Kept-as-is | iOS 提审材料 | — |
| docs/ios/APP_STORE_METADATA.md | Kept-as-is | iOS 提审材料 | — |
| docs/ios/SUBMISSION_CHECKLIST.md | Kept-as-is | iOS 提审 checklist | — |
| docs/ops/GOLIVE_DRYRUN_REPORT_2026-04-25.md | Kept-as-is | 被 runbook-go-live 引用，dry-run 追溯材料 | — |
| docs/ops/INCIDENT_PLAYBOOK.md | Kept-as-is | 永续 SOP | — |
| docs/ops/recon_sop_v0.1.md | Kept-as-is | Action #7 当周发布的 SOP v0.1 | — |
| docs/quality/recon_coverage.md | Kept-as-is | recon 测试覆盖快照 | — |
| docs/reviews/2026-04-20-arch.md | **Deleted** | 一次性 review 快照，已被 docs/REVIEW_2026-04-20.md 总报告汇总 | git rm |
| docs/reviews/2026-04-20-backend.md | **Deleted** | 同上 | git rm |
| docs/reviews/2026-04-20-design.md | **Deleted** | 同上 | git rm |
| docs/reviews/2026-04-20-frontend.md | **Deleted** | 同上 | git rm |
| docs/reviews/2026-04-20-pm.md | **Deleted** | 同上（PRODUCT_BACKLOG / D-030 引用已更新指向 REVIEW_2026-04-20.md） | git rm |
| docs/reviews/2026-04-20-qa.md | **Deleted** | 同上 | git rm |
| docs/reviews/2026-04-20-ops.md | **Deleted** | 同上 | git rm |
| docs/test-cases/reject-expiry.md | Kept-as-is | 测试用例文档，与 D-016 状态机对齐 | — |
| docs/test-cases/release-uat-checklist.md | Kept-as-is | UAT checklist，与 W18 release 对齐 | — |
| deploy/staging/reports/rehearsal-2026-04-27.md | Kept-as-is | 被 STAGING_REHEARSAL_RUNBOOK 引用 | — |

---

## 删除合计（18）

1. docs/privacy-policy.md（小写重复）
2. docs/terms-of-service.md（小写重复）
3. docs/SPRINT_PLAN_2026-04-21.md（W17 已结束）
4. docs/decisions/D-029_sprint_scope_2026-W17.md（W17 已结束）
5. docs/wechat-submission-dryrun-2026-04-22.md（dry-run 已落地）
6. docs/discussions/2026-04-10-parallel-dependency.md（已落地）
7. docs/discussions/2026-04-10-payment-phase2.md（已落地）
8. docs/discussions/2026-04-21-payment-backup.md（已落地）
9. docs/discussions/2026-04-21-tab-naming.md（已落地）
10–16. docs/reviews/2026-04-20-{arch,backend,design,frontend,pm,qa,ops}.md（已被 REVIEW_2026-04-20.md 汇总覆盖）

> 注：docs/decisions/ 下三个 ADR (0028/0029/0030) 与 docs/adr/ 下相同编号的 ADR 主题**完全不同**——号码冲突源于历史并行开题（commit `2ffecd7` 已记载"原拟 ADR-0030 因撞号改记 0032"）。保守保留全部内容，仅修正其内部对已删文件的引用。

## 更新合计（12）

README.md / PROJECT_STATUS.md / TASK_BREAKDOWN.md / docs/COVERAGE_TODO.md / docs/CRON_TASKS.md / docs/DECISION_LOG.md / docs/PRODUCT_BACKLOG.md / docs/REVIEW_2026-04-20.md / docs/TECH_DEBT.md / docs/test_coverage.md / docs/TODO_CREDENTIALS.md / docs/wechat-submission-checklist.md / docs/decisions/ADR-0030-money-decimal-migration.md / docs/decisions/D-030_feature_backlog_decisions.md
