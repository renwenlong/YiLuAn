# Git Push 标准执行流程(SOP / 已验证逐步清单)

> 配套文档:`git-push-policy.md`(讲"规矩/不准做什么")。
> 本文讲"怎么一步步照着做不出错"--已在 PR #102 / #103 完整跑通验证。
> ⚠️ **已同步到 #108 hook 瘦身后模型(S2-OPS-003)**:本地只跑 marker 快速门(~12s),全量测试平移到 CI required check。旧的「本地 push 前跑全量 ~6min」已废弃(撞 SSH 超时)。
> 适用:每个 develop / bug / docs task 从写完代码到 merge main 的全过程。
> 触发背景:胡桃在 5/28-5/29 反复踩同样的坑(游离 commit 被挡、add . 一把梭、删文件没改 README、PR 缺自测证据),固化成动作清单消除弯路。

---

## 0. 开工前(每次都做,30 秒)

```bash
git status                      # 确认当前在哪个分支、有没有遗留改动
git checkout main && git pull   # main 同步到最新,避免基于旧 main 开分支
```

⚠️ **坑1**:不要在 main 上直接改。改之前一定先开分支(下一步)。直推 main 会被 branch protection 挡住--**被挡 ≠ commit 丢了**,commit 还在本地,摘到分支即可(见 §6 救援)。
> 🛡️ **机制兜底(S2-OPS-005)**:`.githooks/pre-commit` 现在会在 main/master/develop 上**直接拒绝 commit**(防手滑)。被拒就按提示先开 feature 分支。逃生口 `git commit --no-verify`。

---

## 1. 开分支(命名硬规则)

```bash
git checkout -b feature/<TASK-ID>-<简述>
# 例:git checkout -b feature/S2-DEV-012-wechat-share-page
```

- 分支名前缀只用 `feature/` `fix/` `docs/`,后接 task-id,必须能对回 taskboard。
- **同步 taskboard**:`set_status(in-progress)`(开始写代码就置,不要等)。

---

## 2. 暂存改动(禁止 `git add .`)

```bash
git status                       # 先看清楚动了哪些文件
git add <明确路径> ...           # 逐个/逐目录加,只加本 task 相关的
git status                       # 再确认一遍暂存区,杜绝误加
```

⚠️ **坑②**：`git add .` 会把 `.taskboard-tmp/`、`backend/.hypothesis/` 等缓存/临时目录一把梭进去。这些已在 `.gitignore`，但仍要养成“看清楚再加”的习惯，新出现的临时目录第一时间补进 `.gitignore`。

⚠️ **坑②.5（并行编辑冲突，胡桃实际踩过）**：多个 agent 同时在同一 feature 分支改同一文件会撞车（AC#2 那次 `deploy/docker-compose.yml` 就撞了）。**动手前先 `git status` 看工作区有没有别人未提交的改动，撞了先在群里对齐再动，别硬叠。**

---

## 3. 删/改文件的连带检查(最容易坐坏的一步)

⚠️ **坑3(胡桃 #103 实际踩过)**:删了 `backend/docker-compose.yaml`,但 README §本地开发还在引用它 → 自测全绿,review 时被打回(AC 回归)。

**删或重命名任何文件前,先全仓搜引用:**

```bash
# 1) 搜文件名(basename + 不带扩展名都搜,覆盖 compose/脚本简写)
grep -rn "docker-compose" . --exclude-dir=.git --exclude-dir=node_modules
# 2) 搜被删文件"提供的能力关键字",不能只搜文件名(容易漏间接引用)
#    例:删 dev compose 还要搜服务名、端口、make target、相对路径
grep -rni -e "compose up" -e "<服务名>" -e "<端口号>" -e "<make target>" . \
     --exclude-dir=.git --exclude-dir=node_modules
```

- 搜到的引用(README、脚本、CI、文档)必须同步改掉或提供替代路径。
- ⚠️ **只搜 basename 会漏**:文件常被以相对路径、服务名、命令简写、Makefile target 间接引用。删"提供能力的文件"必须按上面第 2 条搜能力关键字。
- 删"提供能力的文件"(如 dev 栈、入口脚本)必须在 PR body 写明**替代方案**,否则 reviewer 必打回。

### §3.1 删"提供能力的文件"后必须跑一遍替代路径(可测性硬动作)

> grep 只是静态检查,挡不住"替代方案写了但跑不起来"。删 dev 栈/入口脚本这类**提供能力的文件**,必须按文档从零实际跑一遍替代路径,验证可用。

```bash
# 例:删了 dev compose,按改后的 README 从零起本地后端 + 冒烟
<README 里新写的本地启动命令>          # 必须真能起来
curl -fsS localhost:<端口>/health     # 或等价冒烟,确认服务可用
```

- **验收点(写进对应 task acceptance,可被 reviewer/测试实际复跑)**:删除 `<能力文件>` 后,按 README 替代路径能成功起本地环境并通过冒烟,无悬空引用。
- 这条是 AC 级别的回归点(#103 AC#2 即此),不是声明--reviewer 复跑不过即打回。

---

## 4. 提交(commit message 规范)

```bash
git commit -m "<type>(<scope>): <简述> [TASK-ID]"
# 例:git commit -m "feat(share): 微信分享页落地 [S2-DEV-012]"
```

- type:`feat` / `fix` / `docs` / `chore` / `test` / `refactor`
- 一个逻辑改动一个 commit,message 带 task-id,便于回溯。

---

## 5. push 前自检 gate(绿了才推)

> ⚠️ **已更新到 #108 瘦身后模型（S2-OPS-003）**：本地 pre-push = `ruff lint(改动文件) + marker gate`（秒级）。
> **全量 pytest/jest 不再在本地 push 前跑**——已平移到 GitHub Actions CI 的 required check（`Backend Tests`/`Docker Build Verification`/`WeChat Mini Program Tests`，strict）。
> 旧的「本地 push 前跑全量 ~6min」会撞 SSH idle-timeout 致 push 失败，已废弃，别走回头路。

```bash
# ⚠️ 必须在 backend venv 里跑（裸 python 报 No module named pytest）：
# 本地快速门只跑 marker（pre-push hook 自动跑这个，~12s）：
cd backend && python -m pytest -m "money_safety or share_security"
# 全量测试交 CI，本地不用手动跑（push 后 GitHub Actions 自动全量 + required check 挡红 PR）
```

- ⚠️ **跑在 backend venv，不是裸 python**：pre-push hook 跑的就是项目 venv 的 pytest，直接 `pytest`/`python3 -m pytest` 可能报 No module。
- **本地只需 marker gate**：pre-push hook 自动跑 `money_safety or share_security`（~12s），守资金/分享最高危线。**不再要求本地跑全量**。
- **全量在 CI 兜底**：push 后 GitHub Actions 跑全量 pytest+e2e+jest+release gate，且是 required check——红了 PR 合不进 main（负向验证 #107 证实）。所以本地不跑全量不等于放水，是平移到 CI。
- pre-push 被 SSH 超时/网络异常打断时才用 `git push --no-verify`（极少；marker gate 失败别绕，先修）。

```bash
git push origin feature/<TASK-ID>-<简述>   # 推分支,不受 protection 限制
```

---

## 6. 救援:commit 已经误落到本地 main(被 protection 挡住推不动)

⚠️ **坑4(游离 commit `4985832` 实际场景)**:在 main 上 commit 了,push 被挡。**别慌,commit 没丢。**

**第一步先判别这个 commit 是不是已经在某个 feature 分支上了**(#103 当时就是分支已建+已 push、只剩本地 main 残留 ahead 1):

```bash
git log --oneline -n 3                          # 记下要摘走的 commit hash
git branch -r --contains <hash>                 # 先查这个 commit 是否已在某远端分支
```

**情形 A:commit 已在某 feature 分支(如 #103)** —— 不用再建分支,本地 main 只需退回:

```bash
git checkout main
git reset --hard origin/main                    # 本地 main 退回与远端一致,清掉残留 commit
```

**情形 B:commit 还没被摘到任何分支(全新场景)** —— 先建分支接住再退 main:

```bash
git checkout main
git branch feature/<TASK-ID>-<简述>             # 用当前 main 建分支(带上误落的 commit)
git log feature/<TASK-ID>-<简述> --oneline -1  # 💭 reset 前先确认分支确实带上了那个 commit
git reset --hard origin/main                    # 确认无误后,本地 main 退回与远端一致
git checkout feature/<TASK-ID>-<简述>        # 切到分支继续走正常 PR 流程
```

⚠️ **别跳过前置判别直接建分支**:情形 A 下再 `git branch` 会重复建分支。

然后回到 §7 开 PR。**误落 main 的 commit 一定要补一个 taskboard task 承载**(#103 当时补了 S2-OPS-002),不留游离。

---

## 7. 建 PR(body 模板,缺一项 reviewer 必打回)

```bash
gh pr create --title "[TASK-ID] <简述>" --body "$(cat <<'EOF'
## Task
- taskboard: <TASK-ID>
- 关联 ADR / PRD: <编号或 N/A>

## 改动摘要
- <一句话说清这个 PR 干了什么>

## 自测结果(必填)
- [ ] pytest -m "money_safety or share_security" ✅ 全绿(本地 marker gate，贴尾部统计如 `32 passed`)
- [ ] 全量测试：交 CI（push 后 GitHub Actions 自动跑 + required check），本地不用贴全量证据
- [ ] 删/改文件已做连带引用检查(§3,grep 含能力关键字):<结论>
- [ ] 删能力文件已按 README 替代路径复跑冒烟(§3.1):<起本地+健康检查结果 / N/A>

## 风险 / 替代方案
- <删能力文件时必填替代路径;无则写 N/A>
EOF
)"
```

- 建完 PR:`set_status(in-review)` → 本 turn 跟 `get_reviewers` 通知魈。
  - ⚠️ **agentsquad 后端命令名就是 `get_reviewers`**;SKILL 文档里的 `request_review` 已过时,照拄会报 Unknown command。
- PR open 才置 in-review,**别提前**。

---

## 8. Review → Merge

1. 魈在 GitHub PR 上 review,给 comment / approve / request changes。
2. **resolve 对象 = PR 上的 review thread / 行内 comment**(不是 issue comment)。`required_conversation_resolution:true` 只对 review thread / 行内 comment 计数;`gh pr comment` 发的 issue comment 不进计数、不挡 merge,但 `gh pr review --request-changes` 或行内 review comment **必须 resolve** 才能合。
3. 被 request changes:`set_status(in-progress)`,按 comment 改,改完重新 push(同分支)+ 重新 cue review。
4. merge 前先校验状态,再合:

```bash
# 🔴 确认非 CHANGES_REQUESTED 且无 unresolved review thread,否则 GitHub 会挡且不直观提示卡在哪条
gh pr view <PR号> --json reviewDecision        # 必须 ≠ CHANGES_REQUESTED
gh pr merge <PR号> --squash --delete-branch    # squash 合并 + 删分支
```

5. merge 后:`set_status(done)` → 本 turn 跟 `get_handoff_targets` 通知下游。
6. **PR 没 merge 不准置 done。**

---

## 9. 状态机对齐速查

| taskboard 状态 | Git/PR 对应动作 |
|---|---|
| `in-progress` | feature 分支开发中 / 被打回后修改中 |
| `in-review` | PR open + 等魈 review(必跟 `get_reviewers`)|
| `done` | PR merged(必跟 `get_handoff_targets`)|

---

## 一页纸速记(贴墙版)

1. `git checkout main && git pull`
2. `git checkout -b feature/<TASK-ID>-xxx` + set_status(in-progress)
3. `git status` 看有无别人未提交改动(撞车先群里对齐) → `git add <明确路径>`(**禁 add .**)
4. 删/改文件 → `grep -rn` 查引用(能力关键字也搜);删能力文件再按§3.1 复跑替代路径
5. `git commit -m "feat(x): ... [TASK-ID]"`
6. `cd backend && python -m pytest -m "money_safety or share_security"`（本地 marker 快速门；全量交 CI 不用本地跑）
7. `git push origin feature/...`（pre-push 自动跑 marker gate ~12s，秒级完成）
8. `gh pr create`(body 带 marker 证据；全量由 CI required check 兜底)+ set_status(in-review) + cue 魈
9. resolve 所有 review thread → `gh pr view --json reviewDecision` 确认非 CHANGES_REQUESTED → `gh pr merge --squash` → set_status(done) + handoff

> 误落 main 被挡?→ §6 救援(先 `git branch -r --contains` 判别是否已在分支),commit 没丢。
</content>
</invoke>
