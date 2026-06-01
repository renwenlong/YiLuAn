# Git / PR 流程 SOP（YiLuAn 项目）

> 生效：2026-05-29 起（D4-D10 三端前端阶段）
> 维护：架构师（魈）；流程对齐：协调者（甘雨）
> **本文档是已验证的标准流程**——照此执行不会再撞今天踩过的坑。

---

## 0. TL;DR —— 一个 task 的完整命令（照抄）

```bash
cd /home/wenlongren/repo/YiLuAn

# ① 永远从最新 main 开分支（不在 main 上直接 commit）
git checkout main && git pull origin main
git checkout -b feature/<TASK-ID>-<简述>      # 例 feature/S2-DEV-012-wechat-share

# ② 开发 + 提交（在 feature 分支上）
git add -A && git commit -m "<type>(<scope>): <subject> [TASK-ID]"

# ③ push feature 分支（不受 protection 限制；pre-push hook 会跑全量 gate ~6min）
git push origin feature/<TASK-ID>-<简述>

# ④ 建 PR
gh pr create --base main --head feature/<TASK-ID>-<简述> \
  --title "<type>(<scope>): <subject>" \
  --body "TASK-ID: <id>
自测: pytest 1349 passed + wechat jest 369 passed (pre-push 全绿)
关联: ADR-xxxx / PRD §x.x"

# ⑤ reviewer(魈) 在 PR 上留 review comment（见 §3）
# ⑥ 合并（comment resolve 后）
gh pr merge <PR#> --squash --delete-branch

# ⑦ 回 main 同步 + 删本地分支
git checkout main && git pull origin main
```

**就这 7 步。不要在 main 上 commit，不要手动配 GitHub 凭证，不要 `--no-verify`。**

---

## 1. 机制层硬约束（main branch protection，当前生效配置）

帝君 2026-05-29 拍板 **A 方案**，当前 protection：

| 约束 | 状态 | 说明 |
|---|---|---|
| 禁直接 push main | ✅ 强制 | 必须走 PR |
| 必须经 PR 才能合 | ✅ 强制 | `required_pull_request_reviews` 开 |
| 强制 approval 数 | ❌ **= 0** | **单账号无法 approve 自己 PR，故去掉**（见 §4 坑3）|
| PR comment 必须 resolve | ✅ 强制 | reviewer 意见 resolve 才能合 |
| 禁 force push / 禁删 main | ✅ 强制 | — |
| 全量 pytest + jest + release gate | ✅ **CI required check** | `required_status_checks` strict=true：`Backend Tests` / `Docker Build Verification` / `WeChat Mini Program Tests`，PR 三个全绿 + 基于最新 main 才能合（负向验证已证红 PR 被锁，S2-OPS-003）|
| 本地 pre-push 快速门 | ✅ `.githooks/pre-push` | ruff lint(改动文件) + marker gate(`money_safety/share_security`, ~12s)，秒级；全量交 CI（启用：`bash scripts/setup-hooks.sh`）|

#### CI 路径分流（S2-OPS-004）

`test.yml` 按改动路径分流，纯前端/纯后端 PR 不再跑无关全量 job：

| PR 改动命中 | 跑哪些 required check | 其余 required check |
|---|---|---|
| `backend/**`、`scripts/qa/**` | **Backend Tests** + **Docker Build Verification**(needs:backend) | WeChat → skip(计为 success) |
| `wechat/**` | **WeChat Mini Program Tests** | Backend / Docker Build → skip(计为 success) |
| `.github/workflows/test.yml` | 全部三个（改 CI 本身全跑） | — |
| 纯文档/其余（不碰上述路径） | 无重活 job | 三个均 skip(计为 success)，PR 不被锁死 |

> ⚠️ 实现关键：**不能用 workflow 级 `on.pull_request.paths` 过滤** required check job——path 不匹配时整个 workflow 不触发，required check 变 **missing(永久 pending)** → PR 永久 BLOCKED。正确做法：workflow 永远触发，前置 `changes` job(dorny/paths-filter) 输出各端是否改动，重活 job 用 `if:` 按路径条件跑；被 `if` skip 的 required job **GitHub 计为 success(算过)**，不是 missing。详见 `test.yml` 顶部注释。

**质量门没放水**：approval 仪式去掉，但靠 ① comment resolve ② **CI required check 全量 gate**（机制硬闸，负向验证确认红 PR 真合不了）③ 本地 marker gate 守资金/分享最高危线 ④ 高风险 PR reviewer 显式 LGTM 四道补偿。

> 注：早前「pre-push 本地跑全量 6min」已废弃——会撞 SSH idle-timeout 致 push 失败（见 §4 坑4）。全量已平移到 CI required check。

### 🔴 红线：禁止 `gh pr merge --admin` 绕 required check

`--admin` 是机制内唯一能绕过 required check 的后门（`enforce_admins=false`）。机制挡不住它，**靠纪律 + 留痕守**：

- **绝不**用 `gh pr merge --admin` / 任何 admin 强合绕过红 CI（尤其 `money_safety` / `share_security` 这种最高危 gate）
- **若确有紧急必须 admin 强合**：事后**必须**在项目群 + 该 PR comment 显式报备——**谁、哪个 PR、为什么绕、绕过了哪个红 check**
- **审计**：灰度前测试员（release gate）查 main 的 merge 历史，**有未报备的 admin merge = release gate 直接 fail**
- 理由：admin 无声绕过 = 资金/隐私风险无痕进生产。机制挡不住 admin，那就让 admin **留痕可审计**，这是 gate 的最后一道。

---

## 2. taskboard 状态机 ↔ Git/PR 对齐

| taskboard | Git/PR | 谁操作 |
|---|---|---|
| `in-progress` | feature 分支开发中，未建 PR | 开发者 |
| `in-review` | PR open（必跟 `request_review`）| 开发者建 PR 后置 |
| `done` | **PR merged**（必跟 `handoff`）| **reviewer/架构师** merge 后置 |

- **PR 未 merge 不得置 done**
- review comment 未 resolve → PR 合不了 → task 到不了 done

---

## 3. Review 怎么做（单账号现实）

⚠️ **单账号 `renwenlong` 下，GitHub 的 `approve` / `request-changes` 全部失效**（都被判为"review 自己的 PR"）。所以：

- reviewer（魈）用 **普通 PR comment** 留 verdict，不用 approve 按钮：
  - 通过：`gh pr comment <PR#> --body "✅ 魈 LGTM —— 已核对 acceptance: ..."`
  - 打回：`gh pr comment <PR#> --body "🟡 合并前必修: ..."`（开发者修完 re-push 同分支，PR 自动更新）
- **高风险 PR（资金 / share 安全 / 生产配置 / 部署）merge 前 reviewer 必须显式留 `LGTM + 已核对 acceptance` comment**
- merge 由 reviewer 执行（`gh pr merge --squash --delete-branch`），确保 review 通过才合

---

## 4. 今天踩过的 4 个坑（这就是"绕弯路"的根因，照 SOP 走全部规避）

### 坑 1：在 main 上直接 commit → push 被 protection 挡
- **现象**：commit 成功但 `git push origin main` 被拒，`main ahead N` 推不上去
- **根因**：没开 feature 分支，直接在 main 提交
- **规避**：§0 第①步——永远 `git checkout -b feature/...` 再 commit。**绝不在 main 上 commit。**
- **补救**（已在 main 上 commit 了）：
  ```bash
  git branch feature/xxx          # 把 commit 留到新分支
  git reset --hard origin/main    # main 回退到远端（确认无其他未提交改动！）
  git checkout feature/xxx        # commit 还在，从这里走 PR
  ```

### 坑 2：HTTPS remote 没凭证 → push 卡住等认证
- **现象**：`git push` 长时间 hang，或提示输密码
- **根因**：remote 是 HTTPS URL 但机器没配 credential
- **规避**：remote 已统一改 SSH（`git@github.com:renwenlong/YiLuAn.git`），gh CLI 已 SSH 认证。**不要改回 HTTPS，不要手配 PAT。**

### 坑 3：approve 自己的 PR 被 GitHub 拒 → PR 永远合不了
- **现象**：`gh pr review --approve` 报 `Can not approve your own pull request`
- **根因**：全队共用一个 GitHub 账号 `renwenlong`，作者=审查者
- **规避**：protection 已设 approval=0（A 方案），review 走 comment（§3）。**不要再尝试 approve 按钮。**
- **中期**：若要恢复硬 approval，配 reviewer-bot 独立账号（backlog，非当前必须）

### 坑 4（已修复 S2-OPS-003）：pre-push hook 全量 pytest 跑 6 分钟 → SSH idle-timeout 断连
- **原现象**：push “失败”（`Connection closed by remote host` + exit 141），但 gate 已全绿。
- **真根因**（已诊断）：pre-push 跑 ~6 分钟全量 pytest+jest 期间，到 GitHub 的 SSH 连接空闲被服务端 idle-timeout 断开 → hook 跑完传输发不出。复现铁证：带全量 hook push 连续 2 次失败，`--no-verify` 纯 push 秒成。
- **✅ 修复（S2-OPS-003）**：
  - 本地 pre-push hook 瘦身为 `ruff lint(改动文件) + marker gate(money_safety/share_security, ~12s)`，不再跑全量 → push **秒级完成**（实测 14.8s，含 force update），不再撞 SSH 超时。
  - 全量 pytest+jest 平移到 GitHub Actions CI required check（质量门不丢，负向验证已证红 PR 被锁）。
  - 启用新 hook：`bash scripts/setup-hooks.sh`（设 `core.hooksPath=.githooks`）。
- **负面参考（旧现象，保留备查）**：若未来又出现长耗时 pre-push 导致 push 卡顿，优先查是不是又把重活塞回了本地 hook。
- ✅ 仍然：**绝不 `--no-verify` 绕过**（本地 marker gate 秒级，没理由绕；plus CI required check 是真闸）。

---

## 5. commit message 规范

`<type>(<scope>): <subject> [TASK-ID]`
- type：`feat` / `fix` / `test` / `docs` / `chore` / `refactor`
- 例：`feat(share): WS 家属端实时位置通道 [S2-DEV-003]`

---

## 6. push 前自检清单

- [ ] 在 feature 分支（不是 main）：`git branch --show-current`
- [ ] 工作区该提交的都 commit 了：`git status -s`
- [ ] 缓存目录没混进来（`.hypothesis/` `.taskboard-tmp/` 已 gitignore）
- [ ] 涉及资金/share 安全：PR body 声明已跑 `pytest -m money_safety` / `-m share_security`
- [ ] push 用后台 + 足够 timeout，等 pre-push 全量 gate 全绿

---

## 7. 例外

- 2026-05-29 之前直推 main 的 commit 不回溯（既成事实，双 gate 干净）
- 紧急 hotfix 仍走 PR，但 reviewer 优先响应 fast-track；**不绕过 protection、不 `--no-verify`**
