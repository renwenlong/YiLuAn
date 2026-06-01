# OPS-RETRO-001 — commit 5982627 直推 main 回溯审计 + 直推漏洞堵口留痕

- **审计人**：魈（架构师）
- **日期**：2026-06-01
- **Task**：OPS-RETRO-001（type=bug, P1）
- **被审 commit**：`598262725b701dbad2fdbcb8255ca86faaaed52d`
- **性质**：事后 Code Review（视同正式 PR review 留痕）+ 直推漏洞根因/堵口/防复发记录

---

## 1. 事实陈述

### 1.1 直推事实

| 项 | 值 |
|----|----|
| commit | `5982627` |
| author | `AI智能助手 <ai-assistant@yiluan.local>` |
| date | 2026-05-29 16:47 UTC |
| parent | `013cecff`（PR #104 的后续基线） |
| 关联 PR | **0**（REST `GET /commits/{sha}/pulls` 返回空，未经任何 PR） |
| 落地方式 | **直接 push 到 `origin/main`，绕过 PR 流程** |

commit 内容（refactor，无业务逻辑变更）：
- `deploy/docker-compose.yml` 通用骨架（staging/production 共用，profiles 控制 mock）
- dev 栈独立为 `deploy/dev/`（db+redis，端口 5433/6380，后端 uvicorn 裸跑）—— 即「方案 C」
- `up.sh`/`down.sh` dev 分支修复，`seed.sql` 迁至 `deploy/dev/`
- README / CLAUDE.md / DEV_SETUP.md / backend 文档全量对齐（README +437 行）

### 1.2 根因（已查实）

直推之所以成功，是两个条件叠加：

1. **`enforce_admins = false`**（当时）—— branch protection 对 repo admin **全旁路**，所有规则（required PR / required checks / conversation resolution）对 admin 形同虚设。
2. **操作账号 `admin = true`** —— 触发上述旁路。

"required PR" 在 GitHub 层只是君子协定，未在服务端强制拦截 admin 直推。本地 pre-commit/pre-push hook（#112/#108）只能拦本机操作，挡不住绕过 hook 或换机直推。

---

## 2. 事后 Code Review 结论

对 `5982627` 全量 diff 做事后审查，视同正式 PR review：

| 维度 | 结论 |
|------|------|
| 安全 | 🟢 无敏感信息硬编码；`env.dev.example` 中密码为占位 `***`；端口绑定 `127.0.0.1` 不对外暴露 |
| 数据 | 🟢 `seed.sql` 为纯文件迁移（move，内容未变），无数据破坏 |
| 逻辑 | 🟢 纯部署/文档重构，无业务代码改动；compose 骨架、up/down 分支逻辑自洽 |
| 架构 | 🟡 dev 栈独立为 `deploy/dev/`（方案 C）与团队后续拍板的「方案 B（统一 compose dev profile）」**方向相反**——见第 3 节 |
| 文档 | 🟢 README 审计数据（表 30 / 迁移 44 / 路由 102 等）与代码对齐，质量合格 |

**Review 结论**：代码质量本身**通过**（无 🔴 阻塞项）。唯一架构争议（方案 C vs B）已被后续 #115 处理。

---

## 3. 影响范围 + 现状收敛

`5982627`（方案 C）引入的 `deploy/dev/` 已被 **PR #115（`9769479`，S2-OPS-006）完全回退**到方案 B：

```
deploy/dev/docker-compose.yml   -45   (删)
deploy/dev/env.dev.example      -31   (删)
deploy/dev/seed.sql            -387   (删)
deploy/docker-compose.yml       +62   (统一 dev profile 回归)
deploy/up.sh / down.sh                (dev 分支改回 profile 模式)
```

**现状**：`origin/main` 上 dev 栈已是方案 B（统一 compose dev profile），`deploy/dev/` 目录代码产物已清空（仅本地 gitignore 的 `env.dev` 残留，不入库）。

→ **acceptance #2 结论**：方案 C 已被 #115 回退，**无需另开回退 task**。当前承载方案 = B，与团队拍板一致。无需回退 `5982627` 本身（已在远端且后续基于它，按 git-push-sop §6「已在远端不强退」，#115 是 forward-fix 而非 revert commit）。

### 3.1 遗留缺口（归属 #115，非本 task）

🟡 `origin/main` 上 `backend/README.md` 与 `docs/DEV_SETUP.md` **仍残留方案 C 的旧路径**（`deploy/dev/env.dev`、`-f dev/docker-compose.yml`），#115 回退时漏改文档对齐。

→ 这是 #115 的收尾遗漏，**应由程序员（胡桃）走 PR 补文档对齐**，不在 OPS-RETRO-001 范围内，本审计仅记录、不越界修改。

---

## 4. 已采取措施（堵口）

复核 `origin/main` branch protection 当前实配：

| 规则 | 当前值 | 状态 |
|------|--------|------|
| **`enforce_admins`** | **`true`** | ✅ **admin 旁路已堵**（根因已修复） |
| `allow_force_pushes` | `false` | ✅ 禁 force push |
| `allow_deletions` | `false` | ✅ 禁删分支 |
| `required_pull_request_reviews` | enabled | ✅ 必须走 PR |
| `required_conversation_resolution` | `true` | ✅ comment 必 resolve |
| `required_status_checks.strict` | `true` | ✅ 严格 |
| required checks | Backend Tests / Docker Build Verification / WeChat Mini Program Tests | ✅ 正确 |

**核心**：`enforce_admins=true` 已生效，操作账号虽仍为 admin，但 protection 对其不再旁路 —— **本次直推漏洞的根因已堵死**。A 方案要求项（禁直推 / comment 必 resolve / 禁 force push / required checks 正确）**全部满足，无需补配置**。

---

## 5. 后续防复发

1. **`enforce_admins=true` 不得回退**。副作用已知：单 admin 体系下任何人（含 hotfix）都必须走 PR，无人可 bypass —— 这正是堵口要的效果。如需 hotfix 快速通道，另设方案（如临时降级需 Owner 显式批准并留痕），不得长期关闭 enforce_admins。
2. **本地 hook 是第二道防线不是第一道**：#112 pre-commit 拦受保护分支直接 commit、#108 pre-push 瘦身——只挡本机，服务端 `enforce_admins` 才是硬拦。两者并存，缺一不可。
3. **🟡 建议项（需 Owner 拍板，本 task 不擅自改）**：当前 `required_approving_review_count = 0`，PR 可零审批自合。这是另一维度的口子——单 admin 体系下设为 >0 会卡死自己所有 PR，是否收紧由帝君决定，不在 A 方案明确列项内，故仅标注不动手。

---

## 6. 审计动作清单（可复核）

```
git show 5982627 --stat                          # 全量 diff 审查
gh api repos/renwenlong/YiLuAn/branches/main/protection   # 复核 protection 实配
gh api .../protection/enforce_admins  -q .enabled # → true
git diff 5982627 origin/main --stat -- deploy/    # 核 #115 回退净效果
git api .../commits/5982627/pulls                 # 关联 PR=0，确认直推
```

**结论**：审计完成 → 根因已堵（enforce_admins=true）→ 留痕落盘 → 本文档走 PR 流程提交，不直推 main。
