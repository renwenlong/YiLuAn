# PR Review 规约还原: r1/r2 走 --approve (ADR-0061 S4 / AC#6-7)

任务: S3-OPS-SEPARATE-GH-IDENTITY-PER-AGENT — 根治反案#37 self-approve workaround 留痕断链。

## 背景 (反案#37 root cause)

5 agent 共用 renwenlong 单账号, GitHub 协议禁 self-approve, architect 被迫走 gh pr review --comment (state=COMMENTED) 代替 --approve (state=APPROVED)。后果:
- GitHub UI 显示 0 APPROVED reviews
- branch protection 无法加 required_approving_review_count=1
- audit trail 模糊 (author/reviewer/merger 都是 renwenlong)

独立 identity 到位后 (architect=yiluan-xiao != author=yiluan-hutao), self-approve 物理禁解除。

## 规约 (identity 到位后生效)

### 新 PR (本 task 完成 + 账号到位后)

review 表态必走 APPROVED 真留痕:

    gh pr review <PR> --approve --body "..."

- r1 (architect 首轮) / r2 (复审) 一律 --approve
- GitHub UI 显示 APPROVED, branch protection required=1 可真正生效

### deprecated fallback (仅极端 case)

    gh pr review <PR> --comment --body "APPROVE: ..."

- 仅当 PAT 失效 / identity 未就位等极端情况临时用
- body 首行必显式写 APPROVE/REQUEST_CHANGES 表态
- 标记 deprecated, 账号到位后不再作为常规路径

### 旧 PR (renwenlong era, 2026-06-15 04:23Z 前)

- 历史 COMMENTED review 不回溯改写 (AC#7)
- renwenlong era PR 全留 renwenlong 名, 历史 audit 断裂可接受

## 迁移期兼容

- secret 未就位时 agent 回退共享 renwenlong (反案#37 workaround), 此期间仍只能 --comment
- 账号逐个到位逐个切; architect identity 到位即可对他人 PR 真 --approve
- 硬切换时点: branch protection apply required=1 (卡帝君背书, 见 scripts/qa/enable-required-approvals.sh)

## 关联

- ADR-0061 S4 / 反案#37
- scripts/agent-gh-identity.sh / scripts/qa/enable-required-approvals.sh
