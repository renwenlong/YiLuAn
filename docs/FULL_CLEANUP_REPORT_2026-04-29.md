# Full Repo Cleanup Report - 2026-04-29

> **Branch:** `chore/full-repo-cleanup-2026-04-29` (based on main `1e0238a`)
> **Scope:** 全仓深度扫描，所有目录。是 PR #70 (docs cleanup) 之后的代码/资源/配置层清理。
> **结论：** 仓库整体非常干净（PR #70 已扫过 docs，整个 backend/wechat/ios/infra 主线代码无废弃）。仅发现 **9 个真实垃圾文件**：1 个 `.tmp` + 8 个 0 引用的占位 PNG。

## 概要

| 指标 | 数量 |
|---|---|
| 候选文件总数 | 9 |
| 删除 (Deleted) | 9 |
| 保留 (Kept) | 0 |
| 净变化 | -9 文件 |

## CI 验证

| 检查项 | 基线 | 删除后 | 结果 |
|---|---|---|---|
| `pytest -q` | 1108 passed / 16 skipped / 5 deselected | 1108 passed / 16 skipped / 5 deselected | ✅ |
| `npx jest` | 256 passed / 42 suites / 1 snapshot | 256 passed / 42 suites / 1 snapshot | ✅ |
| `ruff check .` | 446 errors (pre-existing, main 也是) | 不变 | ➖ baseline持平 |
| `alembic check` | DB 未启动（local 无 PG 服务） | DB 未启动 | ➖ 环境受限，CI on push 会跑 |

> 备注：本地 PG 未运行，alembic check 无法真正执行（需要 `docker compose up db`）。`ruff` 有 446 个 pre-existing errors，本次未触碰任何 .py，与本 PR 无关。CI workflow `.github/workflows/test.yml` + `alembic-smoke.yml` 会在 push 后跑全套。

## 删除清单

| Path | Category | Action | Why | Refs Found |
|---|---|---|---|---|
| `.git-commit-msg.tmp` | 1. 临时/废弃 | Deleted | 上一次 D-051 的 commit-msg 草稿（2.5KB），文件名以 `.tmp` 结尾，红线第一档"必删" | 0 |
| `wechat/images/tabbar/chat.png` | 5. 配置/资源僵尸 | Deleted | 占位 tabBar 图标 (298 字节)。`wechat/app.json` 已无 `tabBar` 字段（自定义 `patient-tab-bar`/`companion-tab-bar` 组件接管），且 grep `images/tabbar` 在所有 `.json/.wxml/.wxss/.js` 中 0 命中 | 0 |
| `wechat/images/tabbar/chat_active.png` | 5. | Deleted | 同上 (299 字节) | 0 |
| `wechat/images/tabbar/home.png` | 5. | Deleted | 同上 (298 字节) | 0 |
| `wechat/images/tabbar/home_active.png` | 5. | Deleted | 同上 (299 字节) | 0 |
| `wechat/images/tabbar/order.png` | 5. | Deleted | 同上 (298 字节) | 0 |
| `wechat/images/tabbar/order_active.png` | 5. | Deleted | 同上 (299 字节) | 0 |
| `wechat/images/tabbar/profile.png` | 5. | Deleted | 同上 (298 字节) | 0 |
| `wechat/images/tabbar/profile_active.png` | 5. | Deleted | 同上 (299 字节) | 0 |

## 已扫描但保留（重点反例，避免下次重判）

| Path / Pattern | 误判风险 | 实际结论 |
|---|---|---|
| `backend/app/services/upload.py` | "似乎只在一处用" | 被 `backend/app/api/v1/users.py` 用于头像上传，**保留** |
| `backend/app/services/wechat.py` `sms.py` `metrics.py` `outbound.py` `rate_limit.py` `distributed_lock.py` `log_retention.py` `wallet_ledger_writer.py` `reconciliation_metrics.py` `admin_audit.py` | 模块名通用，怀疑是否冗余 | grep 全仓引用 6-28 处不等，全部活跃使用 |
| `wechat/utils/tokens.js` `wechat/styles/tokens.wxss` | 仅被 `design/generate.py` 生成、grep 查不到 require | 是 design system 单一真源的 generated 产物，`design/README.md` 显式说明保留状态；删除会破坏跨端 token 同步合约 |
| `wechat/styles/variables.wxss` | 旧版 token | `wechat/app.wxss` 用 `@import './styles/variables.wxss'`，**保留** |
| `wechat/styles/order-action.wxss` | 单点引用 | `wechat/pages/patient/order-detail/index.wxss` `@import "/styles/order-action.wxss"`，**保留** |
| `wechat/utils/haptic.js` | grep 仅 1 命中（test） | 配套 polish-backlog P-03，被 `__tests__/utils/haptic.test.js` 锁定 contract，**保留** |
| `wechat/utils/badge.js` | grep 1 命中 | 被 `wechat/app.js` 引入做 tabBar badge 同步，**保留** |
| `wechat/components/{patient,companion}-tab-bar/` | tabBar 是否还在用 | `app.json.usingComponents` 显式注册并被多个 page 用，**保留** |
| `prometheus/`、`deploy/prometheus/`、`ops/alertmanager/`、`ops/grafana/`、`ops/canary/`、`ops/scripts/` | 看似过期 ops 资产 | 全部被 `docker-compose.alertmanager.yml`、`docs/runbook-go-live.md`、`docs/RUNBOOK_ROLLBACK.md`、ADR-0028、`infra/helm/yiluan/templates/alertmanager-deployment.yaml` 引用，**保留** |
| `deploy/staging/**` | 早期 staging 演练 | 仍是当前 staging SOP（`docs/STAGING_REHEARSAL_RUNBOOK.md` + `.github/workflows/staging-rehearsal.yml`）的实际入口，**保留** |
| `infra/helm/yiluan/templates/*.yaml` | 数量多 | 全是有效 Helm chart，**保留** |
| 12 个 0 字节 `__init__.py`（backend/app/* 与 backend/tests/*） | 0 字节文件 | 红线"绝对不能删"——Python 包标识，**保留** |
| `backend/alembic/versions/*.py` (33 个) | 是否有重复迁移 | 红线"绝对不能删"——alembic 历史不可破，且本次未发现真正重复，**全部保留** |
| `docs/COVERAGE_TODO.md` `docs/TODO_CREDENTIALS.md` | 文件名含 TODO | 是活跃 backlog 文档，PR #70 已处理过，**保留** |
| `polish-backlog.md` | 看似 backlog 草稿 | DECISION_LOG 引用、活跃跟踪 P-01~P-12，**保留** |
| `.claude/settings.local.json` | 个人 IDE 配置 | 已在 git 历史，且仅是本地 allowlist，无敏感数据；不属于本次清理范围（应由 .gitignore 处理） |

## 扫描方法（6 步串行）

每个候选都走完了：
1. `read` 内容前 50 行 + 文件大小
2. `git grep -F <stem>` 全仓（覆盖 `.py .js .ts .swift .json .yaml .yml .wxml .wxss .html`）
3. 引用 == 0 → 删除
4. 引用 > 0 → 保留并记录引用方
5. README 提及但代码无 import → 保守保留
6. `git rm` 单文件

无批量 `rm`，无 `--admin`。

## 反思：为什么本次清理这么少

- PR #70（2 天前）刚扫过 docs，删了 18 个 + 更新 12 个；
- 仓库代码层在 W17/W18 sprint 中持续重构（order/ 拆分、provider 分层、reconciliation 子包、ws 统一），重构 PR 都自带"删旧文件"步骤；
- 没有保留 legacy 实现的习惯——新旧切换都直接 `git mv` / 直接覆盖；
- 资源文件（图片）只引入了一次（占位 tabBar 那次），引入后 app.json 走了自定义组件方案，PNG 立刻成了僵尸，但因为命名"看起来正常"长期没被发现。这次找到了。

## 后续建议（不在本 PR 处理）

1. `wechat/images/tabbar/` 目录将变空——保持空目录无意义，建议加 `.gitkeep` 或后续创建真实 tabbar 资产时再用；本 PR 让 git 自动忽略空目录（git 不跟踪空目录）；
2. 长期看，若 P-03 触感反馈、tokens.wxss 迁移完成，可下一轮删除 `variables.wxss`（README 已注明计划）；
3. `.claude/settings.local.json` 后续应迁到 `.gitignore`（这是工具配置，不应在版本控制）。

—— 全文完
