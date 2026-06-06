# DRAFT_PR_PROTOCOL.md

Draft PR 转 Ready 协议 + Reviewer 显式 ack 自律规则.

> **背景**: 2026-06-06 07:30 UTC 我 merge PR #195 时, PR 状态 ready-for-review,
> 但 author (胡桃) 实际意图是 "draft + 等 SUBDIR 合 main 后 rebase" (07:18 转 draft
> 留 comment). 问题: draft 被转 ready 后, maintainer 视为可 merge, 实际 author
> 还在 hold. 损失: author review opportunity 被绕过.
>
> **根因**: GitHub draft 状态非强制 hold, 任何 maintainer 可以 ready-then-merge,
> 不需 author 同意. 本仓库 branch protection 不区分 draft transition.
>
> **目标**: 文档约束 + reviewer 自律(不上 CI check, 避免过度流程化).

---

## 1. 谁可以把 draft PR 转 ready (AC#1 强约束)

**只允许 author 本人**把自己的 draft PR 转 ready-for-review.

- ✅ Author: 在自己代码完成 + 本地通过 lint/test/alembic check 后, 自己点
  GitHub UI "Ready for review" 按钮.
- ❌ Maintainer: **禁止替 author 转 ready**, 即使 CI 全绿, 即使你认为 author
  忘了, 即使 PR 看起来已经完成.
- ❌ Reviewer: 同上, 禁止替 author 转 ready.

**例外**: 如果 author 已离线 > 24h 且 PR 阻塞 critical path, maintainer
可以转 ready, 但必须:

1. PR 评论 ping author 说明转 ready 原因.
2. 等 author 在 GitHub 上明确 reply "OK ready" 或类似字样后才 merge.
3. 不等 reply 直接 merge = 流程违规.

---

## 2. Maintainer 看到 ready PR 时 merge 前必查 (AC#2 强约束)

任何 maintainer (含 architect / reviewer / Owner) **merge 一个 PR 前必须**:

1. 看 PR comments **最近 5 条**是否有以下字样:
   - "hold"
   - "等 X 合 main 后"
   - "不要 merge"
   - "WIP"
   - "draft" / "草稿"
   - "等 review"
   - "等 author 确认"
   - 任何看起来是 author 主动 hold 的字样

2. 如果命中任意一个上述字样, **必须先 ping author 确认**:
   - GitHub PR 上 `@author 这条 hold 是否还有效?`
   - 等 author 明确 reply "可以 merge" / "OK" 才能 merge.
   - author 无 reply 而你 merge = 流程违规.

3. 如果 PR comments 没命中, 但 PR 标题或 description 有 "WIP" / "DRAFT" /
   "草稿" 字样, 也按上面规则 ping author 确认.

---

## 3. Author 转 ready 时的自检 checklist (AC#3 引用)

Author 在点 GitHub "Ready for review" 前, 必须确认:

- [ ] 本地跑过 `pytest -q` (相关测试) + 全绿
- [ ] 本地跑过 `alembic check` (如果改 model/migration) + 全绿
- [ ] 本地跑过 `ruff check` / lint + 全绿
- [ ] PR description 写清 scope, 不夸大严重度 (见
      `docs/dev/PR_SEVERITY_LEXICON.md` if exists)
- [ ] 如果跨 scope, description 显式列每个 scope 的目的 + 单向性证明
- [ ] PR template 的 "Ready Status" section 已勾选 (见 §4)

未达成上述任一项, 必须保持 draft 状态.

---

## 4. PR template 的 "Ready Status" section (AC#3 强约束)

`.github/PULL_REQUEST_TEMPLATE.md` 含 "Ready Status" 必填 section:

```markdown
## Ready Status

- [ ] 我 (author) 确认本 PR ready for merge (本地 test/lint/alembic 全过, scope
      清晰, 无 hold)
- [ ] 我 (author) 同意 maintainer 在 reviewer ack 后 merge
- [ ] 我 (author) 没有未声明的 hold 意图 (无 "等 X 合 main 后" 或类似 dependency)

> ⚠️ 上述任一项未勾选, 维持 draft 状态. Maintainer 不替 author 转 ready.
```

**Reviewer 在 review 时必须看这 3 项是否全勾**. 没全勾 = author 没真正 ready =
不应 merge.

---

## 5. Reviewer 看到 PR comments 含 hold 字样但 PR 已 ready 时 (AC#4 强约束)

如果 reviewer 在 review 过程中发现:

- PR 状态 ready-for-review
- 但 PR comments 含 "hold" / "等 X 合 main 后" / "不要 merge" / "WIP" /
  "draft" / 任何 hold 类字样

reviewer **必须**:

1. **不要直接 merge / approve**, 即使 review 内容已通过.
2. 在 PR 上 ping author: `@author 这条 hold 是否还有效? 如不需要 hold, 请明
   确 reply "OK 可以 merge".`
3. 等 author 明确 reply 后, reviewer 才决定是否 approve + merge.
4. author 不 reply 而 reviewer merge = 流程违规.

---

## 6. 为什么不上 CI check (AC#5)

候选方案: 在 CI 加 check, 检测 PR 状态是 ready 但 author 未在 "Ready Status"
section 全勾时 fail check, 阻止 merge.

**拒绝原因**:

1. CI check 过度流程化, GitHub draft → ready 转换是 frontend 行为, CI 验证
   GitHub UI 状态成本高.
2. PR template "Ready Status" section 已经在 reviewer 视野内, 不必加 CI 复读.
3. 5 AC 的目标是"文档约束 + reviewer 自律", 加 CI 与目标冲突.
4. 如果 reviewer 不看 PR template, 加 CI 也没用 (reviewer 会 force-bypass).

**正解**: 文档 + reviewer 教育 + PR template, 三层非强制约束足够.

---

## 7. 违规的处理 (本节非 AC, 仅参考)

如果发现某次 merge 违反本协议 (如 maintainer 替 author 转 ready 后直接 merge):

1. **不追责**: 不在群里点名批评, 不在 PR 上指责.
2. **复盘**: 在事件后 24h 内, 当事 maintainer + author 私聊复盘, 写一句
   "下次怎么改".
3. **记录**: 复盘结论落到 `memory/` 或对应 OPS task notes, 不另起 task.
4. **再犯**: 同一 maintainer 同一类型违规 ≥ 2 次, OPS 流程负责人 (架构师)
   群里点出, 督促复盘.

---

## 8. 修订历史

- 2026-06-06 16:18 UTC, 魈 (架构师): v1 初版, S2-OPS-018-DRAFT-PR-READY-PROTOCOL.
