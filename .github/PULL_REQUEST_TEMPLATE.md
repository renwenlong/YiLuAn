<!--
本 PR template 由 S2-OPS-018-DRAFT-PR-READY-PROTOCOL 引入. 见
docs/dev/DRAFT_PR_PROTOCOL.md 了解为什么需要 "Ready Status" section.
-->

## What

<!-- 1-3 句话说明本 PR 做什么. 不要复述 commit message. -->

## Why

<!-- 1-3 句话说明为什么需要做. link 对应的 task / ADR / PRD. -->

## Scope

<!-- 列本 PR 改了哪些 scope. 如果跨 scope, 显式说明每个 scope 的目的 + 单向性证明 (无破坏性). -->

- [ ] 单 scope (推荐)
- [ ] 跨 scope (列出每个 scope 的目的)

## Severity

<!-- 选一个, 不夸大. 见 docs/dev/PR_SEVERITY_LEXICON.md 词汇表 (when exists). -->

- [ ] security fix (真 attack path 且 exploitable, 必须附 attack chain 5 项)
- [ ] defense-in-depth hardening (无真 attack path 但加层防御)
- [ ] feat / refactor / cleanup / docs (无 security 含义)

## Test evidence

<!-- 本地跑过哪些 test? 截图或 paste output. -->

- [ ] `pytest -q <relevant_tests>` 全绿
- [ ] `alembic check` (如果改 model/migration) 全绿
- [ ] `ruff check` / lint 全绿

## Ready Status

<!--
⚠️ 这个 section 是 S2-OPS-018-DRAFT-PR-READY-PROTOCOL 强约束.
未全勾的 PR 必须维持 draft 状态. Maintainer 不替 author 转 ready.
见 docs/dev/DRAFT_PR_PROTOCOL.md.
-->

- [ ] 我 (author) 确认本 PR ready for merge (本地 test/lint/alembic 全过, scope 清晰, 无 hold)
- [ ] 我 (author) 同意 maintainer 在 reviewer ack 后 merge
- [ ] 我 (author) 没有未声明的 hold 意图 (无 "等 X 合 main 后" 或类似 dependency)

## Reviewer checklist

<!-- Reviewer 在 review 前必查. -->

- [ ] PR comments 最近 5 条无 "hold" / "等 X 合 main 后" / "不要 merge" / "WIP" / "draft" 字样
- [ ] 上面 "Ready Status" 3 项全勾
- [ ] PR description "Scope" + "Severity" + "Test evidence" 填完整

