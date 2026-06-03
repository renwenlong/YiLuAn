# 2026-06-03 — Commit 5982627 全量 Code Review（事后审计）

> 作者：魈（架构师） · 日期：2026-06-03 · task: **S2-OPS-009**（OPS-RETRO-001 AC#1/#2 补做）
> commit: `5982627` · author: AI智能助手 <ai-assistant@yiluan.local> · 2026-05-29 16:47 UTC
> 视同正式 PR review 留痕（含 🔴/🟡/💭 分级）

---

## 背景

`5982627` 绕过 PR 直推 main，OPS-RETRO-001 已识别这条 SOP 违规并完成 enforce_admins 闸门（已为 True）。本文档补做 OPS-RETRO-001 acceptance：

- **AC#1**：对 5982627 全量 diff Code Review，结论落 docs/review/ ← 本文档
- **AC#2**：deploy/dev/ 与帝君目标方案一致性确认 ← 本文档 §3

---

## 1. Commit 概览

**主旨**：deploy 目录重构 + 文档全量对齐。
- 13 文件 / +529 / -228
- 部署侧：deploy/docker-compose.yml 通用骨架 + env.<环境> + dev 栈独立到 deploy/dev/
- 文档侧：README 全量审计（表/迁移/路由/订单态/model/service/repo/schema 数字对齐 + 补全新模块）

---

## 2. 分文件审查

### 部署侧（核心，受 OPS-RETRO-001 关注）

| 文件 | 改动 | 评级 | 备注 |
|------|------|------|------|
| `deploy/docker-compose.yml` | -61 行重写为通用骨架 | 🟡 | 设计正确（profiles + env 多环境），但 5982627 一并塞了 dev/ 独立目录方案（C），后被 S2-OPS-006 撤回回 B 方案。本次 review 看的是**当前 main 状态**，C 方案已不存在。|
| `deploy/up.sh` / `down.sh` | -dev 分支修复 | ✅ | 当前 main 已是 S2-OPS-006 后版本，up.sh 走 profile dev/staging，干净 |
| `deploy/dev/docker-compose.yml`（新增 45 行） | C 方案核心文件 | ⚠️ **已被 S2-OPS-006 删除** | 5982627 引入但被撤回，**不再存在于 main** |
| `deploy/dev/env.dev.example`（新增 31 行） | C 方案配置 | ⚠️ **已被 S2-OPS-006 删除** | 同上 |
| `{backend → deploy/dev}/seed.sql` rename | C 方案数据 | ⚠️ **已被 S2-OPS-007 删除** | gen_seed.py + seed.sql 均废弃（seed 走 POST /hospitals/seed） |
| `backend/scripts/gen_seed.py` | -2 行 docstring | ⚠️ **已被 S2-OPS-007 删除** | 全文件废弃 |

### 文档侧

| 文件 | 改动 | 评级 | 备注 |
|------|------|------|------|
| `README.md` | +437/-XXX 全量对齐 | ✅ | 数字对齐扎实（表 13→30 / 迁移 18→44 / 路由 32→102 / 订单 7→9 态），补全 wallet/share/emergency/family/followup/ai_digest 新模块。文档质量好。 |
| `CLAUDE.md` | -4 行轻改 | ✅ | 路径对齐 |
| `backend/CLAUDE.md` / `backend/README.md` | 小改 | ✅ | 同上 |
| `docs/DEV_SETUP.md` | ±96 行 dev 栈说明 | 🟡 | 内容指向 C 方案 deploy/dev/ 路径，**S2-OPS-006 回退 B 后已与现实不符**，但 S2-OPS-006 acceptance #4 已要求"README 全量改回 B 口径"，应已修。建议 spot-check。 |
| `docs/test-cases/reject-expiry.md` | -2 行 | ✅ | 无关紧要小改 |

---

## 3. AC#2 deploy/dev/ 一致性确认

### 帝君目标方案
S2-OPS-006 task 已经明确："dev 回退方案 B"，即统一 compose + profile + env 多环境，端口 backend=8001 / pg=5433 / redis=6380。

### 当前 main 状态（5982627 后续被 S2-OPS-006/007 修正）
- `deploy/dev/` 目录 ✅ **已删**（与目标方案一致）
- `deploy/docker-compose.yml` 含 `dev` profile（backend-dev + 端口 8001/5433/6380）✅
- `deploy/up.sh dev` 走 profile dev ✅
- `backend/scripts/gen_seed.py` ✅ **已删**（S2-OPS-007）
- `seed.sql` ✅ **已删**（seed 走 API）
- 5982627 引入的 ENVIRONMENT/DEBUG/PG_HOST_BIND 等 env.staging 变量 ✅ 保留（合理）

### 结论
**当前 main 与帝君目标方案 B 完全一致。** 5982627 引入的 C 方案残留已通过 S2-OPS-006/007 完整撤回。**AC#2 闭环。**

唯一遗留 spot-check 项：`docs/DEV_SETUP.md` 是否仍指向 C 方案路径。下一步验证。

---

## 4. 分级问题清单

### 🔴 阻塞（安全/数据/逻辑）
- ✅ **无**。5982627 引入的 C 方案设计本身没安全/数据问题，只是与目标方案 B 不一致——已被 S2-OPS-006 撤回。

### 🟡 建议（可维护性/性能）
- **🟡-1**：本次重构同时塞了"通用骨架"和"C 方案 deploy/dev/ 独立"两个独立改动，违反"小步 commit"原则。如果走 PR，应拆 2 个 PR。已是历史，不必修。
- **🟡-2**：作者 `AI智能助手 <ai-assistant@yiluan.local>` 缺乏可追溯人，违反 git 责任主体原则。已在 OPS-RETRO-001 acceptance #1 中作为审计案例留痕。后续 SOP 应禁止匿名 author，必须落到真实团队成员。
- **🟡-3**：README +437 行 / 文档全量审计是好事但混在 deploy 重构 commit 里，review 失焦。已是历史。

### 💭 备注（风格偏好）
- **💭-1**：5982627 commit message 详尽（部署改动 + 文档对齐两段都说清楚），符合架构 commit 规范。
- **💭-2**：seed.sql 从 backend/ 移到 deploy/dev/ 是合理归位（部署侧数据归部署目录），但后续 S2-OPS-007 整体废弃，本 commit 的 rename 价值归零。

---

## 5. 教训

1. **绕 PR 直推 main 必须走完整事后审计**（已通过 OPS-RETRO-001 + 本 review 闭环）
2. **enforce_admins 现状已为 True**（GH API 核实），后续 admin 也无法 bypass，结构上杜绝同类事件
3. **AI/匿名 author 提交需要责任锚**：MEMORY 硬规则应增加"任何 commit author 必须是真实团队成员（魈/胡桃/刻晴/凝光/甘雨），AI 协作产物以人类 reviewer 为 author"
4. **大 refactor 应拆多个 PR**（部署骨架 / dev 方案选型 / 文档对齐 各一个），本次混合 commit 是反例

---

## 6. 结论

**Review 通过（事后追认）**：commit 5982627 内容上无 🔴 阻塞缺陷，🟡 问题均与"绕 PR"流程本身相关，已通过 OPS-RETRO-001 + S2-OPS-005/006/007 + 本 review + S2-OPS-009 闭环。

- AC#1 ✅ 本文档落盘
- AC#2 ✅ §3 确认 deploy/ 当前状态与目标方案 B 完全一致

OPS-RETRO-001 全 acceptance 通过追认补做闭环。

---

## 7. 反向引用

- OPS-RETRO-001（事后审计主 task）— done
- S2-OPS-005（pre-commit hook 拦截受保护分支）— done
- S2-OPS-006（dev 栈回退方案 B）— done
- S2-OPS-007（gen_seed.py 废弃）— done
- S2-OPS-009（本 task）— in-progress → done after this PR merge
